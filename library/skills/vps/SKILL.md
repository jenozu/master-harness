---
name: vps
description: Deploy and operate this project on the owner's VPS through the restricted "vps" SSH alias - create the app, write deploy/vps.json, deploy with git push, check status and logs, set config, take backups. Use for any task about hosting, deploying, production config, logs or backups.
---

# VPS (master-harness VPS kit)

The owner's VPS is reachable as the SSH alias `vps`. The key behind it can only run `vps-agent` subcommands
(enforced on the server), so you can use it without asking: it can't run arbitrary commands, read secrets,
restore or delete. App name for this project: `{{VPS_APP}}` · domain: `{{VPS_DOMAIN}}`.

## Commands
```
ssh vps help
ssh vps create {{VPS_APP}} [--domain {{VPS_DOMAIN}}] [--db] [--ext pg_trgm,unaccent]   # once; idempotent
git remote add vps vps:/srv/git/{{VPS_APP}}.git                                      # once per clone
git push vps main                     # deploys: build, migrate, switch, health check, auto-rollback on failure
ssh vps status {{VPS_APP}}
ssh vps logs {{VPS_APP}} -n 50        # service logs (max 200)   |   --deploy  for the last deploy log
ssh vps env-keys {{VPS_APP}}          # variable names only
ssh vps env-set {{VPS_APP}} KEY=VALUE # no spaces in values; PORT/APP_NAME/DATABASE_URL/SECRET_KEY are managed
ssh vps backup {{VPS_APP}}            # database dump now (nightly dumps run anyway)
ssh vps tls {{VPS_APP}}               # HTTPS certificate once DNS points at the server
ssh vps rollback {{VPS_APP}}
```
The app's `.env` on the server already has `APP_NAME`, `PORT`, `DOMAIN`, `ALLOWED_ORIGINS`, `SECRET_KEY`, and
`DATABASE_URL` if created with `--db`. The app must read its config from these environment variables.

## deploy/vps.json (in the repo, committed)
```json
{
  "web": {"dir": "frontend", "build": "npm ci --no-audit --no-fund && npm run build", "out": "dist"},
  "api": {"dir": "backend", "runtime": "python",
          "start": "venv/bin/uvicorn main:app --host 127.0.0.1 --port $PORT --proxy-headers",
          "migrate": "venv/bin/alembic upgrade head",
          "health": "/health", "path": "/api/"}
}
```
- `web` (optional): static build served by nginx; `out` is relative to `dir`. Single-page-app fallback included.
- `api` (optional): a server process on `127.0.0.1:$PORT`. `runtime` python or node sets a default `install`
  (venv + `pip install -r requirements.txt`, or `npm ci`); override with `install`. Optional `build`, `migrate`.
  `path` defaults to `/api/` when there's a `web`, else `/`; the prefix is stripped before proxying unless
  `"strip_prefix": false`. `health` is a path on the api that returns 2xx.
- Next.js / any node server: only `api` (`"runtime": "node", "build": "npm run build", "start": "npm start -- -p $PORT"`).
- Every command is one line and runs as the app's own unprivileged user, with the app's `.env` loaded.

## Rules
- Deploy only committed code: `git status --short` clean, tests pass, production build passes locally first.
- Deploy task flow: create (once) → add the remote → `git push vps main` → read the output: it ends with
  `OK: ... is live` or `FAILED: <step>` plus log lines → on failure `ssh vps logs {{VPS_APP}} --deploy -n 80`,
  fix in the repo, commit, push again. Don't keep pushing the same failing commit.
- Smoke test after deploy: `curl -fsS https://{{VPS_DOMAIN}}/` and the api health URL. TLS missing → `ssh vps tls`.
- Secrets the owner must provide (API keys): ask as a human step with the exact `ssh vps env-set` line for them
  to run, or ask them to give you the value to set. Never commit secrets.
- Restores and deleting apps are admin-only: if needed, give the owner the exact `sudo vps-agent restore ...`
  command to run on the server.
- `ssh vps` fails with "Permission denied" or "Could not resolve hostname vps": the VPS kit isn't set up on this
  computer. Report it as HUMAN NEEDED pointing to master-harness `library/vps-kit/README.md`.
