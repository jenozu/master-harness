# Changelog

## 2.1.0 (2026-11-15)
- **Cheaper upgrades.** The installer now compares each harness-owned file with the template as it was at the
  project's old version (from the master-harness git history). Files nobody edited are replaced quietly; only
  files edited in the project are backed up and listed under CUSTOMIZED. Before, the lead diffed every replaced
  file, which cost the most tokens of any upgrade step.
- The installer prints the CHANGELOG's project actions since the old version, oldest first, so the lead doesn't
  read the changelog.
- UPGRADE.md works only from that output; no dry run. The template is cloned without `--depth` for the history.
- `/harness upgrade` stops right away when the project is already current, and suggests `/model sonnet`.
- Fix: the upgrade also wrote `HARNESS_VERSION` with CRLF on Windows.

## 2.0.1 (2026-11-15)
- **Fix: Windows line endings.** On Windows, `tasks.py`, `render_tasks_md.py` and the installer wrote
  `tasks.json`, `TASKS.md` and `HARNESS_VERSION` with CRLF line endings. Projects whose CI checks whitespace
  (`git diff --check`) failed on every harness commit. All harness writes now use LF on every OS.
- The installer adds LF rules for harness files to `.gitattributes`, so git stores them with LF even when another
  Windows tool writes CRLF.
- `check_harness.py` reports harness files committed with CRLF, with the one-line fix.
- Project action (upgrade): after `--upgrade`, run
  `git add --renormalize CLAUDE.md AGENTS.md TASKS.md .claude .taskmaster .gitattributes` and commit it as
  `normalize harness line endings` (skip if nothing changes). Then `check_harness.py` must show no CRLF error.

## 2.0.0 (2026-11-14)
Breaking: merging and human steps work differently. Read the project actions.
- **Merge gate.** New `.claude/scripts/merge_gate.py` is the only way the harness merges. It waits for CI, reading
  GitHub check runs **and** classic commit statuses (before, a failing status-only check such as a preview
  deploy could be missed), gives up cleanly after `ci_wait_minutes`, and then applies the new seeded
  `.claude/harness.json`:
  - `merge`: `auto` (merge any green PR, the old behaviour), `safe-only` (merge only PRs that touch docs, tests or
    the plan; app code waits for the owner), or `owner` (never merges).
  - `merge_deploys`: whether merging to the default branch puts the code live. When true, the gate also holds the
    PR while human steps are queued or eyes-on checks are open, so code can't ship before a migration, an env
    value or a human look.
  - When the gate says OWNER, the lead stops at the phase boundary with the PR link and the reasons.
  - New ask rules in settings.json for `gh pr merge` and `gh api .../merge`, so agents can't merge around the gate
    (the old `gh pr merge` ask rule never covered the harness's REST merge).
- **Queued human steps.** `tasks.py queue <id>` replaces "mark the human task done and build around it". The task
  stays open (`[QUEUED]`), dependents become workable, and only the human's confirmation marks it done.
  `tasks.py phase <n>` reports "agent work done" when only queued steps remain.
- **Project rules win.** New seeded `.claude/rules/project.md`: owner rules that override `rules.md` and the
  harness skills, and that upgrades never touch.
- **Phase cap.** `max_phases_per_launch` in harness.json (0 = no limit) stops the lead after N phases.
- **Context check** reads only this project's transcripts; with two windows open it reports the larger one, so it
  can stop early but never late.
- **`/harness` command.** `user-skill/harness/SKILL.md`, installed once per computer (README): `/harness prd.md`
  sets up a new project, `/harness upgrade` upgrades one. It updates itself when it runs.
- BOOTSTRAP asks (or detects) whether merging deploys and writes harness.json; live projects default to safe-only.
- `check_harness.py` validates harness.json and warns when merging deploys with `merge: auto`.
- Project action (upgrade): `--upgrade` adds `merge_gate.py`, `harness.json` (defaults: `auto`, not deploying),
  `rules/project.md` and the new permissions. Then:
  1. **Ask the owner whether merging to the default branch puts the code live** (or detect it: vercel.json,
     netlify.toml, a deploy-on-push workflow). Set `merge_deploys`. Live → `"merge": "safe-only"` unless the owner
     says otherwise; a project rule like "the owner merges PRs" → `"merge": "owner"`. Add the project's sensitive
     folders (auth, payments, admin, migrations, middleware) to `never_auto_paths`.
  2. Move owner rules found in other rule files or old customizations into `.claude/rules/project.md`, and delete
     hand-written merge rules there that harness.json now covers (say which in the report).
  3. Human tasks that were marked done but whose step the owner hasn't confirmed (check human-checklist.md for
     unticked boxes): set them back to `pending`, then `tasks.py queue <id>`.
  4. `python .claude/scripts/check_harness.py --no-git` → 0 errors. Report the merge mode chosen.

## 1.5.0 (2026-11-14)
- **Free checks.** Tasks can be tagged `"runner": "script"` with a `"check"` list of commands. The new
  `.taskmaster/run_checks.py` runs them with no model: no builder, no verifier, zero tokens. A model is only
  called when a check fails, and then gets the command and the last 20 lines of output.
  - `run_checks.py plan` lists open script tasks in dependency order; `run [--only id | --from id]` runs them,
    marks a task done only after every command passes, and stops at the first failure with the status unchanged.
  - Safety: commands are argument lists run without a shell; shell operators, shells, `python -c` and folders
    outside the repo are refused; every command must match the allowlist in the new `.taskmaster/checks.json`
    (seeded, so each project keeps its own). Retries only on a timeout, never on a failed check. Each run is
    recorded in `.claude/tmp/checks/<id>.log` (times, exit codes, stdout sha256, output tails).
  - `tasks.py validate` checks the new fields; `show`/`next`/`phase` mark script tasks; `add --runner script
    --check "..."`. `check_harness.py` reports commands the allowlist would refuse.
  - `plan-from-prd` ends every phase with a free **gate task** (lint, types, tests, build) and tags other
    check-only tasks as script tasks. The phase-runner and next-task run them before any builder.
- Project action (upgrade): `--upgrade` adds `run_checks.py`, `checks.json` and the new permissions. Then
  (1) trim `.taskmaster/checks.json` `allow` to this project's tools and add any check-only tool it needs;
  (2) for each phase that isn't done, add a gate task with
  `python .taskmaster/tasks.py add --title "Phase <n> gate: lint, types, tests and build pass" --phase <n>
  --complexity 3 --deps <every other task in the phase> --runner script --check "<lint cmd>" --check "<test cmd>" ...`
  (commands from AGENTS.md; a command that needs a folder gets `{"cmd": [...], "cwd": "<dir>"}` in tasks.json);
  (3) `python .taskmaster/run_checks.py plan` shows nothing REFUSED, then `tasks.py validate` and
  `render_tasks_md.py`. Existing tasks keep working unchanged.

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
- **Context limit between phases.** After each completed phase the lead runs `.claude/scripts/context_check.py`
  (reads the session transcript). Under 150K it starts the next phase; at 150K or more it stops at the phase
  boundary and tells you the exact `/clear` + `/run-phase <next>` to continue. Never mid-phase, so a running
  phase can finish. Change the limit with env `HARNESS_CONTEXT_LIMIT`.
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
