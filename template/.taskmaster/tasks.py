#!/usr/bin/env python3
"""Task state helper for the master-harness Taskmaster plan (Python stdlib only).

Run from the repo root:  python .taskmaster/tasks.py [--file PATH] [--tag TAG] <command> ...

Commands: init, status, phase, list, next, show, set-status, log, add, queue, close, meta, validate
IDs are "3" for a task and "3.2" for subtask 2 of task 3.
Phases live in metadata.phases ([{"id": 0, "name": "Foundation"}, ...]); each top-level task has "phase".
Optional task flags: "human": true (only the human can do it), "review": true (reviewer agent after verifier).
A human task can be queued ("queued": true, `tasks.py queue <id>`): it stays pending on the human checklist, but
tasks that depend on it may be built against placeholders. Only the human's confirmation closes it:
`set-status <id> done --human-confirmed`, which the lead runs only after the human says the step is done.
Notes with quotes, backticks or $(...): `tasks.py log <id> - <<'EOF'` ... `EOF` (the text comes from stdin).
Script tasks: "runner": "script" plus "check" (a list of commands) are run by run_checks.py with no model at all.
"verify" (a list of commands): run_checks.py verify <id> checks a built task with no model when its changes touch no
app code. metadata.goal / metadata.non_goals: the PRD's goal and non-goals, printed by show (set them with meta).
`close <id>` is the whole close-out after verification: log, done, render TASKS.md, stage, commit, push.
"""
import argparse
import datetime
import json
import os
import shlex
import subprocess
import sys

DEFAULT_FILE = ".taskmaster/tasks/tasks.json"
STATUSES = ["pending", "in-progress", "review", "done", "deferred", "cancelled"]
PRIORITY = {"high": 3, "medium": 2, "low": 1}
ICON = {"pending": "[ ]", "in-progress": "[~]", "review": "[?]", "done": "[x]",
        "deferred": "[-]", "cancelled": "[/]"}
RUNNERS = ("agent", "script")
# A check command is an argv list, never a shell string. These can't appear in one.
SHELL_TOKENS = {"&&", "||", "|", ";", "&", ">", ">>", "<", "2>", "2>&1", "1>"}
SHELL_CHARS = ("`", "$(", "\n")
SHELLS = {"sh", "bash", "zsh", "dash", "fish", "cmd", "powershell", "pwsh", "cd", "env", "xargs", "sudo"}
INLINE_CODE = {"python": {"-c"}, "python3": {"-c"}, "py": {"-c"}, "node": {"-e", "--eval", "-p", "--print"},
               "bun": {"-e", "--eval", "-p", "--print"}, "deno": {"eval"}}


def die(msg, code=2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


# ---------- storage ----------

def is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def structure_problem(data, tag):
    """One line describing why the file can't be used at all, or None. (validate() checks the plan itself.)"""
    if not isinstance(data, dict):
        return "the file must hold a JSON object like {\"master\": {\"tasks\": [...]}}"
    if tag not in data:
        return f"tag '{tag}' not found (available: {', '.join(map(str, data)) or 'none'})"
    if not isinstance(data[tag], dict) or not isinstance(data[tag].get("tasks"), list):
        return f"'{tag}' needs a \"tasks\" list"
    for i, t in enumerate(data[tag]["tasks"], 1):
        if not isinstance(t, dict):
            return f"task #{i} is not an object"
        if not is_int(t.get("id")):
            return f"task #{i} ('{t.get('title', '')}'): id must be a whole number, got {json.dumps(t.get('id'))}"
        subs = t.get("subtasks", [])
        if not isinstance(subs, list):
            return f"task {t['id']}: subtasks must be a list"
        for s in subs:
            if not isinstance(s, dict) or not is_int(s.get("id")):
                got = json.dumps(s.get("id")) if isinstance(s, dict) else "not an object"
                return f"task {t['id']}: every subtask id must be a whole number, got {got}"
    return None


def load(path, tag):
    if not os.path.exists(path):
        die(f"{path} not found. Run `tasks.py init` first.")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except ValueError as e:
        die(f"{path} is not valid JSON ({e}). Fix it by hand (git diff shows what changed), then `tasks.py validate`.")
    prob = structure_problem(data, tag)
    if prob:
        die(f"{path}: {prob}")
    return data


def save(path, data, tag):
    data[tag].setdefault("metadata", {})["updated"] = now()
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:  # LF on Windows too
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp, path)


# ---------- id helpers ----------

def parse_id(s):
    s = str(s)
    parts = s.split(".")
    try:
        if len(parts) == 1:
            return int(parts[0]), None
        if len(parts) == 2:
            return int(parts[0]), int(parts[1])
    except ValueError:
        pass
    die(f"bad id '{s}' (use 3 or 3.2)")


def lookup(tasks, sid):
    """Return (item, parent_or_None), or (None, None) if the id does not exist."""
    tid, sub = parse_id(sid)
    task = next((t for t in tasks if t.get("id") == tid), None)
    if task is None:
        return None, None
    if sub is None:
        return task, None
    st = next((s for s in task.get("subtasks", []) if s.get("id") == sub), None)
    return (st, task) if st is not None else (None, None)


def find(tasks, sid):
    """Like lookup, but exits with an error if the id does not exist."""
    item, parent = lookup(tasks, sid)
    if item is None:
        die(f"{sid} not found")
    return item, parent


def full_id(item, parent):
    return f"{parent['id']}.{item['id']}" if parent else str(item["id"])


def norm_dep(dep, parent):
    """Normalise a dependency to an absolute id string.
    In a subtask, an int means a sibling subtask; a string is absolute."""
    if isinstance(dep, int) and parent is not None:
        return f"{parent['id']}.{dep}"
    return str(dep)


def status_of(item):
    return (item.get("status") or "pending").lower()


def runner_of(item, parent=None):
    return item.get("runner") or (parent or {}).get("runner") or "agent"


def exe_name(arg):
    """Executable name without folder or Windows extension, lower case: 'C:/x/NPM.cmd' -> 'npm'."""
    base = arg.replace("\\", "/").rsplit("/", 1)[-1].lower()
    for ext in (".exe", ".cmd", ".bat", ".ps1"):
        if base.endswith(ext):
            return base[: -len(ext)]
    return base


def split_args(cmd):
    """Split a command line into arguments like a shell would, but keep backslashes (Windows paths)."""
    lex = shlex.shlex(cmd, posix=True)
    lex.whitespace_split = True
    lex.escape = ""
    lex.commenters = ""
    return list(lex)


def norm_check(entry):
    """One check entry -> (argv, cwd, problem). Entry: ["pytest", "-q"] or {"cmd": [...], "cwd": "frontend"}."""
    cwd = "."
    if isinstance(entry, dict):
        cwd = entry.get("cwd") or "."
        entry = entry.get("cmd")
    if isinstance(entry, str):
        try:
            hint = f", e.g. {split_args(entry)}"
        except ValueError:
            hint = ""
        return None, cwd, f"'{entry}' is a string; write it as a list of arguments{hint}"
    if not isinstance(entry, list) or not entry or not all(isinstance(x, str) and x for x in entry):
        return None, cwd, "a command must be a non-empty list of non-empty strings"
    if not isinstance(cwd, str) or os.path.isabs(cwd) or cwd.replace("\\", "/").startswith("/") \
            or ":" in cwd or ".." in cwd.replace("\\", "/").split("/"):
        return entry, cwd, f"cwd '{cwd}' must be a folder inside the repo (relative, no '..')"
    if exe_name(entry[0]) in SHELLS:
        return entry, cwd, f"'{entry[0]}' is a shell or wrapper; run the program directly instead"
    if set(entry[1:]) & INLINE_CODE.get(exe_name(entry[0]), set()):
        return entry, cwd, f"inline code in {entry}; put it in a script file in the repo and run that"
    for x in entry:
        if x in SHELL_TOKENS or any(c in x for c in SHELL_CHARS):
            return entry, cwd, f"shell operator in {entry}; split it into separate commands (use cwd instead of cd)"
    return entry, cwd, None


def check_problems(item, fid):
    out = []
    r = item.get("runner")
    if r is not None and r not in RUNNERS:
        out.append(f"{fid}: runner '{r}' must be one of {', '.join(RUNNERS)}")
    chk = item.get("check")
    if r == "script" and status_of(item) not in ("cancelled", "deferred", "done") and not chk:
        out.append(f"{fid}: runner is script but there is no check (the commands the script runs)")
    for field in ("check", "verify"):
        cmds = item.get(field)
        if cmds is None:
            continue
        if not isinstance(cmds, list):
            out.append(f"{fid}: {field} must be a list of commands")
            continue
        for c in cmds:
            _, _, prob = norm_check(c)
            if prob:
                out.append(f"{fid}: {field}: {prob}")
    return out


def done_ids(tasks):
    out = set()
    for t in tasks:
        if status_of(t) == "done":
            out.add(str(t["id"]))
        for s in t.get("subtasks", []):
            if status_of(s) == "done":
                out.add(f"{t['id']}.{s['id']}")
    return out


def is_queued(item, parent=None):
    return bool(item.get("queued")) and bool(item.get("human") or (parent or {}).get("human")) \
        and status_of(item) in ("pending", "in-progress", "review")


def met_ids(tasks):
    """Ids that count as met for dependencies: done, plus queued human steps (agents build around them)."""
    out = done_ids(tasks)
    for t in tasks:
        if is_queued(t):
            out.add(str(t["id"]))
        for s in t.get("subtasks", []):
            if is_queued(s, t):
                out.add(f"{t['id']}.{s['id']}")
    return out


def queued_human(tasks):
    """Open queued human steps as (full id, title, phase)."""
    out = []
    for t in tasks:
        for item, parent in [(t, None)] + [(s, t) for s in t.get("subtasks", [])]:
            if is_queued(item, parent):
                out.append((full_id(item, parent), item.get("title", ""), phase_of(t)))
    return out


def deps_of(item, parent):
    return [norm_dep(d, parent) for d in item.get("dependencies", [])]


def unmet(item, parent, done):
    return [d for d in deps_of(item, parent) if d not in done]


def all_ids(tasks):
    ids = set()
    for t in tasks:
        ids.add(str(t["id"]))
        for s in t.get("subtasks", []):
            ids.add(f"{t['id']}.{s['id']}")
    return ids


def prio(item, parent=None):
    p = item.get("priority") or (parent or {}).get("priority") or "medium"
    return PRIORITY.get(p, 2)


def phase_of(task):
    return task.get("phase")


def phase_key(task):
    """Sort key: earlier phases first, tasks without a phase last."""
    ph = phase_of(task)
    return ph if is_int(ph) else 10 ** 6


def meta_of(data, tag):
    return data[tag].setdefault("metadata", {})


def phase_names(meta):
    return {p["id"]: p.get("name", "") for p in meta.get("phases", []) if "id" in p}


def open_status(item):
    return status_of(item) in ("pending", "in-progress", "review")


def current_phase(tasks):
    """Lowest phase that still has open top-level tasks (not counting queued human steps), or None."""
    ph = [phase_of(t) for t in tasks if open_status(t) and not is_queued(t) and phase_of(t) is not None]
    return min(ph) if ph else None


# ---------- next-task selection ----------

def pick_next(tasks, phase=None):
    """Resume in-progress work first, then highest priority with deps satisfied.
    Descends into subtasks so the result is the actual unit of work.
    With phase set, only tasks in that phase are considered."""
    done = met_ids(tasks)
    if phase is not None:
        tasks = [t for t in tasks if phase_of(t) == phase]
    live = ("pending", "in-progress")

    # 1. subtasks of an in-progress parent
    subs = []
    for t in tasks:
        if status_of(t) != "in-progress":
            continue
        for s in t.get("subtasks", []):
            if status_of(s) in live and not is_queued(s, t) and not unmet(s, t, done):
                subs.append((t, s))
    if subs:
        subs.sort(key=lambda ts: (0 if status_of(ts[1]) == "in-progress" else 1,
                                  -prio(ts[1], ts[0]), len(ts[1].get("dependencies", [])),
                                  ts[0]["id"], ts[1]["id"]))
        return subs[0]

    # 2. top-level tasks
    elig = [t for t in tasks if status_of(t) in live and not is_queued(t) and not unmet(t, None, done)]
    if not elig:
        return None
    elig.sort(key=lambda t: (0 if status_of(t) == "in-progress" else 1, phase_key(t),
                             -prio(t), len(t.get("dependencies", [])), t["id"]))
    top = elig[0]
    # descend into first workable subtask, if any are left
    open_subs = [s for s in top.get("subtasks", []) if status_of(s) in live and not is_queued(s, top)]
    for s in open_subs:
        if not unmet(s, top, done):
            return top, s
    return None, top


# ---------- validation ----------

def validate(tasks, meta=None):
    errors, warns = [], []
    meta = meta or {}
    pids = set(phase_names(meta))
    by_id = {t.get("id"): t for t in tasks}
    if pids:
        for t in tasks:
            ph = phase_of(t)
            if ph is None:
                errors.append(f"{t.get('id')}: no phase (metadata.phases is defined, so every task needs one)")
            elif ph not in pids:
                errors.append(f"{t.get('id')}: phase {ph} is not in metadata.phases")
            for d in t.get("dependencies", []):
                dt = by_id.get(int(str(d).split(".")[0])) if str(d).split(".")[0].isdigit() else None
                if dt is not None and ph is not None and phase_of(dt) is not None and phase_of(dt) > ph:
                    errors.append(f"{t['id']}: depends on {d}, which is in a later phase ({phase_of(dt)} > {ph})")
    ids = all_ids(tasks)
    seen = set()
    for t in tasks:
        if t.get("id") in seen:
            errors.append(f"duplicate task id {t.get('id')}")
        seen.add(t.get("id"))
        sub_seen = set()
        for s in t.get("subtasks", []):
            if s.get("id") in sub_seen:
                errors.append(f"duplicate subtask id {t['id']}.{s.get('id')}")
            sub_seen.add(s.get("id"))

    graph = {}
    for t in tasks:
        items = [(t, None)] + [(s, t) for s in t.get("subtasks", [])]
        for item, parent in items:
            fid = full_id(item, parent)
            st = status_of(item)
            if st not in STATUSES:
                errors.append(f"{fid}: unknown status '{st}'")
            deps = deps_of(item, parent)
            graph[fid] = deps
            for d in deps:
                if d not in ids:
                    errors.append(f"{fid}: depends on missing id {d}")
                elif d == fid:
                    errors.append(f"{fid}: depends on itself")
                elif parent is None and "." not in d and int(d) > t["id"]:
                    errors.append(f"{fid}: depends on later task {d} (tasks may depend only on lower ids)")
            errors.extend(check_problems(item, fid))
            if item.get("queued") and not (item.get("human") or (parent or {}).get("human")):
                errors.append(f"{fid}: queued is only for human tasks")
            if not item.get("testStrategy") and st not in ("cancelled", "deferred"):
                warns.append(f"{fid}: no testStrategy")
            if st in ("pending", "in-progress"):
                for d in deps:
                    if d not in ids:
                        continue
                    dt, _ = lookup(tasks, d)
                    if dt is not None and status_of(dt) in ("cancelled", "deferred"):
                        warns.append(f"{fid}: blocked by {status_of(dt)} dependency {d}")
        if status_of(t) == "done":
            for s in t.get("subtasks", []):
                if status_of(s) in ("pending", "in-progress", "review"):
                    errors.append(f"{t['id']} is done but subtask {t['id']}.{s['id']} is {status_of(s)}")
        if (t.get("complexity") or 0) >= 7 and not t.get("subtasks") and status_of(t) in ("pending", "in-progress"):
            warns.append(f"{t['id']}: complexity {t['complexity']} but no subtasks (expand it before starting)")

    # cycle detection (DFS)
    state = {}

    def visit(n, stack):
        if state.get(n) == 2:
            return
        if state.get(n) == 1:
            errors.append("dependency cycle: " + " -> ".join(stack[stack.index(n):] + [n]))
            return
        state[n] = 1
        for d in graph.get(n, []):
            if d in graph:
                visit(d, stack + [n])
        state[n] = 2

    for n in graph:
        visit(n, [])

    if tasks and not str(meta.get("goal") or "").strip():
        warns.append("metadata.goal is empty: `tasks.py meta --goal '...' --non-goal '...'` from the PRD "
                     "(agents read it in `tasks.py show` instead of opening the PRD)")
    inprog = [str(t["id"]) for t in tasks if status_of(t) == "in-progress"]
    if len(inprog) > 1:
        warns.append(f"{len(inprog)} tasks in progress ({', '.join(inprog)}): finish or defer before starting more")
    return errors, warns


# ---------- display ----------

def line(item, parent=None, indent=""):
    fid = full_id(item, parent)
    extra = ""
    if item.get("priority") and not parent:
        extra += f" ({item['priority']})"
    if item.get("complexity"):
        extra += f" c{item['complexity']}"
    if item.get("human"):
        extra += " [HUMAN]"
    if is_queued(item, parent):
        extra += " [QUEUED]"
    if item.get("runner") == "script":
        extra += " [SCRIPT]"
    return f"{indent}{ICON.get(status_of(item), '[ ]')} {fid} {item.get('title', '')}{extra}"


def cmd_init(a):
    if os.path.exists(a.file):
        die(f"{a.file} already exists")
    os.makedirs(os.path.dirname(a.file) or ".", exist_ok=True)
    data = {a.tag: {"tasks": [], "metadata": {"created": now(), "updated": now(),
                                               "project": a.project or "", "phases": []}}}
    save(a.file, data, a.tag)
    docs = os.path.join(os.path.dirname(os.path.dirname(a.file)), "docs")
    os.makedirs(docs, exist_ok=True)
    pl = os.path.join(docs, "parking-lot.md")
    if not os.path.exists(pl):
        with open(pl, "w", encoding="utf-8", newline="\n") as f:
            f.write("# Parking lot\n\nIdeas that are not part of the current plan. "
                    "Review at the end of each phase: promote, defer or drop.\n\n")
    print(f"created {a.file} and {pl}")


def cmd_status(a):
    data = load(a.file, a.tag)
    tasks = data[a.tag]["tasks"]
    counts = {s: 0 for s in STATUSES}
    for t in tasks:
        counts[status_of(t)] = counts.get(status_of(t), 0) + 1
    total = len(tasks)
    pct = round(100 * counts["done"] / total) if total else 0
    print(f"[{a.tag}] {total} tasks, {pct}% done: " +
          ", ".join(f"{v} {k}" for k, v in counts.items() if v))
    names = phase_names(meta_of(data, a.tag))
    for pid, name in sorted(names.items()):
        pts = [t for t in tasks if phase_of(t) == pid]
        d = sum(status_of(t) in ("done", "cancelled", "deferred") for t in pts)
        print(f"  phase {pid} {name}: {d}/{len(pts)} closed")
    cp = current_phase(tasks)
    if cp is not None:
        print(f"current phase: {cp}")
    for t in tasks:
        if status_of(t) == "in-progress":
            print("in progress: " + line(t))
            for s in t.get("subtasks", []):
                if status_of(s) in ("in-progress", "review"):
                    print(line(s, t, "    "))
    nxt = pick_next(tasks)
    if nxt:
        parent, item = nxt
        print("next: " + line(item, parent))
    elif total and counts["done"] + counts["cancelled"] + counts["deferred"] == total:
        print("next: nothing left. Review the PRD success criteria and the parking lot.")
    elif total:
        print("next: nothing is workable (everything left is blocked). Check dependencies.")
    errors, warns = validate(tasks, meta_of(data, a.tag))
    for e in errors:
        print("ERROR: " + e)
    for w in warns:
        print("warn: " + w)


def cmd_phase(a):
    data = load(a.file, a.tag)
    tasks = data[a.tag]["tasks"]
    names = phase_names(meta_of(data, a.tag))
    if a.n is None:
        if not names:
            print("no phases defined in metadata.phases")
            return
        for pid, name in sorted(names.items()):
            pts = [t for t in tasks if phase_of(t) == pid]
            left = [str(t["id"]) for t in pts if open_status(t)]
            print(f"phase {pid} {name}: {len(pts)} tasks, open: {', '.join(left) or 'none'}")
        print(f"current phase: {current_phase(tasks)}")
        return
    pts = [t for t in tasks if phase_of(t) == a.n]
    if not pts:
        die(f"no tasks in phase {a.n}")
    print(f"phase {a.n} {names.get(a.n, '')}")
    for t in pts:
        print(line(t))
    left = [str(t["id"]) for t in pts if open_status(t)]
    human = [str(t["id"]) for t in pts if open_status(t) and t.get("human")]
    queued = [fid for fid, _, ph in queued_human(tasks) if ph == a.n]
    print(f"remaining: {', '.join(left) or 'none'}")
    if human:
        print(f"human-only: {', '.join(human)}")
    if queued:
        print(f"queued for the human (agents build around them): {', '.join(queued)}")
    agent_left = [x for x in left if x not in queued]
    if left and not agent_left:
        print("agent work done: only queued human steps remain")
    elif left and pick_next(tasks, a.n) is None:
        print("blocked: no open task in this phase has its dependencies met")


def cmd_list(a):
    data = load(a.file, a.tag)
    for t in data[a.tag]["tasks"]:
        if a.status and status_of(t) != a.status and not any(
                status_of(s) == a.status for s in t.get("subtasks", [])):
            continue
        print(line(t))
        if a.subtasks or a.status:
            for s in t.get("subtasks", []):
                if not a.status or status_of(s) == a.status:
                    print(line(s, t, "    "))


def cmd_next(a):
    data = load(a.file, a.tag)
    tasks = data[a.tag]["tasks"]
    nxt = pick_next(tasks, a.phase)
    if not nxt:
        where = f" in phase {a.phase}" if a.phase is not None else ""
        print(f"nothing workable{where}: all tasks are done, or what's left is blocked")
        sys.exit(1)
    parent, item = nxt
    if a.details:
        print_details(data, a.tag, tasks, item, parent)
    else:
        print(line(item, parent))
    if parent:
        print(f"  part of task {parent['id']}: {parent.get('title', '')}")
    if not parent and (item.get("complexity") or 0) >= 7 and not item.get("subtasks"):
        print(f"  note: complexity {item['complexity']} with no subtasks. Expand before starting.")
    if item.get("human") or (parent or {}).get("human"):
        print("  HUMAN STEP: only the human can do this. Escalate as HUMAN NEEDED with exact instructions.")
    elif runner_of(item, parent) == "script":
        print(f"  SCRIPT TASK: no builder. Run: python .taskmaster/run_checks.py run --only {full_id(item, parent)}")
    if not a.details:
        print(f"  show details: tasks.py show {full_id(item, parent)}")


def cmd_show(a):
    data = load(a.file, a.tag)
    tasks = data[a.tag]["tasks"]
    item, parent = find(tasks, a.id)
    print_details(data, a.tag, tasks, item, parent)


def print_details(data, tag, tasks, item, parent):
    meta = meta_of(data, tag)
    done = done_ids(tasks)
    print(line(item, parent))
    if meta.get("goal"):
        print(f"goal: {' '.join(str(meta['goal']).split())}")
    if meta.get("non_goals"):
        print("non-goals: " + "; ".join(str(x) for x in meta["non_goals"]))
    print(f"status: {status_of(item)}")
    top = parent or item
    if phase_of(top) is not None:
        print(f"phase: {phase_of(top)}")
    if item.get("complexity") or top.get("complexity"):
        print(f"complexity: {item.get('complexity') or top.get('complexity')}")
    flags = [f for f in ("human", "review") if item.get(f) or top.get(f)]
    if flags:
        print("flags: " + ", ".join(flags))
    if runner_of(item, parent) == "script":
        print("runner: script (python .taskmaster/run_checks.py run --only " + full_id(item, parent) + ")")
        for c in item.get("check") or []:
            argv, cwd, _ = norm_check(c)
            print("  check: " + " ".join(argv or [str(c)]) + (f"   (in {cwd})" if cwd != "." else ""))
    if item.get("verify"):
        print(f"verify: free (python .taskmaster/run_checks.py verify {full_id(item, parent)}) if no app code changed")
    if item.get("description"):
        print(f"description: {item['description']}")
    deps = deps_of(item, parent)
    if deps:
        print("depends on: " + ", ".join(f"{d} {'(done)' if d in done else '(NOT done)'}" for d in deps))
    if item.get("details"):
        print("\ndetails:\n" + item["details"])
    if item.get("testStrategy"):
        print("\ntest strategy: " + item["testStrategy"])
    if item.get("subtasks"):
        print("\nsubtasks:")
        for s in item["subtasks"]:
            print(line(s, item, "  "))


def cmd_set_status(a):
    if a.status not in STATUSES:
        die(f"status must be one of: {', '.join(STATUSES)}")
    data = load(a.file, a.tag)
    tasks = data[a.tag]["tasks"]
    item, parent = find(tasks, a.id)
    human = bool(item.get("human") or (parent or {}).get("human"))
    if human and a.status in ("done", "cancelled", "deferred") and not a.human_confirmed:
        die(f"{a.id} is a human step: only the human closes it. After they confirm it's {a.status}, run "
            f"`tasks.py set-status {a.id} {a.status} --human-confirmed` (--force doesn't override this)")
    if a.human_confirmed and not human:
        die(f"{a.id} is not a human task; --human-confirmed is only for human steps")
    done = met_ids(tasks)
    if a.status in ("in-progress", "done") and not a.force:
        miss = unmet(item, parent, done)
        if miss:
            die(f"{a.id} has unmet dependencies: {', '.join(miss)} (use --force to override)")
    if a.status == "done" and not a.force and not parent:
        open_subs = [full_id(s, item) for s in item.get("subtasks", [])
                     if status_of(s) in ("pending", "in-progress", "review")]
        if open_subs:
            die(f"{a.id} still has open subtasks: {', '.join(open_subs)} (use --force to override)")
    item["status"] = a.status
    if a.status in ("done", "cancelled"):
        item.pop("queued", None)
    if a.human_confirmed:
        entry = f"[{now()}] human confirmed: {a.status}"
        item["details"] = (item.get("details", "").rstrip() + "\n\n" + entry).lstrip("\n")
    msgs = []
    if parent and a.status == "in-progress" and status_of(parent) == "pending":
        parent["status"] = "in-progress"
        msgs.append(f"task {parent['id']} also set to in-progress")
    if parent and a.status == "done":
        left = [s for s in parent.get("subtasks", [])
                if status_of(s) in ("pending", "in-progress", "review")]
        if not left:
            msgs.append(f"all subtasks of {parent['id']} are done: run its test strategy, then mark {parent['id']} done")
    save(a.file, data, a.tag)
    print(f"{a.id} -> {a.status}")
    for m in msgs:
        print(m)
    if a.status == "in-progress":
        others = [str(t["id"]) for t in tasks
                  if status_of(t) == "in-progress" and t is not (parent or item)]
        if others:
            print(f"warn: other tasks already in progress: {', '.join(others)}")


def cmd_log(a):
    data = load(a.file, a.tag)
    item, parent = find(data[a.tag]["tasks"], a.id)
    text = sys.stdin.read().strip() if a.text == "-" else a.text
    if not text:
        die("empty note")
    entry = f"[{now()}] {text}"
    item["details"] = (item.get("details", "").rstrip() + "\n\n" + entry).lstrip("\n")
    save(a.file, data, a.tag)
    print(f"logged to {a.id}")


def cmd_add(a):
    data = load(a.file, a.tag)
    tasks = data[a.tag]["tasks"]
    deps = []
    for d in (a.deps.split(",") if a.deps else []):
        d = d.strip()
        if d.startswith("top:"):
            d = d[4:]
            deps.append(d if a.parent is not None else int(d))
        elif d:
            deps.append(int(d) if d.isdigit() else d)
    new = {
        "title": a.title,
        "description": a.description or "",
        "status": "pending",
        "priority": a.priority,
        "dependencies": deps,
        "details": a.details or "",
        "testStrategy": a.test or "",
    }
    if a.complexity:
        new["complexity"] = a.complexity
    if a.human:
        new["human"] = True
    if a.review:
        new["review"] = True
    if a.runner:
        new["runner"] = a.runner
    if a.verify:
        new["verify"] = [split_args(c) for c in a.verify]
    if a.check:
        new["check"] = [split_args(c) for c in a.check]
        if not a.test:
            new["testStrategy"] = "python .taskmaster/run_checks.py run --only <this id>"
    if a.parent is None:
        if a.phase is not None:
            new["phase"] = a.phase
        else:
            dep_phases = [phase_of(t) for t in tasks
                          if str(t["id"]) in {str(d).split(".")[0] for d in deps} and phase_of(t) is not None]
            cp = current_phase(tasks)
            if dep_phases:
                new["phase"] = max(dep_phases)
            elif cp is not None:
                new["phase"] = cp
    if a.parent is not None:
        parent, _ = find(tasks, str(a.parent))
        new["id"] = max([s["id"] for s in parent.get("subtasks", [])] + [0]) + 1
        new.pop("priority")
        parent.setdefault("subtasks", []).append(new)
        fid = f"{parent['id']}.{new['id']}"
    else:
        new["id"] = max([t["id"] for t in tasks] + [0]) + 1
        new["subtasks"] = []
        tasks.append(new)
        fid = str(new["id"])
    if new["testStrategy"].endswith("<this id>"):
        new["testStrategy"] = new["testStrategy"].replace("<this id>", fid)
    errors, _ = validate(tasks, meta_of(data, a.tag))
    if errors:
        print("warning: the new item introduces problems:")
        for e in errors:
            print("  " + e)
    save(a.file, data, a.tag)
    print(f"added {fid}: {a.title}")


def cmd_queue(a):
    data = load(a.file, a.tag)
    item, parent = find(data[a.tag]["tasks"], a.id)
    if not (item.get("human") or (parent or {}).get("human")):
        die(f"{a.id} is not a human task; only human steps can be queued")
    if not open_status(item):
        die(f"{a.id} is {status_of(item)}; nothing to queue")
    item["queued"] = True
    entry = f"[{now()}] human step queued: see human-checklist.md (agents may build around it; stays open until the human confirms)"
    item["details"] = (item.get("details", "").rstrip() + "\n\n" + entry).lstrip("\n")
    save(a.file, data, a.tag)
    print(f"{a.id} queued for the human; dependent tasks are now workable")


def cmd_meta(a):
    data = load(a.file, a.tag)
    meta = meta_of(data, a.tag)
    if a.goal is None and a.non_goal is None:
        print(f"goal: {meta.get('goal') or '(not set)'}")
        print("non-goals: " + ("; ".join(meta.get("non_goals") or []) or "(not set)"))
        return
    if a.goal is not None:
        meta["goal"] = " ".join(a.goal.split())
    if a.non_goal is not None:
        meta["non_goals"] = [" ".join(x.split()) for x in a.non_goal if x.strip()]
    save(a.file, data, a.tag)
    print("metadata updated: goal and non-goals are printed by tasks.py show")


def git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace")


def default_branches():
    names = {"main", "master"}
    r = git("symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if r.returncode == 0 and r.stdout.strip():
        names.add(r.stdout.strip().split("/", 1)[-1])
    return names


def cmd_close(a):
    """After the verifier (and reviewer) passed: log, mark done, render TASKS.md, stage, commit, push."""
    data = load(a.file, a.tag)
    tasks = data[a.tag]["tasks"]
    item, parent = find(tasks, a.id)
    fid = full_id(item, parent)
    if item.get("human") or (parent or {}).get("human"):
        die(f"{fid} is a human step: only the human closes it (the lead runs set-status --human-confirmed)")
    branch = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if not branch or branch == "HEAD":
        die("not on a branch (git rev-parse failed or detached HEAD)")
    if branch in default_branches():
        die(f"on the default branch ({branch}): tasks are committed on a phase branch, never the default branch")
    if status_of(item) != "done":
        miss = unmet(item, parent, met_ids(tasks))
        if miss:
            die(f"{fid} has unmet dependencies: {', '.join(miss)}")
        if not parent:
            open_subs = [full_id(s, item) for s in item.get("subtasks", []) if open_status(s)]
            if open_subs:
                die(f"{fid} still has open subtasks: {', '.join(open_subs)}")
        who = "script check, no model" if a.tier == "script" else f"done by {a.tier}"
        if a.escalated_from:
            who += f", escalated from {a.escalated_from}"
        entry = f"[{now()}] {who}; verified" + (f" ({a.note})" if a.note else "")
        item["details"] = (item.get("details", "").rstrip() + "\n\n" + entry).lstrip("\n")
        item["status"] = "done"
        save(a.file, data, a.tag)
    here = os.path.dirname(os.path.abspath(__file__))
    r = subprocess.run([sys.executable, os.path.join(here, "render_tasks_md.py")], capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        die(f"render_tasks_md.py failed: {(r.stderr or r.stdout).strip()[-300:]}")
    files = [f.strip() for f in (a.files or "").split(",") if f.strip()]
    tm_dir = os.path.relpath(os.path.dirname(os.path.dirname(os.path.abspath(a.file))))
    r = git("add", "-A", "--", *files, tm_dir, "TASKS.md")
    if r.returncode != 0:
        die(f"git add failed: {r.stderr.strip()[-300:]}")
    left = [ln[3:] for ln in git("status", "--porcelain", "--untracked-files=all").stdout.splitlines()
            if ln[:2] == "??" or ln[1] in "MD"]
    if left:
        print(f"not committed: these changes aren't in --files: {', '.join(left[:15])}")
        print(f"If the task made them, run close again with them in --files; if not, delete or restore them. "
              f"{fid} is marked done; nothing was committed.")
        sys.exit(3)
    title = " ".join(str(item.get("title", "")).split())
    msg = f"task {fid}: {title}" + (" (script check)" if a.tier == "script" else "")
    if a.trailer:
        msg += "\n\n" + "\n".join(a.trailer)
    r = git("commit", "-q", "-m", msg)
    if r.returncode != 0 and "nothing to commit" not in (r.stdout + r.stderr):
        die(f"git commit failed: {(r.stderr or r.stdout).strip()[-300:]}")
    sha = git("rev-parse", "--short", "HEAD").stdout.strip()
    if git("remote", "get-url", "origin").returncode != 0:
        pushed = "not pushed (no origin remote)"
    else:
        p = git("push", "-q", "-u", "origin", "HEAD")
        pushed = "pushed" if p.returncode == 0 else f"PUSH FAILED (commit is safe locally): {p.stderr.strip()[-200:]}"
    print(f"closed {fid}: done, TASKS.md rendered, committed {sha} on {branch}, {pushed}")


def cmd_validate(a):
    data = load(a.file, a.tag)
    errors, warns = validate(data[a.tag]["tasks"], meta_of(data, a.tag))
    for e in errors:
        print("ERROR: " + e)
    for w in warns:
        print("warn: " + w)
    if not errors and not warns:
        print("ok: no problems found")
    sys.exit(1 if errors else 0)


def main():
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252: never crash on "→" or "·"
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--file", default=DEFAULT_FILE)
    p.add_argument("--tag", default="master")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init")
    sp.add_argument("--project")
    sp.set_defaults(fn=cmd_init)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sp = sub.add_parser("phase", help="list phases, or the tasks of phase N")
    sp.add_argument("n", nargs="?", type=int)
    sp.set_defaults(fn=cmd_phase)
    sp = sub.add_parser("list")
    sp.add_argument("--status")
    sp.add_argument("--subtasks", action="store_true")
    sp.set_defaults(fn=cmd_list)
    sp = sub.add_parser("next")
    sp.add_argument("--phase", type=int, help="only consider tasks in this phase")
    sp.add_argument("--details", action="store_true", help="also print what `show` prints (saves a call)")
    sp.set_defaults(fn=cmd_next)
    sp = sub.add_parser("show")
    sp.add_argument("id")
    sp.set_defaults(fn=cmd_show)
    sp = sub.add_parser("set-status")
    sp.add_argument("id")
    sp.add_argument("status")
    sp.add_argument("--force", action="store_true", help="ignore unmet dependencies or open subtasks")
    sp.add_argument("--human-confirmed", action="store_true",
                    help="close a human step; only after the human said it's done")
    sp.set_defaults(fn=cmd_set_status)
    sp = sub.add_parser("log")
    sp.add_argument("id")
    sp.add_argument("text", help="the note, or - to read it from stdin (use for quotes, backticks, $(...))")
    sp.set_defaults(fn=cmd_log)
    sp = sub.add_parser("add")
    sp.add_argument("--title", required=True)
    sp.add_argument("--description")
    sp.add_argument("--details")
    sp.add_argument("--test", help="test strategy")
    sp.add_argument("--priority", default="medium", choices=list(PRIORITY))
    sp.add_argument("--deps", help="comma-separated. Top-level task: 1,2 or 2.1. "
                    "Subtask (--parent): a bare number is a sibling subtask, 3.1 is an "
                    "absolute subtask, top:3 is top-level task 3")
    sp.add_argument("--parent", type=int, help="add as a subtask of this task id")
    sp.add_argument("--complexity", type=int)
    sp.add_argument("--phase", type=int, help="top-level only; defaults to the latest phase of its deps")
    sp.add_argument("--human", action="store_true", help="only the human can do this task")
    sp.add_argument("--review", action="store_true", help="reviewer agent must approve after the verifier")
    sp.add_argument("--runner", choices=list(RUNNERS), help="script = run_checks.py runs it, no model")
    sp.add_argument("--verify", action="append", help="a command that proves the built task works, e.g. "
                    "\"pytest -q tests/test_x.py\" (repeatable; run free by run_checks.py verify when no app code "
                    "changed)")
    sp.add_argument("--check", action="append", help="a command the script runs, e.g. \"ruff check .\" "
                    "(repeatable; no shell operators; for a cwd, edit tasks.json: {\"cmd\": [...], \"cwd\": \"dir\"})")
    sp.set_defaults(fn=cmd_add)
    sp = sub.add_parser("queue", help="queue a human task: it stays open, dependents become workable")
    sp.add_argument("id")
    sp.set_defaults(fn=cmd_queue)
    sp = sub.add_parser("close", help="after verification: log, done, render, stage, commit, push in one call")
    sp.add_argument("id")
    sp.add_argument("--tier", required=True, choices=["haiku", "sonnet", "opus", "script", "lead"],
                    help="who built it (script = a free script task)")
    sp.add_argument("--escalated-from", choices=["haiku", "sonnet", "opus"])
    sp.add_argument("--files", help="the builder's FILES CHANGED, comma-separated (new and deleted files too)")
    sp.add_argument("--note", help="short extra text for the log line")
    sp.add_argument("--trailer", action="append", help="a commit message trailer line, e.g. Co-Authored-By: ...")
    sp.set_defaults(fn=cmd_close)
    sp = sub.add_parser("meta", help="show or set the PRD goal and non-goals that `show` prints")
    sp.add_argument("--goal")
    sp.add_argument("--non-goal", action="append", help="repeatable; replaces the whole list")
    sp.set_defaults(fn=cmd_meta)
    sub.add_parser("validate").set_defaults(fn=cmd_validate)

    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
