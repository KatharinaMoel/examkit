#!/usr/bin/env python3
"""Fail when a tracked path is exam content: anything under exams/ except exams/.gitkeep,
any sources/ directory except example/sources/, any build/ directory.

Usage: git ls-files | python3 engine/check_tracked.py
Paths git quotes (non-ASCII, default core.quotePath) are unquoted first; the workflow also passes -c core.quotepath=off.
Exit 1 and the offending paths on stderr; "ok" on stdout otherwise.
"""
import sys

ALLOWED = {"exams/.gitkeep"}


def forbidden(path):
    if path in ALLOWED:
        return False
    parts = path.split("/")
    dirs = parts[:-1]
    if parts[0] == "exams":
        return True
    if "build" in dirs:
        return True
    if "sources" in dirs and not path.startswith("example/sources/"):
        return True
    return False


def main():
    paths = [line.strip() for line in sys.stdin if line.strip()]
    paths = [p[1:-1] if len(p) >= 2 and p[0] == p[-1] == '"' else p for p in paths]
    bad = [p for p in paths if forbidden(p)]
    if bad:
        print("tracked files that must never enter the repository:", file=sys.stderr)
        for p in bad:
            print("  " + p, file=sys.stderr)
        sys.exit(1)
    print(f"ok: {len(paths)} tracked files, no exam content, sources or build output")


if __name__ == "__main__":
    main()
