---
name: manual-checks
description: Handle .taskmaster/docs/manual-checks.md - "run" has the verifier execute every agent-checkable item (starting dev servers in the background) so the human only does the eyes-on ones; "results" takes the human's pass/fail report, adds fix tasks for failures and clears what passed. Use after a phase completes or when the human reports check results.
argument-hint: "run | results <what passed and failed>"
---

# Manual checks

The file has two sections: `## Agent-checkable` and `## Eyes-on`. Each item is `### Task <id> - <title> (<date>)`
with numbered steps.

## `run`
1. Dispatch the **verifier** with: "Run every item under `## Agent-checkable` in `.taskmaster/docs/manual-checks.md`.
   Start the dev servers you need with `python .claude/scripts/devserver.py start <name>`; if a port is busy and
   the server wasn't started by devserver.py, report it instead of killing anything. Stop what you started at the
   end. Reply per item: PASS, or FAIL with the command, expected and actual."
2. For each PASS, delete that item's section. For each FAIL, handle it as in `results` below.
3. Tell the human in at most 6 lines: how many agent checks passed or failed, fix tasks added, and how many eyes-on
   checks are left for them, with the first one's steps if it's short.

## `results <report>`
For each item the human mentions:
- **Passed** → delete its section.
- **Failed** → `python .taskmaster/tasks.py add --title "Fix: <what failed>" --deps <original id> --complexity <est>
  --details "<exact repro: steps, expected, actual, any error text the human gave>" --test "<the check that failed>"`.
  Add `--review` if it involves auth or data. Then delete its section (the task now tracks it).
- Unclear → keep the section and ask the human one specific question.
Then `tasks.py validate`, `render_tasks_md.py`, commit `manual checks: <n> passed, <n> fix tasks`, and tell the human
the fix task ids and the command to run them: `/run-phase <ids>`.

Never edit a done task to record a failure; the fix task is the record.
