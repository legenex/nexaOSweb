"""Integration request schemas. Reads reuse IntegrationRead from schemas.entities."""

from pydantic import BaseModel


class ConnectRequest(BaseModel):
    provider: str
