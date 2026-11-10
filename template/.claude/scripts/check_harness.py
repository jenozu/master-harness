#!/usr/bin/env python3
"""Check a project's master-harness setup (Python stdlib only).

  python .claude/scripts/check_harness.py [--target <repo>] [--allow-empty-plan] [--no-git]

Prints one line per problem: ERROR (must fix) or warn (look at it). Exit code 1 if any ERROR.
Frontmatter field lists match the Claude Code docs (sub-agents, skills) as of master-harness v1.0.0;
update AGENT_FIELDS / SKILL_FIELDS when the docs add fields.
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

AGENT_FIELDS = {"name", "description", "tools", "disallowedTools", "model", "effort", "permissionMode",
                "maxTurns", "autoCompactWindow", "skills", "mcpServers", "hooks", "memory", "background",
                "omitClaudeMd", "isolation", "color", "initialPrompt", "experimental"}
AGENT_MODELS = {"sonnet", "opus", "haiku", "fable", "inherit"}
SKILL_FIELDS = {"name", "description", "when_to_use", "argument-hint", "arguments", "disable-model-invocation",
                "user-invocable", "allowed-tools", "disallowed-tools", "model", "effort", "context", "agent",
                "background", "hooks", "paths", "shell", "metadata", "license", "compatibility"}
RULE_FIELDS = {"paths", "description"}
EFFORTS = {"low", "medium", "high", "xhigh", "max"}
CORE_AGENTS = ["phase-runner", "builder-haiku", "builder-sonnet", "builder-opus", "verifier", "reviewer"]
CORE_SKILLS = ["run-phase", "next-task", "plan-from-prd", "adapt", "status", "manual-checks", "dev-servers"]
CORE_FILES = [".claude/scripts/check_harness.py", "CLAUDE.md", "AGENTS.md", ".claude/settings.json", ".claude/rules/rules.md", ".claude/rules/memory.md",
              ".claude/dev-servers.json", ".claude/scripts/devserver.py", ".claude/HARNESS_VERSION",
              ".taskmaster/tasks.py", ".taskmaster/render_tasks_md.py", ".taskmaster/tasks/tasks.json",
              ".taskmaster/docs/prd.md", ".taskmaster/docs/parking-lot.md", ".taskmaster/docs/manual-checks.md"]
LINE_CAPS = {"CLAUDE.md": 60, "AGENTS.md": 80, ".claude/rules/memory.md": 80}
PLACEHOLDER = re.compile(r"\{\{[A-Z0-9_]+\}\}")
SECRET = re.compile(r"(sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}"
                    r"|xox[bap]-[A-Za-z0-9-]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")
FOREIGN_PATH = re.compile(r"([A-Za-z]:\\Users\\[^\\\s]+|/home/[a-z_][a-z0-9_-]*/|/Users/[A-Za-z][^/\s]*/)")

errors, warns = [], []


def err(msg):
    errors.append(msg)


def warn(msg):
    warns.append(msg)


def frontmatter(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.startswith("---"):
        return None, text
    end = text.find("\n---", 3)
    if end == -1:
        return None, text
    block = text[3:end]
    fields, cur = {}, None
    for line in block.splitlines():
        m = re.match(r"^([A-Za-z][\w-]*):\s*(.*)$", line)
        if m:
            cur = m.group(1)
            fields[cur] = m.group(2).strip().strip('"').strip("'")
        elif cur and line.strip().startswith("- "):
            item = line.strip()[2:].strip().strip('"').strip("'")
            fields[cur] = (fields[cur] if isinstance(fields[cur], list) else
                           ([fields[cur]] if fields[cur] else [])) + [item]
    return fields, text[end + 4:]


def as_list(v):
    return v if isinstance(v, list) else [x for x in re.split(r"[,\s]+", v or "") if x]


def harness_text_files(root):
    paths = [root / "CLAUDE.md", root / "AGENTS.md"]
    for d in (".claude", ".taskmaster"):
        base = root / d
        if base.exists():
            paths += [p for p in base.rglob("*") if p.is_file() and "tmp" not in p.relative_to(base).parts[:1]
                      and "__pycache__" not in p.parts and p.suffix in (".md", ".json", ".py", ".txt", "")]
    return [p for p in paths if p.exists()]


def check_files(root):
    for rel in CORE_FILES:
        if not (root / rel).exists():
            err(f"missing {rel}")
    for name in CORE_AGENTS:
        if not (root / f".claude/agents/{name}.md").exists():
            err(f"missing core agent .claude/agents/{name}.md")
    for name in CORE_SKILLS:
        if not (root / f".claude/skills/{name}/SKILL.md").exists():
            err(f"missing core skill .claude/skills/{name}/SKILL.md")
    for rel, cap in LINE_CAPS.items():
        p = root / rel
        if p.exists():
            n = len(p.read_text(encoding="utf-8", errors="replace").splitlines())
            if n > cap:
                err(f"{rel} has {n} lines (cap {cap}); trim it, it loads every session")


def check_text(root):
    for p in harness_text_files(root):
        rel = p.relative_to(root).as_posix()
        text = p.read_text(encoding="utf-8", errors="replace")
        left = sorted(set(PLACEHOLDER.findall(text)))
        if left:
            err(f"{rel}: unfilled placeholders {', '.join(left)}")
        if SECRET.search(text):
            err(f"{rel}: looks like it contains a secret or private key")
        m = FOREIGN_PATH.search(text)
        if m and rel not in (".claude/rules/memory.md",):
            warn(f"{rel}: machine-specific absolute path '{m.group(1)}' (fine only if it's this machine)")
        if text.startswith("﻿") or "\x00" in text[:200]:
            err(f"{rel}: not plain UTF-8 (BOM or UTF-16)")


def check_agents(root):
    for p in sorted((root / ".claude/agents").glob("*.md")):
        rel = p.relative_to(root).as_posix()
        fm, _ = frontmatter(p)
        if fm is None:
            err(f"{rel}: no frontmatter")
            continue
        for f in ("name", "description"):
            if not fm.get(f):
                err(f"{rel}: missing '{f}'")
        for f in fm:
            if f not in AGENT_FIELDS:
                err(f"{rel}: unknown agent field '{f}' (Claude Code ignores it silently)")
        if fm.get("name") and fm["name"] != p.stem:
            warn(f"{rel}: name '{fm['name']}' differs from the file name")
        model = fm.get("model")
        if model and model not in AGENT_MODELS and not model.startswith("claude-"):
            err(f"{rel}: model '{model}' is not one of {sorted(AGENT_MODELS)} or a full model id")
        if fm.get("effort") and fm["effort"] not in EFFORTS:
            err(f"{rel}: effort '{fm['effort']}' invalid")
        if fm.get("autoCompactWindow"):
            try:
                v = int(fm["autoCompactWindow"])
                if not 100000 <= v <= 1000000:
                    err(f"{rel}: autoCompactWindow must be 100000-1000000")
            except ValueError:
                err(f"{rel}: autoCompactWindow must be an integer")
        for s in as_list(fm.get("skills")):
            if s and not (root / f".claude/skills/{s}/SKILL.md").exists():
                err(f"{rel}: preloads skill '{s}' which doesn't exist")
    pr = root / ".claude/agents/phase-runner.md"
    if pr.exists():
        fm, _ = frontmatter(pr)
        if fm and "Agent" not in as_list(fm.get("tools")):
            err("phase-runner must have the Agent tool to dispatch builders")
    for name in ("verifier", "reviewer"):
        p = root / f".claude/agents/{name}.md"
        if p.exists():
            fm, _ = frontmatter(p)
            if fm and not {"Edit", "Write"} <= set(as_list(fm.get("disallowedTools"))):
                err(f"{name} must stay read-only (disallowedTools: Agent, Edit, Write)")


def check_skills(root):
    for p in sorted((root / ".claude/skills").glob("*/SKILL.md")):
        rel = p.relative_to(root).as_posix()
        fm, _ = frontmatter(p)
        if fm is None:
            err(f"{rel}: no frontmatter")
            continue
        if not fm.get("description"):
            err(f"{rel}: missing description (it's how Claude decides when to use the skill)")
        for f in fm:
            if f not in SKILL_FIELDS:
                err(f"{rel}: unknown skill field '{f}'")
        if fm.get("effort") and fm["effort"] not in EFFORTS:
            err(f"{rel}: effort '{fm['effort']}' invalid")


def tracked_files(root):
    r = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True)
    return r.stdout.splitlines() if r.returncode == 0 else None


def check_rules(root, files):
    for p in sorted((root / ".claude/rules").glob("*.md")):
        rel = p.relative_to(root).as_posix()
        fm, _ = frontmatter(p)
        if not fm:
            continue
        for f in fm:
            if f not in RULE_FIELDS:
                warn(f"{rel}: unexpected rule field '{f}'")
        if fm.get("paths") and files is not None:
            raw = fm["paths"]
            pats = raw if isinstance(raw, list) else [x.strip().strip('"').strip("'") for x in split_globs(raw)]
            if not any(match(f, pat) for f in files for pat in pats):
                warn(f"{rel}: paths {pats} match no tracked files yet (fine early on; check the folder names)")


def split_globs(s):
    """Split 'a/**, b/{x,y}' on commas/spaces outside braces."""
    out, cur, depth = [], "", 0
    for ch in s:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        if ch in ", " and depth == 0:
            if cur.strip():
                out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def glob_regex(pat):
    i, out = 0, ""
    while i < len(pat):
        if pat.startswith("**/", i):
            out += "(?:.*/)?"
            i += 3
        elif pat.startswith("**", i):
            out += ".*"
            i += 2
        elif pat[i] == "*":
            out += "[^/]*"
            i += 1
        elif pat[i] == "?":
            out += "[^/]"
            i += 1
        elif pat[i] == "{":
            j = pat.index("}", i)
            out += "(?:" + "|".join(re.escape(x) for x in pat[i + 1:j].split(",")) + ")"
            i = j + 1
        else:
            out += re.escape(pat[i])
            i += 1
    return re.compile(out + r"\Z")


def match(path, pat):
    return bool(glob_regex(pat).match(path))


def check_json(root):
    p = root / ".claude/settings.json"
    if p.exists():
        try:
            s = json.loads(p.read_text(encoding="utf-8"))
            if s.get("env", {}).get("CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH") != "2":
                err('settings.json: env CLAUDE_CODE_MAX_SUBAGENT_SPAWN_DEPTH must be "2" (lead -> phase-runner -> builders)')
            deny = " ".join(s.get("permissions", {}).get("deny", []))
            if ".env" not in deny:
                warn("settings.json: .env files are not in permissions.deny")
        except json.JSONDecodeError as e:
            err(f"settings.json is not valid JSON: {e}")
    p = root / ".claude/dev-servers.json"
    if p.exists():
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(d, list):
                err("dev-servers.json must be a list")
            else:
                for s in d:
                    if not {"name", "cmd"} <= set(s):
                        err(f"dev-servers.json: entry {s} needs at least name and cmd")
                if not d:
                    warn("dev-servers.json is empty (add servers once the app has any)")
        except json.JSONDecodeError as e:
            err(f"dev-servers.json is not valid JSON: {e}")


def check_imports(root):
    p = root / "CLAUDE.md"
    if p.exists():
        for m in re.finditer(r"(?m)^@(\S+)", p.read_text(encoding="utf-8", errors="replace")):
            if not (root / m.group(1)).exists():
                err(f"CLAUDE.md imports @{m.group(1)}, which doesn't exist")


def check_plan(root, allow_empty):
    tp = root / ".taskmaster/tasks.py"
    if not tp.exists():
        return
    r = subprocess.run([sys.executable, str(tp), "validate"], cwd=root, capture_output=True, text=True)
    for line in (r.stdout + r.stderr).splitlines():
        if line.startswith("ERROR"):
            err(f"tasks.json: {line[7:]}")
        elif line.startswith("warn"):
            warn(f"tasks.json: {line[6:]}")
    data = json.loads((root / ".taskmaster/tasks/tasks.json").read_text(encoding="utf-8"))["master"]
    if not data["tasks"]:
        (warn if allow_empty else err)("tasks.json has no tasks yet (run the plan-from-prd skill)")
        return
    if not data.get("metadata", {}).get("phases"):
        err("tasks.json: metadata.phases is empty; /run-phase needs phases")
    r = subprocess.run([sys.executable, str(tp), "next"], cwd=root, capture_output=True, text=True)
    if r.returncode != 0 and any(t.get("status") == "pending" for t in data["tasks"]):
        err("tasks.py next finds nothing workable although tasks are pending (dependency problem)")
    for t in data["tasks"]:
        ts = t.get("testStrategy", "").strip().lower()
        if t.get("status") == "pending" and ts in ("", "n/a", "none", "manual"):
            err(f"task {t['id']}: testStrategy must name something runnable")


def check_git(root):
    if subprocess.run(["git", "rev-parse"], cwd=root, capture_output=True).returncode != 0:
        warn("not a git repository: can't check that the harness is committed")
        return
    r = subprocess.run(["git", "status", "--porcelain", "--", "CLAUDE.md", "AGENTS.md", "TASKS.md", ".claude",
                        ".taskmaster", ".gitignore"], cwd=root, capture_output=True, text=True)
    if r.stdout.strip():
        err("harness files not committed:\n    " + "\n    ".join(r.stdout.strip().splitlines()[:15]))
    for rel in CORE_FILES:
        p = root / rel
        if p.exists() and p.stat().st_size == 0:
            err(f"{rel} is empty")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default=".")
    ap.add_argument("--allow-empty-plan", action="store_true", help="don't fail when tasks.json has no tasks")
    ap.add_argument("--no-git", action="store_true", help="skip the committed-files check")
    a = ap.parse_args()
    root = Path(a.target).resolve()
    check_files(root)
    check_text(root)
    if (root / ".claude/agents").exists():
        check_agents(root)
    if (root / ".claude/skills").exists():
        check_skills(root)
    if (root / ".claude/rules").exists():
        check_rules(root, None if a.no_git else tracked_files(root))
    check_json(root)
    check_imports(root)
    if (root / ".taskmaster/tasks/tasks.json").exists():
        check_plan(root, a.allow_empty_plan)
    if not a.no_git:
        check_git(root)
    for e in errors:
        print(f"ERROR {e}")
    for w in warns:
        print(f"warn  {w}")
    print(f"{len(errors)} errors, {len(warns)} warnings" + ("" if errors else " - harness OK"))
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
