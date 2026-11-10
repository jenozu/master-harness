# tasks.json schema

Paths and fields follow Task Master conventions (`.taskmaster/tasks/tasks.json`, tag `master`) so the real
Task Master tool could adopt a project later. Extra fields: `phase`, `human`, `review`, `metadata.phases`.

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
| `id` | Integer, unique. Subtasks are numbered within their parent and referenced as `4.2`. |
| `status` | `pending`, `in-progress`, `review`, `done`, `deferred`, `cancelled`. Never delete a task: cancel it. |
| `priority` | `high`, `medium`, `low` (top-level only). Breaks ties in `next`. |
| `phase` | Top-level only, must exist in `metadata.phases`. A task may not depend on a task in a later phase. |
| `complexity` | 1-10. Starting model: 1-3 haiku, 4-6 sonnet, 7+ opus (split first). Subtasks default to parent − 2. |
| `dependencies` | Top-level: lower task ids (`3`, or `"2.1"` for a subtask). In a subtask: a bare number is a sibling. |
| `human` | `true` = only the human can do it. Routed as HUMAN NEEDED, never to a builder. |
| `review` | `true` = the reviewer must approve after the verifier passes. |
| `details` | What to build and how. The work log is appended here by `tasks.py log`. |
| `testStrategy` | Required for open tasks. Must name something runnable. |

## Rules `validate` enforces
No duplicate ids, unknown statuses, missing or later-numbered dependencies, cycles, done parents with open
subtasks, tasks without a phase (once phases exist), or dependencies on later phases. It warns about a missing
testStrategy, complexity 7+ without subtasks, blocked-by-cancelled tasks, and more than one task in progress.

## Commands
`status`, `phase [n]`, `list [--status s] [--subtasks]`, `next [--phase n]`, `show <id>`,
`set-status <id> <status> [--force]`, `log <id> "text"`, `add --title ... [--parent id] [--phase n]
[--complexity n] [--deps 1,2] [--test ...] [--details ...] [--human] [--review]`, `validate`, `init [--project name]`.
