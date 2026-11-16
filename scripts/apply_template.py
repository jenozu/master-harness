#!/usr/bin/env python3
"""Copy the master-harness template into a project, fill placeholders, merge settings (Python stdlib only).

Bootstrap (new project; never overwrites existing files):
  python scripts/apply_template.py --target <repo> --values values.json \
      [--rules python-fastapi,react-vite-tailwind] [--skills db-migration,mobile-ui-check] [--settings python,node]

Upgrade (existing project; replaces harness-owned files, backs up the old ones, never touches project content):
  python scripts/apply_template.py --target <repo> --upgrade [--values values.json]
  Library pieces can be added during an upgrade too (created only if missing): --skills vps --settings vps
  The upgrade compares each harness-owned file with the template as it was at the project's old version (from
  this clone's git history, or --old-template DIR). Untouched files are replaced quietly; only files someone edited
  are backed up and listed for review. It also prints the CHANGELOG's project actions since the old version.

values.json: {"PROJECT_NAME": "...", ..., "dev_servers": [ {...} ]}. See docs/placeholders.md.
--dry-run prints what would happen without writing anything.
"""
import argparse
import datetime
import json
import re
import shutil
import subprocess
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
    ".taskmaster/docs/human-checklist.md", ".taskmaster/checks.json",
    ".claude/harness.json", ".claude/rules/project.md",
}
# Rules an older harness put in settings.json that upgrades take out again (merging otherwise only adds).
RETIRED_RULES = {"allow": ["Bash(curl -s *)", "Bash(curl -fsS *)"]}  # 2.1.2: curl now asks (it can send data out)
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
        self.customized, self.actions = [], None
        self.old = None
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
        clean = [r for r in self.replaced if r not in self.customized]
        for label, items in (("created", self.created), ("replaced, untouched since the old version", clean),
                             ("kept existing (merge by hand if needed)", self.kept)):
            if items:
                print(f"{label}: {len(items)}")
                for i in items:
                    print(f"  {i}")
        if self.same:
            print(f"unchanged: {len(self.same)}")
        if self.customized:
            print(f"CUSTOMIZED (edited in this project; review only these: "
                  f"diff .harness-backup/{self.old}/<file> <file>): {len(self.customized)}")
            for i in self.customized:
                print(f"  {i}")
        elif self.replaced:
            print("CUSTOMIZED: none (nothing to review)")
        for n in self.notes:
            print(f"note: {n}")
        if self.missing:
            print("UNFILLED PLACEHOLDERS (fill these in before running check_harness.py):")
            for rel, names in sorted(self.missing.items()):
                print(f"  {rel}: {', '.join(names)}")
        if self.actions is not None:
            if self.actions:
                print("PROJECT ACTIONS (from CHANGELOG, apply these in order; no need to read the rest):")
                for line in self.actions:
                    print(f"  {line}")
            else:
                print("PROJECT ACTIONS: none")
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


GITATTRIBUTES_LINES = [".claude/** text=auto eol=lf", ".taskmaster/** text=auto eol=lf", "TASKS.md text eol=lf",
                       "CLAUDE.md text eol=lf", "AGENTS.md text eol=lf"]


def ensure_gitattributes(plan):
    """Harness files are stored with LF endings even when a Windows tool writes CRLF (keeps diffs and CI checks clean)."""
    ga = plan.target / ".gitattributes"
    have = ga.read_text(encoding="utf-8").splitlines() if ga.exists() else []
    patterns = {l.split()[0] for l in have if l.strip() and not l.startswith("#")}
    add = [l for l in GITATTRIBUTES_LINES if l.split()[0] not in patterns]
    if add:
        text = "\n".join(have).rstrip("\n")
        text = (text + "\n\n" if text else "") + "# master-harness: LF line endings for harness files\n" + "\n".join(add) + "\n"
        if not plan.dry:
            ga.write_text(text, encoding="utf-8", newline="\n")
        plan.notes.append(f".gitattributes: added LF rules for harness files")


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
    ensure_gitattributes(plan)
    if not plan.dry:
        (plan.target / ".claude").mkdir(exist_ok=True)
        (plan.target / ".claude/HARNESS_VERSION").write_text(VERSION + "\n", encoding="utf-8", newline="\n")


def upgrade(a, plan, values):
    vfile = plan.target / ".claude/HARNESS_VERSION"
    old = vfile.read_text(encoding="utf-8").strip() if vfile.exists() else "unknown"
    plan.notes.append(f"harness {old} -> {VERSION}")
    plan.old = old
    backup = plan.target / ".harness-backup" / old
    pristine = OldTemplate(old, a.old_template)
    if not pristine.available:
        plan.notes.append(f"couldn't find the v{old} template (shallow clone or unknown version): every replaced "
                          "file is listed as CUSTOMIZED; clone master-harness without --depth to avoid this")
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
                base = merge_settings(cur, {"remove": RETIRED_RULES})
                merged = settings_with_fragments(names, merge_settings(base, settings_with_fragments([])))
                if merged != cur:
                    plan.write(dst, json.dumps(merged, indent=2) + "\n")
                    plan.notes.append("settings.json: added new harness permissions/env (nothing removed)")
            continue
        new = fill(src.read_text(encoding="utf-8"), values)
        if not target.exists():
            plan.write(dst, new)
            plan.created.append(dst)
            continue
        cur = target.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        if cur == new:
            plan.same.append(dst)
            continue
        was = pristine.text(src) if pristine.available else None
        untouched = was is not None and cur == fill(was, values).replace("\r\n", "\n")
        if not untouched:
            plan.customized.append(dst)
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
    ensure_gitattributes(plan)
    if not plan.dry:
        vfile.parent.mkdir(exist_ok=True)
        vfile.write_text(VERSION + "\n", encoding="utf-8", newline="\n")
    if plan.customized:
        plan.notes.append(f"edited copies saved in .harness-backup/{old}/: move project-specific lines into "
                          ".claude/rules/project.md (or another project file), then delete the backup")
    plan.actions = changelog_actions(old if old != "unknown" else "0.0.0")


def vtuple(v):
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


def changelog_actions(old):
    """'Project action' bullets of every CHANGELOG section newer than `old`, oldest first."""
    sections, cur = [], None
    for line in (HERE / "CHANGELOG.md").read_text(encoding="utf-8").splitlines():
        m = re.match(r"## (\d+(?:\.\d+)*)", line)
        if m:
            cur = (m.group(1), [])
            sections.append(cur)
        elif cur is not None:
            cur[1].append(line)
    out = []
    for ver, lines in reversed(sections):
        if vtuple(ver) <= vtuple(old):
            continue
        grab = []
        for line in lines:
            if line.startswith("- "):
                plain = line.replace("**", "")
                grab = [line] if plain.lower().startswith("- project action") else []
                if grab:
                    out.append(f"[{ver}] {plain[2:]}")
            elif grab and line.startswith("  "):
                out.append("      " + line.strip())
    return out


class OldTemplate:
    """The template as it was at the project's old version, to tell untouched files from customized ones."""

    def __init__(self, old, override=None):
        self.dir = Path(override).resolve() if override else None
        self.commit = None
        if self.dir is None and old not in ("unknown", "0.0.0"):
            self.commit = self._find(old)

    @staticmethod
    def _git(*args):
        try:
            return subprocess.run(["git", "-C", str(HERE), *args], capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
        except OSError:
            return None

    def _find(self, old):
        r = self._git("log", "--format=%H", "--", "VERSION")
        if r is None or r.returncode != 0:
            return None
        for c in r.stdout.split():
            v = self._git("show", f"{c}:VERSION")
            if v is not None and v.returncode == 0 and v.stdout.strip() == old:
                return c
        return None

    @property
    def available(self):
        return self.dir is not None or self.commit is not None

    def text(self, src):
        """Old content of a template/library source file, or None if it didn't exist then."""
        rel = Path(src).resolve().relative_to(HERE).as_posix()
        if self.dir is not None:
            p = self.dir / Path(rel).relative_to("template") if rel.startswith("template/") else None
            return p.read_text(encoding="utf-8") if p and p.is_file() else None
        r = self._git("show", f"{self.commit}:{rel}")
        return r.stdout if r is not None and r.returncode == 0 else None


def split(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def main():
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252: never crash on "→" or "·"
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--target", required=True, help="the project repo root")
    p.add_argument("--values", help="JSON file with placeholder values")
    p.add_argument("--rules", help="library rules to add, comma-separated")
    p.add_argument("--skills", help="library skills to add, comma-separated")
    p.add_argument("--settings", help="library settings fragments to merge, comma-separated")
    p.add_argument("--upgrade", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--old-template", help=argparse.SUPPRESS)  # testing/offline: the old template folder
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
