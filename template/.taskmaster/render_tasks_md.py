"""Regenerate TASKS.md (human-readable checklist) from .taskmaster/tasks/tasks.json.
Phases come from metadata.phases; each task's "phase" field places it. Stdlib only.
Run from the repo root:  python .taskmaster/render_tasks_md.py"""
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ left in .taskmaster/
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tasks as tm  # noqa: E402  (tasks.py, next to this file: same loading and error messages)

for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252: never crash on "→" or "·"
    if hasattr(stream, "reconfigure"):
        stream.reconfigure(encoding="utf-8", errors="replace")

root = Path(__file__).resolve().parent.parent
data = tm.load(str(root / ".taskmaster/tasks/tasks.json"), "master")["master"]
tasks, meta = data["tasks"], data.get("metadata") or {}
names = {p["id"]: p.get("name", "") for p in meta.get("phases", []) if isinstance(p, dict) and "id" in p}
box = {"done": "[x]", "cancelled": "[~]", "deferred": "[-]", "in-progress": "[>]"}
title = f"# {meta.get('project') or 'Project'} task checklist"
out = [title, "",
       "Generated from `.taskmaster/tasks/tasks.json` (the source of truth). Never edit by hand; regenerate with",
       "`python .taskmaster/render_tasks_md.py`.", ""]
done = sum(tm.status_of(t) == "done" for t in tasks)
out.append(f"**Progress: {done}/{len(tasks)} tasks done.**")
current = object()
for t in sorted(tasks, key=lambda t: (tm.phase_key(t), t["id"])):
    p = t.get("phase") if tm.is_int(t.get("phase")) else None
    if p != current:
        current = p
        head = f"Phase {p} - {names.get(p, '')}".rstrip(" -") if p is not None else "Unphased"
        out += ["", f"## {head}", ""]
    deps = f" _(after {', '.join(map(str, t.get('dependencies', [])))})_" if t.get("dependencies") else ""
    tag = " **[HUMAN]**" if t.get("human") else ""
    lines = [f"- {box.get(tm.status_of(t), '[ ]')} **{t['id']}. {' '.join(str(t.get('title', '')).split())}**{tag}{deps}"]
    if t.get("description"):
        lines.append(f"  {' '.join(str(t['description']).split())}")
    if t.get("testStrategy"):
        lines.append(f"  _Test:_ {' '.join(str(t['testStrategy']).split())}")
    # Line breaks inside a list item: a trailing backslash (CommonMark), never trailing spaces, which
    # `git diff --check` and whitespace linters reject.
    out += [ln + "\\" for ln in lines[:-1]] + lines[-1:]
    for s in t.get("subtasks", []):
        out.append(f"  - {box.get(tm.status_of(s), '[ ]')} {t['id']}.{s['id']} {' '.join(str(s.get('title', '')).split())}")
out = [ln.rstrip() for ln in out]  # no trailing whitespace anywhere in the generated file
(root / "TASKS.md").write_text("\n".join(out) + "\n", encoding="utf-8", newline="\n")
print(f"wrote TASKS.md ({len(tasks)} tasks)")
