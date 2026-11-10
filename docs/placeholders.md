# Placeholders

`apply_template.py --values values.json` fills `{{NAME}}` in `.tmpl` files and library files. A value that's a
JSON list becomes a markdown bullet list. `check_harness.py` fails while any `{{NAME}}` is left.

| Key | Used in | What to write |
|---|---|---|
| `PROJECT_NAME` | CLAUDE.md, AGENTS.md, memory.md, tasks.json | Short name |
| `PROJECT_SUMMARY` | AGENTS.md | One line: what it is and for whom |
| `STACK` | AGENTS.md | One line: languages, frameworks, database, where each lives |
| `CMD_INSTALL` | AGENTS.md | Exact install command(s) that work in this repo |
| `CMD_TEST` | AGENTS.md | Exact test command (quiet flags; test DB env vars if needed) |
| `CMD_LINT` | AGENTS.md | Lint command, or `n/a` |
| `CMD_BUILD` | AGENTS.md | Production build command, or `n/a` |
| `PHASES` | CLAUDE.md | One line, e.g. `0 Foundation · 1 Core loop · 2 Ship` (fill after planning) |
| `RISKY_PATHS` | CLAUDE.md | List: paths whose changes need the reviewer (auth, migrations, server scripts) |
| `PROJECT_FACTS` | AGENTS.md | List: facts a model would get wrong (data rules, hosting, hidden features) |
| `PROJECT_SKILLS` | CLAUDE.md | One line listing the library/project skills installed, or `none` |
| `MEMORY_FACTS` | memory.md | List: stable facts (dev OS, local DB, hosting, users) |
| `OPEN_QUESTIONS` | memory.md | List: questions for the human (TBDs from the PRD) |
| `dev_servers` | dev-servers.json | List of `{name, cwd, cmd, cmd_windows?, health}`; `[]` if none yet |
| `DATE` | memory.md, tasks.json | Automatic (today), override if needed |
| `HARNESS_VERSION` | CLAUDE.md, memory.md | Automatic, from `VERSION` |

Library skill `deploy-vps` also uses: `DEPLOY_APP_PATH`, `DEPLOY_SERVICE`, `DEPLOY_SCRIPT`, `HEALTH_URL`, `SITE_URL`.

Example: `tests/fixtures/sample/values.json`.
