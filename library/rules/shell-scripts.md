---
paths:
  - "scripts/**"
  - "**/*.sh"
---

# Script rules

<!-- Library rule. -->

- Bash: `#!/usr/bin/env bash` + `set -euo pipefail`, quote every variable, idempotent (safe to run twice), print
  what each step does, fail with a clear message. `shellcheck -S warning` clean if shellcheck is installed.
- Header comment: what it does, how to run it, what it needs. Keep it accurate.
- Scripts that run on a server (as root) get the reviewer, every change.
- Never put secrets in scripts; generate them on the server (`openssl rand -hex 32`) into a mode-600 env file.
- Local scripts must work in Git Bash on Windows (handle `venv/Scripts` vs `venv/bin`, CRLF, no `sudo`).
