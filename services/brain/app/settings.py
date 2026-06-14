"""Application settings.

Every value is read from the environment. Provider keys are read only here, on the
server side, and are never returned to a client. DATABASE_URL defaults to a local
SQLite file so a fresh checkout runs without configuration.
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Core
    database_url: str = "sqlite:///./nexaos.db"
    nexa_session_secret: str = "dev-insecure-session-secret-change-me"
    nexa_public_https: bool = False
    nexa_desktop_bearer: str = ""

    # On disk roots for project files and uploads
    nexa_projects_root: str = "./.data/projects"
    nexa_uploads_root: str = "./.data/uploads"
    # Where the runtime stores large tool output referenced from step evidence by content_ref.
    nexa_runtime_root: str = "./.data/runtime"
    # The Brain secret store root. Provider secrets live here, server side only, and are never
    # returned to a client. The runtime ledger holds only a reference into this store.
    nexa_secrets_root: str = "./.data/secrets"

    # CORS, comma separated list of allowed origins
    cors_origins: str = "http://localhost:5173"

    # Per source inbound journal ingestion tokens, server side only. A comma separated list of
    # source:token pairs (for example "whatsapp:abc123,smart-inventory:def456"). An external
    # source authenticates POST /journal/ingest with its own token; the token never enters an
    # entry. Empty by default so ingestion is closed until a source is configured.
    journal_ingest_tokens: str = ""

    # Provider keys, read only by the Brain
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    gemini_api_key: str = ""
    tavily_api_key: str = ""

    # Intake knobs (defaults, overridable through AppSetting at runtime)
    classify_confidence_threshold: float = 0.55
    classify_sweep_enabled: bool = False
    classify_sweep_interval: int = 300
    classify_batch: int = 20

    # Dreaming consolidation. Disabled by default so a fresh checkout and the tests do not
    # spawn the nightly loop. The manual /dreaming/run trigger always works.
    dreaming_enabled: bool = False
    dreaming_interval: int = 86400
    dreaming_lookback_hours: int = 24
    dreaming_max_items: int = 50

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def journal_ingest_token_map(self) -> dict[str, str]:
        """Parse the source:token pairs into a map. Malformed or empty pairs are ignored."""
        out: dict[str, str] = {}
        for pair in self.journal_ingest_tokens.split(","):
            pair = pair.strip()
            if ":" not in pair:
                continue
            source, token = pair.split(":", 1)
            source, token = source.strip(), token.strip()
            if source and token:
                out[source] = token
        return out

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
