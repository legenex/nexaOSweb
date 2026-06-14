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

    # CORS, comma separated list of allowed origins
    cors_origins: str = "http://localhost:5173"

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
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
