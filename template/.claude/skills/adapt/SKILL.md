---
name: adapt
description: Change direction safely - when the human wants to change what's being built, or a build discovery makes the plan wrong. Updates the PRD decision log first, then the affected tasks, then lets building continue. Use when the human says "actually let's...", "change of plan", "drop X", "add Y", or the lead gets an ESCALATE that is a scope change.
argument-hint: "[what changed]"
---

# Adapt the plan

Change: `$ARGUMENTS` (or what the human just said).

1. **Classify it.**
   - Small idea, not needed now → one dated line in `.taskmaster/docs/parking-lot.md`. Stop here.
   - Changes a goal, a non-goal, the stack, hosting, or a data model the PRD fixed → continue, and confirm with
     the human in one sentence before editing anything if it came from you rather than them.
2. **PRD first.** Add a dated entry to the PRD's decision log: what changed, why, what it replaces. Edit the
   affected PRD section to match. Never silently rewrite the goal.
3. **Then tasks.**
   - Obsolete pending tasks → `tasks.py set-status <id> cancelled` + a log line saying why. Never delete.
   - Done tasks whose result is now wrong → add a corrective task or subtask; never reword done work.
   - New work → `tasks.py add` with phase, complexity, testStrategy, deps (same rules as `plan-from-prd`).
   - `tasks.py validate`, `render_tasks_md.py`.
4. **Memory.** One line under "Decisions since the PRD" in `.claude/rules/memory.md`; prune to its cap.
5. Commit: `adapt: <one-line change>`.
6. Tell the human in at most 5 lines: what changed in the plan (tasks cancelled/added), and the next `/run-phase`.
