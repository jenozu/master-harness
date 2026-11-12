# Rules (always loaded, for the main session and every subagent)

<!-- Harness-owned file: UPGRADE.md may replace it. Put project-specific rules in other files in this folder. -->

## Scope and drift
- The plan is `.taskmaster/`. Work only on the task you were given, or the one `tasks.py next` returns.
- PRD non-goals (`.taskmaster/docs/prd.md`) are off limits, even if they'd be easy.
- No new dependency unless the task or PRD names it. Otherwise report it as an idea.
- Ideas → one dated line in `.taskmaster/docs/parking-lot.md`. Never build them on the side.
- Changing what's being built → the `adapt` skill: PRD decision log first, then tasks, then code.
- Stop and say so if you're editing files the task didn't mention, rewriting finished work, or the task has
  doubled in size.

## Safety
- Never commit secrets. `.env` files are gitignored; config comes from environment variables, with no real
  defaults for secrets. Agents can't read `.env`; pass values through the environment.
- No destructive commands outside local dev/test data: no dropping or truncating real data, `rm -rf` outside the
  repo, `git push --force`, `git reset --hard` on shared branches.
- Never ssh to a server or deploy unless the human asked for it, or it's a planned deploy task done through the
  `vps` skill (`ssh vps ...`, `git push vps main`): that key is limited on the server to safe operations.
- Never spend money or create accounts.

## Code
- Small, direct changes that match the surrounding style. No speculative abstractions, no drive-by refactors.
- Raw SQL only with bound parameters; never build queries or shell commands from user input by string formatting.
- Every task ends with its testStrategy actually run. "Looks right" is not done.

## Keep command output short (it costs tokens; running the command doesn't)
- Quiet flags: `pytest -q`, `pip install -q`, `npm ... --loglevel=error --no-audit --no-fund`, `git ... -q`.
- Anything that can print more than ~30 lines: send it to a log and read the end, e.g.
  `<cmd> > .claude/tmp/out.log 2>&1; tail -20 .claude/tmp/out.log`. On failure,
  `grep -n -i "error\|failed" .claude/tmp/out.log | head -20` before reading more.
- Never `cat` a large file or dump a whole table: `head`, `grep -n`, `sed -n 'X,Yp'`, `LIMIT 10`.
- Dev servers only through `python .claude/scripts/devserver.py` (the `dev-servers` skill), never in the foreground.
- Very long jobs (big downloads, data imports, hours-long builds): ask the human to run them in their own
  terminal and send back just the summary lines.

## Git and delivery
- Work on a branch, never directly on the default branch. Commit per task with the id: `task 7.2: <short title>`.
  Nothing a task created may stay untracked.
- Never commit generated junk (virtualenvs, node_modules, build output, caches, `.claude/tmp/`).
- Push after every task commit. At the end of each phase, and before any stop, use the `deliver` skill: open a PR,
  and **merge it automatically once checks pass**. Don't ask the human to merge or approve. Never merge red, never
  force-push, never bypass checks.

## Keep going, don't wait for approval
- "Phase done, PR merged, shall I continue?" is never the right ending. Start the next phase right away.
- If a human step exists but work can continue without it, **queue it and continue**: append it to
  `.taskmaster/docs/human-checklist.md` as `- [ ] **Task <id>: <title>**: exact steps, where to run them, what to
  send back`, build against placeholders/mocks/env vars, and log it on the task.
- Stop only when the human is truly critical right now: nothing workable is left, the next step needs credentials
  or an account that every remaining task depends on, money, a destructive action, or a goal/non-goal change.

## When stuck
- Same error twice after a real fix attempt → stop and report; a stronger model is cheaper than a loop.
- Needs a credential, account, server, money or a decision → report it as a human step with exact instructions.
