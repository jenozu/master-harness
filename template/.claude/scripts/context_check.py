#!/usr/bin/env python3
"""Print how big this Claude Code session's context is (Python stdlib only).

    python .claude/scripts/context_check.py [--limit 150000]

Reads this project's session transcripts under ~/.claude/projects (only this project's folder, never another
project's) and sums the token usage of the last main-thread assistant message (input + cache reads + cache writes =
what the model just saw). If the session id is in the environment, only that transcript is read. Otherwise, when
several sessions in this project were active in the last 15 minutes, it reports the largest, so a second window
can make it stop early but never late.
Output, one line: CONTEXT_TOKENS=<n> LIMIT=<n> STATUS=OK|OVER|UNKNOWN. The lead calls it once per finished phase.
Limit: --limit, else env HARNESS_CONTEXT_LIMIT, else 150000.
"""
import argparse, json, os, re
from pathlib import Path


RECENT = 15 * 60


def transcripts(base=None, cwd=None):
    """This project's candidate transcripts (newest first): the current session's if known, else recent ones."""
    base = base or Path.home() / ".claude" / "projects"
    enc = re.sub(r"[^A-Za-z0-9]", "-", str(cwd or Path.cwd()))
    d = base / enc
    if not d.is_dir():
        return []
    for var in ("CLAUDE_SESSION_ID", "CLAUDE_CODE_SESSION_ID"):
        sid = os.environ.get(var)
        if sid and (d / f"{sid}.jsonl").is_file():
            return [d / f"{sid}.jsonl"]
    files = sorted(d.glob("*.jsonl"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not files:
        return []
    newest = files[0].stat().st_mtime
    return [f for f in files if newest - f.stat().st_mtime <= RECENT]


def last_usage(path):
    tokens = None
    with open(path, encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            try:
                m = json.loads(raw)
            except ValueError:
                continue
            if m.get("type") != "assistant" or m.get("isSidechain"):
                continue
            u = (m.get("message") or {}).get("usage") or {}
            n = sum(int(u.get(k) or 0) for k in
                    ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            if n:
                tokens = n
    return tokens


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=int(os.environ.get("HARNESS_CONTEXT_LIMIT", "150000")))
    a = ap.parse_args()
    sizes = [n for n in (last_usage(t) for t in transcripts()) if n is not None]
    n = max(sizes) if sizes else None
    status = "UNKNOWN" if n is None else ("OVER" if n >= a.limit else "OK")
    print(f"CONTEXT_TOKENS={n if n is not None else '?'} LIMIT={a.limit} STATUS={status}")


if __name__ == "__main__":
    main()
