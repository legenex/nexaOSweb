"""SQLAlchemy models.

Importing this package registers every model on the shared metadata so Alembic and
create_all can see them. New model modules are imported here as they are added.
"""

from .base import Base

__all__ = ["Base"]
