"""Model provider credentials and discovered models.

A ProviderCredential records that a model provider (anthropic, openai, gemini) is connected, by
reference into the Brain secret store, never by value. The raw key lives only in the secret store;
the row carries a reference and a non secret last four hint so an operator can recognise the key.
These credentials are server wide, keyed by provider, distinct from the per user Integration rows.

A DiscoveredModel caches one concrete model id pulled live from a connected provider. Discovery is
additive: rows accumulate, each carries an enabled flag, and the models the semantic keys already
reference are auto enabled. The model router still resolves a semantic key to a concrete id through
config/models.yaml; the discovered cache backs the Settings surface that picks those ids.
"""

from sqlalchemy import Boolean, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class ProviderCredential(Base, TimestampMixin):
    __tablename__ = "provider_credentials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # The provider slug (anthropic, openai, gemini). Server wide, one row per provider.
    provider: Mapped[str] = mapped_column(String(80), unique=True, index=True, nullable=False)
    # connected once a key is stored by reference, available otherwise.
    status: Mapped[str] = mapped_column(String(40), default="available", nullable=False)
    # A reference into the Brain secret store, never the raw key.
    credentials_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    # A non secret last four hint, for example ****1234, so the connected key is recognisable.
    hint: Mapped[str | None] = mapped_column(String(40), nullable=True)


class DiscoveredModel(Base, TimestampMixin):
    __tablename__ = "discovered_models"
    __table_args__ = (
        UniqueConstraint("provider", "model_id", name="uq_discovered_models_provider_model"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    # The provider prefixed canonical id, for example anthropic/claude-sonnet-4-6, so it matches
    # what config/models.yaml references and can be auto enabled.
    model_id: Mapped[str] = mapped_column(String(200), nullable=False)
    # The raw model name as the provider returned it, for display.
    name: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    # Whether the model is available for selection. Auto enabled when a semantic key references it.
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
