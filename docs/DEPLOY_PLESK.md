# Deploying nexaOSweb on Plesk (nexa.legenex.com)

The go-live runbook for the browser companion at https://nexa.legenex.com. One Plesk site serves
the built web at the root and proxies /api to the Brain, with Postgres on the same server.

Secrets never live in this repo. They live in a server side .env read only by the Brain, and in
GitHub repository secrets for CI.

```
browser  ->  Nginx (Plesk, HTTPS, Let's Encrypt)
                 |-- /         -> static apps/web build (httpdocs)
                 |-- /api/...  -> http://127.0.0.1:8847   (the Brain, uvicorn)
                                       |
                                    Postgres (127.0.0.1:5432)
```

Throughout, VHOST is the document root Plesk created for the subdomain. Find it in Plesk under
the domain, Hosting Settings, Document root. For a subdomain of legenex.com it is usually
`/var/www/vhosts/legenex.com/nexa.legenex.com`. Export it once on the server to paste the rest:

```bash
export VHOST=/var/www/vhosts/legenex.com/nexa.legenex.com
```

## 1. DNS and the Plesk site

1. Point an A record for `nexa.legenex.com` at the VPS IP (Plesk, Domains, or your registrar DNS).
2. In Plesk add the subdomain `nexa.legenex.com` (Websites and Domains, Add Subdomain). This
   creates the vhost and `httpdocs`.

## 2. SSL (Let's Encrypt)

In Plesk, open the domain, SSL/TLS Certificates, run SSL It! to issue a Let's Encrypt certificate
for `nexa.legenex.com`, and turn on Permanent SEO safe 301 redirect from http to https. HTTPS is
required: the session cookie is Secure in production.

## 3. Postgres

Plesk, Databases, Add Database. Create database `nexa` with a user and a strong password. Note the
connection string:

```
postgresql+psycopg://nexa:STRONG_PASSWORD@127.0.0.1:5432/nexa
```

## 4. The Brain source and virtualenv

Put the repo on the server and build the Brain venv. SSH in as the subscription system user.

```bash
cd "$VHOST"
git clone https://github.com/legenex/nexaOSweb.git app_src
cd app_src/services/brain
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install .
```

## 5. Server side .env (absolute paths)

Storage paths must be absolute. A relative path silently points at a different database and an
empty secret store. Create `"$VHOST"/brain.env`, readable only by the Brain user:

```bash
mkdir -p "$VHOST"/data/{secrets,runtime,projects,uploads}
cat > "$VHOST"/brain.env <<EOF
DATABASE_URL=postgresql+psycopg://nexa:STRONG_PASSWORD@127.0.0.1:5432/nexa
NEXA_SESSION_SECRET=$(openssl rand -hex 32)
NEXA_PUBLIC_HTTPS=true
NEXA_DESKTOP_BEARER=$(openssl rand -hex 24)

NEXA_SECRETS_ROOT=$VHOST/data/secrets
NEXA_RUNTIME_ROOT=$VHOST/data/runtime
NEXA_PROJECTS_ROOT=$VHOST/data/projects
NEXA_UPLOADS_ROOT=$VHOST/data/uploads

CORS_ORIGINS=https://nexa.legenex.com

# Owner and admin are created on first boot from these values.
NEXA_SEED_ON_BOOT=true
NEXA_OWNER_EMAIL=team@legenex.com
NEXA_OWNER_PASSWORD=CHANGE_ME_STRONG
NEXA_ADMIN_EMAIL=admin@legenex.com
NEXA_ADMIN_PASSWORD=CHANGE_ME_STRONG
NEXA_SEED_FORCE_PASSWORD=false

# Provider keys are optional here: connect them in Settings, Models and Agents (store first).
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
GEMINI_API_KEY=
TAVILY_API_KEY=
EOF
chmod 600 "$VHOST"/brain.env
```

## 6. Run the Brain as a systemd service

A systemd unit is the simplest reliable option on Plesk: it reaches the local Postgres directly
and binds the Brain to 127.0.0.1 so only Nginx can reach it. Run migrations before each start.

Create `/etc/systemd/system/nexa-brain.service` (as root, set User to the subscription system
user, for example the one shown by `stat -c %U "$VHOST"/httpdocs`):

```ini
[Unit]
Description=nexaOSweb Brain
After=network.target postgresql.service

[Service]
User=REPLACE_WITH_VHOST_USER
WorkingDirectory=VHOST/app_src/services/brain
EnvironmentFile=VHOST/brain.env
ExecStartPre=VHOST/app_src/services/brain/.venv/bin/alembic upgrade head
ExecStart=VHOST/app_src/services/brain/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8847
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
```

Replace the literal `VHOST` in that file with the real path, then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now nexa-brain
sudo systemctl status nexa-brain        # should be active (running)
curl -s http://127.0.0.1:8847/healthz   # {"status":"ok"}
```

The boot seed creates the owner and admin from the .env on first start. To rotate the Brain on a
new release: `cd "$VHOST"/app_src && git pull && cd services/brain && . .venv/bin/activate && pip install . && sudo systemctl restart nexa-brain` (migrations run via ExecStartPre).

Alternative, Docker: the repo ships services/brain/Dockerfile (runs alembic then uvicorn on 8847).
If you prefer it, run with `--add-host=host.docker.internal:host-gateway`, point DATABASE_URL at
`host.docker.internal:5432`, publish `-p 127.0.0.1:8847:8847`, and bind mount the four data roots
at the same absolute paths. The systemd route above avoids that networking and is recommended.

## 7. Build and publish the web

Build the static frontend (locally or on the server) and copy it to the document root. The web
calls /api by default in production, so no build time URL is needed.

```bash
# from a checkout with pnpm available
pnpm install
pnpm --filter web build           # outputs apps/web/dist
# publish to the site root (adjust httpdocs if your docroot differs)
rsync -a --delete apps/web/dist/ "$VHOST"/httpdocs/
```

## 8. Nginx: proxy /api and the SPA fallback

In Plesk, the domain, Apache and nginx Settings, Additional nginx directives:

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8847/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}

location / {
    try_files $uri $uri/ /index.html;
}
```

The trailing slash on `proxy_pass http://127.0.0.1:8847/` strips the `/api` prefix, so the browser
path `/api/healthz` reaches the Brain route `/healthz`. The `try_files` line makes the single page
app deep links resolve. Apply the changes.

## 9. Verify go-live

```bash
curl -sf https://nexa.legenex.com/api/healthz     # {"status":"ok"} over HTTPS
```

Then open https://nexa.legenex.com, sign in with the owner account from the .env, connect a model
provider in Settings, Models and Agents, and run a capture through the Flow Builder end to end.

Cookies, CSRF, CORS, all already handled: NEXA_PUBLIC_HTTPS makes the session cookie Secure, the
client sends the CSRF token on writes, and CORS_ORIGINS scopes any cross origin caller. Because the
web and the Brain share one origin through the /api proxy, requests are same origin.

## Optional: CI deploy on a tag

The repo has .github/workflows/deploy.yml, which on a version tag ships the web build and the Brain
to the server over SSH, runs migrations, and checks /healthz. To use it, set these repository
secrets and tag a release: PLESK_HOST, PLESK_USER, PLESK_SSH_KEY, PLESK_WEB_ROOT (the httpdocs
path), PLESK_BRAIN_DIR (VHOST/app_src/services/brain), PLESK_HEALTH_URL
(https://nexa.legenex.com/api/healthz). Until those exist, deploy manually with the steps above.
