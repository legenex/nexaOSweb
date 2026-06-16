"""Project, integration, project manager run, and build log models."""

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin, utcnow


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("inbox_items.id"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    stage: Mapped[str] = mapped_column(String(40), default="idea", nullable=False)
    # The build pipeline mode (app, automation, website, funnel, data_pipeline, campaign,
    # content_system, product_concept). Drives capture questions, required files, and the
    # default build destination. See app/project_modes.py.
    mode: Mapped[str] = mapped_column(String(40), default="app", nullable=False)
    plan_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    plan_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    build_destination: Mapped[str | None] = mapped_column(String(200), nullable=True)
    selected_integrations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # Editable workspace overview metadata: status, url, repo, local_path, priority,
    # revenue_potential, current_blocker, next_action. Kept as JSON so the Projects
    # workspace can edit fields without a migration per field.
    workspace: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # When this is a research project attached to a build project, the target build project.
    research_target_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id"), index=True, nullable=True
    )
    # Research project configuration when this project is a research project. A JSON blob with
    # kind ("research"), topic, purpose, goals, depth, lookback, schedule, and category, so the
    # research config can grow without a migration per field. Empty for build projects.
    research_config: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # The project level autonomy default new tasks inherit (green, yellow, or red). The starting
    # position of the dial for work in this project; shown prominently in the UI. See app/autonomy.py.
    agent_autonomy_default: Mapped[str] = mapped_column(
        String(10), default="yellow", nullable=False
    )
    # The kill switch. When engaged, in flight agent runs for this project are halted and new runs are
    # refused, until it is released. Shown prominently in the UI as an always reachable stop.
    agent_kill_switch: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False
    )


class Integration(Base, TimestampMixin):
    __tablename__ = "integrations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="available", nullable=False)
    # A reference to where credentials live, never the raw secret.
    credentials_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)


class PMRun(Base, TimestampMixin):
    __tablename__ = "pm_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), index=True, nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="active", nullable=False)
    # The orchestrator loop's audit and progress record for the project: every dispatch, gate
    # decision, and pause, plus the run cap and wall-clock budget it ran under and why it stopped.
    # A JSON blob so the loop record grows without a migration per field. Empty for the PMRun stub
    # the builder stage writes before any orchestration.
    state: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)


class BuildLogEntry(Base, TimestampMixin):
    """A record on a project's build log.

    Created by the build pipeline (action build), the gated AI editor (action edit), and
    rollbacks (action rollback). An edit entry begins life as a proposal (status proposed),
    holding the before and after content but writing nothing to disk. Explicit approval flips
    it to applied and writes the file. before_content is the full prior file content for
    rollback, or null when the file did not exist before the edit.
    """

    __tablename__ = "build_log_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"), index=True, nullable=False
    )
    # build, edit, or rollback.
    action: Mapped[str] = mapped_column(String(40), default="edit", nullable=False)
    # proposed, applied, or rolled_back.
    status: Mapped[str] = mapped_column(
        String(40), default="proposed", index=True, nullable=False
    )
    summary: Mapped[str] = mapped_column(String(400), default="", nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    diff_summary: Mapped[str] = mapped_column(Text, default="", nullable=False)
    # Full content snapshots backing apply and rollback. before is null for new files.
    before_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_content: Mapped[str | None] = mapped_column(Text, nullable=True)
