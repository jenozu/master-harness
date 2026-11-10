# Changelog

## 1.2.0 (2026-11-09)
- **VPS kit works on servers that already run Traefik.** `bootstrap.sh` detects a Traefik container, reads its
  config folder, certificate resolver and HTTPS entrypoint, and switches to Traefik mode: nginx only listens on
  `127.0.0.1:<port>` behind it, certbot isn't installed, and each app gets one Traefik file
  (`vps-<app>.yml`). Traefik issues the certificates. Servers without Traefik keep the nginx + certbot setup.
  Force a mode with `--edge nginx|traefik`.
- Fixed: cloning on Windows turned the kit's scripts into CRLF files, which failed on the server
  (`invalid option name: set: pipefail`). `.gitattributes` now forces LF, and `setup_vps.sh` strips CRs before copying.
- `ssh vps tls <app>` in Traefik mode checks DNS and waits for Traefik's certificate.
- Tests for Traefik detection (using real Traefik settings), Traefik file rendering and the LF guard.

## 1.1.0 (2026-11-09)
- **VPS kit** (`library/vps-kit/`): one-time `setup_vps.sh` creates a dedicated Claude key, installs `vps-agent`
  on the server and an `ssh vps` alias on your PC. The key is restricted to `vps-agent` (forced command): create,
  deploy (`git push vps main`, build + migrate + health check + auto rollback), status, logs, env, backups, tls,
  rollback. Restore and destroy are admin-only. Nightly database backups.
- New library skill `vps` + settings fragment `vps`; BOOTSTRAP detects the kit (`~/.claude/vps.json`) and plans
  deploys as agent tasks.
- Base permissions: ask rules narrowed to `git push`, `git push origin *`, `scp`, `rsync` (ask rules beat allow
  rules, so the old `ssh *` / `git push *` would have blocked the vps skill). Settings fragments can now remove
  rules (`"remove"`), and `apply_template.py --upgrade` accepts `--rules/--skills/--settings`.
- rules.md, phase-runner and plan-from-prd: deploying through the vps skill is agent work, not a human step.
- **Project action** (existing projects adding the VPS): see "Add the VPS kit to an existing project" in UPGRADE.md.

## 1.0.0 (2026-11-09)
First release, generalized from the FitTrack+ setup that ran phases 0-2 end to end.

- Lead → phase-runner → builders (haiku/sonnet/opus) + verifier + reviewer, complexity-based routing.
- Phases live in `tasks.json` (`metadata.phases`, per-task `phase`), so nothing is hard-coded per project.
  New `tasks.py phase [n]` and `next --phase n`; `human` and `review` task flags.
- New core skills: `plan-from-prd`, `adapt`, `status`, `manual-checks`, `dev-servers`.
- `devserver.py`: background dev servers with log files, never kills servers it didn't start.
- `manual-checks.md` split into Agent-checkable and Eyes-on.
- phase-runner checks git at start and end (untracked or empty files are escalated, not ignored).
- Phase reports capped at 15 lines (phone-friendly); the lead reminds you to `/clear` between phases.
- `apply_template.py` (bootstrap and `--upgrade` with backups) and `check_harness.py` (shipped into every project).
- Library: rules for Python/FastAPI, React/Vite/Tailwind, Node/TypeScript, Next.js, Postgres, phone-first/PWA,
  shell scripts; skills `db-migration`, `deploy-vps`, `mobile-ui-check`, `security-review`; permission fragments.
