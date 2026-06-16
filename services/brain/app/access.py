"""Shared read-scope helper.

A run or an audit row with no project is a system or container record, visible to any
authenticated user. A row tied to a project is visible only to that project's owner, resolved
through the project's source inbox item. The runtime reads and the agent governance reads both
scope through this single function so the visibility rule lives in one place.
"""

from sqlalchemy.orm import Session

from app.models.inbox import InboxItem
from app.models.project import Project
from app.models.user import User


def user_owns_project(project_id: int | None, user: User, db: Session) -> bool:
    """True when the user may see records tied to this project (or to no project)."""
    if project_id is None:
        return True
    project = db.get(Project, project_id)
    if project is None:
        return False
    if project.item_id is None:
        return True
    item = db.get(InboxItem, project.item_id)
    return item is not None and item.user_id == user.id
