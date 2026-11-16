#!/usr/bin/env python3
"""Decide whether a phase's pull request may be merged, and merge it if so (Python stdlib only).

The only way the harness merges. Run from the repo root:

  python .claude/scripts/merge_gate.py --pr <n> --wait --merge   # wait for CI, decide, merge if allowed
  python .claude/scripts/merge_gate.py --pr <n>                  # decide only

Reads .claude/harness.json **as committed on the default branch** (merge mode, merging deploys, require_ci, safe
paths; a work branch can't loosen its own rules), the PR's changed files, the task list (queued human steps),
.taskmaster/docs/manual-checks.md (open eyes-on checks) and CI: both GitHub check runs and classic commit statuses
(some services, e.g. preview deploys, report only the latter). A PR that changes the gate's own config, the
harness scripts, settings.json or CI workflows always waits for the owner.

First line of output is DECISION=<value>; exit code matches:
  0 MERGED / MERGE (decide-only)   merged, or (without --merge) allowed
  1 FIX_CI         a check failed: fix it through the builder ladder (failing checks and log commands printed)
  3 OWNER          the owner has to merge (or do something first); reasons printed, one per line
  4 CI_TIMEOUT     CI still running after ci_wait_minutes: nothing merged
  2 ERROR          could not work it out (no gh, no remote, bad arguments): nothing merged
Testing/offline (decide only, never with --merge): --ci green|pending|red|none and --files a,b,c skip GitHub.
"""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path.cwd()
CONFIG_PATH = ".claude/harness.json"
TASKS = ROOT / ".taskmaster" / "tasks" / "tasks.json"
MANUAL = ROOT / ".taskmaster" / "docs" / "manual-checks.md"
MODES = ("auto", "safe-only", "owner")
RED = {"failure", "timed_out", "cancelled", "action_required", "startup_failure", "stale"}
EXIT = {"MERGED": 0, "MERGE": 0, "FIX_CI": 1, "ERROR": 2, "OWNER": 3, "CI_TIMEOUT": 4}
# Changing any of these changes what the gate allows or what CI checks: the owner reviews it, whatever the mode.
PROTECTED = [".claude/harness.json", ".claude/settings.json", ".claude/scripts/**", ".github/**"]
POLL = float(__import__("os").environ.get("HARNESS_GATE_POLL_SECONDS", "25"))


def out(decision, lines=()):
    print(f"DECISION={decision}")
    for ln in lines:
        print(ln)
    sys.exit(EXIT[decision])


def git(*args):
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                              errors="replace")
    except OSError:
        return None


def ref_exists(ref):
    r = git("rev-parse", "--verify", "-q", f"{ref}^{{commit}}")
    return r is not None and r.returncode == 0


def base_ref(base=None):
    """The default branch as git knows it: the PR's base on origin, origin/HEAD, then main/master."""
    cands = []
    if base:
        cands.append(f"origin/{base}")
        if not ref_exists(cands[0]):
            git("fetch", "-q", "origin", base)
    r = git("symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    if r is not None and r.returncode == 0 and r.stdout.strip():
        cands.append(r.stdout.strip())
    cands += ["origin/main", "origin/master"] + ([base] if base else []) + ["main", "master"]
    return next((c for c in cands if ref_exists(c)), None)


def load_config(base=None):
    """harness.json as committed on the default branch, never the work tree's copy (an agent could edit that)."""
    ref = base_ref(base)
    if ref is None:
        return None, ["can't find the default branch to read .claude/harness.json from, so the owner merges"]
    r = git("show", f"{ref}:{CONFIG_PATH}")
    if r is None or r.returncode != 0:
        return None, [f"no {CONFIG_PATH} on {ref}, so the owner merges (merge the harness setup first)"]
    try:
        cfg = json.loads(r.stdout)
    except ValueError as e:
        return None, [f"{CONFIG_PATH} on {ref} is not valid JSON ({e}), so the owner merges"]
    if not isinstance(cfg, dict) or cfg.get("merge") not in MODES:
        return None, [f"{CONFIG_PATH} merge must be one of {', '.join(MODES)}, so the owner merges"]
    return cfg, []


def require_ci(cfg):
    return bool(cfg.get("require_ci", cfg.get("merge_deploys", False)))


def glob_re(pattern):
    """Path glob to regex: ** = any folders, * = within one folder, ? = one character."""
    i, rx = 0, ""
    while i < len(pattern):
        if pattern.startswith("**/", i):
            rx, i = rx + "(?:.*/)?", i + 3
        elif pattern.startswith("**", i):
            rx, i = rx + ".*", i + 2
        elif pattern[i] == "*":
            rx, i = rx + "[^/]*", i + 1
        elif pattern[i] == "?":
            rx, i = rx + "[^/]", i + 1
        else:
            rx, i = rx + re.escape(pattern[i]), i + 1
    return re.compile(rx + r"\Z")


def matches(path, patterns):
    return any(glob_re(p).match(path) for p in patterns)


def is_safe(path, cfg):
    if matches(path, PROTECTED):
        return False
    safe = cfg.get("safe_paths", [])
    if path in [p for p in safe if not any(c in p for c in "*?")]:
        return True
    return matches(path, safe) and not matches(path, cfg.get("never_auto_paths", []))


def queued_human_steps():
    """Open queued human steps; a task list that can't be read counts as one (fail closed)."""
    if not TASKS.exists():
        return []
    try:
        data = json.loads(TASKS.read_text(encoding="utf-8"))
        tasks = data["master"]["tasks"]
        if not isinstance(tasks, list):
            raise ValueError("tasks is not a list")
    except (ValueError, KeyError, TypeError) as e:
        return [f"(tasks.json can't be read: {e}; fix it with tasks.py validate)"]
    found = []
    for t in tasks:
        if not isinstance(t, dict):
            continue
        for item, parent in [(t, None)] + [(s, t) for s in t.get("subtasks", [])]:
            human = item.get("human") or (parent or {}).get("human")
            status = (item.get("status") or "pending").lower()
            if human and item.get("queued") and status in ("pending", "in-progress", "review"):
                fid = f"{t['id']}.{item['id']}" if parent else str(t["id"])
                found.append(f"{fid} {item.get('title', '')}")
    return found


def open_eyes_on():
    if not MANUAL.exists():
        return []
    section, items = None, []
    for line in MANUAL.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            section = line[3:].strip().lower()
        elif line.startswith("### ") and section and section.startswith("eyes-on"):
            items.append(line[4:].strip())
    return items


def blockers(cfg, files, ci="green"):
    """Reasons the owner has to merge. Empty list = agents may merge (once CI is green)."""
    why = []
    prot = [f for f in files if matches(f, PROTECTED)]
    if prot:
        why.append("this PR changes the merge rules, harness scripts, settings or CI, which the owner reviews: "
                   + ", ".join(prot[:8]))
    if ci == "none" and require_ci(cfg):
        why.append("require_ci is on and this PR has no CI checks: nothing proves it works (add a CI workflow "
                   "that runs on pull_request, or the owner merges)")
    if cfg["merge"] == "owner":
        why.append("merge mode is owner: the owner merges every PR")
    elif cfg["merge"] == "safe-only":
        unsafe = [f for f in files if not is_safe(f, cfg)]
        if unsafe:
            more = f" (+{len(unsafe) - 8} more)" if len(unsafe) > 8 else ""
            why.append("merge mode is safe-only and this PR changes app or config files: "
                       + ", ".join(unsafe[:8]) + more)
    if cfg.get("merge_deploys"):
        for step in queued_human_steps():
            why.append(f"merging deploys, and human step {step} isn't done yet (code was built around it)")
        eyes = open_eyes_on()
        if eyes:
            why.append(f"merging deploys, and {len(eyes)} eyes-on check(s) are open in manual-checks.md: "
                       + "; ".join(eyes[:3]))
    return why


# ---------- GitHub (REST only: GraphQL is blocked in Claude Code sessions) ----------

def gh(*args, method=None):
    cmd = ["gh", "api"] + (["-X", method] if method else []) + list(args)
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:
        return None, str(e)
    if p.returncode != 0:
        return None, (p.stderr or p.stdout).strip()
    try:
        return (json.loads(p.stdout) if p.stdout.strip() else {}), ""
    except ValueError:
        return p.stdout, ""


def repo_slug():
    r = git("remote", "get-url", "origin")
    if r is None:
        return None
    url = r.stdout.strip()
    m = re.search(r"github\.com[:/]([^/]+)/([^/]+?)(?:\.git)?/?$", url)
    return f"{m.group(1)}/{m.group(2)}" if m else None


def ci_state(check_runs, status):
    """(state, failing names) from the check-runs and combined-status API payloads."""
    runs = (check_runs or {}).get("check_runs", [])
    statuses = (status or {}).get("statuses", [])
    failing = [r.get("name", "?") for r in runs if r.get("status") == "completed" and r.get("conclusion") in RED]
    failing += [s.get("context", "?") for s in statuses if s.get("state") in ("failure", "error")]
    if failing:
        return "red", failing
    if any(r.get("status") != "completed" for r in runs) or any(s.get("state") == "pending" for s in statuses):
        return "pending", []
    return ("green" if runs or statuses else "none"), []


def has_workflows():
    wf = ROOT / ".github" / "workflows"
    return wf.is_dir() and any(f.suffix in (".yml", ".yaml") for f in wf.iterdir())


def fetch_ci(slug, sha):
    runs, err = gh(f"repos/{slug}/commits/{sha}/check-runs?per_page=100")
    if runs is None:
        return None, [], err
    status, err = gh(f"repos/{slug}/commits/{sha}/status")
    if status is None:
        return None, [], err
    state, failing = ci_state(runs, status)
    jobs = [f"  log: gh api repos/{slug}/actions/jobs/{r['id']}/logs | tail -40   ({r.get('name')})"
            for r in runs.get("check_runs", []) if r.get("conclusion") in RED and r.get("id")]
    return state, failing, jobs


def merge(slug, pr, branch):
    """Merge through the REST API. GitHub's REST API can't turn on auto-merge (only GraphQL can, and GraphQL is
    blocked in Claude Code sessions), so a merge that branch protection refuses goes to the owner."""
    last = ""
    for method in ("squash", "merge", "rebase"):
        res, err = gh(f"repos/{slug}/pulls/{pr}/merge", "-f", f"merge_method={method}", method="PUT")
        if res is not None:
            if branch:
                gh(f"repos/{slug}/git/refs/heads/{branch}", method="DELETE")
            return "MERGED", [f"merged PR #{pr} ({method})"]
        last = err
        if "not allowed" not in err.lower():
            break
    low = last.lower()
    if "405" in last or "review" in low or "protect" in low or "required" in low:
        return "OWNER", [f"REASON: branch protection refused the merge (a required review or check): the owner "
                         f"merges PR #{pr}, or turns on auto-merge for it on GitHub. GitHub said: {last[:200]}"]
    return "OWNER", [f"REASON: GitHub refused the merge: {last[:300]}"]


def wait_for_ci(cfg, slug, sha, wait):
    """Poll CI. Workflows that exist but never report on the PR (e.g. they run only on push to main) count as no
    CI once ci_start_minutes have passed, instead of 'still running' until the timeout."""
    t0 = time.monotonic()
    deadline = 60 * float(cfg.get("ci_wait_minutes", 20))
    grace = 60 * float(cfg.get("ci_start_minutes", 3))
    while True:
        state, failing, jobs = fetch_ci(slug, sha)
        if state is None:
            out("ERROR", [f"can't read CI status: {str(jobs)[:300]}"])
        elapsed = time.monotonic() - t0
        if state == "none" and has_workflows() and elapsed < min(grace, deadline):
            state = "pending"  # workflows exist; give them time to report
            if not wait:
                return state, failing, jobs, []
        if state != "pending" or not wait or elapsed > deadline:
            note = ([f"no CI check reported on this PR within {cfg.get('ci_start_minutes', 3)} minutes "
                     "(do the workflows run on pull_request?): treated as no CI"]
                    if state == "none" and has_workflows() else [])
            return state, failing, jobs, note
        time.sleep(POLL)


def main():
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to cp1252: never crash on "→" or "·"
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pr", type=int, help="pull request number")
    ap.add_argument("--wait", action="store_true", help="poll CI until it finishes (up to ci_wait_minutes)")
    ap.add_argument("--merge", action="store_true", help="merge if the decision is MERGE")
    ap.add_argument("--ci", choices=["green", "pending", "red", "none"], help="offline: use this CI state")
    ap.add_argument("--files", help="offline: comma-separated changed files")
    a = ap.parse_args()
    try:
        decide(a)
    except Exception as e:  # anything unexpected is ERROR (exit 2), never FIX_CI (exit 1)
        out("ERROR", [f"merge_gate.py failed: {type(e).__name__}: {e}"])


def decide(a):
    if a.merge and (a.ci or a.files is not None):
        out("ERROR", ["--ci and --files are for offline testing only and can't be combined with --merge"])

    slug = None if (a.ci and a.files is not None) else repo_slug()
    pr_info = {}
    if a.pr and slug:
        pr_info, err = gh(f"repos/{slug}/pulls/{a.pr}")
        if pr_info is None:
            out("ERROR", [f"can't read PR #{a.pr}: {err[:300]}"])
        if pr_info.get("merged"):
            out("MERGED", [f"PR #{a.pr} is already merged"])
        if pr_info.get("state") != "open":
            out("ERROR", [f"PR #{a.pr} is {pr_info.get('state')}"])

    cfg, cfg_errors = load_config((pr_info.get("base") or {}).get("ref"))
    if cfg is None:
        out("OWNER", ["REASON: " + e for e in cfg_errors])

    if a.files is not None:
        files = [f.strip() for f in a.files.split(",") if f.strip()]
    elif slug and a.pr:
        listed, err = gh(f"repos/{slug}/pulls/{a.pr}/files?per_page=100")
        if listed is None:
            out("ERROR", [f"can't list PR files: {err[:300]}"])
        files = [f["filename"] for f in listed]
        if len(files) >= 100:
            files.append("(more than 100 files: treated as unsafe)")
    else:
        out("ERROR", ["need --pr (and a GitHub origin remote), or --files and --ci for an offline decision"])

    notes = []
    if a.ci:
        state, failing, jobs = a.ci, (["(offline)"] if a.ci == "red" else []), []
    else:
        sha = (pr_info.get("head") or {}).get("sha")
        if not slug or not sha:
            out("ERROR", ["can't find the PR's head commit"])
        state, failing, jobs, notes = wait_for_ci(cfg, slug, sha, a.wait)

    if state == "red":
        out("FIX_CI", ["failing: " + ", ".join(failing)] + list(jobs))
    if state == "pending":
        out("CI_TIMEOUT", [f"CI still running after {cfg.get('ci_wait_minutes', 20)} minutes; nothing merged"])

    why = blockers(cfg, files, state)
    if why:
        out("OWNER", ["REASON: " + w for w in why] + notes)
    if not a.merge:
        out("MERGE", [f"allowed: merge mode {cfg['merge']}, CI {state}"] + notes)
    if not slug or not a.pr:
        out("ERROR", ["--merge needs --pr and a GitHub origin remote"])
    branch = (pr_info.get("head") or {}).get("ref")
    decision, lines = merge(slug, a.pr, branch)
    out(decision, lines + notes)


if __name__ == "__main__":
    main()
