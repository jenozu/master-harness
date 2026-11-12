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
1. `git status --short` is empty. `git fetch -q origin`; if the default branch moved, `git merge -q origin/<default>`
   (mechanical conflicts: fix and commit; anything else is an ESCALATE).
2. `git push -q -u origin HEAD`. Never force-push.
3. PR: `gh pr view --json number,state` first; reuse an open one, else `gh pr create --fill --title "phase <n>: <name>"`.
4. Checks: `gh pr checks <n> --watch --fail-fast > .claude/tmp/ci.log 2>&1; tail -15 .claude/tmp/ci.log`.
   - **No checks configured** → merge; the verifier already ran every testStrategy.
   - **Green** → step 5.
   - **Red** → it's a failed task, not a stop. `gh run view --log-failed | tail -40`, hand the failure to the
     builder ladder (next-task section 5) as a fix, commit, push, wait again. Never merge red. Never use
     `--admin` or skip checks. Same failure twice after real fixes → ESCALATE.
5. Merge: `gh pr merge <n> --squash --delete-branch`. If the repo refuses that method, use the one it allows.
6. Blocked by branch protection or required review: `gh pr merge <n> --auto --squash`. If auto-merge isn't
   available, add `- [ ] Merge PR #<n> (<url>)` to `.taskmaster/docs/human-checklist.md` and **keep going**:
   start the next phase on a new branch cut from this one, and deliver again once the PR merges.
7. Merged → `git checkout <default> && git pull -q`, new branch `phase-<n+1>` (or keep the session's branch name
   convention), `tasks.py log` the PR number on the phase's last task.

Merging is not deploying. Deploys still follow the `vps` / `deploy-vps` rules.
