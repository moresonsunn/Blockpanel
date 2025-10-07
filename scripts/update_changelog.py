#!/usr/bin/env python3
"""Append a new CHANGELOG section based on commits since previous tag.

If no earlier tag exists, uses initial commit boundary.
Simple heuristic (no full conventional commit parsing yet).
"""
from __future__ import annotations
import subprocess
import argparse
from pathlib import Path
import re
from datetime import datetime

SECTION_TEMPLATE = """## {version} - {date}

{body}

"""

def run(cmd: list[str]) -> str:
    r = subprocess.run(cmd, capture_output=True, text=True, check=False)
    if r.returncode != 0:
        return ''
    return r.stdout.strip()

def get_last_tag() -> str | None:
    tags = run(["git", "tag", "--list", "v*"]).splitlines()
    tags = [t.strip() for t in tags if t.strip()]
    if not tags:
        return None
    # sort semantic-ish by version weight (fallback lexical)
    try:
        tags.sort(key=lambda s: [int(x) if x.isdigit() else x for x in re.split(r'[._-]', s.lstrip('v'))])
    except Exception:
        tags.sort()
    return tags[-1]

def collect_commits(since: str | None) -> list[str]:
    if since:
        log_range = f"{since}..HEAD"
    else:
        log_range = "HEAD"
    raw = run(["git", "log", log_range, "--pretty=%s"])
    if not raw:
        return []
    lines = [l.strip() for l in raw.splitlines() if l.strip()]
    # Filter out merge commits noise but keep descriptive merges
    cleaned = []
    for l in lines:
        if l.lower().startswith('merge branch'):
            continue
        cleaned.append(l)
    return cleaned

def categorize(lines: list[str]) -> str:
    if not lines:
        return "No changes recorded."
    buckets = {"Features": [], "Bug Fixes": [], "Tweaks": [], "Other": []}
    for l in lines:
        low = l.lower()
        if low.startswith("feat"):
            buckets["Features"].append(l)
        elif low.startswith("fix") or "bug" in low:
            buckets["Bug Fixes"].append(l)
        elif any(k in low for k in ("refactor", "tweak", "perf", "chore")):
            buckets["Tweaks"].append(l)
        else:
            buckets["Other"].append(l)
    parts = []
    for k in ["Features", "Bug Fixes", "Tweaks", "Other"]:
        if buckets[k]:
            parts.append(f"### {k}\n" + "\n".join(f"- {x}" for x in buckets[k]) + "\n")
    return "\n".join(parts).rstrip() + "\n"

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--version', required=True)
    ap.add_argument('--write', action='store_true', help='Append to CHANGELOG.md')
    args = ap.parse_args()

    last = get_last_tag()
    commits = collect_commits(last)
    body = categorize(commits)
    section = SECTION_TEMPLATE.format(version=args.version, date=datetime.utcnow().strftime('%Y-%m-%d'), body=body)

    cl_path = Path('CHANGELOG.md')
    if args.write:
        original = cl_path.read_text() if cl_path.exists() else "# Changelog\n\nAll notable changes will be documented here.\n\n"
        # Prepend new section after header
        if original.startswith('# Changelog'):
            parts = original.split('\n', 2)
            if len(parts) >= 3:
                header = '\n'.join(parts[:2]) + '\n'
                rest = parts[2]
                updated = header + '\n' + section + rest
            else:
                updated = original + '\n' + section
        else:
            updated = section + original
        cl_path.write_text(updated)
        print(f"Appended section for {args.version} to CHANGELOG.md (commits={len(commits)})")
    else:
        print(section)

if __name__ == '__main__':
    main()
