#!/usr/bin/env bash
# Start the Brain for local development. Idempotent: creates the venv and installs
# dependencies on first run, copies .env from the example if missing, applies migrations,
# then runs uvicorn with reload. Safe to run repeatedly (for example after a Codespace
# restart, which is the usual reason login stops working: the web server comes up but the
# Brain does not).
set -euo pipefail

cd "$(dirname "$0")/.."

VENV=".venv"
PORT="${BRAIN_PORT:-8847}"

if [ ! -d "$VENV" ]; then
  echo "[brain] creating virtualenv"
  python3 -m venv "$VENV"
fi

# Install (or refresh) dependencies. Quiet unless something goes wrong.
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet -e .

if [ ! -f ".env" ]; then
  echo "[brain] no .env found, creating one from .env.example with a generated session secret"
  cp .env.example .env
  SECRET="$("$VENV/bin/python" -c 'import secrets; print(secrets.token_urlsafe(48))')"
  # Fill the session secret and a sane local default for the SQLite database.
  "$VENV/bin/python" - "$SECRET" <<'PY'
import pathlib, sys
secret = sys.argv[1]
path = pathlib.Path(".env")
lines = []
for line in path.read_text().splitlines():
    if line.startswith("NEXA_SESSION_SECRET="):
        line = f"NEXA_SESSION_SECRET={secret}"
    elif line.startswith("DATABASE_URL="):
        line = "DATABASE_URL=sqlite:///./nexaos.db"
    lines.append(line)
path.write_text("\n".join(lines) + "\n")
PY
fi

echo "[brain] applying migrations"
"$VENV/bin/alembic" upgrade head

echo "[brain] starting on http://localhost:${PORT}"
exec "$VENV/bin/uvicorn" app.main:app --reload --host 0.0.0.0 --port "$PORT"
