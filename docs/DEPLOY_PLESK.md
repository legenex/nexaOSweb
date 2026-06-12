# Deploying nexaOSweb on Plesk

How the Brain, the web companion, and the deploy pipeline run in production. Morne owns the server.

Secrets never live in this repo. They live in a server side .env read only by the Brain, and in GitHub repository secrets for CI.

## Topology

One Plesk site, for example `nexaos.example.com`, with a Let's Encrypt certificate. The Plesk Nginx serves the built web at the site root and proxies `/api` to the Brain. The Brain runs as a Dockerized uvicorn service (recommended) or as a Plesk Python application via Passenger. Postgres runs on the same server.

```
browser / desktop
      |
   Nginx (Plesk, HTTPS, Let's Encrypt)
      |-- /            -> static apps/web build
      |-- /api/...     -> http://127.0.0.1:8847  (the Brain)
                                |
                             Postgres
```

## 1. Database

Create a Postgres database and user in Plesk (Databases, Add Database). Note the connection string, for example:

```
postgresql+psycopg://nexa:STRONG_PASSWORD@127.0.0.1:5432/nexaos
```

## 2. Server side environment

Create `/var/www/vhosts/nexaos.example.com/brain/.env`, readable only by the Brain service user. It is never committed. Fill every variable from `services/brain/.env.example`:

```
DATABASE_URL=postgresql+psycopg://nexa:STRONG_PASSWORD@127.0.0.1:5432/nexaos
NEXA_SESSION_SECRET=<64 random hex chars>
NEXA_PUBLIC_HTTPS=true
NEXA_DESKTOP_BEARER=<long random token for the desktop app>
NEXA_PROJECTS_ROOT=/var/www/vhosts/nexaos.example.com/nexa_projects
NEXA_UPLOADS_ROOT=/var/www/vhosts/nexaos.example.com/nexa_uploads
CORS_ORIGINS=https://nexaos.example.com
ANTHROPIC_API_KEY=...
OPENAI_API_KEY=...
GEMINI_API_KEY=...
TAVILY_API_KEY=...
```

## 3. Run the Brain (Docker, recommended)

Build and run the image from `services/brain`. The image runs `alembic upgrade head` then `uvicorn` on port 8847 (see the Dockerfile CMD).

```bash
cd services/brain
docker build -t nexaosweb-brain .
docker run -d --name nexaosweb-brain \
  --restart unless-stopped \
  --env-file /var/www/vhosts/nexaos.example.com/brain/.env \
  -p 127.0.0.1:8847:8847 \
  -v /var/www/vhosts/nexaos.example.com/nexa_projects:/var/www/vhosts/nexaos.example.com/nexa_projects \
  -v /var/www/vhosts/nexaos.example.com/nexa_uploads:/var/www/vhosts/nexaos.example.com/nexa_uploads \
  nexaosweb-brain
```

Bind to `127.0.0.1` so only Nginx can reach it. Migrations run on every container start, which is safe because they are additive only.

Alternative without Docker: a Plesk Python application pointing at `services/brain`, with the startup command `alembic upgrade head` and the application object `app.main:app` run by Passenger. Use the same `.env`.

Provision the first user once:

```bash
docker exec -it nexaosweb-brain python -m scripts.create_user you@example.com 'a strong password'
```

## 4. Nginx proxy for /api

In Plesk, site, Apache and nginx Settings, Additional nginx directives:

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8847/;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

The trailing slash on `proxy_pass http://127.0.0.1:8847/` strips the `/api` prefix, so the browser path `/api/healthz` reaches the Brain route `/healthz`.

## 5. Certificate and verification

Issue a Let's Encrypt certificate for the domain in Plesk (SSL/TLS Certificates) and force HTTPS. Then verify the Brain is up over HTTPS:

```bash
curl -sf https://nexaos.example.com/api/healthz
# {"status":"ok"}
```

A successful `ok` over HTTPS is the acceptance for the Brain deploy.

## 6. Web companion

The web companion is the static `apps/web` build served by the same Nginx at the site root, calling the Brain at `/api`.

Build it:

```bash
pnpm install
pnpm --filter web build
# output in apps/web/dist
```

The frontend calls `/api` by default in production (see `apps/web/src/app/config.ts`), so no build time API URL is required when the Brain is proxied at `/api` on the same domain. To point at a different host, set `VITE_API_BASE` at build time.

Publish the build to the site document root, for example `/var/www/vhosts/nexaos.example.com/httpdocs`. Because the app is a single page app, route unknown paths back to `index.html`. Add to the Plesk Additional nginx directives, alongside the `/api` block:

```nginx
location / {
    try_files $uri $uri/ /index.html;
}
```

### Cookies, CSRF, and CORS

- The Brain `.env` sets `NEXA_PUBLIC_HTTPS=true`, so the session cookie is issued with `Secure` and is only sent over HTTPS.
- State changing requests carry the CSRF token from the readable `nexa_csrf` cookie in the `X-CSRF-Token` header; the client does this automatically. The Brain rejects a session request that omits it.
- `CORS_ORIGINS=https://nexaos.example.com` matches the site origin. Because the web and the Brain share one origin through the `/api` proxy, requests are same origin and CORS is not exercised for the browser; the setting still scopes any cross origin caller.

### Acceptance

Open `https://nexaos.example.com`, sign in with the user created in step 3, and confirm the Flow panorama loads and a capture round trips. A working browser login end to end is the acceptance for the web companion.

## Desktop signing secrets (D2)

The `desktop-build` workflow signs the Mac dmg and Windows msi and publishes them, with updater artifacts, to a draft GitHub release. It reads these repository secrets:

Updater (both platforms):
- `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`. Generate with `pnpm --filter desktop tauri signer generate`. Put the public key in `apps/desktop/src-tauri/tauri.conf.json` under `plugins.updater.pubkey`.

macOS code signing and notarization:
- `APPLE_CERTIFICATE` (base64 of the .p12), `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_PASSWORD` (app specific password), `APPLE_TEAM_ID`.

Windows code signing:
- `WINDOWS_CERTIFICATE` (base64 of the .pfx) and `WINDOWS_CERTIFICATE_PASSWORD`.

The updater endpoint in `tauri.conf.json` points at `https://nexaos.example.com/updates/...`; replace the host and serve the generated `latest.json` and installers there so installed apps can pull new versions.
