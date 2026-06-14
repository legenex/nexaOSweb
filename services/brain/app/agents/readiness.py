"""Readiness evaluation over the knowledge sources.

Given a project plan, this service decides whether the plan is ready to build: for every item
the plan declares it needs, it tries to answer the item from what the system already knows before
ever asking a human. The five knowledge sources, consulted in this order for a non credential
item, are:

    1. project              answers already carried on the plan itself
    2. knowledge_base       active KnowledgeEntry rows (facts, preferences, rules)
    3. operating_instructions  the general instructions AppSetting
    4. prior_runs           answers resolved on earlier readiness runs (known or approved)
    5. integrations         connected Integration rows (the only source for a credential item)

The assessment is persisted as an AgentRun of kind readiness, and each item as an AgentStep:

    known            a resolved step (completed) carrying its source as knowledge sourced
                     evidence. Never verified: knowledge is not tool sourced proof.
    needs_user       a blocking item no source could answer, proposed at waiting_approval so it
                     lands in the existing approval queue.
    needs_credential a blocking credential item with no connected integration, also proposed at
                     waiting_approval. Only the provider and the credentials reference are ever
                     recorded; a secret value is never written to a step.
    unknown          a non blocking item no source could answer, left planned and flagged, so it
                     is surfaced without stopping the build.

A run is readiness satisfied only when no blocking item is still open. Resolved readiness answers
flow back into the agent context (see app/agents/context.py) so the agent does not re ask what was
already answered here.
"""

import logging

from sqlalchemy.orm import Session

from app.gates import SAFE_TAGS
from app.models.knowledge import KnowledgeEntry
from app.models.project import Integration, Project
from app.models.runtime import AgentRun, AgentStep
from app.models.workspace import AppSetting
from app.runtime import (
    COMPLETED_UNVERIFIED,
    COMPLETED_VERIFIED,
    create_run,
    propose_step,
    record_execution,
)

logger = logging.getLogger(__name__)

READINESS_KIND = "readiness"
READINESS_AUTONOMY = 1

# Resolutions an item can land on. known is resolved from a source; the rest are open or flagged.
KNOWN = "known"
NEEDS_USER = "needs_user"
NEEDS_CREDENTIAL = "needs_credential"
UNKNOWN = "unknown"

# The five named sources, in the order a non credential item is tried. A credential item is only
# ever answered by the integrations source.
SOURCE_PROJECT = "project"
SOURCE_KNOWLEDGE = "knowledge_base"
SOURCE_INSTRUCTIONS = "operating_instructions"
SOURCE_PRIOR_RUNS = "prior_runs"
SOURCE_INTEGRATIONS = "integrations"

# A credential or connector item is satisfied by a connected provider, never by a stored value.
_CREDENTIAL_KINDS = ("credential", "connector")
# An integration that counts as connected. available means offered but not yet wired.
_CONNECTED_STATUSES = ("connected", "active", "linked")

# A resolved or non blocking item is classified safe so it auto resolves past the entry gate at a
# non zero autonomy. A blocking gap is classified by what it needs, so the gate holds it.
_SAFE_RISK = {tag: True for tag in SAFE_TAGS}
_NEEDS_USER_RISK = {"user_facing": True}
_NEEDS_CREDENTIAL_RISK = {"credential": True}

_DETAIL_CHARS = 280


# --- requirement normalisation ------------------------------------------------------------


def _keywords(raw: dict) -> list[str]:
    explicit = raw.get("keywords")
    if isinstance(explicit, list) and explicit:
        return [str(k).lower() for k in explicit if str(k).strip()]
    # Derive from the key and question so a bare requirement is still matchable.
    text = f"{raw.get('key', '')} {raw.get('question', '')}"
    words = [w.strip(".,:;()").lower() for w in text.split()]
    return [w for w in words if len(w) > 3]


def _normalize_requirement(raw: dict) -> dict | None:
    if not isinstance(raw, dict):
        return None
    key = str(raw.get("key") or raw.get("question") or "").strip()
    if not key:
        return None
    kind = str(raw.get("kind") or "decision").strip().lower()
    return {
        "key": key,
        "question": str(raw.get("question") or key).strip(),
        "kind": kind,
        # Deny by default: an item blocks unless the plan explicitly says it does not.
        "blocking": raw.get("blocking") is not False,
        "provider": (str(raw.get("provider")).strip() if raw.get("provider") else None),
        "keywords": _keywords(raw),
    }


def requirements_from_plan(plan: dict) -> list[dict]:
    """Extract the readiness items from a plan, explicit first then derived from integrations.

    A plan declares its needs under requirements. Any provider listed under integrations or
    selected_integrations becomes a blocking credential item, so a plan that only names the
    integrations it wants still produces a readiness check. Items are deduped by key.
    """
    plan = plan if isinstance(plan, dict) else {}
    items: list[dict] = []
    seen: set[str] = set()

    for raw in plan.get("requirements") or []:
        item = _normalize_requirement(raw)
        if item and item["key"] not in seen:
            seen.add(item["key"])
            items.append(item)

    providers = plan.get("integrations") or plan.get("selected_integrations") or []
    for provider in providers:
        name = str(provider).strip()
        if not name:
            continue
        key = f"credential:{name}"
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "key": key,
                "question": f"Connect the {name} integration.",
                "kind": "credential",
                "blocking": True,
                "provider": name,
                "keywords": [name.lower()],
            }
        )
    return items


# --- the five sources ---------------------------------------------------------------------


def _matches(text: str, keywords: list[str]) -> bool:
    low = (text or "").lower()
    return any(kw in low for kw in keywords)


def _resolve_from_project(item: dict, plan: dict, project: Project | None) -> dict | None:
    """Source 1: an answer the plan or project already carries, keyed by the item key."""
    for store in (plan.get("answers"), plan.get("context"), plan.get("facts")):
        if isinstance(store, dict) and item["key"] in store:
            value = store[item["key"]]
            return {"origin": SOURCE_PROJECT, "detail": str(value)[:_DETAIL_CHARS]}
    if project is not None and isinstance(project.workspace, dict):
        if item["key"] in project.workspace:
            value = project.workspace[item["key"]]
            return {"origin": SOURCE_PROJECT, "detail": str(value)[:_DETAIL_CHARS]}
    return None


def _resolve_from_knowledge(db: Session, item: dict) -> dict | None:
    """Source 2: an active knowledge entry whose content matches the item keywords."""
    if not item["keywords"]:
        return None
    entries = (
        db.query(KnowledgeEntry)
        .filter(KnowledgeEntry.status == "active")
        .order_by(KnowledgeEntry.confidence.desc(), KnowledgeEntry.updated_at.desc())
        .limit(200)
        .all()
    )
    for entry in entries:
        if _matches(entry.content, item["keywords"]):
            return {
                "origin": SOURCE_KNOWLEDGE,
                "detail": " ".join(entry.content.split())[:_DETAIL_CHARS],
                "knowledge_id": entry.id,
                "scope": entry.scope,
            }
    return None


def _resolve_from_instructions(db: Session, item: dict) -> dict | None:
    """Source 3: the general operating instructions mention the item."""
    if not item["keywords"]:
        return None
    row = (
        db.query(AppSetting)
        .filter(AppSetting.key == "general")
        .order_by(AppSetting.id.asc())
        .first()
    )
    instructions = ""
    if row and isinstance(row.value, dict):
        instructions = str(row.value.get("general_instructions") or "")
    if instructions and _matches(instructions, item["keywords"]):
        detail = " ".join(instructions.split())[:_DETAIL_CHARS]
        return {"origin": SOURCE_INSTRUCTIONS, "detail": detail}
    return None


def _resolve_from_prior_runs(db: Session, item: dict) -> dict | None:
    """Source 4: the same item answered on an earlier readiness run, known or approved."""
    steps = (
        db.query(AgentStep)
        .filter(AgentStep.kind == READINESS_KIND)
        .order_by(AgentStep.updated_at.desc())
        .limit(200)
        .all()
    )
    for step in steps:
        rd = step.payload.get("readiness") if isinstance(step.payload, dict) else None
        if not isinstance(rd, dict) or rd.get("key") != item["key"]:
            continue
        if rd.get("resolution") == KNOWN and step.status in (
            COMPLETED_VERIFIED,
            COMPLETED_UNVERIFIED,
        ):
            detail = f"resolved earlier from {rd.get('source')}"
            return {"origin": SOURCE_PRIOR_RUNS, "detail": detail}
        approval = step.approval if isinstance(step.approval, dict) else None
        if approval and approval.get("resolution") == "approved":
            note = str(approval.get("note") or "").strip()
            detail = (note or "approved earlier")[:_DETAIL_CHARS]
            return {"origin": SOURCE_PRIOR_RUNS, "detail": detail}
    return None


def _resolve_credential(db: Session, item: dict) -> dict | None:
    """Source 5: a connected integration for the item provider.

    Only the provider, the integration status, and the credentials reference are read. The raw
    secret never exists on the row and is never copied onto a step.
    """
    provider = item.get("provider") or item["key"].split(":", 1)[-1]
    integration = (
        db.query(Integration)
        .filter(Integration.provider == provider)
        .order_by(Integration.id.desc())
        .first()
    )
    if integration is not None and integration.status in _CONNECTED_STATUSES:
        return {
            "origin": SOURCE_INTEGRATIONS,
            "detail": f"{provider} connected",
            "provider": provider,
            "integration_status": integration.status,
            # A reference only, never the secret. The row holds no secret value to leak.
            "credentials_ref": integration.credentials_ref,
        }
    return None


def _resolve_item(
    db: Session, item: dict, plan: dict, project: Project | None
) -> tuple[str, str | None, dict | None]:
    """Try the sources for one item. Returns (resolution, source, evidence_detail)."""
    if item["kind"] in _CREDENTIAL_KINDS:
        hit = _resolve_credential(db, item)
        if hit:
            return KNOWN, SOURCE_INTEGRATIONS, hit
        return NEEDS_CREDENTIAL, None, None

    for resolver in (
        lambda: _resolve_from_project(item, plan, project),
        lambda: _resolve_from_knowledge(db, item),
        lambda: _resolve_from_instructions(db, item),
        lambda: _resolve_from_prior_runs(db, item),
    ):
        hit = resolver()
        if hit:
            return KNOWN, hit["origin"], hit

    if item["blocking"]:
        return NEEDS_USER, None, None
    return UNKNOWN, None, None


# --- persistence: the run and its steps ---------------------------------------------------


def _readiness_payload(item: dict, resolution: str, source: str | None) -> dict:
    base = {
        "key": item["key"],
        "question": item["question"],
        "item_kind": item["kind"],
        "blocking": item["blocking"],
        "resolution": resolution,
        "source": source,
    }
    if item.get("provider"):
        base["provider"] = item["provider"]
    return base


def evaluate_readiness(
    db: Session,
    *,
    plan: dict,
    project_id: int | None = None,
) -> AgentRun:
    """Assess a plan and persist the result as a readiness AgentRun with one step per item.

    The run is opened at a non zero autonomy so a resolved or non blocking item passes the entry
    gate on its safe classification, while a blocking gap is classified by what it needs and is
    held at waiting_approval for the existing approval queue.
    """
    plan = plan if isinstance(plan, dict) else {}
    project = db.get(Project, project_id) if project_id is not None else None
    items = requirements_from_plan(plan)

    run = create_run(
        db,
        project_id=project_id,
        autonomy_level=READINESS_AUTONOMY,
        plan=plan,
        kind=READINESS_KIND,
        goal_summary="Readiness assessment over the knowledge sources",
        proposed_by="system",
    )

    for item in items:
        resolution, source, detail = _resolve_item(db, item, plan, project)
        payload = {"readiness": _readiness_payload(item, resolution, source)}

        if resolution == KNOWN:
            payload["risk"] = dict(_SAFE_RISK)
            step = propose_step(
                db,
                run,
                kind=READINESS_KIND,
                title=item["question"],
                intent=f"Resolve readiness item {item['key']} from {source}.",
                payload=payload,
                proposed_by="system",
            )
            # The evidence is knowledge sourced, never tool sourced, so the step lands
            # completed_unverified: an answer the system already holds, not proven work.
            evidence = [{"source": "knowledge", **(detail or {"origin": source})}]
            record_execution(db, step, outcome="completed", evidence=evidence)
            continue

        if resolution == NEEDS_CREDENTIAL:
            payload["risk"] = dict(_NEEDS_CREDENTIAL_RISK)
        elif resolution == NEEDS_USER:
            payload["risk"] = dict(_NEEDS_USER_RISK)
        else:  # UNKNOWN, non blocking: safe so it stays planned and is surfaced as a flag.
            payload["risk"] = dict(_SAFE_RISK)

        propose_step(
            db,
            run,
            kind=READINESS_KIND,
            title=item["question"],
            intent=f"Readiness item {item['key']} ({resolution}).",
            payload=payload,
            proposed_by="system",
        )

    return run


# --- reads: the structured assessment and the satisfied check ------------------------------


def readiness_steps(db: Session, run: AgentRun) -> list[AgentStep]:
    return (
        db.query(AgentStep)
        .filter(AgentStep.run_id == run.id, AgentStep.kind == READINESS_KIND)
        .order_by(AgentStep.seq.asc(), AgentStep.id.asc())
        .all()
    )


def _blocking_step_satisfied(step: AgentStep) -> bool:
    """A blocking item is satisfied when it is known, or a human approved its gate.

    It is not satisfied while it waits at the gate or is blocked, nor when it was rejected.
    """
    rd = step.payload.get("readiness") if isinstance(step.payload, dict) else None
    if isinstance(rd, dict) and rd.get("resolution") == KNOWN:
        return True
    approval = step.approval if isinstance(step.approval, dict) else None
    return bool(approval and approval.get("resolution") == "approved")


def readiness_satisfied(db: Session, run: AgentRun) -> bool:
    """True only when no blocking readiness item remains open."""
    for step in readiness_steps(db, run):
        rd = step.payload.get("readiness") if isinstance(step.payload, dict) else None
        if not (isinstance(rd, dict) and rd.get("blocking")):
            continue
        if not _blocking_step_satisfied(step):
            return False
    return True


def readiness_assessment(db: Session, run: AgentRun) -> dict:
    """The structured assessment: the run, its items, and whether it is satisfied."""
    items = []
    for step in readiness_steps(db, run):
        rd = step.payload.get("readiness") if isinstance(step.payload, dict) else {}
        rd = rd if isinstance(rd, dict) else {}
        items.append(
            {
                "step_id": step.id,
                "key": rd.get("key"),
                "question": rd.get("question"),
                "item_kind": rd.get("item_kind"),
                "blocking": bool(rd.get("blocking")),
                "resolution": rd.get("resolution"),
                "source": rd.get("source"),
                "status": step.status,
            }
        )
    blocking_open = [
        item
        for item, step in zip(items, readiness_steps(db, run), strict=False)
        if item["blocking"] and not _blocking_step_satisfied(step)
    ]
    return {
        "run_id": run.id,
        "kind": run.kind,
        "satisfied": readiness_satisfied(db, run),
        "items": items,
        "blocking_open": [item["key"] for item in blocking_open],
    }
