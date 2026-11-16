# UPGRADE: bring an existing project up to the latest master-harness

Shortcut: with the `/harness` command installed (see README), just type `/harness upgrade`. Upgrades are
mechanical: `/model sonnet` is enough and costs far less than Opus.

You are the lead in a project that already has an agent setup. The human told you to follow this file from the
master-harness clone at `.harness-tmp/`. Don't change app code and don't start a phase.

## 0. Get the template
If `.harness-tmp/` doesn't exist: `git clone -q https://github.com/jenozu/master-harness .harness-tmp` (no
`--depth`: the installer uses the history to tell untouched files from edited ones).
`git status --short` must be clean first; if not, ask the human to commit or stash.

## 1. Which case is it?
- `.claude/HARNESS_VERSION` exists → **normal upgrade** (step 2).
- No `HARNESS_VERSION` but there's a hand-made setup (agents like `phase-runner`, `.taskmaster/tasks.py`) →
  **migration from a pre-harness setup** (step 3 first, then step 2).

## 2. Normal upgrade
Work on a branch, never on the default branch: `git checkout -q -b harness-upgrade` (if the name is taken,
`harness-upgrade-<new version>`). Every commit below, including ones a project action asks for, goes on it.
```
python .harness-tmp/scripts/apply_template.py --target . --upgrade
```
What it does: replaces harness-owned files (core agents, core skills, `rules.md`, `tasks.py`, renderer, scripts),
saving copies of any this project edited in `.harness-backup/<old-version>/` (git has the rest); adds new core files; adds new harness permissions to
settings.json without removing any. It never touches CLAUDE.md, AGENTS.md, memory.md, tasks.json, the PRD,
parking lot, manual checks, dev-servers.json, or project/library rules and skills.

Then work only from what the installer printed (don't read the changelog or diff files yourself):
1. **PROJECT ACTIONS**: apply each one, in order. `none` → skip.
2. **CUSTOMIZED**: only these files were edited in this project. For each, `diff .harness-backup/<old>/<file> <file>`;
   move project-specific lines (paths, commands, owner rules) into `.claude/rules/project.md`, AGENTS.md or a
   project rule file, never back into the harness-owned file. `none` → skip. Files under "replaced, untouched"
   need nothing.
3. `python .claude/scripts/check_harness.py --no-git` → fix every ERROR.
4. `rm -rf .harness-tmp .harness-backup`, then `git add -A`, `git commit -q -m "harness: upgrade to v<new>"` and
   `git push -q -u origin HEAD`.
5. Open a PR with GitHub's REST API (`{o}/{r}` from `git remote get-url origin`):
   `gh api repos/{o}/{r}/pulls -f title="harness: upgrade to v<new>" -f head=harness-upgrade -f base=<default> -f body="<old> -> <new>; project actions done" --jq .html_url`.
   Don't merge it and don't run the merge gate with `--merge`: an upgrade changes `.claude/scripts/`, so the owner
   reviews and merges it. No `gh` or no remote: leave the branch pushed (or local) and say so.
6. Report in at most 6 lines: old → new version, project actions done, customized files handled, the PR link,
   anything the owner must decide.

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
