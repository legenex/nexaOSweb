"""Schemas for the provider credentials and model discovery surface.

A provider is connected by handing its API key once; the key goes straight to the Brain secret
store and is never echoed back. Reads carry only the provider, its status, a non secret last four
hint, and whether a key is available. Discovered models carry the concrete id, an enabled flag, and
the provider they came from. No schema here ever carries a raw key.
"""

from pydantic import BaseModel, Field

# A provider slug, lower snake case, for example anthropic.
_PROVIDER_PATTERN = r"^[a-z][a-z0-9_-]*$"


class ConnectProviderRequest(BaseModel):
    """Connect a model provider by supplying its API key once.

    The key is accepted only over the authenticated session and is written straight to the Brain
    secret store. It is never echoed back, logged, or written to the ledger.
    """

    provider: str = Field(pattern=_PROVIDER_PATTERN, max_length=80)
    api_key: str = Field(min_length=1)


class ProviderStatus(BaseModel):
    provider: str
    # connected once a key is available, available otherwise.
    status: str
    connected: bool
    # Where the key resolves from: store, env, or null when none is configured.
    source: str | None = None
    # A non secret last four hint for a key connected through the store, for example ****1234.
    hint: str | None = None


class DiscoveredModelRead(BaseModel):
    id: int
    provider: str
    model_id: str
    name: str
    enabled: bool


class ToggleModelRequest(BaseModel):
    enabled: bool
