"""Application settings.

Every value is read from the environment. Provider keys are read only here, on the
server side, and are never returned to a client. DATABASE_URL defaults to a local
SQLite file so a fresh checkout runs without configuration.

Storage paths should be absolute in any real deployment. A relative path resolves against the
working directory, so starting the Brain from a different folder points it at a different database
and an empty secret store. log_storage_paths makes the resolved locations visible on boot.
"""

import logging
import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("nexaos.settings")

# The .env lives next to the Brain project root (services/brain/.env). Pin it by absolute path so
# the same configuration loads no matter which working directory the process starts from. A
# relative env_file would silently go unread when the Brain is launched from elsewhere, falling
# back to the relative storage defaults that caused data to scatter across directories.
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
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
    # Where the runtime stores large tool output referenced from step evidence by content_ref, and
    # the single agent execution root. Every executor worktree and every Agent Build Engine
    # workspace is an isolated working directory under this one root, kept separate from the served
    # project files in nexa_projects_root so agent execution never touches the live folders
    # directly, and every path is validated through the path safety gate. The former separate
    # NEXA_BUILDS_ROOT was collapsed into this so there is a single ensure_within_root boundary.
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
    # xAI key for the Grok Build agent backend, server side only. Read by the Grok adapter and
    # injected straight into its CLI process, never into a prompt or a response. Empty until set.
    xai_api_key: str = ""

    # Agent build backends. Grok Build is gated off by default: while NEXA_ENABLE_GROK is false the
    # backend is not selectable and its health probe reports disabled, so nothing depends on Grok in
    # a fresh checkout or the tests. Set this true (and supply XAI_API_KEY) to make it selectable.
    # Claude Code and Codex need no flag.
    nexa_enable_grok: bool = False

    # The orchestrator loop. While NEXA_ENABLE_ORCHESTRATOR is false the unattended green auto-advance
    # loop cannot dispatch a real agent: the orchestrate endpoint is refused. It stays off until the
    # AB2.1 live single-run acceptance has passed against the real Claude Code CLI and the per-task
    # autonomy projection is in place (see docs/ARCHITECTURE.md). Two bounds keep a loop from running
    # unbounded: a run cap (the most dispatches one loop may make) and a wall-clock budget in seconds.
    nexa_enable_orchestrator: bool = False
    nexa_orchestrator_run_cap: int = 50
    nexa_orchestrator_budget_seconds: int = 900

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

    # Durable account seed, read on boot. Disabled by default so a fresh checkout and the tests do
    # not create accounts. The local .env enables it and supplies the real emails and passwords;
    # committed code never carries a password. The owner is the highest privilege account; the
    # admin has the same privileges except it can never delete the owner.
    nexa_seed_on_boot: bool = False
    nexa_owner_email: str = "nick@legenex.com"
    nexa_owner_password: str = ""
    nexa_admin_email: str = "team@legenex.com"
    nexa_admin_password: str = ""
    # When true, the boot seed resets the owner and admin passwords to the configured values so a
    # recovery run has a known good login. Leave off in steady state.
    nexa_seed_force_password: bool = False

    # Public base URL of the web companion, used to build the link in a password reset email (for
    # example https://nexa.legenex.com). Empty falls back to the first CORS origin, then localhost.
    nexa_app_base_url: str = ""
    # How long a password reset link stays valid, in minutes.
    nexa_password_reset_ttl_minutes: int = 60

    # Outbound email (SMTP), server side only. Used today for password reset links. When the host
    # is empty the mailer is disabled and the reset link is written to the Brain log instead of
    # sent, so the flow still works in local dev without a mail server. On Plesk point these at the
    # server's mail service. The password lives only in the server .env, never in the apps.
    nexa_smtp_host: str = ""
    nexa_smtp_port: int = 587
    nexa_smtp_user: str = ""
    nexa_smtp_password: str = ""
    nexa_smtp_from: str = ""
    nexa_smtp_starttls: bool = True

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


def resolved_database_path(settings: Settings | None = None) -> str:
    """The DATABASE_URL shown as a resolved absolute on disk path for sqlite, or the raw URL."""
    settings = settings or get_settings()
    url = settings.database_url
    if not url.startswith("sqlite"):
        return url
    # sqlite:///relative or sqlite:////absolute. Strip the scheme, then resolve to absolute.
    raw = url.split(":///", 1)[-1] if ":///" in url else url
    return raw if raw.startswith("/") else os.path.abspath(os.path.expanduser(raw))


def log_storage_paths(settings: Settings | None = None) -> None:
    """Log the resolved absolute database and secret store locations on boot.

    A wrong or working directory dependent path is then visible immediately in the logs rather than
    discovered later as missing data. This is the canary for the relative path failure mode.
    """
    settings = settings or get_settings()
    logger.info(
        "storage resolved: database=%s secrets_root=%s",
        resolved_database_path(settings),
        os.path.abspath(os.path.expanduser(settings.nexa_secrets_root)),
    )
