"""SQLAlchemy models.

Importing this package registers every model on the shared metadata so Alembic and
create_all can see them. New model modules are imported here as they are added.
"""

from .audit import AgentAudit
from .base import Base
from .dreaming import DreamRun, MemoryCandidate
from .inbox import ClassificationRecord, InboxItem, PipelineRun
from .insight import Insight, InsightRun
from .knowledge import KnowledgeEntry
from .project import BuildLogEntry, Integration, PMRun, Project
from .provider import DiscoveredModel, ProviderCredential
from .research import ProjectUpdate, ResearchFinding, ResearchRun
from .runtime import AgentRun, AgentStep
from .user import User
from .workspace import (
    AppSetting,
    JournalAttachment,
    JournalNote,
    JournalTopic,
    Task,
)

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
    "ProviderCredential",
    "DiscoveredModel",
    "Task",
    "JournalNote",
    "JournalTopic",
    "JournalAttachment",
    "AppSetting",
    "KnowledgeEntry",
    "MemoryCandidate",
    "DreamRun",
    "ProjectUpdate",
    "ResearchRun",
    "ResearchFinding",
    "Insight",
    "InsightRun",
    "AgentRun",
    "AgentStep",
    "AgentAudit",
]
