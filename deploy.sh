#!/usr/bin/env bash
set -e
cd /workspaces/nexaOSweb
pnpm --filter web build
git add -f apps/web/dist
git add -u
git commit -m "${1:-deploy: web update}"
git push
