# tasks.json schema

Paths and fields follow Task Master conventions (`.taskmaster/tasks/tasks.json`, tag `master`) so the real
Task Master tool could adopt a project later. Extra fields: `phase`, `human`, `review`, `queued`, `runner`, `check`, `metadata.phases`.

```json
{
  "master": {
    "tasks": [
      {
        "id": 4,
        "title": "Phone UI for habits",
        "description": "List, tick, streak badges at 390px.",
        "status": "pending",
        "priority": "medium",
        "phase": 2,
        "complexity": 5,
        "dependencies": [3],
        "human": false,
        "review": false,
        "details": "Files, approach, gotchas. tasks.py log appends timestamped entries here.",
        "testStrategy": "cd frontend && npm run build",
        "subtasks": [
          {"id": 1, "title": "...", "status": "pending", "complexity": 3, "dependencies": [],
           "details": "...", "testStrategy": "..."}
        ]
      }
    ],
    "metadata": {
      "project": "Habit Dots",
      "description": "...",
      "phases": [{"id": 0, "name": "Foundation"}, {"id": 1, "name": "Habits API"}],
      "created": "2026-11-09", "updated": "2026-11-09T20:00:00-05:00"
    }
  }
}
```

## Fields
| Field | Rules |
|---|---|
| `id` | Integer (a whole number, never `"1"`), unique. Subtasks are numbered within their parent and referenced as `4.2`. |
| `status` | `pending`, `in-progress`, `review`, `done`, `deferred`, `cancelled`. Never delete a task: cancel it. |
| `priority` | `high`, `medium`, `low` (top-level only). Breaks ties in `next`. |
| `phase` | Top-level only, must exist in `metadata.phases`. A task may not depend on a task in a later phase. |
| `complexity` | 1-10. Starting model: 1-3 haiku, 4-6 sonnet, 7+ opus (split first). Subtasks default to parent − 2. |
| `dependencies` | Top-level: lower task ids (`3`, or `"2.1"` for a subtask). In a subtask: a bare number is a sibling. |
| `human` | `true` = only the human can do it. Routed as HUMAN NEEDED, never to a builder. |
| `queued` | Human tasks only, set by `tasks.py queue <id>`: the step is on the human checklist and tasks that depend on it may be built against placeholders. It stays open; only the human's confirmation closes it (`set-status <id> done --human-confirmed`, run by the lead after they say so). While any are queued and merging deploys, the merge gate holds the PR. |
| `review` | `true` = the reviewer must approve after the verifier passes. |
| `runner` | `"agent"` (default when missing) or `"script"`. Script tasks are run by `run_checks.py` with no model: free. |
| `check` | Script tasks: the commands to run, each an argument list (`["ruff", "check", "."]`) or `{"cmd": [...], "cwd": "frontend", "expect": 0, "timeout": 600}`. No shell strings, `cd`, `&&`, pipes, shells or `python -c`. The first words must match an entry in `.taskmaster/checks.json` `allow`. |
| `verify` | Optional, agent tasks: commands that prove the built task works, same format as `check`. `run_checks.py verify <id>` runs them with no model when every uncommitted change is docs, tests or the plan (`safe_paths` in the committed harness.json); otherwise the verifier agent checks it. |
| `details` | What to build and how. The work log is appended here by `tasks.py log`. |
| `testStrategy` | Required for open tasks. Must name something runnable. |

`metadata.goal` and `metadata.non_goals` (set with `tasks.py meta`): the PRD's goal and non-goals, printed at the
top of `show` and `next --details`, so agents don't open the PRD for them. `validate` warns while the goal is empty.

## Rules `validate` enforces
No duplicate ids, unknown statuses, missing or later-numbered dependencies, cycles, done parents with open
subtasks, tasks without a phase (once phases exist), or dependencies on later phases. It also rejects an unknown `runner`, a script task without `check`, and check or verify commands that are strings or use
shell operators, a shell, inline code, or a cwd outside the repo. It warns about a missing
testStrategy, complexity 7+ without subtasks, blocked-by-cancelled tasks, and more than one task in progress.

## Commands
`status`, `phase [n]`, `list [--status s] [--subtasks]`, `next [--phase n] [--details]`, `show <id>`,
`set-status <id> <status> [--force] [--human-confirmed]`, `log <id> 'text'` (or `log <id> -` to read the note from stdin), `add --title ... [--parent id] [--phase n]
[--complexity n] [--deps 1,2] [--test ...] [--details ...] [--human] [--review] [--runner script --check "ruff check ."]`,
`queue <id>`, `close <id> --tier <t> [--escalated-from t] [--files a,b] [--trailer line]` (after verification: log,
done, render TASKS.md, stage, commit, push; exit 3 if changes aren't in `--files`; refuses human tasks and the
default branch), `meta [--goal ...] [--non-goal ...]`, `validate`, `init [--project name]`.

## Free checks: `run_checks.py`
`python .taskmaster/run_checks.py plan [--phase n]` lists open script tasks in dependency order (runs nothing;
exits 1 if a command would be refused). `run [--phase n] [--only id | --from id]` runs them: commands without a
shell, each with a timeout, retried only when it times out (`retries_on_timeout`), never when it fails. A task
is marked done only when every command exits with its expected code. The first failure stops the run, leaves the
status alone, and prints the command with the last 20 lines of output; start/end time, exit code, stdout sha256
and both tails go to `.claude/tmp/checks/<id>.log`. Exit 0 = passed, 1 = a check failed (send a builder),
2 = refused or not runnable (fix the plan or the allowlist).
