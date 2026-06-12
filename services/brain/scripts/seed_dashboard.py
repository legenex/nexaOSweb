"""Seed demo data so the Dashboard returns real local state.

Idempotent enough for dev: it skips seeding when the earliest user already has projects.
Run with: python -m scripts.seed_dashboard
"""

from app.db import SessionLocal
from app.models.dreaming import DreamRun, MemoryCandidate
from app.models.inbox import ClassificationRecord, InboxItem
from app.models.knowledge import KnowledgeEntry
from app.models.project import Integration, Project
from app.models.user import User
from app.models.workspace import Task


def seed() -> None:
    db = SessionLocal()
    try:
        user = db.query(User).order_by(User.id.asc()).first()
        if user is None:
            print("no user provisioned; run scripts.create_user first")
            return
        if db.query(Project).first() is not None:
            print("projects already present; skipping seed")
            return

        # Captured items, one promoted to a project, one left as a research finding.
        promoted = InboxItem(
            user_id=user.id, name="Launch tracker", body="A small US market launch tracker.",
            source="note", status="processed",
        )
        finding = InboxItem(
            user_id=user.id, name="Competitor pricing scan", body="Notes on three competitors.",
            source="url", status="classified",
        )
        upload = InboxItem(
            user_id=user.id, name="Brand deck.pdf", body="", source="pdf", status="captured",
        )
        db.add_all([promoted, finding, upload])
        db.flush()

        db.add_all(
            [
                ClassificationRecord(
                    item_id=promoted.id, shape="project", confidence=0.88,
                    recommended_route="project_build", recommended_model_key="agentic_code",
                    resolved_model_id="anthropic/claude-opus-4-8",
                ),
                ClassificationRecord(
                    item_id=finding.id, shape="content", confidence=0.74,
                    recommended_route="research", recommended_model_key="research_synthesis",
                    resolved_model_id="anthropic/claude-sonnet-4-6",
                ),
            ]
        )

        active = Project(
            item_id=promoted.id, name="Launch tracker", slug="launch-tracker", stage="build",
            build_destination="local directory",
        )
        gate = Project(
            item_id=None, name="Pricing one pager", slug="pricing-one-pager", stage="clarify",
            build_destination="google drive",
        )
        db.add_all([active, gate])
        db.flush()

        db.add_all(
            [
                Task(user_id=user.id, project_id=active.id, title="Wire the tracker UI", status="open"),
                Task(user_id=user.id, title="Reply to the pricing thread", status="open"),
                Task(user_id=user.id, title="Archive last quarter", status="done"),
            ]
        )

        db.add_all(
            [
                Integration(user_id=user.id, provider="github", status="connected"),
                Integration(user_id=user.id, provider="google_drive", status="connected"),
                Integration(user_id=user.id, provider="slack", status="available"),
            ]
        )

        db.add(
            KnowledgeEntry(
                kind="preference", scope="general", source="dreaming",
                content="Prefers terse morning briefs that lead with one focus.",
                confidence=0.8, status="active",
                provenance={"from": "memory_candidate", "facet": "about_user"},
            )
        )

        run = DreamRun(
            status="completed", trigger="scheduled", model_key="bulk",
            items_considered=4, candidates_created=2,
        )
        db.add(run)
        db.flush()
        db.add(
            MemoryCandidate(
                facet="about_user", kind="pattern", scope="general",
                content="Works in focused evening blocks.", confidence=0.7,
                source_refs=[{"type": "journal", "id": 1, "title": "evening notes"}],
                status="pending",
            )
        )

        db.commit()
        print("seeded dashboard demo data")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
