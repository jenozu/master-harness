# Changelog

## 1.4.0 (2026-11-12)
- **Auto-merge delivery.** New core skill `deliver`: push, open a PR, wait for CI, merge automatically when green
  (squash, through the REST API because GraphQL is blocked in Claude Code sessions), then continue from the updated default branch. Red CI is treated as a failed task and fixed through
  the builder ladder; checks are never skipped. Protected branches use `gh pr merge --auto`, otherwise the merge
  goes on the checklist and work continues on a branch cut from the PR branch. Branches are pushed after every
  task commit; the PR happens at the end of each phase and before any stop.
- **Keep going.** The lead now starts the next phase itself when one completes (no `/clear` and go-ahead
  needed). Human-only steps no longer stop a phase: they're queued in the new
  `.taskmaster/docs/human-checklist.md` (checkbox list) and later tasks build against placeholders. The harness
  stops only when nothing workable is left, or for money, destructive actions and goal/non-goal changes.
- **Fresh context per phase.** `.claude/scripts/run-phases.py` runs `claude -p "/run-phase"` in a new process per
  phase until nothing is left, workable or two runs in a row finish nothing. Inside a session, the lead hands over
  after 3 phases: a one-shot scheduled task (fresh session) if it has a scheduler, else it asks you to `/clear`.
- Needs `gh` logged in, and push permission (use the `open` settings, or allow `git push origin *` yourself).
- Project action: `--upgrade` replaces the owned files; the checklist file is created if missing.

## 1.3.1 (2026-11-09)
- **Fixed a duplicate-builder bug.** A phase-runner could return PARTIAL while its builder was still running; the
  relaunched runner then started a second builder on the same working tree (about a quarter of one phase's
  tokens, and a risk of clobbered files). The phase-runner now waits for every subagent it starts and sends
  half-finished tasks to the verifier before building again; the lead checks nothing is still running before it
  relaunches after PARTIAL.
- **Routing:** risky tasks of complexity 4-6 stay on builder-sonnet and get the reviewer, instead of jumping to
  builder-opus. Tasks that change a stored-data schema still start on builder-opus.
- Project action: none. Upgrade replaces the owned files (`--upgrade`).

## 1.3.0 (2026-11-09)
- **`open` settings fragment** (`library/settings/open.json`): opt-in no-prompt permissions for unattended work.
  Allows `Bash`, `Edit`, `Write`, `WebFetch`, `WebSearch`; removes the `ask` rules for git push, ssh/scp/rsync and
  package installs; keeps every deny (force push, `reset --hard`, `clean -fdx`, `.env`/`.pem`/`.key`) and adds
  `Read(~/.ssh/**)` and `rm -rf /*`. Destructive database prompts (`dropdb`, `prisma migrate reset`) still ask.
- `apply_template.py` merges `open` last regardless of order, and `--upgrade` keeps an already-open project open.
- Use: add `--settings open` (or tell BOOTSTRAP "Permissions: open"). Existing projects: UPGRADE.md,
  "Switch a project to open permissions". Not applied by default.

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
