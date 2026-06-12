# Deploying nexaOSweb on Plesk

Placeholder. This document is filled in by the Phase 5 prompts.

- S1 documents the Brain as a Dockerized uvicorn service or a Plesk Python application behind the Plesk Nginx, with Postgres, a server side .env, alembic upgrade head on deploy, and a Let's Encrypt certificate.
- S2 documents building apps/web to static files served at the site root with the API at /api, Secure session cookies, CSRF, and CORS.
- D2 documents the desktop signing secrets for the Mac dmg and Windows msi.
- S3 documents the tagged release deploy pipeline.

Secrets never live in this repo. They live in a server side .env read only by the Brain, and in GitHub repository secrets for CI.

## Desktop signing secrets (D2)

The `desktop-build` workflow signs the Mac dmg and Windows msi and publishes them, with updater artifacts, to a draft GitHub release. It reads these repository secrets:

Updater (both platforms):
- `TAURI_SIGNING_PRIVATE_KEY` and `TAURI_SIGNING_PRIVATE_KEY_PASSWORD`. Generate with `pnpm --filter desktop tauri signer generate`. Put the public key in `apps/desktop/src-tauri/tauri.conf.json` under `plugins.updater.pubkey`.

macOS code signing and notarization:
- `APPLE_CERTIFICATE` (base64 of the .p12), `APPLE_CERTIFICATE_PASSWORD`, `APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_PASSWORD` (app specific password), `APPLE_TEAM_ID`.

Windows code signing:
- `WINDOWS_CERTIFICATE` (base64 of the .pfx) and `WINDOWS_CERTIFICATE_PASSWORD`.

The updater endpoint in `tauri.conf.json` points at `https://nexaos.example.com/updates/...`; replace the host and serve the generated `latest.json` and installers there so installed apps can pull new versions.
