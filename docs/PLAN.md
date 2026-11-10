# master-harness: build plan

A reusable template that turns a PRD into a working Claude Code setup: a lead (Opus), a phase-runner (Sonnet), cheap builders, a memory file, and a Taskmaster-style plan in git. It's built from the FitTrack+ setup that's already working, made generic.

Status: **built as v1.0.0** (2026-11-09). Changes from this plan: the `install.sh`/`install.ps1` scripts became one cross-platform `scripts/apply_template.py` (bootstrap + upgrade); `check_harness.py` lives in the template so every project keeps a copy; dev servers got a stdlib helper (`devserver.py`) instead of only a skill.

---

## 1. How you'll use it (the goal)

For any new project:

1. Create the project repo and put your PRD in it (anywhere; `prd.md` at the root is fine).
2. Open Claude Code in that folder, run `/model opus`, and paste one line:

   ```
   Clone https://github.com/jenozu/master-harness into .harness-tmp and follow .harness-tmp/BOOTSTRAP.md using my PRD.
   ```
3. It builds the whole setup, checks it, deletes `.harness-tmp`, makes one commit and stops.
4. You run `/clear`, `/model opus`, `/run-phase 0`.

The same repo also gets an **upgrade** path, so projects that already have the setup (fit-boo, adhd) can pull in later improvements without being rebuilt.

---

## 2. Folder structure

```
master-harness/
├── README.md                 what this is, the 4-step usage above, FAQ
├── BOOTSTRAP.md              the master prompt: PRD → full setup in a new project
├── UPGRADE.md                prompt: update an existing project to a newer harness version
├── VERSION                   e.g. 1.0.0, stamped into each project
├── CHANGELOG.md
│
├── template/                 copied into every project (placeholders filled in)
│   ├── CLAUDE.md.tmpl
│   ├── AGENTS.md.tmpl
│   ├── .claude/
│   │   ├── settings.json.tmpl
│   │   ├── HARNESS_VERSION.tmpl
│   │   ├── agents/
│   │   │   ├── phase-runner.md
│   │   │   ├── builder-haiku.md
│   │   │   ├── builder-sonnet.md
│   │   │   ├── builder-opus.md
│   │   │   ├── verifier.md
│   │   │   └── reviewer.md
│   │   ├── skills/
│   │   │   ├── run-phase/SKILL.md       lead's command for one phase
│   │   │   ├── next-task/SKILL.md       per-task loop used by the phase-runner
│   │   │   ├── plan-from-prd/SKILL.md   PRD → tasks.json (breakdown + scoring)
│   │   │   ├── adapt/SKILL.md           direction change: PRD log → tasks → build
│   │   │   ├── status/SKILL.md          "where are we?" in 5 lines, cheap
│   │   │   ├── manual-checks/SKILL.md   run agent-checkable items, collect your results
│   │   │   └── dev-servers/SKILL.md     start/stop servers in background, logs to files
│   │   └── rules/
│   │       ├── rules.md                 scope, anti-drift, short output, git, escalation
│   │       └── memory.md.tmpl           capped ~80 lines, seeded from the PRD
│   └── .taskmaster/
│       ├── tasks.py                     stdlib-only helper (next, status, validate, ...)
│       ├── render_tasks_md.py           tasks.json → TASKS.md
│       ├── tasks/tasks.json.tmpl        empty skeleton with metadata
│       └── docs/
│           ├── prd.md.tmpl              PRD template (used if your PRD needs reshaping)
│           ├── parking-lot.md
│           └── manual-checks.md
│
├── library/                  optional pieces BOOTSTRAP picks to match the PRD's stack
│   ├── rules/
│   │   ├── python-fastapi.md
│   │   ├── react-vite-tailwind.md
│   │   ├── node-typescript.md
│   │   ├── nextjs.md
│   │   ├── postgres.md
│   │   ├── pwa-mobile.md
│   │   └── shell-scripts.md
│   ├── skills/
│   │   ├── db-migration/SKILL.md
│   │   ├── deploy-vps/SKILL.md          nginx + systemd + your backup scripts
│   │   ├── mobile-ui-check/SKILL.md
│   │   └── security-review/SKILL.md
│   └── settings/                        permission allowlists per stack, merged in
│       ├── python.json
│       ├── node.json
│       └── postgres.json
│
├── scripts/
│   ├── check_harness.py      validates a project's setup (see section 5)
│   ├── install.sh            no-AI fallback: copy template/ without overwriting
│   └── install.ps1           same for Windows PowerShell
│
├── docs/
│   ├── architecture.md       the hierarchy, escalation ladder, why it's cheap
│   ├── task-schema.md        every field in tasks.json, statuses, ID rules
│   ├── placeholders.md       list of {{PLACEHOLDERS}} and where each is used
│   ├── customizing.md        adding a stack to library/, changing models
│   └── SOURCES.md            any external skills adopted, with URL + license
│
├── tests/
│   ├── test_tasks.py         unittest for tasks.py (next, validate, cycles, subtasks)
│   └── fixtures/             a tiny sample PRD + expected-valid tasks.json
│
└── .github/workflows/check.yml   runs tests + check_harness on the template itself
```

---

## 3. The agent hierarchy (unchanged, just generic)

| Role | Model | Job | Stops when |
|---|---|---|---|
| Lead | Opus | Runs `/run-phase N`, reads only the final report | Never builds |
| phase-runner | Sonnet, medium | Loops a whole phase with no check-ins | Opus builder fails, scope/PRD change, destructive or human-only step, 3 escalations in a row |
| builder-haiku | Haiku | Tasks scored 1–3 | Fails twice → hands back |
| builder-sonnet | Sonnet | Tasks scored 4–6, or escalated | Fails twice → hands back |
| builder-opus | Opus | Tasks scored 7–10, or escalated | Fails → phase-runner escalates to lead |
| verifier | Haiku, read-only | Runs the task's testStrategy | — |
| reviewer | Sonnet, read-only | Diff vs task + PRD, drift check | — |

Report format stays: `PHASE STATUS: COMPLETE | PARTIAL | ESCALATE | HUMAN NEEDED`.

---

## 4. Improvements from what we learned on FitTrack+

| Problem we hit | Fix in the template |
|---|---|
| `backend/food_data` was never committed; `requirements.txt` got committed empty | phase-runner checks `git status` and empty/missing files at phase start and end; BOOTSTRAP verifies its own commit |
| Two terminals needed for checks; you didn't know | `dev-servers` skill starts servers in background with logs to files, so the verifier can run the API-level checks itself |
| Manual checks mixed "agent can do" with "needs your eyes" | `manual-checks.md` gets two sections: **Agent-checkable** (run by `/manual-checks`) and **Eyes-on** (yours) |
| Unclear when to start fresh | `run-phase` ends its report with "run `/clear` before the next phase" |
| Docker assumed; you had Postgres already | BOOTSTRAP asks "local DB: existing install or Docker?" only if the PRD needs a database |
| Windows + Git Bash | All scripts tested for Git Bash; Python helpers are stdlib-only; PowerShell installer included |
| Phone / Remote Control | Reports kept short enough to read on a phone; HUMAN NEEDED items phrased as one clear question |
| Can't update old projects | `VERSION` + `HARNESS_VERSION` stamp + `UPGRADE.md` |

---

## 5. Placeholders and the checker

Template files use `{{LIKE_THIS}}`: project name, one-line summary, stack, install/test/lint/run commands, deploy target, phase list. `docs/placeholders.md` lists them all.

`scripts/check_harness.py` (stdlib only) checks a project after bootstrap or upgrade:
- no `{{...}}` left anywhere
- agent and skill frontmatter uses only known fields (list kept in the script, updated from current docs at build time)
- `CLAUDE.md` ≤ 60 lines, `memory.md` ≤ 80 lines
- `settings.json` is valid JSON and has the spawn-depth env set to `"2"`
- `tasks.py validate` passes and `tasks.py next` returns a task
- every `@import` in `CLAUDE.md` points to a file that exists
- no absolute paths from another machine, no secrets-looking strings
- everything under `.claude/` and `.taskmaster/` is committed

Prints one line per failure, exits non-zero if any. BOOTSTRAP and UPGRADE both must end with it passing.

---

## 6. What BOOTSTRAP.md does (step order)

1. **Read** the PRD and the target repo (stack, commands, existing CLAUDE.md/.claude: merge, never overwrite).
2. **Ask** only if blocked: PRD missing, or a choice that changes phase 0 (e.g. local DB method).
3. **Fetch current Claude Code docs** (sub-agents, skills, memory, settings) and confirm frontmatter fields before writing.
4. **Copy `template/`**, fill placeholders.
5. **Pick from `library/`** what matches the stack; merge settings allowlists.
6. **Research external skills** (Sonnet subagent): max 5, markdown only, read in full, no scripts run, logged in `docs/SOURCES.md` with URL + license, rejected ones listed in a line each.
7. **Plan** with the `plan-from-prd` skill: tasks.json with phases, complexity scores → model hints, subtasks for 7+, runnable testStrategy each, human-only steps marked, every PRD capability mapped.
8. **Seed `memory.md`** from the PRD.
9. **Check** with `check_harness.py` + a capability→task table.
10. **Clean up** `.harness-tmp`, one commit `task 0: bootstrap agent harness (harness vX.Y.Z)`, short report. Does not start phase 0.

UPGRADE.md: diff the project's harness version against the latest, update only harness-owned files (agents, core skills, `tasks.py`, `rules.md`), never touch `memory.md`, `tasks.json`, the PRD or project-specific rules, show the diff summary, run the checker, commit.

---

## 7. How I'll build it

1. **Pull the latest FitTrack+ harness** from `jenozu/fittrack-plus` (your agents may have fixed things since I wrote it), and use that as the base instead of my older copy.
2. **Core template**: genericize agents, skills, rules, CLAUDE/AGENTS templates, `tasks.py`, renderer.
3. **New skills**: plan-from-prd, adapt, status, manual-checks, dev-servers.
4. **Library**: stack rules, library skills, settings fragments.
5. **Checker + tests**: `check_harness.py`, `test_tasks.py`, fixtures, CI workflow.
6. **Prompts + docs**: BOOTSTRAP, UPGRADE, README, architecture, schema, placeholders, customizing.
7. **Dry run**: bootstrap the sample fixture PRD into a scratch repo, run the checker, fix until clean. Then a second dry run with a different stack.
8. **Commit and push** to `jenozu/master-harness` as v1.0.0.

---

## 8. Decisions I need from you

1. **Stacks in `library/` for v1.** My default: Python/FastAPI, React/Vite/Tailwind, Node/TypeScript, Next.js, Postgres, PWA/mobile, shell + VPS deploy. Add or remove any?
2. **Upgrade fit-boo and adhd** to the new template afterwards, or leave them as they are?
3. **Repo visibility.** If `master-harness` is private, the one-line clone works on your machines (you're signed in to git) but not for anyone else. Fine?
