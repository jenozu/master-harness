---
name: security-review
description: Focused security pass over the whole app before shipping or after auth, permission or data-handling changes. Produces findings as fix tasks. Use when the human asks for a security review, before the first deploy, or when a phase touched auth.
disable-model-invocation: true
---

# Security review

Dispatch the **reviewer** agent per area below (one area per dispatch, to keep each context small). For each,
it reads the relevant code and reports findings with file:line, a concrete exploit or failure, and the fix.

1. **Secrets:** `git grep -n -I -E "(api[_-]?key|secret|password|token)\s*[:=]" -- ':!*.lock'`; committed `.env`
   files (`git ls-files | grep -i env`); secrets in logs or error messages.
2. **Auth:** every route or handler that reads or writes user data checks the user and filters by owner; tokens
   expire; password hashing uses a slow hash; registration can be closed.
3. **Input:** SQL/shell/HTML injection, path traversal in file handling, unvalidated redirects, file upload limits.
4. **Web:** CORS allowlist (no `*` with credentials), cookies `HttpOnly`/`Secure`/`SameSite`, security headers at
   the proxy, HTTPS only.
5. **Server:** firewall (only 22/80/443), ssh keys only, the app runs as a non-root user, automatic security
   updates, backups exist and a restore was tested.
6. **Dependencies:** `npm audit --omit=dev` / `pip-audit` if available; note high/critical only.

Each finding → `python .taskmaster/tasks.py add --title "Security: <issue>" --review --complexity <n>
--details "<file:line, exploit, fix>" --test "<how to prove it's fixed>"`. Report counts by severity in 5 lines.
