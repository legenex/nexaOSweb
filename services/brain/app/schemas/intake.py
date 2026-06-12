"""Intake schemas."""

from app.schemas.entities import InboxItemRead, ORMModel


class ItemsPage(ORMModel):
    items: list[InboxItemRead]
    total: int
    limit: int
    offset: int
