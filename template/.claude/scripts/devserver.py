#!/usr/bin/env python3
"""Start/stop dev servers in the background with logs in files (Python stdlib only).

Config: .claude/dev-servers.json, a list of
  {"name": "api", "cwd": "backend", "cmd": "...", "cmd_windows": "... (optional)", "health": "http://localhost:8000/"}
Run from the repo root:
  python .claude/scripts/devserver.py start [name|all]
  python .claude/scripts/devserver.py stop [name|all]
  python .claude/scripts/devserver.py status
  python .claude/scripts/devserver.py logs <name> [-n 30]
Logs: .claude/tmp/logs/<name>.log   PIDs: .claude/tmp/<name>.pid
Exit codes: 0 ok, 1 failed, 2 usage/config error, 3 port busy (server not started by this script).
"""
import argparse
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / ".claude" / "dev-servers.json"
TMP = ROOT / ".claude" / "tmp"
LOGS = TMP / "logs"
WINDOWS = os.name == "nt"


def die(msg, code=2):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


def servers():
    if not CONFIG.exists():
        die(f"{CONFIG.relative_to(ROOT)} not found: define your dev servers there first")
    try:
        data = json.loads(CONFIG.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"{CONFIG.name} is not valid JSON: {e}")
    if not isinstance(data, list):
        die(f"{CONFIG.name} must be a JSON list")
    return {s["name"]: s for s in data}


def pick(all_servers, name):
    if name in (None, "all"):
        return list(all_servers.values())
    if name not in all_servers:
        die(f"unknown server '{name}' (have: {', '.join(all_servers) or 'none'})")
    return [all_servers[name]]


def healthy(url, timeout=2.0):
    if not url:
        return False
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status < 500
    except urllib.error.HTTPError as e:
        return e.code < 500
    except Exception:
        return False


def pid_file(name):
    return TMP / f"{name}.pid"


def read_pid(name):
    try:
        return int(pid_file(name).read_text().strip())
    except (OSError, ValueError):
        return None


def alive(pid):
    if pid is None:
        return False
    if WINDOWS:
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"], capture_output=True, text=True)
        return str(pid) in out.stdout
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def start(s, wait):
    name = s["name"]
    pid = read_pid(name)
    if alive(pid):
        print(f"{name}: already running (pid {pid}, started by devserver.py)")
        return 0
    if healthy(s.get("health")):
        print(f"{name}: BUSY - {s.get('health')} already answers but devserver.py didn't start it. "
              f"Use that server, or stop it yourself. Not touching it.")
        return 3
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"{name}.log"
    cmd = s.get("cmd_windows") if WINDOWS and s.get("cmd_windows") else s.get("cmd")
    if not cmd:
        die(f"{name}: no cmd in config")
    cwd = ROOT / s.get("cwd", ".")
    log = open(log_path, "w", encoding="utf-8", errors="replace")
    kwargs = dict(cwd=str(cwd), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, shell=True)
    if WINDOWS:
        kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP | 0x00000008  # DETACHED_PROCESS
    else:
        kwargs["start_new_session"] = True
    proc = subprocess.Popen(cmd, **kwargs)
    pid_file(name).write_text(str(proc.pid))
    if not s.get("health"):
        print(f"{name}: started (pid {proc.pid}, no health URL to wait on), log {log_path.relative_to(ROOT)}")
        return 0
    deadline = time.time() + wait
    while time.time() < deadline:
        if proc.poll() is not None:
            print(f"{name}: EXITED with code {proc.returncode}. Last log lines:")
            tail(log_path, 20)
            pid_file(name).unlink(missing_ok=True)
            return 1
        if healthy(s["health"]):
            print(f"{name}: up at {s['health']} (pid {proc.pid}), log {log_path.relative_to(ROOT)}")
            return 0
        time.sleep(1)
    print(f"{name}: no answer from {s['health']} after {wait}s (still running, pid {proc.pid}). Last log lines:")
    tail(log_path, 20)
    return 1


def stop(s):
    name = s["name"]
    pid = read_pid(name)
    if not alive(pid):
        pid_file(name).unlink(missing_ok=True)
        print(f"{name}: not running (nothing started by devserver.py)")
        return 0
    if WINDOWS:
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], capture_output=True)
    else:
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            pass
        for _ in range(10):
            if not alive(pid):
                break
            time.sleep(0.5)
        if alive(pid):
            try:
                os.killpg(pid, signal.SIGKILL)
            except OSError:
                pass
    pid_file(name).unlink(missing_ok=True)
    print(f"{name}: stopped (pid {pid})")
    return 0


def status(all_servers):
    for s in all_servers.values():
        pid = read_pid(s["name"])
        mine = alive(pid)
        up = healthy(s.get("health"))
        who = f"started by devserver.py, pid {pid}" if mine else ("running, NOT started by devserver.py" if up else "-")
        print(f"{s['name']}: {'up' if up else 'down'} ({who}) {s.get('health', '')}")
    return 0


def tail(path, n):
    try:
        lines = Path(path).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        print("(no log)")
        return
    for line in lines[-n:]:
        print(line[:300])


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sp = sub.add_parser("start")
    sp.add_argument("name", nargs="?")
    sp.add_argument("--wait", type=int, default=60)
    sp = sub.add_parser("stop")
    sp.add_argument("name", nargs="?")
    sub.add_parser("status")
    sp = sub.add_parser("logs")
    sp.add_argument("name")
    sp.add_argument("-n", type=int, default=30)
    a = p.parse_args()
    all_servers = servers()
    if a.cmd == "status":
        sys.exit(status(all_servers))
    if a.cmd == "logs":
        pick(all_servers, a.name)
        tail(LOGS / f"{a.name}.log", a.n)
        return
    codes = [start(s, a.wait) if a.cmd == "start" else stop(s) for s in pick(all_servers, a.name)]
    sys.exit(max(codes) if codes else 0)


if __name__ == "__main__":
    main()
