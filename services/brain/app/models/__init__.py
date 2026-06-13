"""SQLAlchemy models.

Importing this package registers every model on the shared metadata so Alembic and
create_all can see them. New model modules are imported here as they are added.
"""

from .base import Base
from .dreaming import DreamRun, MemoryCandidate
from .inbox import ClassificationRecord, InboxItem, PipelineRun
from .knowledge import KnowledgeEntry
from .project import BuildLogEntry, Integration, PMRun, Project
from .research import ProjectUpdate, ResearchFinding, ResearchRun
from .user import User
from .workspace import AppSetting, JournalNote, Task

__all__ = [
    "Base",
    "User",
    "InboxItem",
    "ClassificationRecord",
    "PipelineRun",
    "Project",
    "Integration",
    "PMRun",
    "BuildLogEntry",
    "Task",
    "JournalNote",
    "AppSetting",
    "KnowledgeEntry",
    "MemoryCandidate",
    "DreamRun",
    "ProjectUpdate",
    "ResearchRun",
    "ResearchFinding",
]
