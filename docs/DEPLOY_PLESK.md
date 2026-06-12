# Deploying nexaOSweb on Plesk

Placeholder. This document is filled in by the Phase 5 prompts.

- S1 documents the Brain as a Dockerized uvicorn service or a Plesk Python application behind the Plesk Nginx, with Postgres, a server side .env, alembic upgrade head on deploy, and a Let's Encrypt certificate.
- S2 documents building apps/web to static files served at the site root with the API at /api, Secure session cookies, CSRF, and CORS.
- D2 documents the desktop signing secrets for the Mac dmg and Windows msi.
- S3 documents the tagged release deploy pipeline.

Secrets never live in this repo. They live in a server side .env read only by the Brain, and in GitHub repository secrets for CI.
