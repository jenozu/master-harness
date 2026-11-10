---
name: plan-from-prd
description: Turn the PRD (.taskmaster/docs/prd.md) into the task plan in .taskmaster/tasks/tasks.json - phases, dependency-ordered tasks, complexity scores that drive model routing, subtasks for big tasks, runnable test strategies, human-only steps flagged. Use at bootstrap, when the human asks to plan or re-plan, or to add a new phase after the PRD grows.
argument-hint: "[new | add-phase]"
disable-model-invocation: true
---

# Plan from the PRD

Mode: `$ARGUMENTS` (`new` if empty and tasks.json has no tasks; `add-phase` appends after the last phase and
never touches existing tasks).

## 1. Read
- The whole PRD. List for yourself: every capability (what a user can do), every constraint (stack, hosting,
  budget, privacy), every non-goal, and anything only the human can do (accounts, keys, DNS, servers, devices,
  purchases, large downloads, decisions).
- The repo: what already exists and works. Don't plan to build what's there; plan to verify or fix it.
- `add-phase`: also `python .taskmaster/tasks.py phase` and the PRD decision log, so new tasks fit what's done.

## 2. Phases
4 to 6 tasks each, each phase ending in something the human can see or use. Typical shape (adapt, don't copy):
- **Phase 0 Foundation:** repo cleanup if needed, local dev environment, config and secrets handling, database and
  migrations if there is a database, test runner, a first passing test.
- **Middle phases:** one user-visible slice each (the core loop first, then supporting features).
- **Ship:** production build, hosting/server setup, deploy, backups, monitoring basics.
  If the `vps` skill is installed, these are agent tasks, not human ones: production config read from env vars
  (`review`), `deploy/vps.json`, `ssh vps create` + first `git push vps main`, smoke test + TLS. Only secrets the
  owner must supply (third-party API keys) and DNS (if there's no wildcard apps domain) are `human` tasks.
- **Live with it (optional):** close registration, first real use, fix-up from real feedback.

Write them to `metadata.phases` as `[{"id": 0, "name": "Foundation"}, ...]`.

## 3. Tasks
Add each task with `python .taskmaster/tasks.py add` (or write tasks.json directly for a large initial plan,
then run `validate`). Every task needs:
- `title` (imperative, short), `description` (1-2 sentences: the outcome), `phase`, `priority`.
- `details`: files to create or change, libraries to use, approach, gotchas. Specific enough that a cheap model
  can follow it: name the files.
- `dependencies`: only lower-numbered tasks, never a task in a later phase.
- `testStrategy`: something runnable that proves it works (a test command, a curl, a script with expected
  output). "Looks right" is not a test. If part of it needs eyes on a screen, add that part as a manual step.
- `complexity` 1-10. It decides the starting model: **1-3 haiku** (exact files and steps, small), **4-6 sonnet**
  (normal feature work, anything touching auth/data/migrations), **7-10 opus** (cross-cutting, unclear, hard).
  Be honest: underscoring wastes a haiku attempt, overscoring wastes money.
- `human: true` for anything only the human can do. Give exact steps in details (commands, which terminal,
  what to paste back). Keep these as separate small tasks so agent work isn't blocked behind them.
- `review: true` for auth, permissions, migrations that change existing data, server scripts, payments, deletion.

Tasks scored 7+ get 3-5 subtasks (`tasks.py add --parent <id> ...`), each with its own test and complexity.

## 4. Check
1. `python .taskmaster/tasks.py validate` → no errors. Fix every warning you can.
2. Coverage: every PRD capability maps to at least one task; every task traces to the PRD. Tasks that trace to
   nothing are scope creep: cut them or park them in `parking-lot.md`.
3. `python .taskmaster/tasks.py phase` shows sensible phases; `tasks.py next` returns task 1 (or the first new
   task in add-phase mode).
4. `python .taskmaster/render_tasks_md.py`.
5. Update the "Phases" line in CLAUDE.md if it lists phases.

Report: phases with task counts, the capability → task table, the human-only tasks, and anything in the PRD you
couldn't plan because it's ambiguous (as questions).
