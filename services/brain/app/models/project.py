"""Project, integration, and project manager run models."""

from sqlalchemy import JSON, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    item_id: Mapped[int | None] = mapped_column(
        ForeignKey("inbox_items.id"), index=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    slug: Mapped[str] = mapped_column(String(160), index=True, nullable=False)
    stage: Mapped[str] = mapped_column(String(40), default="idea", nullable=False)
    plan_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    plan_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    build_destination: Mapped[str | None] = mapped_column(String(200), nullable=True)
    selected_integrations: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    # When this is a research project attached to a build project, the target build project.
    research_target_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id"), index=True, nullable=True
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
