"""Regenerate TASKS.md (human-readable checklist) from .taskmaster/tasks/tasks.json.
Phases come from metadata.phases; each task's "phase" field places it. Stdlib only.
Run from the repo root:  python .taskmaster/render_tasks_md.py"""
import json
from pathlib import Path

root = Path(__file__).resolve().parent.parent
data = json.loads((root / ".taskmaster/tasks/tasks.json").read_text(encoding="utf-8"))["master"]
tasks, meta = data["tasks"], data.get("metadata", {})
names = {p["id"]: p.get("name", "") for p in meta.get("phases", [])}
box = {"done": "[x]", "cancelled": "[~]", "deferred": "[-]", "in-progress": "[>]"}
title = f"# {meta.get('project') or 'Project'} task checklist"
out = [title, "",
       "Generated from `.taskmaster/tasks/tasks.json` (the source of truth). Never edit by hand; regenerate with",
       "`python .taskmaster/render_tasks_md.py`.", ""]
done = sum(t.get("status") == "done" for t in tasks)
out.append(f"**Progress: {done}/{len(tasks)} tasks done.**")
current = object()
for t in sorted(tasks, key=lambda t: (t.get("phase", 10**6), t["id"])):
    p = t.get("phase")
    if p != current:
        current = p
        head = f"Phase {p} - {names.get(p, '')}".rstrip(" -") if p is not None else "Unphased"
        out += ["", f"## {head}", ""]
    deps = f" _(after {', '.join(map(str, t.get('dependencies', [])))})_" if t.get("dependencies") else ""
    tag = " **[HUMAN]**" if t.get("human") else ""
    out.append(f"- {box.get(t.get('status'), '[ ]')} **{t['id']}. {t['title']}**{tag}{deps}  ")
    if t.get("description"):
        out.append(f"  {t['description']}  ")
    if t.get("testStrategy"):
        out.append(f"  _Test:_ {' '.join(t['testStrategy'].split())}")
    for s in t.get("subtasks", []):
        out.append(f"  - {box.get(s.get('status'), '[ ]')} {t['id']}.{s['id']} {s['title']}")
(root / "TASKS.md").write_text("\n".join(out) + "\n", encoding="utf-8")
print(f"wrote TASKS.md ({len(tasks)} tasks)")
