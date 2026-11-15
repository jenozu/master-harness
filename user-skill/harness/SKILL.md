---
name: harness
description: Set up master-harness in the current project from a PRD, or upgrade a project that already has it. Run only when the user types /harness.
argument-hint: "[path/to/prd.md | upgrade]"
disable-model-invocation: true
---

# /harness: set up or upgrade master-harness here

Argument: `$ARGUMENTS` (a PRD path, `upgrade`, or empty). You are the lead. Don't write app code and don't start
a phase.

## 1. Where are we
- Not a git repo (`git rev-parse` fails) → `git init -q` and say so in one line.
- `git status --short` must be clean (ignoring untracked PRD files). If not, ask the human to commit or stash, and stop.
- **Mode:** `upgrade` if the argument is `upgrade` or `.claude/HARNESS_VERSION` exists (or the repo has a hand-made
  setup: a `phase-runner` agent or `.taskmaster/tasks.py`). Otherwise **new**.

## 2. Get the latest template
`rm -rf .harness-tmp` only if it exists and is a master-harness clone (`git -C .harness-tmp remote get-url origin`
contains `jenozu/master-harness`); if it's something else, stop and ask. Then
`git clone -q --depth 1 https://github.com/jenozu/master-harness .harness-tmp` and read `.harness-tmp/VERSION`.

Keep this command current: if `.harness-tmp/user-skill/harness/SKILL.md` differs from the installed copy at
`~/.claude/skills/harness/SKILL.md`, copy the new one over it and mention it in the report.

## 3a. New project
1. Find the PRD: the argument's path; else `prd.md`, `PRD.md`, `docs/prd*.md`, or a PRD attached to the message.
   None → ask the human to attach or paste one, and stop.
2. Follow `.harness-tmp/BOOTSTRAP.md` from step 1 with that PRD, to the end (it plans the phases, checks itself,
   commits, delivers and reports). Its step 3 asks whether merging to the default branch deploys live; ask that if
   you can't tell.

## 3b. Upgrade
Follow `.harness-tmp/UPGRADE.md` to the end, including every "Project action" in `.harness-tmp/CHANGELOG.md`
between the project's version (`.claude/HARNESS_VERSION`) and the new one. Don't start a phase afterwards.

## 4. Finish
`.harness-tmp/` must be gone. Report as BOOTSTRAP/UPGRADE says, then one line: how to start (`/clear`, then
`/run-phase <n>`).
