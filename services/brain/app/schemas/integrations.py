"""Integration request schemas. Reads reuse IntegrationRead from schemas.entities."""

from pydantic import BaseModel, Field


class ConnectRequest(BaseModel):
    provider: str


class FulfilCredentialRequest(BaseModel):
    """Provide a secret for a pending credential request, by waiting_approval step id.

    The secret is accepted only over the authenticated session and is written straight to the
    Brain secret store. It is never echoed back, logged, or written to the runtime ledger.
    """

    step_id: int
    secret: str = Field(min_length=1)
