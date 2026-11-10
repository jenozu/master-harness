---
name: deploy-vps
description: Push and deploy to the project's own VPS (nginx + systemd style), then check it's healthy. Only when the human explicitly asks to deploy.
disable-model-invocation: true
argument-hint: "[ssh-target, e.g. me@app.example.com]"
---

# Deploy to the VPS

<!-- Library skill. BOOTSTRAP fills in the {{...}} values below. -->

App path: `{{DEPLOY_APP_PATH}}` · service: `{{DEPLOY_SERVICE}}` · deploy script: `{{DEPLOY_SCRIPT}}` · health: `{{HEALTH_URL}}`

SSH target: `$ARGUMENTS`. If empty, read `.claude/deploy-target` (one line, gitignored). If neither exists, ask the
human once and offer to save it there.

1. **Pre-flight** (stop on any failure and report it):
   - `git status --short` is clean and the branch is the deploy branch.
   - Tests pass and the production build succeeds (commands in CLAUDE.md).
   - `python .taskmaster/tasks.py validate`.
2. Show `git log --oneline origin/<branch>..<branch>` (what will ship) and get a yes.
3. `git push origin <branch>`.
4. `ssh <target> "sudo bash {{DEPLOY_APP_PATH}}/{{DEPLOY_SCRIPT}}"`. On failure:
   `ssh <target> "sudo journalctl -u {{DEPLOY_SERVICE}} -n 60 --no-pager"`, report the error, and propose the fix as a new
   task. Don't hot-fix on the server.
5. Smoke test: `curl -fsS {{HEALTH_URL}}` and
   `curl -fsS -o /dev/null -w "%{http_code} %{time_total}s\n" {{SITE_URL}}`.
6. Log it on the current task: `python .taskmaster/tasks.py log <id> "deployed <sha>"`.
Destructive migration in this release → take a database backup on the server before step 4.
