#!/usr/bin/env python3
"""Regenerate the status board's numbers from a REAL test sweep.

The dashboard used to carry hand-typed counts, which is a standing invitation to drift — and it
did drift. This derives every number by actually running the suites, so the public page cannot
claim a test total the code doesn't back.

Run from a workspace where ../repos holds the suite:
    python3 tools/refresh-dashboard.py [--check]

--check makes no edits and exits 1 if the page is out of date (use it as a CI/pre-push gate).
"""
import argparse
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
REPOS = ROOT / "repos"
PAGE = pathlib.Path(__file__).resolve().parents[1] / "dashboard.html"
NON_TOOL_REPOS = 2  # the site itself + the org .github repo


def count_tests(repo: pathlib.Path):
    """Return the passing-test count for a repo, or None if it has no suite."""
    if (repo / "package.json").exists():
        out = subprocess.run(["node", "--test"], cwd=repo, capture_output=True, text=True).stdout
        m = re.search(r"^# pass (\d+)", out, re.M)
        fail = re.search(r"^# fail (\d+)", out, re.M)
        if fail and fail.group(1) != "0":
            raise SystemExit(f"RED: {repo.name} has failing tests — refusing to publish numbers")
        return int(m.group(1)) if m else None
    if (repo / "pyproject.toml").exists():
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                           cwd=repo, capture_output=True, text=True,
                           env={"PYTHONPATH": "src", "PATH": "/usr/bin:/bin:/usr/local/bin"})
        blob = r.stdout + r.stderr
        if not re.search(r"^OK", blob, re.M):
            raise SystemExit(f"RED: {repo.name} has failing tests — refusing to publish numbers")
        m = re.search(r"^Ran (\d+) test", blob, re.M)
        return int(m.group(1)) if m else None
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="verify only; exit 1 if stale")
    args = ap.parse_args()

    counts = {}
    for repo in sorted(p for p in REPOS.iterdir() if p.is_dir() and not p.name.startswith(".")):
        n = count_tests(repo)
        if n is not None:
            counts[repo.name] = n

    total = sum(counts.values())
    public = len(counts) + NON_TOOL_REPOS
    html = original = PAGE.read_text()

    for name, n in counts.items():
        html = re.sub(rf"(name:'{re.escape(name)}',mod:'[a-z]+',tests:)\d+", rf"\g<1>{n}", html)

    def stat(doc, label, value):
        return re.sub(rf'(data-count=")\d+("\s*>)\d+(</div><div class="l">{label})',
                      rf"\g<1>{value}\g<2>{value}\g<3>", doc)

    html = stat(html, "tests passing", total)
    html = stat(html, "public repos", public)

    print(f"swept {len(counts)} repos · {total} tests · {public} public repos")
    for name, n in sorted(counts.items()):
        print(f"  {name:28} {n}")

    if html == original:
        print("dashboard already accurate ✓")
        return 0
    if args.check:
        print("STALE: dashboard numbers do not match the code", file=sys.stderr)
        return 1
    PAGE.write_text(html)
    print("dashboard updated ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
