# Architecture

## The hierarchy

```
human ── /run-phase N ──▶ lead (main session, Opus)
                            │ one Agent call per phase, waits for one report
                            ▼
                         phase-runner (Sonnet, medium, maxTurns 300, autoCompact 150k)
                            │ loops: tasks.py next --phase N → next-task procedure
                            ▼
              builder-haiku ─fail─▶ builder-sonnet ─fail─▶ builder-opus ─fail─▶ ESCALATE to lead
                            │ DONE
                            ▼
                         verifier (Haiku, read-only) ──▶ reviewer (Sonnet, read-only) if risky
                            │ PASS
                            ▼
                         close out: log, done, render TASKS.md, commit "task <id>: ..."
```

`CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH=2` allows exactly lead → phase-runner → builders. Builders, the verifier and
the reviewer have `Agent` disallowed.

## Why it's cheap
- **The lead does almost nothing.** Its context grows by one report per phase. It's on Opus because its rare
  decisions (escalations, scope) are the hard ones.
- **Routing by complexity.** Each task has a 1-10 score from planning: 1-3 starts on Haiku, 4-6 on Sonnet, 7+ on
  Opus (split into subtasks first). Most work lands on Haiku and Sonnet.
- **Escalate, don't loop.** A builder that fails the same way twice stops. One rung up costs less than ten retries.
- **Fresh contexts.** Each builder starts clean with just a task id. The phase-runner doesn't read source files,
  only builder reports and `tasks.py` output.
- **Short output everywhere.** Quiet flags, logs to files, tails only. Dev servers run in the background through
  `devserver.py`, so their logs never enter a context.
- **memory.md is updated once per phase**, not per task. It's capped at 80 lines.
- **`/clear` between phases.** All state is in files.

## Where state lives
| File | Holds | Written by |
|---|---|---|
| `.taskmaster/docs/prd.md` | Goal, non-goals, success criteria, decision log | Lead (`adapt`) |
| `.taskmaster/tasks/tasks.json` | Phases, tasks, status, deps, tests, work log | `tasks.py` (everyone) |
| `.claude/rules/memory.md` | Now / facts / decisions / learned / routing / open questions | phase-runner once per run, lead |
| `.taskmaster/docs/manual-checks.md` | Checks waiting (agent-checkable, eyes-on) | phase-runner; cleared by `manual-checks` |
| `.taskmaster/docs/parking-lot.md` | Ideas not in the plan | Anyone, one dated line |
| `TASKS.md` | Readable checklist | `render_tasks_md.py` only |

## The reports
- Builder: `STATUS: DONE | FAILED | BLOCKED`, files, tests, manual check, ideas.
- Verifier: `VERDICT: PASS | FAIL | MANUAL CHECK NEEDED`.
- Reviewer: `REVIEW: APPROVE | CHANGES NEEDED`.
- phase-runner → lead: `PHASE STATUS: COMPLETE | PARTIAL | ESCALATE | HUMAN NEEDED`, ≤ 15 lines.

## When the phase-runner stops
Opus failed, a task needed 2 escalations, a scope/PRD change, a human-only step, something destructive, the same
tier escalated 3 times in a row, or files missing from git at the start. Manual checks never stop it.

## Owned vs seeded files
- **Owned** (replaced by upgrades; keep project specifics out of them): core agents, core skills, `rules.md`,
  `tasks.py`, `render_tasks_md.py`, `.claude/scripts/*`, `prd-template.md`.
- **Seeded** (created once, then the project's): CLAUDE.md, AGENTS.md, memory.md, settings.json,
  dev-servers.json, tasks.json, parking-lot.md, manual-checks.md, and any library or project rules and skills.
