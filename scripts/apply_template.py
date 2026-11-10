#!/usr/bin/env python3
"""Copy the master-harness template into a project, fill placeholders, merge settings (Python stdlib only).

Bootstrap (new project; never overwrites existing files):
  python scripts/apply_template.py --target <repo> --values values.json \
      [--rules python-fastapi,react-vite-tailwind] [--skills db-migration,mobile-ui-check] [--settings python,node]

Upgrade (existing project; replaces harness-owned files, backs up the old ones, never touches project content):
  python scripts/apply_template.py --target <repo> --upgrade [--values values.json]
  Library pieces can be added during an upgrade too (created only if missing): --skills vps --settings vps

values.json: {"PROJECT_NAME": "...", ..., "dev_servers": [ {...} ]}. See docs/placeholders.md.
--dry-run prints what would happen without writing anything.
"""
import argparse
import datetime
import json
import re
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
TEMPLATE = HERE / "template"
LIBRARY = HERE / "library"
VERSION = (HERE / "VERSION").read_text(encoding="utf-8").strip()
PLACEHOLDER = re.compile(r"\{\{([A-Z0-9_]+)\}\}")

# Project-owned once created: filled at bootstrap, never replaced by an upgrade.
SEEDED = {
    "CLAUDE.md", "AGENTS.md",
    ".claude/rules/memory.md", ".claude/settings.json", ".claude/dev-servers.json",
    ".taskmaster/tasks/tasks.json", ".taskmaster/docs/parking-lot.md", ".taskmaster/docs/manual-checks.md",
}
GITIGNORE_LINES = [
    ".env", ".env.*", "!.env.example",
    ".claude/settings.local.json", ".claude/deploy-target",
    ".harness-backup/", ".harness-tmp/",
]


def dest_name(rel):
    return rel[:-5] if rel.endswith(".tmpl") else rel


def fill(text, values):
    return PLACEHOLDER.sub(lambda m: str(values[m.group(1)]) if m.group(1) in values else m.group(0), text)


def unfilled(text):
    return sorted(set(PLACEHOLDER.findall(text)))


def union(a, b):
    out = list(a)
    for x in b:
        if x not in out:
            out.append(x)
    return out


def merge_settings(base, extra):
    """Union permission lists and env; a fragment's "remove" lists take rules out (e.g. an ask rule that would
    override the fragment's allow rules, since ask beats allow)."""
    out = json.loads(json.dumps(base))
    for k, v in extra.items():
        if k == "remove":
            perms = out.setdefault("permissions", {})
            for kind, rules in v.items():
                perms[kind] = [r for r in perms.get(kind, []) if r not in rules]
        elif k == "permissions":
            perms = out.setdefault("permissions", {})
            for kind, rules in v.items():
                perms[kind] = union(perms.get(kind, []), rules)
        elif k == "env":
            env = out.setdefault("env", {})
            for ek, ev in v.items():
                env.setdefault(ek, ev)
        elif k not in out:
            out[k] = v
    return out


class Plan:
    def __init__(self, target, dry):
        self.target, self.dry = target, dry
        self.created, self.kept, self.replaced, self.same, self.notes = [], [], [], [], []
        self.missing = {}

    def write(self, rel, text):
        p = self.target / rel
        if not self.dry:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(text, encoding="utf-8", newline="\n")
        left = unfilled(text)
        if left:
            self.missing[rel] = left

    def report(self):
        for label, items in (("created", self.created), ("replaced (old copy in .harness-backup/)", self.replaced),
                             ("kept existing (merge by hand if needed)", self.kept), ("unchanged", self.same)):
            if items:
                print(f"{label}: {len(items)}")
                for i in items:
                    print(f"  {i}")
        for n in self.notes:
            print(f"note: {n}")
        if self.missing:
            print("UNFILLED PLACEHOLDERS (fill these in before running check_harness.py):")
            for rel, names in sorted(self.missing.items()):
                print(f"  {rel}: {', '.join(names)}")
        if self.dry:
            print("(dry run: nothing written)")


def load_values(path):
    values = {}
    if path:
        values = json.loads(Path(path).read_text(encoding="utf-8"))
    servers = values.pop("dev_servers", None)
    values.setdefault("DEV_SERVERS_JSON", json.dumps(servers if servers is not None else [], indent=2))
    values.setdefault("DATE", datetime.date.today().isoformat())
    values["HARNESS_VERSION"] = VERSION
    for k, v in list(values.items()):
        if isinstance(v, list):
            values[k] = "\n".join(f"- {x}" for x in v) if v else "- (none yet)"
    return values


def template_files():
    for p in sorted(TEMPLATE.rglob("*")):
        if p.is_file() and "__pycache__" not in p.parts:
            yield p.relative_to(TEMPLATE).as_posix(), p


def library_files(kind, names):
    out = []
    for name in names:
        if kind == "rules":
            src = LIBRARY / "rules" / f"{name}.md"
            if not src.exists():
                sys.exit(f"error: no library rule '{name}' (have: {', '.join(p.stem for p in (LIBRARY / 'rules').glob('*.md'))})")
            out.append((f".claude/rules/{name}.md", src))
        else:
            src = LIBRARY / "skills" / name
            if not src.is_dir():
                sys.exit(f"error: no library skill '{name}' (have: {', '.join(p.name for p in (LIBRARY / 'skills').iterdir())})")
            for f in sorted(src.rglob("*")):
                if f.is_file():
                    out.append((f".claude/skills/{name}/{f.relative_to(src).as_posix()}", f))
    return out


def settings_with_fragments(names, base=None):
    settings = base if base is not None else json.loads((TEMPLATE / ".claude/settings.json").read_text(encoding="utf-8"))
    # "open" removes ask rules the other fragments add, so it must be merged last whatever order was given.
    names = [n for n in names if n != "open"] + (["open"] if "open" in names else [])
    for name in names:
        frag = LIBRARY / "settings" / f"{name}.json"
        if not frag.exists():
            sys.exit(f"error: no settings fragment '{name}'")
        settings = merge_settings(settings, json.loads(frag.read_text(encoding="utf-8")))
    return settings


def ensure_gitignore(plan):
    gi = plan.target / ".gitignore"
    have = gi.read_text(encoding="utf-8").splitlines() if gi.exists() else []
    add = [l for l in GITIGNORE_LINES if l not in have]
    if add:
        text = "\n".join(have).rstrip("\n")
        text = (text + "\n\n" if text else "") + "# master-harness\n" + "\n".join(add) + "\n"
        if not plan.dry:
            gi.write_text(text, encoding="utf-8", newline="\n")
        plan.notes.append(f".gitignore: added {', '.join(add)}")


def bootstrap(a, plan, values):
    settings = settings_with_fragments(split(a.settings))
    files = list(template_files()) + library_files("rules", split(a.rules)) + library_files("skills", split(a.skills))
    for rel, src in files:
        dst = dest_name(rel)
        if dst == ".claude/settings.json":
            existing = plan.target / dst
            if existing.exists():
                merged = settings_with_fragments(split(a.settings), merge_settings(
                    json.loads(existing.read_text(encoding="utf-8")), settings))
                plan.write(dst, json.dumps(merged, indent=2) + "\n")
                plan.notes.append("settings.json existed: merged harness permissions and env into it")
            else:
                plan.write(dst, json.dumps(settings, indent=2) + "\n")
                plan.created.append(dst)
            continue
        if (plan.target / dst).exists():
            plan.kept.append(dst)
            text = (plan.target / dst).read_text(encoding="utf-8", errors="replace")
            if unfilled(text):
                plan.missing[dst] = unfilled(text)
            continue
        plan.write(dst, fill(src.read_text(encoding="utf-8"), values))
        plan.created.append(dst)
    ensure_gitignore(plan)
    if not plan.dry:
        (plan.target / ".claude").mkdir(exist_ok=True)
        (plan.target / ".claude/HARNESS_VERSION").write_text(VERSION + "\n", encoding="utf-8")


def upgrade(a, plan, values):
    vfile = plan.target / ".claude/HARNESS_VERSION"
    old = vfile.read_text(encoding="utf-8").strip() if vfile.exists() else "unknown"
    plan.notes.append(f"harness {old} -> {VERSION}")
    backup = plan.target / ".harness-backup" / old
    for rel, src in template_files():
        dst = dest_name(rel)
        target = plan.target / dst
        if dst in SEEDED:
            if not target.exists():
                if dst == ".claude/settings.json":
                    plan.write(dst, json.dumps(settings_with_fragments([]), indent=2) + "\n")
                else:
                    plan.write(dst, fill(src.read_text(encoding="utf-8"), values))
                plan.created.append(dst)
            elif dst == ".claude/settings.json":
                cur = json.loads(target.read_text(encoding="utf-8"))
                names = split(a.settings)
                if "Bash" in cur.get("permissions", {}).get("allow", []) and "open" not in names:
                    names.append("open")  # project already runs open: keep upgrades from re-adding the ask rules
                merged = settings_with_fragments(names, merge_settings(cur, settings_with_fragments([])))
                if merged != cur:
                    plan.write(dst, json.dumps(merged, indent=2) + "\n")
                    plan.notes.append("settings.json: added new harness permissions/env (nothing removed)")
            continue
        new = fill(src.read_text(encoding="utf-8"), values)
        if not target.exists():
            plan.write(dst, new)
            plan.created.append(dst)
            continue
        cur = target.read_text(encoding="utf-8", errors="replace")
        if cur.replace("\r\n", "\n") == new:
            plan.same.append(dst)
            continue
        if not plan.dry:
            (backup / dst).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, backup / dst)
        plan.write(dst, new)
        plan.replaced.append(dst)
    for rel, src in library_files("rules", split(a.rules)) + library_files("skills", split(a.skills)):
        if (plan.target / rel).exists():
            plan.kept.append(rel)
        else:
            plan.write(rel, fill(src.read_text(encoding="utf-8"), values))
            plan.created.append(rel)
    ensure_gitignore(plan)
    if not plan.dry:
        vfile.parent.mkdir(exist_ok=True)
        vfile.write_text(VERSION + "\n", encoding="utf-8")
    if plan.replaced:
        plan.notes.append(f"old versions saved in .harness-backup/{old}/: re-apply any project-specific edits, then delete it")


def split(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", required=True, help="the project repo root")
    p.add_argument("--values", help="JSON file with placeholder values")
    p.add_argument("--rules", help="library rules to add, comma-separated")
    p.add_argument("--skills", help="library skills to add, comma-separated")
    p.add_argument("--settings", help="library settings fragments to merge, comma-separated")
    p.add_argument("--upgrade", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    target = Path(a.target).resolve()
    if not target.is_dir():
        sys.exit(f"error: {target} is not a directory")
    if target == HERE or HERE in target.parents and target.name == "template":
        sys.exit("error: target must be the project repo, not master-harness itself")
    plan = Plan(target, a.dry_run)
    values = load_values(a.values)
    (upgrade if a.upgrade else bootstrap)(a, plan, values)
    print(f"master-harness v{VERSION} {'upgrade' if a.upgrade else 'bootstrap'} -> {target}")
    plan.report()


if __name__ == "__main__":
    main()
