#!/usr/bin/env python3
"""Run the plan phase after phase, each in a FRESH Claude Code session (Python stdlib only).

    python .claude/scripts/run-phases.py [--max-runs 20] [--claude-args "--dangerously-skip-permissions"]

Each run is `claude -p "/run-phase"` in a new process, so the lead's context never grows from one phase to the
next; all state lives in .taskmaster/ and memory.md. Stops when nothing is left or workable, when two runs in a
row finish no task, or after --max-runs. Logs: .claude/tmp/run-phases-<n>.log. Sets HARNESS_LOOP=1 so the lead
ends its turn after each phase instead of continuing in the same session.
"""
import argparse, json, os, shlex, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TASKS = ROOT / ".taskmaster" / "tasks" / "tasks.json"


def done_count():
    data = json.loads(TASKS.read_text(encoding="utf-8"))
    n = 0
    for tag in data.values():
        for t in tag.get("tasks", []):
            n += t.get("status") == "done"
            n += sum(s.get("status") == "done" for s in t.get("subtasks", []))
    return n


def next_line():
    out = subprocess.run([sys.executable, str(ROOT / ".taskmaster" / "tasks.py"), "status"],
                         cwd=ROOT, capture_output=True, text=True).stdout
    return next((l for l in out.splitlines() if l.startswith("next:")), "next: ?")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-runs", type=int, default=20)
    ap.add_argument("--claude-cmd", default="claude")
    ap.add_argument("--claude-args", default="", help="extra flags, e.g. --dangerously-skip-permissions")
    ap.add_argument("--prompt", default="/run-phase")
    a = ap.parse_args()
    (ROOT / ".claude" / "tmp").mkdir(parents=True, exist_ok=True)
    stuck = 0
    for i in range(1, a.max_runs + 1):
        nl = next_line()
        if nl.startswith(("next: nothing left", "next: nothing is workable")):
            print(f"stop: {nl}")
            break
        before = done_count()
        log = ROOT / ".claude" / "tmp" / f"run-phases-{i}.log"
        print(f"run {i}: {nl}")
        cmd = shlex.split(a.claude_cmd) + ["-p", a.prompt] + shlex.split(a.claude_args)
        with open(log, "w", encoding="utf-8") as fh:
            rc = subprocess.run(cmd, cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT,
                                env={**os.environ, "HARNESS_LOOP": "1"}).returncode
        after = done_count()
        print(f"  exit {rc}, tasks done {before} -> {after}, log {log.name}")
        stuck = stuck + 1 if after == before else 0
        if stuck >= 2:
            print("stop: two runs in a row finished nothing. Read the last log and "
                  ".taskmaster/docs/human-checklist.md.")
            break
    else:
        print("stop: --max-runs reached; run again to continue.")


if __name__ == "__main__":
    main()
