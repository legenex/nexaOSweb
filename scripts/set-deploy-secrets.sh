#!/usr/bin/env bash
# Set the GitHub Actions secrets (and optional variables) that the deploy workflow
# (.github/workflows/deploy.yml) reads to ship nexaOSweb to Plesk.
#
# Values come from scripts/deploy.env (gitignored). Copy scripts/deploy.env.example
# to scripts/deploy.env, fill it in, then run: bash scripts/set-deploy-secrets.sh
#
# This needs a GitHub token that can write repository secrets. The Codespaces token
# cannot, so first authenticate gh with a Personal Access Token that has the repo
# scope (classic) or Secrets read and write (fine grained):
#     gh auth login          # paste the PAT when asked, or
#     export GH_TOKEN=<PAT>   # for a single run
set -euo pipefail

cd "$(dirname "$0")/.."

ENV_FILE="${1:-scripts/deploy.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "error: $ENV_FILE not found." >&2
  echo "Copy scripts/deploy.env.example to scripts/deploy.env and fill it in." >&2
  exit 1
fi

# Load the values. They are exported only into this process, never printed.
set -a
# shellcheck disable=SC1090
. "$ENV_FILE"
set +a

# Target repository, inferred from the origin remote unless GH_REPO overrides it.
REPO="${GH_REPO:-$(gh repo view --json nameWithOwner -q .nameWithOwner 2>/dev/null || true)}"
if [ -z "${REPO:-}" ]; then
  echo "error: could not determine the repository. Set GH_REPO=owner/name and retry." >&2
  exit 1
fi
echo "Target repository: $REPO"

# Fail early, with a clear message, if the token cannot manage secrets.
if ! gh secret list -R "$REPO" >/dev/null 2>&1; then
  echo "error: this gh token cannot manage secrets for $REPO." >&2
  echo "Authenticate with a PAT that has the repo scope (gh auth login, or export GH_TOKEN=...)." >&2
  exit 1
fi

require() {
  if [ -z "${2:-}" ]; then
    echo "error: $1 is empty in $ENV_FILE" >&2
    exit 1
  fi
}

require PLESK_HOST "${PLESK_HOST:-}"
require PLESK_USER "${PLESK_USER:-}"
require PLESK_SSH_KEY_FILE "${PLESK_SSH_KEY_FILE:-}"
require PLESK_WEB_ROOT "${PLESK_WEB_ROOT:-}"
require PLESK_BRAIN_DIR "${PLESK_BRAIN_DIR:-}"
require PLESK_HEALTH_URL "${PLESK_HEALTH_URL:-}"

# Expand a leading ~ in the key path, then confirm the key file exists.
KEY_FILE="${PLESK_SSH_KEY_FILE/#\~/$HOME}"
if [ ! -f "$KEY_FILE" ]; then
  echo "error: PLESK_SSH_KEY_FILE ($KEY_FILE) does not exist." >&2
  exit 1
fi

echo "Setting secrets on $REPO ..."
gh secret set PLESK_HOST       -R "$REPO" --body "$PLESK_HOST"
gh secret set PLESK_USER       -R "$REPO" --body "$PLESK_USER"
gh secret set PLESK_SSH_KEY    -R "$REPO" < "$KEY_FILE"
gh secret set PLESK_WEB_ROOT   -R "$REPO" --body "$PLESK_WEB_ROOT"
gh secret set PLESK_BRAIN_DIR  -R "$REPO" --body "$PLESK_BRAIN_DIR"
gh secret set PLESK_HEALTH_URL -R "$REPO" --body "$PLESK_HEALTH_URL"

# Optional homepage installer links, set only when provided.
if [ -n "${VITE_DOWNLOAD_MACOS:-}" ]; then
  gh variable set VITE_DOWNLOAD_MACOS -R "$REPO" --body "$VITE_DOWNLOAD_MACOS"
fi
if [ -n "${VITE_DOWNLOAD_WINDOWS:-}" ]; then
  gh variable set VITE_DOWNLOAD_WINDOWS -R "$REPO" --body "$VITE_DOWNLOAD_WINDOWS"
fi

echo "Done. Secrets now set on $REPO:"
gh secret list -R "$REPO"
