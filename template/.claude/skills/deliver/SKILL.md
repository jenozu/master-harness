---
name: deliver
description: Push the work branch, open a pull request, wait for CI, and merge it automatically when checks pass, then carry on from the updated default branch. Used by the phase-runner at the end of each phase and before it stops. Never waits for the human unless a merge is truly impossible.
---

# Deliver: push, PR, merge, continue

Goal: finished work lands on the default branch without the human clicking anything. Needs `gh` (GitHub CLI)
logged in. No `gh`, no remote, or not a GitHub repo → skip this skill, say so once in the report, and keep going.

## When
- End of every phase (title `phase <n>: <name>`, body: task ids and one line each, plus any checklist items added).
- Before returning PARTIAL, ESCALATE or HUMAN NEEDED, so nothing finished stays unmerged.
- After each task commit only `git push -q -u origin HEAD` (a backup; no PR yet).

## Steps
Claude Code sessions block GitHub's GraphQL API, so `gh pr create`, `gh pr merge`, `gh pr view` and `gh pr checks`
fail with HTTP 403. Use `gh api` (REST) for everything; `{o}/{r}` is `owner/repo` from `git remote get-url origin`.
1. `git status --short` is empty. `git fetch -q origin`; if the default branch moved, `git merge -q origin/<default>`
   (mechanical conflicts: fix and commit; anything else is an ESCALATE).
2. `git push -q -u origin HEAD`. Never force-push.
3. PR: `gh api "repos/{o}/{r}/pulls?head={o}:<branch>&state=open" --jq '.[0].number'`; reuse it, else
   `gh api repos/{o}/{r}/pulls -f title="phase <n>: <name>" -f head=<branch> -f base=<default> -f body="<task ids>" --jq .number`.
4. Checks, polled every 20-30s (cap ~15 min) on the pushed commit `sha=$(git rev-parse HEAD)`:
   `gh api repos/{o}/{r}/commits/$sha/check-runs --jq '[.check_runs[]|{name,status,conclusion}]'`.
   - **No check runs and the workflows folder is empty** → merge; the verifier already ran every testStrategy.
   - **All completed with success/neutral/skipped** → step 5.
   - **Any failure** → it's a failed task, not a stop. Read the failing job's log tail
     (`gh api repos/{o}/{r}/actions/jobs/<id>/logs | tail -40`), hand it to the builder ladder (next-task section 5)
     as a fix, commit, push, poll again. Never merge red, never bypass checks. Same failure twice after real
     fixes → ESCALATE.
5. Merge: `gh api -X PUT repos/{o}/{r}/pulls/<n>/merge -f merge_method=squash`. If the repo rejects squash, use
   the method it allows (`merge`, `rebase`). Then delete the branch:
   `gh api -X DELETE repos/{o}/{r}/git/refs/heads/<branch>`.
6. Blocked by branch protection or required review (HTTP 405): `gh api -X PUT repos/{o}/{r}/pulls/<n>/ccr/auto_merge`
   turns on auto-merge. If that isn't available either, add `- [ ] Merge PR #<n> (<url>)` to
   `.taskmaster/docs/human-checklist.md` and **keep going**: start the next phase on a new branch cut from this
   one, and deliver again once the PR merges.
7. Merged → `git checkout <default> && git pull -q`, new branch `phase-<n+1>` (or the session's branch naming),
   `tasks.py log` the PR number on the phase's last task.

Merging is not deploying. Deploys still follow the `vps` / `deploy-vps` rules.
