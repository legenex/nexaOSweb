"""Intake schemas."""

from pydantic import BaseModel

from app.schemas.entities import InboxItemRead, ORMModel


class ItemsPage(ORMModel):
    items: list[InboxItemRead]
    total: int
    limit: int
    offset: int


class ExpandRequest(BaseModel):
    name: str = ""
    body: str = ""


class ExpandResponse(BaseModel):
    expanded: str
