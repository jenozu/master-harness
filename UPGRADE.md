# UPGRADE: bring an existing project up to the latest master-harness

You are the lead in a project that already has an agent setup. The human told you to follow this file from the
master-harness clone at `.harness-tmp/`. Don't change app code and don't start a phase.

## 0. Get the template
If `.harness-tmp/` doesn't exist: `git clone -q --depth 1 https://github.com/jenozu/master-harness .harness-tmp`.
`git status --short` must be clean first; if not, ask the human to commit or stash.

## 1. Which case is it?
- `.claude/HARNESS_VERSION` exists → **normal upgrade** (step 2).
- No `HARNESS_VERSION` but there's a hand-made setup (agents like `phase-runner`, `.taskmaster/tasks.py`) →
  **migration from a pre-harness setup** (step 3 first, then step 2).

## 2. Normal upgrade
```
python .harness-tmp/scripts/apply_template.py --target . --upgrade --dry-run
python .harness-tmp/scripts/apply_template.py --target . --upgrade
```
What it does: replaces harness-owned files (core agents, core skills, `rules.md`, `tasks.py`, renderer, scripts)
and saves the old ones in `.harness-backup/<old-version>/`; adds new core files; adds new harness permissions to
settings.json without removing any. It never touches CLAUDE.md, AGENTS.md, memory.md, tasks.json, the PRD,
parking lot, manual checks, dev-servers.json, or project/library rules and skills.

Then:
1. Read `.harness-tmp/CHANGELOG.md` from the old version to the new one. Apply anything it marks
   "project action" (e.g. a new line for CLAUDE.md, a new field in tasks.json).
2. For each replaced file, `diff .harness-backup/<old>/<file> <file>`. Old lines that were **project-specific
   customizations** (a routing tweak, a project fact, a reviewer trigger) → move them where they belong now:
   CLAUDE.md "Risky paths" / facts, a project rule file, or memory.md. Don't paste them back into owned files,
   or the next upgrade overwrites them again.
3. `python .claude/scripts/check_harness.py --no-git` → fix every ERROR.
4. `rm -rf .harness-tmp .harness-backup`, commit `harness: upgrade to v<new>`, and report in at most 8 lines:
   version change, files replaced, customizations moved, project actions done.

## Switch a project to open permissions
```
python .harness-tmp/scripts/apply_template.py --target . --upgrade --settings open
```
Allows all shell commands, edits and web access, drops the `ask` prompts for push/scp/rsync/installs, and keeps
the deny rules. Later plain upgrades notice the project is open and don't bring the prompts back. To go back,
re-copy `template/.claude/settings.json` and re-run with your stack fragments.

## Add the VPS kit to an existing project
If `ssh -o BatchMode=yes vps version` works on this computer and the project should deploy there:
```
python .harness-tmp/scripts/apply_template.py --target . --upgrade --skills vps --settings vps
```
Then fill `{{VPS_APP}}` / `{{VPS_DOMAIN}}` in `.claude/skills/vps/SKILL.md`, add `vps` to CLAUDE.md's Project
skills, and replace any old deploy tasks with the vps flow (`/adapt`). An app already running on the server
outside the kit (e.g. under /var/www) keeps running; moving it is a planned task with a backup first.

## 3. Migration from a pre-harness setup (e.g. projects built before master-harness existed)
Do these, then run step 2 (the upgrade will replace the old agents and skills, backing them up):
1. **Phases into tasks.json.** Find the phase list (usually in the old `phase-runner.md`, `run-phase/SKILL.md` or
   `render_tasks_md.py`, e.g. "Phase 0: 1-4"). Write `metadata.phases` (`[{"id": 0, "name": "..."}]`) and add
   `"phase": <n>` to every top-level task. Set `"human": true` on tasks only the human can do and
   `"review": true` on the ones the old reviewer rules listed. Keep `metadata.project` set to the project name.
2. **Project facts out of owned files.** The old agents, skills and `rules.md` contain project specifics (paths,
   test commands, non-goals, reviewer triggers, DB URLs). Before they're replaced, copy those facts to:
   AGENTS.md "Project" + "Facts that are easy to get wrong", CLAUDE.md "Risky paths", or a project rule file
   (`.claude/rules/<area>.md`). Non-goals stay in the PRD.
3. **CLAUDE.md** (seeded, so the upgrade won't touch it): rewrite it from
   `.harness-tmp/template/CLAUDE.md.tmpl`, keeping the project's own content: Phases, Risky paths, Skills (core
   list + the project's own skills), and the `<!-- master-harness v... -->` footer. Under 60 lines.
4. **dev-servers.json**: create `.claude/dev-servers.json` from the commands the human used to run the app
   (memory.md and manual-checks.md usually have them). Include `cmd_windows` if the human is on Windows.
5. **manual-checks.md**: add `## Agent-checkable` and `## Eyes-on` headings and move each existing item under the
   right one (anything a curl or script can prove → agent-checkable). Items become `### Task <id> - ...`.
6. **Old project skills** (e.g. db-migration, deploy, mobile-ui-check written for this project): keep them. They
   aren't harness-owned. Compare with `.harness-tmp/library/skills/` and take improvements by hand if useful.
7. Write `.claude/HARNESS_VERSION` with `0.0.0` so the upgrade backs files up under `.harness-backup/0.0.0/`.
