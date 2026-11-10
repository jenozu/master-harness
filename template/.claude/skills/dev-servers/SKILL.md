---
name: dev-servers
description: Start, check and stop the project's dev servers in the background with logs written to files, so agents can test against a running app without flooding their context or needing the human's terminals. Use when a test, a verifier check or a manual check needs the app running.
argument-hint: "start|stop|status|logs [name|all]"
---

# Dev servers

Servers are defined in `.claude/dev-servers.json`:
```json
[{"name": "api", "cwd": "backend", "cmd": "venv/bin/python -m uvicorn main:app --port 8000",
  "cmd_windows": "venv\\Scripts\\python.exe -m uvicorn main:app --port 8000",
  "health": "http://localhost:8000/health"}]
```
`cmd_windows` is optional; it's used instead of `cmd` on Windows (where commands run in cmd.exe, not Git Bash).

Commands (Python stdlib only, works on Windows, macOS, Linux):
```
python .claude/scripts/devserver.py start [name|all]   # background start, waits until health answers (max 60 s)
python .claude/scripts/devserver.py status             # up/down, pid, who started it
python .claude/scripts/devserver.py logs <name> -n 30  # tail of .claude/tmp/logs/<name>.log
python .claude/scripts/devserver.py stop [name|all]    # stops only servers devserver.py started
```

Rules:
- Never run a dev server in the foreground (`npm run dev`, `uvicorn ...` without devserver.py): it never returns
  and its output fills your context.
- `start` refuses when the health URL already answers but devserver.py didn't start it (the human or another
  agent is running one). Use that server as-is, or report it. Never kill a process you didn't start.
- On a failed start, read `logs <name> -n 40`, not the whole log.
- Stop what you started when you're done, unless the human asked you to leave it running.
- No servers defined yet and the task needs one: add an entry to `.claude/dev-servers.json` (same task, listed
  in FILES CHANGED) rather than improvising a command.
