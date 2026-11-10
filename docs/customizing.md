# Customizing master-harness

## Add a stack to the library
- **Rule:** `library/rules/<stack>.md` with a `paths:` header (globs relative to the repo root) and a comment
  saying to adjust them. Under 2 KB. Only rules a model would otherwise get wrong.
- **Skill:** `library/skills/<name>/SKILL.md`. Use `{{UPPER_CASE}}` for values BOOTSTRAP must fill, and list them
  in `docs/placeholders.md`. Use only fields in `SKILL_FIELDS` (check_harness.py).
- **Permissions:** `library/settings/<tool>.json` with `permissions.allow` / `ask` / `deny` lists. They're merged
  as unions. A fragment can also take rules out with a `"remove"` block (see `vps.json`, `open.json`).
  `open` is merged last whatever order `--settings` lists it in.
- Mention it in BOOTSTRAP.md step 5 if it needs a hint about when to pick it.

## Change routing or models
- Starting tiers: the table in `template/.claude/skills/next-task/SKILL.md`.
- Models and effort: the agents' frontmatter (`model`, `effort`, `maxTurns`).
- Per project, without touching the template: edit the installed copy. Note that upgrades replace owned files,
  so record the reason in memory.md ("Learned") and re-apply after an upgrade, or make the change here and
  release a new version.

## Release a new version
1. Make the change, update tests, and run `python -m unittest discover -s tests -q`.
2. Bump `VERSION` (patch: wording/fixes; minor: new skill/field; major: breaking changes to files projects own).
3. Add a `CHANGELOG.md` entry. Anything projects must do by hand goes under **Project action**.
4. Commit and push. Projects pick it up with UPGRADE.md.

## Field lists
When Claude Code adds or renames agent/skill frontmatter fields, update `AGENT_FIELDS` and `SKILL_FIELDS` in
`template/.claude/scripts/check_harness.py` (source: code.claude.com/docs/en/sub-agents.md and skills.md).
