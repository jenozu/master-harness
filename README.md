# master-harness

A reusable Claude Code setup that turns a PRD into a project Claude can build phase by phase, cheaply:

- **Lead** (Opus, your main session) starts each phase and only steps in when something's stuck.
- **phase-runner** (Sonnet) runs a whole phase with no check-ins, then sends one short report.
- **Builders** (Haiku → Sonnet → Opus) take each task at the cheapest model that can do it, and escalate up the
  ladder when they fail. A **verifier** (Haiku) and **reviewer** (Sonnet) check the work.
- A **Taskmaster plan** in git (`.taskmaster/`) holds the phases, tasks, and work log, plus a small
  **memory.md**, so any session on any device picks up where the last one stopped.

## Start a new project

1. Create the project repo and put your PRD in it (`prd.md` at the root is fine).
2. Open Claude Code in that folder: `claude`, then `/model opus`.
3. Paste:
   ```
   Clone https://github.com/jenozu/master-harness into .harness-tmp and follow .harness-tmp/BOOTSTRAP.md using my PRD.
   ```
4. When it reports back: `/clear`, `/model opus`, `/run-phase 0`.

It installs everything, plans the phases from your PRD, checks its own work, makes one commit, and stops. If the
repo is private, your machine's git login is used for the clone. If git asks, sign in once in the browser.

## Day to day

| You type | What happens |
|---|---|
| `/run-phase 2` | The whole phase runs; you get one report (≤ 15 lines) |
| `/clear` | Do this between phases. Everything needed is in the files |
| `/status` | Where things stand, in 6 lines |
| `/manual-checks run` | Agents run the checks they can (dev servers started in the background) |
| `/manual-checks results 10.2 failed: ...` | Failures become fix tasks; passed checks are cleared |
| `/adapt drop the export feature` | PRD decision log → tasks → continue |
| `/plan-from-prd add-phase` | New phase after the PRD grows |

From your phone: `/rc` in the running session, then scan the QR code with the Claude app.

## Let projects deploy to your VPS on their own

One-time setup on your PC: see [`library/vps-kit/README.md`](library/vps-kit/README.md). After that, every
project can create its app on the VPS, deploy with `git push vps main`, and check logs without asking you. A
restricted key and the `vps-agent` gatekeeper on the server limit what agents can do; restores and deletions
stay with you.

## Upgrade an existing project

```
Clone https://github.com/jenozu/master-harness into .harness-tmp and follow .harness-tmp/UPGRADE.md.
```
It covers projects built with an older harness and hand-made setups from before this repo existed.

## What's in here

| Path | What |
|---|---|
| `BOOTSTRAP.md` / `UPGRADE.md` | The prompts Claude follows |
| `template/` | Copied into every project (`.tmpl` files get placeholders filled) |
| `library/` | Optional stack rules, skills and permission sets, picked per project |
| `library/vps-kit/` | One-time VPS setup (`setup_vps.sh`) and the server-side `vps-agent` gatekeeper |
| `scripts/apply_template.py` | Copies and fills the template and merges settings. Never overwrites; `--upgrade` backs up |
| `template/.claude/scripts/check_harness.py` | Checks a project's setup (also lives in each project) |
| `docs/` | Architecture, task schema, placeholders, customizing |
| `tests/` | End-to-end tests (run in CI on Linux and Windows) |

Everything is Python standard library, so there's nothing to install. Run the tests with
`python -m unittest discover -s tests -q`.
