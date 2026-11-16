#!/usr/bin/env python3
"""Free checks: run "script" tasks with no model (Python stdlib only).

A task with "runner": "script" has a "check": a list of commands that need no judgment (lint, type check, tests,
build, a smoke script). This script runs them directly, so they cost zero tokens. Run from the repo root:

  python .taskmaster/run_checks.py plan [--phase N]          list open script tasks in order; runs nothing
  python .taskmaster/run_checks.py run [--phase N] [--only ID] [--from ID]

`run` goes through the open script tasks in dependency order. A task passes only when every command exits with
its expected code (default 0); then it is logged and marked done through tasks.py. The first failure stops the
run, leaves the status alone and prints the failing command with the last lines of its output.

Exit codes: 0 all good (or nothing to run), 1 a check failed (the code needs fixing: send a builder),
2 refused or not runnable: off the allowlist, a shell operator, waiting on a dependency, the program isn't
installed or the command timed out (the plan, checks.json or the machine needs fixing: not a builder job).

Safety: commands are argument lists run without a shell. Each must start with an entry in the allowlist in
.taskmaster/checks.json ("pytest", or a prefix such as "npm run"); anything else is refused. Output never goes
into a model's context except the short tail printed on failure; full details go to .claude/tmp/checks/<id>.log.
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ left in .taskmaster/
sys.path.insert(0, str(Path(__file__).resolve().parent))
import tasks as tm  # noqa: E402  (tasks.py, next to this file)

ROOT = Path.cwd()
CONFIG = ROOT / ".taskmaster" / "checks.json"
LOG_DIR = ROOT / ".claude" / "tmp" / "checks"
OPEN = ("pending", "in-progress", "review")


def stamp():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def load_config():
    cfg = {"allow": [], "timeout_seconds": 900, "retries_on_timeout": 1, "tail_lines": 20}
    if CONFIG.exists():
        cfg.update(json.loads(CONFIG.read_text(encoding="utf-8")))
    return cfg


def allowed(argv, allow):
    """True if argv starts with one of the allowlist entries ("pytest", "npm run", "git diff")."""
    cmd = [tm.exe_name(argv[0])] + argv[1:]
    for entry in allow:
        want = entry.split()
        if want and want[0].lower() == cmd[0] and cmd[1:len(want)] == want[1:]:
            return True
    return False


def problem(entry, allow):
    argv, cwd, prob = tm.norm_check(entry)
    if prob:
        return argv, cwd, prob
    if not allowed(argv, allow):
        return argv, cwd, f"'{' '.join(argv)}' is not on the allowlist in .taskmaster/checks.json"
    if not (ROOT / cwd).is_dir():
        return argv, cwd, f"cwd '{cwd}' does not exist"
    return argv, cwd, None


def script_items(data, tag, phase=None):
    """Open script tasks/subtasks, in dependency order (ties by id)."""
    found = []
    for t in data[tag]["tasks"]:
        for item, parent in [(t, None)] + [(s, t) for s in t.get("subtasks", [])]:
            if tm.runner_of(item, parent) != "script" or tm.status_of(item) not in OPEN:
                continue
            if item.get("runner") is None and parent is not None and item.get("check") is None:
                continue  # a subtask inherits "script" only if it has its own check
            if phase is not None and tm.phase_of(parent or item) != phase:
                continue
            found.append((tm.full_id(item, parent), item, parent))
    ids = {fid for fid, _, _ in found}
    ordered, placed = [], set()
    while len(ordered) < len(found):
        progress = False
        for fid, item, parent in found:
            if fid in placed:
                continue
            if all(d in placed or d not in ids for d in tm.deps_of(item, parent)):
                ordered.append((fid, item, parent))
                placed.add(fid)
                progress = True
        if not progress:  # a cycle: validate reports it; keep the rest in id order
            ordered += [x for x in found if x[0] not in placed]
            break
    return ordered


def tail(text, n):
    lines = text.rstrip("\n").splitlines()
    return "\n".join(lines[-n:]) if lines else "(empty)"


def run_one(argv, cwd, expect, timeout, retries):
    """Run one command without a shell. Returns a result dict."""
    workdir = ROOT / cwd
    if "/" in argv[0] or "\\" in argv[0]:
        exe = str((workdir / argv[0]).resolve())
        exe = exe if os.path.exists(exe) else None
    else:
        exe = shutil.which(argv[0])
    res = {"cmd": " ".join(argv), "cwd": cwd, "expect": expect, "start": stamp(), "attempts": 0}
    if exe is None:
        res.update(end=stamp(), exit=None, ok=False, seconds=0.0, sha256="", stdout="", missing=True,
                   stderr=f"'{argv[0]}' was not found on PATH")
        return res
    env = dict(os.environ, CI="1")  # stops test runners from waiting in watch mode
    t0 = time.monotonic()
    while True:
        res["attempts"] += 1
        try:
            p = subprocess.run([exe] + argv[1:], cwd=workdir, capture_output=True, timeout=timeout,
                               stdin=subprocess.DEVNULL, env=env, shell=False)
            out, err, code = p.stdout, p.stderr, p.returncode
            break
        except subprocess.TimeoutExpired as e:
            if res["attempts"] <= retries:
                continue  # a timeout may be transient (network); a failed check is never retried
            out, err, code = e.stdout or b"", (e.stderr or b"") + f"\ntimed out after {timeout}s".encode(), None
            break
        except OSError as e:
            out, err, code = b"", str(e).encode(), None
            break
    res.update(end=stamp(), exit=code, ok=(code == expect), seconds=round(time.monotonic() - t0, 1),
               timed_out=code is None and b"timed out after" in err,
               sha256=hashlib.sha256(out).hexdigest(),
               stdout=out.decode("utf-8", "replace"), stderr=err.decode("utf-8", "replace"))
    return res


def write_log(fid, item, results, verdict, n):
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    path = LOG_DIR / f"{fid}.log"
    out = [f"task {fid}: {item.get('title', '')}", f"result: {verdict}", ""]
    for r in results:
        out += [f"$ {r['cmd']}" + (f"   (in {r['cwd']})" if r["cwd"] != "." else ""),
                f"start {r['start']}  end {r['end']}  {r['seconds']}s  attempts {r['attempts']}",
                f"exit {r['exit']} (expected {r['expect']})  stdout sha256 {r['sha256']}",
                f"--- stdout, last {n} lines ---", tail(r["stdout"], n),
                f"--- stderr, last {n} lines ---", tail(r["stderr"], n), ""]
    path.write_text("\n".join(out), encoding="utf-8", newline="\n")
    return path.relative_to(ROOT).as_posix()


def tasks_cmd(a, *args):
    return subprocess.run([sys.executable, str(Path(__file__).resolve().parent / "tasks.py"),
                           "--file", a.file, "--tag", a.tag, *args], cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def cmd_plan(a):
    cfg = load_config()
    data = tm.load(a.file, a.tag)
    items = script_items(data, a.tag, a.phase)
    if not items:
        print("no open script tasks" + (f" in phase {a.phase}" if a.phase is not None else ""))
        return 0
    done = tm.met_ids(data[a.tag]["tasks"])
    bad = 0
    for fid, item, parent in items:
        miss = tm.unmet(item, parent, done)
        state = f"waiting on {', '.join(miss)}" if miss else "ready"
        print(f"{fid} {item.get('title', '')}  [{state}]")
        for entry in item.get("check") or []:
            argv, cwd, prob = problem(entry, cfg["allow"])
            where = f"   (in {cwd})" if cwd != "." else ""
            print(f"  $ {' '.join(argv) if argv else entry}{where}" + (f"   REFUSED: {prob}" if prob else ""))
            bad += bool(prob)
    if bad:
        print(f"{bad} command(s) would be refused: fix the check or the allowlist in .taskmaster/checks.json")
        return 1
    return 0


def cmd_run(a):
    cfg = load_config()
    n = int(cfg.get("tail_lines", 20))
    data = tm.load(a.file, a.tag)
    items = script_items(data, a.tag, a.phase)
    if a.only:
        item, parent = tm.find(data[a.tag]["tasks"], a.only)
        if tm.runner_of(item, parent) != "script":
            print(f"refused: {a.only} is not a script task (no \"runner\": \"script\")")
            return 2
        if tm.status_of(item) not in OPEN:
            print(f"{a.only} is already {tm.status_of(item)}; nothing to run")
            return 0
        items = [(a.only, item, parent)]
    elif a.from_id:
        ids = [fid for fid, _, _ in items]
        if a.from_id not in ids:
            print(f"refused: {a.from_id} is not an open script task")
            return 2
        items = items[ids.index(a.from_id):]
    if not items:
        print("nothing to run: no open script tasks" + (f" in phase {a.phase}" if a.phase is not None else ""))
        return 0
    passed, skipped = [], []
    for fid, _, _ in items:
        data = tm.load(a.file, a.tag)  # tasks.py changed the file after the last pass
        item, parent = tm.find(data[a.tag]["tasks"], fid)
        miss = tm.unmet(item, parent, tm.met_ids(data[a.tag]["tasks"]))
        if miss:
            if a.only:
                print(f"refused: {fid} is waiting on {', '.join(miss)}")
                return 2
            skipped.append(f"{fid} (waiting on {', '.join(miss)})")
            continue
        checks = item.get("check") or []
        if not checks:
            print(f"refused: {fid} has no check commands")
            return 2
        prepared = []
        for entry in checks:
            argv, cwd, prob = problem(entry, cfg["allow"])
            if prob:
                print(f"refused: task {fid}: {prob}")
                tasks_cmd(a, "log", fid, f"script check refused: {prob}")
                return 2
            ent = entry if isinstance(entry, dict) else {}
            prepared.append((argv, cwd, int(ent.get("expect", 0)),
                             int(ent.get("timeout", cfg["timeout_seconds"]))))
        results = []
        for argv, cwd, expect, timeout in prepared:
            r = run_one(argv, cwd, expect, timeout, int(cfg.get("retries_on_timeout", 0)))
            results.append(r)
            if not r["ok"]:
                break
        if not results[-1]["ok"] and (results[-1].get("missing") or results[-1].get("timed_out")):
            r = results[-1]
            why = "is not installed or not on PATH" if r.get("missing") else f"timed out after {timeout}s"
            log = write_log(fid, item, results, "NOT RUNNABLE", n)
            tasks_cmd(a, "log", fid, f"script check not runnable: `{r['cmd']}` {why}; details in {log}")
            print(f"NOT RUNNABLE task {fid}: `{r['cmd']}` {why}" + (f"   (in {r['cwd']})" if r["cwd"] != "." else ""))
            print(f"--- last {n} lines of stderr ---\n{tail(r['stderr'], n)}")
            print("status unchanged. This is not a builder job: fix the command in the task's check (e.g. the venv "
                  "path differs on Windows: venv/Scripts/python.exe), or the machine (install the tool); if neither "
                  f"is possible here, escalate. Full record: {log}")
            return 2
        if not results[-1]["ok"]:
            r = results[-1]
            log = write_log(fid, item, results, "FAIL", n)
            tasks_cmd(a, "log", fid, f"script check FAILED: `{r['cmd']}` exit {r['exit']} "
                                     f"(expected {r['expect']}); details in {log}")
            print(f"FAIL task {fid}: {item.get('title', '')}")
            print(f"$ {r['cmd']}" + (f"   (in {r['cwd']})" if r["cwd"] != "." else "")
                  + f"   -> exit {r['exit']}, expected {r['expect']}")
            print(f"--- last {n} lines of stdout ---\n{tail(r['stdout'], n)}")
            print(f"--- last {n} lines of stderr ---\n{tail(r['stderr'], n)}")
            print(f"status unchanged. Full record: {log}")
            if passed:
                print(f"passed before this: {', '.join(passed)}")
            return 1
        log = write_log(fid, item, results, "PASS", n)
        secs = round(sum(r["seconds"] for r in results), 1)
        tasks_cmd(a, "log", fid, f"script check passed: {len(results)} command(s), {secs}s, no model used")
        st = tasks_cmd(a, "set-status", fid, "done")
        if st.returncode != 0:
            print(f"checks passed for {fid} but it can't be marked done: {(st.stderr or st.stdout).strip()}")
            return 2
        passed.append(fid)
        print(f"PASS task {fid}: {item.get('title', '')} ({len(results)} command(s), {secs}s)")
    if skipped:
        print("skipped: " + "; ".join(skipped))
    return 0


def main():
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252: never crash on "→" or "·"
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--file", default=tm.DEFAULT_FILE)
    p.add_argument("--tag", default="master")
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("plan", help="list open script tasks in order; runs nothing")
    sp.add_argument("--phase", type=int)
    sp.set_defaults(fn=cmd_plan)
    sp = sub.add_parser("run", help="run the checks of open script tasks")
    sp.add_argument("--phase", type=int)
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--only", help="run just this task id")
    g.add_argument("--from", dest="from_id", help="start at this task id")
    sp.set_defaults(fn=cmd_run)
    a = p.parse_args()
    sys.exit(a.fn(a))


if __name__ == "__main__":
    main()
