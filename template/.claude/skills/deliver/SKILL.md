---
name: deliver
description: Push the work branch, open a pull request, and hand it to the merge gate script, which waits for CI and merges only when .claude/harness.json allows it (auto, safe-only or owner; stricter when merging deploys). Used by the phase-runner at the end of each phase and before it stops.
---

# Deliver: push, PR, merge gate

Goal: finished work reaches the default branch safely. **Whether it merges is decided by
`.claude/scripts/merge_gate.py`, never by you.** Needs `gh` (GitHub CLI) logged in. No `gh`, no remote, or not a
GitHub repo → skip this skill, say so once in the report, and keep going.

## When
- End of every phase (title `phase <n>: <name>`, body: task ids and one line each, plus any checklist items added).
- Before returning PARTIAL, ESCALATE or HUMAN NEEDED, so finished work is at least in a PR.
- After each task commit only `git push -q -u origin HEAD` (a backup; no PR yet).

## Steps
Claude Code sessions block GitHub's GraphQL API, so `gh pr create/merge/view/checks` fail with HTTP 403. Use
`gh api` (REST); `{o}/{r}` is `owner/repo` from `git remote get-url origin`.
1. `git status --short` is empty. `git fetch -q origin`; if the default branch moved, `git merge -q origin/<default>`
   (mechanical conflicts in `.taskmaster/` or TASKS.md: fix and commit; conflicts in app code go to a builder;
   anything unclear is an ESCALATE).
2. `git push -q -u origin HEAD`. Never force-push.
3. PR: `gh api "repos/{o}/{r}/pulls?head={o}:<branch>&state=open" --jq '.[0].number'`; reuse it, else
   `gh api repos/{o}/{r}/pulls -f title="phase <n>: <name>" -f head=<branch> -f base=<default> -f body="<task ids>" --jq .number`.
4. `python .claude/scripts/merge_gate.py --pr <n> --wait --merge`. It waits for CI (check runs **and** commit
   statuses), decides, and merges only if allowed. Act on its first line:
   - `DECISION=MERGED` → `git checkout <default> && git pull -q`, new branch `phase-<n+1>` (or the session's
     branch naming), `tasks.py log` the PR number on the phase's last task.
   - `DECISION=AUTO_MERGE_SET` → GitHub merges it when its branch rules are met. Continue on a new branch cut from
     this one; deliver again later.
   - `DECISION=FIX_CI` → a failed task, not a stop. Read the failing log with the commands it printed (tail only),
     hand it to the builder ladder (next-task section 5) as a fix, commit, push, run the gate again. Same failure
     twice after real fixes → ESCALATE.
   - `DECISION=OWNER` → the owner must merge, or finish a human step or eyes-on check first. Add
     `- [ ] Merge PR #<n> (<url>): <each REASON line>` to `.taskmaster/docs/human-checklist.md`, commit, push,
     and report `PR: #<n> waiting for owner` with the reasons. The lead stops at this phase boundary.
   - `DECISION=CI_TIMEOUT` → CI is slow or stuck. Put `- [ ] Merge PR #<n> once CI finishes` on the checklist and
     report it like OWNER.
   - `DECISION=ERROR` → report the message as an ISSUE; nothing was merged.

Never merge any other way, and never edit `.claude/harness.json` to get a merge through: changing it is the
owner's call. If merging deploys (`merge_deploys: true`), a merge is a release: the gate already holds it while
human steps are queued or eyes-on checks are open.
