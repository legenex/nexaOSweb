"""The plan to tasks slicer: ordered tasks, preserved dependencies, idempotent re-slice, risk floor.

These tests drive the slicer at the service layer against a Project carrying a plan_json. They prove
the acceptance directly: a plan slices into ordered tasks with dependencies preserved, a re-slice
reconciles rather than duplicates, a higher risk unit starts more conservative than the project
default, a dropped unit is soft deleted (never hard), and a bad or empty plan is rejected cleanly.
"""

import pytest

from app.agents.slicer import PLAN_SOURCE, SlicerError, slice_plan, task_graph
from app.models.project import Project
from app.models.workspace import Task


def _project(db, *, plan, default="yellow", slug="plan-app"):
    project = Project(
        name="Plan App",
        slug=slug,
        stage="approved",
        mode="app",
        plan_json=plan,
        agent_autonomy_default=default,
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def _by_key(db, project):
    rows = (
        db.query(Task)
        .filter(Task.project_id == project.id, Task.plan_unit_key.isnot(None))
        .all()
    )
    return {t.plan_unit_key: t for t in rows}


_STRUCTURED_PLAN = {
    "summary": "Build a small app",
    "subtasks": [
        {"id": "scaffold", "title": "Scaffold the project"},
        {"id": "login", "title": "Add login and sessions", "depends_on": ["scaffold"]},
        {"id": "pay", "title": "Wire the billing flow", "depends_on": ["login"], "risk": "high"},
        {"id": "polish", "title": "Polish the layout", "depends_on": ["scaffold", "login"]},
    ],
}


# --- a plan slices into ordered tasks with dependencies preserved -------------------------


def test_plan_slices_into_ordered_tasks_with_dependencies_preserved(db_session):
    project = _project(db_session, plan=_STRUCTURED_PLAN, default="green")
    graph = slice_plan(db_session, project)

    assert graph["project_id"] == project.id
    assert graph["plan_present"] is True
    assert graph["count"] == 4

    # Ordered by sequence: scaffold, login, pay, polish.
    titles = [n["title"] for n in graph["tasks"]]
    assert titles == [
        "Scaffold the project",
        "Add login and sessions",
        "Wire the billing flow",
        "Polish the layout",
    ]
    sequences = [n["sequence"] for n in graph["tasks"]]
    assert sequences == [1, 2, 3, 4]

    # Every generated task is marked as sliced from the plan.
    assert all(n["plan_unit_key"] for n in graph["tasks"])
    tasks = _by_key(db_session, project)
    assert all(t.source == PLAN_SOURCE for t in tasks.values())

    # Dependencies are preserved, resolved to prerequisite task ids.
    ids = {key: t.id for key, t in tasks.items()}
    assert tasks["id-scaffold"].depends_on == []
    assert tasks["id-login"].depends_on == [ids["id-scaffold"]]
    assert tasks["id-pay"].depends_on == [ids["id-login"]]
    assert sorted(tasks["id-polish"].depends_on) == sorted([ids["id-scaffold"], ids["id-login"]])


def test_string_subtasks_slice_in_order_without_dependencies(db_session):
    plan = {"subtasks": ["First step", "Second step", "Third step"]}
    project = _project(db_session, plan=plan, slug="string-app")
    graph = slice_plan(db_session, project)

    assert [n["title"] for n in graph["tasks"]] == ["First step", "Second step", "Third step"]
    assert [n["sequence"] for n in graph["tasks"]] == [1, 2, 3]
    assert all(n["depends_on"] == [] for n in graph["tasks"])


def test_dependency_by_order_index_resolves(db_session):
    # A unit can name a prerequisite by its 1 based order, not only its id.
    plan = {"subtasks": [{"title": "A"}, {"title": "B", "depends_on": ["1"]}]}
    project = _project(db_session, plan=plan, slug="order-app")
    slice_plan(db_session, project)
    tasks = _by_key(db_session, project)
    a = next(t for t in tasks.values() if t.title == "A")
    b = next(t for t in tasks.values() if t.title == "B")
    assert b.depends_on == [a.id]


def test_falls_back_to_deliverables_then_workstreams(db_session):
    plan = {"deliverables": ["Ship the landing page", "Ship the dashboard"]}
    project = _project(db_session, plan=plan, slug="deliverable-app")
    graph = slice_plan(db_session, project)
    assert graph["count"] == 2
    assert [n["title"] for n in graph["tasks"]] == ["Ship the landing page", "Ship the dashboard"]


# --- a higher risk unit starts more conservative, never less ------------------------------


def test_higher_risk_unit_starts_more_conservative_than_the_default(db_session):
    plan = {
        "subtasks": [
            {"id": "calm", "title": "Write the docs page"},
            {"id": "hot", "title": "Reconcile the data store", "risk": "critical"},
        ]
    }
    project = _project(db_session, plan=plan, default="green", slug="risk-app")
    slice_plan(db_session, project)
    tasks = _by_key(db_session, project)

    # The benign unit inherits the green default; the critical unit starts red, never green.
    assert tasks["id-calm"].autonomy == "green"
    assert tasks["id-hot"].autonomy == "red"


def test_classifier_escalates_a_green_default_for_sensitive_text(db_session):
    plan = {"subtasks": [{"id": "auth", "title": "Add the auth middleware and password reset"}]}
    project = _project(db_session, plan=plan, default="green", slug="sensitive-app")
    slice_plan(db_session, project)
    tasks = _by_key(db_session, project)
    # Auth text trips the classifier, so even a green default starts at least yellow.
    assert tasks["id-auth"].autonomy == "yellow"


def test_default_is_inherited_when_nothing_is_risky(db_session):
    plan = {"subtasks": [{"id": "doc", "title": "Write a short README"}]}
    project = _project(db_session, plan=plan, default="yellow", slug="inherit-app")
    slice_plan(db_session, project)
    tasks = _by_key(db_session, project)
    assert tasks["id-doc"].autonomy == "yellow"


# --- a re-slice stays idempotent ----------------------------------------------------------


def test_reslice_is_idempotent(db_session):
    project = _project(db_session, plan=_STRUCTURED_PLAN, default="yellow", slug="idem-app")
    first = slice_plan(db_session, project)
    first_ids = {n["plan_unit_key"]: n["id"] for n in first["tasks"]}

    second = slice_plan(db_session, project)
    second_ids = {n["plan_unit_key"]: n["id"] for n in second["tasks"]}

    # Same number of tasks, same ids: reconciled in place, nothing duplicated.
    assert second["count"] == first["count"] == 4
    assert second_ids == first_ids

    # No stray rows: the total generated task count for the project is still four.
    total = (
        db_session.query(Task)
        .filter(Task.project_id == project.id, Task.plan_unit_key.isnot(None))
        .count()
    )
    assert total == 4


def test_reslice_reconciles_changes_and_soft_deletes_dropped_units(db_session):
    project = _project(db_session, plan=_STRUCTURED_PLAN, default="yellow", slug="reconcile-app")
    slice_plan(db_session, project)
    before = _by_key(db_session, project)
    pay_id = before["id-pay"].id

    # Drop the pay unit and rename a kept one.
    project.plan_json = {
        "subtasks": [
            {"id": "scaffold", "title": "Scaffold the project once more"},
            {"id": "login", "title": "Add login and sessions", "depends_on": ["scaffold"]},
            {"id": "polish", "title": "Polish the layout", "depends_on": ["scaffold", "login"]},
        ]
    }
    db_session.commit()
    graph = slice_plan(db_session, project)

    # The dropped unit is soft deleted: its row remains but it is gone from the graph.
    assert graph["count"] == 3
    assert "id-pay" not in {n["plan_unit_key"] for n in graph["tasks"]}
    dropped = db_session.get(Task, pay_id)
    assert dropped is not None
    assert dropped.deleted_at is not None

    # The kept unit updated in place (same id, new title); its id did not change.
    after = _by_key(db_session, project)
    assert after["id-scaffold"].id == before["id-scaffold"].id
    assert after["id-scaffold"].title == "Scaffold the project once more"


def test_reslice_never_relaxes_a_more_conservative_task(db_session):
    plan = {"subtasks": [{"id": "u1", "title": "Write the docs"}]}
    project = _project(db_session, plan=plan, default="green", slug="floor-app")
    slice_plan(db_session, project)
    tasks = _by_key(db_session, project)
    # A person tightened the task to red after slicing.
    tasks["id-u1"].autonomy = "red"
    db_session.commit()

    slice_plan(db_session, project)
    tasks = _by_key(db_session, project)
    # Re-slicing recomputes green from the plan but never relaxes the existing red.
    assert tasks["id-u1"].autonomy == "red"


# --- a bad or empty plan is rejected cleanly ----------------------------------------------


def test_empty_plan_json_is_rejected(db_session):
    project = _project(db_session, plan={}, slug="empty-app")
    with pytest.raises(SlicerError):
        slice_plan(db_session, project)


def test_plan_without_buildable_units_is_rejected(db_session):
    project = _project(db_session, plan={"summary": "just words", "risks": ["a risk"]}, slug="nounits-app")
    with pytest.raises(SlicerError):
        slice_plan(db_session, project)


def test_plan_with_only_empty_unit_lists_is_rejected(db_session):
    project = _project(
        db_session, plan={"subtasks": [], "deliverables": [], "workstreams": []}, slug="blank-app"
    )
    with pytest.raises(SlicerError):
        slice_plan(db_session, project)


def test_plan_units_that_are_all_blank_strings_are_rejected(db_session):
    project = _project(db_session, plan={"subtasks": ["", "   "]}, slug="whitespace-app")
    with pytest.raises(SlicerError):
        slice_plan(db_session, project)


# --- the task graph read ------------------------------------------------------------------


def test_task_graph_reads_the_current_graph(db_session):
    project = _project(db_session, plan=_STRUCTURED_PLAN, slug="graph-app")
    slice_plan(db_session, project)
    graph = task_graph(db_session, project)
    assert graph["count"] == 4
    assert graph["plan_present"] is True
    # Ordered and dependency carrying.
    assert [n["sequence"] for n in graph["tasks"]] == [1, 2, 3, 4]


def test_task_graph_is_empty_before_slicing(db_session):
    project = _project(db_session, plan=_STRUCTURED_PLAN, slug="unsliced-app")
    graph = task_graph(db_session, project)
    assert graph["count"] == 0
    assert graph["tasks"] == []
    assert graph["plan_present"] is True
