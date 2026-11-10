---
name: status
description: Quick, cheap "where are we?" - current phase, what's done, what's next, what's waiting on the human. Use when the human asks "where are we", "what's the status", "what's left", or starts a new session.
---

# Status (keep it cheap)

Run, and read nothing else:
1. `python .taskmaster/tasks.py status`
2. `python .taskmaster/tasks.py phase`
3. `grep -c '^### ' .taskmaster/docs/manual-checks.md` (manual checks waiting)
4. `git status --short | head -5` and `git log --oneline -3`

Reply in at most 6 lines:
- Phase <n> <name>: <closed>/<total>. Overall <pct>%.
- Next: <task id and title> (or "phase complete: run `/clear` then `/run-phase <n+1>`").
- Waiting on you: <human-only tasks, manual checks count, open questions from memory.md>, or "nothing".
- Uncommitted changes or unpushed commits, if any.
Don't open task logs, the PRD or source files.
