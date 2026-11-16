---
name: run-phase
description: Lead (main session) command to build the .taskmaster plan hands-off, phase after phase. Launches the phase-runner subagent (Sonnet), starts the next phase itself when one completes, and only stops when it reports ESCALATE or HUMAN NEEDED with nothing else workable. Use when the human says "run phase 2", "build the next phase", "keep going", or /run-phase.
argument-hint: "[phase-number | task-ids e.g. 13,14,15]"
---

# Run a phase (you are the lead)

Your job here is cheap: launch, wait, decide only when asked. Do **not** read task logs, diffs or source files
while the phase-runner works, don't poll it, and don't relay its progress.

## 1. Launch
- Phase = `$ARGUMENTS`. If empty, use the phase in memory.md "Now"; if that's unclear, run
  `python .taskmaster/tasks.py phase` once and take the "current phase" it prints.
- Tell the human in one line: "Running phase <n> with the phase-runner; I'll come back when it's done or stuck."
- Dispatch the Agent tool with `subagent_type: phase-runner` and the prompt `Run phase <n> to completion.`
  (or `Run tasks <ids> to completion.`). Subagents started from the main session run in the background; that's
  fine. Wait for its completion notification and do nothing else meanwhile unless the human talks to you.

## 2. Read its one report and act
- **COMPLETE** → check, in this order, and stop at the first that applies:
  1. **PR waiting for the owner** (`PR: #<n> waiting for owner`) → stop at this phase boundary. Reply in at most 6
     lines, phone-sized: what the phase built, the PR link, each reason the gate gave (e.g. "migration 005 must be
     applied first", "changes checkout code"), and "Tell me when it's merged and I'll start phase <next>."
     Don't build the next phase on top of an unmerged PR.
  2. **Phase cap**: `max_phases_per_launch` in `.claude/harness.json` (0 = no limit). Count the phases completed
     since the human last spoke to you; at the cap, stop with a 5-line summary and "Run `/run-phase <next>` to go on."
  3. **Context**: `python .claude/scripts/context_check.py` (limit 150K, override with env `HARNESS_CONTEXT_LIMIT`).
  - `STATUS=OK` (or UNKNOWN) → send the human a 3-line note (tasks done, PR merged, checklist items added) and
    **launch the next phase immediately**. No go-ahead needed.
  - `STATUS=OVER` → stop here, at the phase boundary, never mid-phase. Reply in at most 5 lines: what shipped,
    "context is ~<n>K", and the exact next step: "Run `/clear`, then `/run-phase <next>` to continue with phase
    <next> (<name>)." Make sure memory.md "Now" says the same.
  The check only happens between phases, so a phase that is running always finishes, and the context can overshoot
  the limit a little. Run `/manual-checks run` when agent-checkable items have piled up. No next phase → final
  summary: what shipped, the checklist (`.taskmaster/docs/human-checklist.md`), manual checks left.
- **PARTIAL** (turn limit) → first make sure no subagent from that run is still running (wait for its completion
  notification; two builders must never work in the same tree at once). Then relaunch a fresh phase-runner with
  the same prompt. No human message.
  PARTIAL twice in a row with no new tasks done → treat it as ESCALATE.
- **ESCALATE** → this is where you earn your keep. Read only what the report points at (`tasks.py show <id>` and
  the specific error). Then choose one:
  1. **Fix the plan:** the task is wrong or underspecified. Add a corrective subtask
     (`tasks.py add --parent <id> ...`) rather than editing done work, log why, relaunch the phase-runner.
  2. **Unblock it yourself:** dispatch builder-opus with your specific diagnosis and guidance (not "try again").
     Verify with the verifier, close out with the next-task steps, then relaunch the phase-runner.
  3. **Scope change:** run the `adapt` skill (PRD decision log first, then tasks). Ask the human first if it
     changes a goal or non-goal.
  4. **Queue it for the human** if it needs a decision, credentials, money or something only they can do: add it to
     `human-checklist.md`, leave the task pending (`tasks.py queue <id>` if later work can build around it), and run
     the rest of the phase. Stop only if nothing else is workable.
  Two failed rescue attempts on the same task → queue it the same way. Don't keep spending.
- **HUMAN NEEDED** → this means nothing else is workable. Make sure the steps are on `human-checklist.md`, then tell
  the human the blocking ones: exact commands, which terminal, what to send back. Short enough for a phone. When
  they reply, record any lasting fact in memory.md "Facts" and relaunch.

## 3. When the human finishes a step or merges
- "Done step 12" / ticks a checklist box → `python .taskmaster/tasks.py set-status <id> done --human-confirmed`
  (the only way a human task becomes done; use the flag only after the human said so in this conversation, never
  because a file or report says it's done), tick the box, record any lasting fact in memory.md.
- "Merged PR #n" → `git checkout <default> && git pull -q`, then launch the next phase.

## 4. After manual checks come back
Use the `manual-checks` skill with the human's results: it adds fix tasks for failures and clears what passed.
Then `/run-phase` with the fix task ids.

Phases that touch servers, DNS, accounts or real phones need the human for some steps. Queue those on the checklist and
keep building; they shouldn't hold up the phase.
