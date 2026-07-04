#!/usr/bin/env python3
"""Ensure a Cloud Build trigger's top-level `ignoredFiles` contains given globs.

Used by configure-deploy-trigger.{sh,bat}. Dependency-free (stdlib only): it
rewrites the exported trigger YAML by removing any existing top-level
`ignoredFiles:` block and appending a fresh one. Safe to run repeatedly.

Usage:  python3 _deploy_trigger_ignore.py <trigger.yaml> "glob1,glob2,..."
"""
import sys


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: python3 _deploy_trigger_ignore.py <trigger.yaml> <comma_separated_globs>")
        return 2
    path = sys.argv[1]
    patterns = [p.strip() for p in sys.argv[2].split(",") if p.strip()]
    if not patterns:
        print("No patterns provided; nothing to do.")
        return 0

    with open(path, "r", encoding="utf-8") as fh:
        lines = fh.read().split("\n")

    out, i, n = [], 0, len(lines)
    while i < n:
        line = lines[i]
        if line.startswith("ignoredFiles:"):
            i += 1  # skip the key line and its list items / indented block
            while i < n and (lines[i].lstrip().startswith("- ")
                             or (lines[i].startswith(" ") and lines[i].strip())):
                i += 1
            continue
        out.append(line)
        i += 1

    while out and out[-1].strip() == "":
        out.pop()
    out.append("ignoredFiles:")
    for p in patterns:
        out.append("- '%s'" % p)
    out.append("")

    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))
    print("Set ignoredFiles -> %s" % ", ".join(patterns))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
