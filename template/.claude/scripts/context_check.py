#!/usr/bin/env python3
"""Print how big this Claude Code session's context is (Python stdlib only).

    python .claude/scripts/context_check.py [--limit 150000]

Reads the newest top-level session transcript for this project under ~/.claude/projects and sums the token usage
of the last main-thread assistant message (input + cache reads + cache writes = what the model just saw).
Output, one line: CONTEXT_TOKENS=<n> LIMIT=<n> STATUS=OK|OVER|UNKNOWN. The lead calls it once per finished phase.
Limit: --limit, else env HARNESS_CONTEXT_LIMIT, else 150000.
"""
import argparse, json, os, re
from pathlib import Path


def newest_transcript():
    base = Path.home() / ".claude" / "projects"
    if not base.is_dir():
        return None
    enc = re.sub(r"[^A-Za-z0-9]", "-", str(Path.cwd()))
    dirs = [d for d in base.iterdir() if d.is_dir() and d.name == enc] or [d for d in base.iterdir() if d.is_dir()]
    files = [f for d in dirs for f in d.glob("*.jsonl")]
    return max(files, key=lambda f: f.stat().st_mtime) if files else None


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
    t = newest_transcript()
    n = last_usage(t) if t else None
    status = "UNKNOWN" if n is None else ("OVER" if n >= a.limit else "OK")
    print(f"CONTEXT_TOKENS={n if n is not None else '?'} LIMIT={a.limit} STATUS={status}")


if __name__ == "__main__":
    main()
