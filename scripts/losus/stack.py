#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 Losus AI LLC
"""Guard and maintain the Losus patch stack on top of Open WebUI.

The stack is every commit between the upstream release tag (e.g. v0.11.4)
and the branch head. Its rules live in .losus/stack.json.

  stack.py check   [--ref REF] [--allow-dropped] [--format text|md]
  stack.py list    [--ref REF]
  stack.py sync    [--ref REF]          rewrite manifest "commits" from git
  stack.py precommit                     git pre-commit hook
  stack.py commitmsg FILE                git commit-msg hook
  stack.py install-hooks                 point git at .losus/hooks

Exit codes: 0 ok, 1 rule violation, 2 usage or git error.
Standard library only (Python 3.9+).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

MANIFEST = Path(".losus/stack.json")
FIXUP_PREFIXES = ("fixup! ", "squash! ", "amend! ")


# ---------- helpers ---------------------------------------------------------

def git(*args: str, check: bool = True) -> str:
    r = subprocess.run(["git", *args], capture_output=True, text=True)
    if check and r.returncode != 0:
        sys.stderr.write(f"git {' '.join(args)} failed:\n{r.stderr}")
        sys.exit(2)
    return r.stdout.strip()


def glob_to_regex(pattern: str) -> re.Pattern:
    """Glob with ** (any depth), * (one segment) and ? support."""
    i, out = 0, ""
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out += r"(?:.*/)?"; i += 3
        elif pattern.startswith("/**", i) and i + 3 == len(pattern):
            out += r"(?:/.*)?"; i += 3
        elif pattern.startswith("**", i):
            out += r".*"; i += 2
        elif pattern[i] == "*":
            out += r"[^/]*"; i += 1
        elif pattern[i] == "?":
            out += r"[^/]"; i += 1
        else:
            out += re.escape(pattern[i]); i += 1
    return re.compile(rf"^{out}$")


def matches(path: str, patterns: list[str]) -> str | None:
    for p in patterns:
        if glob_to_regex(p).match(path):
            return p
    return None


def load_manifest() -> dict:
    if not MANIFEST.exists():
        sys.stderr.write(f"Missing {MANIFEST}. Run from the fork root.\n")
        sys.exit(2)
    m = json.loads(MANIFEST.read_text())
    m.setdefault("prefix", "losus:")
    m.setdefault("max_commits", 5)
    m.setdefault("max_added_lines", 400)
    m.setdefault("budget_exclude", [])
    m.setdefault("allowed_paths", [])
    m.setdefault("denied_paths", [])
    m.setdefault("commits", [])
    return m


def base_tag(ref: str) -> str:
    return git("describe", "--tags", "--abbrev=0", "--match", "v[0-9]*", "--exclude", "*-*", ref)


def stack_commits(base: str, ref: str) -> list[dict]:
    raw = git("log", "--reverse", "--format=%H%x1f%P%x1f%s", f"{base}..{ref}")
    commits = []
    for line in filter(None, raw.splitlines()):
        sha, parents, subject = line.split("\x1f")
        files = git("diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha).splitlines()
        commits.append({"sha": sha, "subject": subject, "merge": len(parents.split()) > 1, "files": files})
    return commits


def path_violations(files: list[str], m: dict) -> list[str]:
    out = []
    for f in files:
        d = matches(f, m["denied_paths"])
        if d:
            out.append(f"{f}  (denied by '{d}': belongs in losus-roster)")
        elif not matches(f, m["allowed_paths"]):
            out.append(f"{f}  (not in allowed_paths)")
    return out


def added_lines(base: str, ref: str, m: dict) -> int:
    total = 0
    for line in git("diff", "--numstat", f"{base}..{ref}").splitlines():
        a, _d, path = line.split("\t", 2)
        if a == "-" or matches(path, m["budget_exclude"]):
            continue
        total += int(a)
    return total


# ---------- commands --------------------------------------------------------

def cmd_check(args) -> int:
    m = load_manifest()
    base = base_tag(args.ref)
    commits = stack_commits(base, args.ref)
    errors, warnings = [], []

    for c in commits:
        short = f"{c['sha'][:8]} {c['subject']}"
        if c["merge"]:
            errors.append(f"{short}: merge commits are not allowed in the stack (rebase instead)")
        if c["subject"].startswith(FIXUP_PREFIXES):
            errors.append(f"{short}: unsquashed fixup (run git rebase -i --autosquash {base})")
        elif not c["subject"].startswith(m["prefix"]):
            errors.append(f"{short}: subject must start with '{m['prefix']}'")
        for v in path_violations(c["files"], m):
            errors.append(f"{short}: {v}")

    actual = [c["subject"] for c in commits]
    listed = [e["subject"] for e in m["commits"]]
    if actual != listed:
        missing = [s for s in listed if s not in actual]
        extra = [s for s in actual if s not in listed]
        if extra:
            errors.append("commits not in manifest: " + "; ".join(extra) + "  (run stack.py sync)")
        if missing:
            msg = "manifest commits missing from history: " + "; ".join(missing)
            (warnings if args.allow_dropped else errors).append(
                msg + ("  (likely absorbed upstream; run stack.py sync before promoting)" if args.allow_dropped else "  (run stack.py sync)"))
        if not extra and not missing:
            errors.append("manifest order differs from history (run stack.py sync)")

    if len(commits) > m["max_commits"]:
        warnings.append(f"{len(commits)} commits exceeds max_commits={m['max_commits']}: squash or upstream some")

    budget = added_lines(base, args.ref, m)
    if budget > m["max_added_lines"]:
        errors.append(f"fork adds {budget} lines outside budget_exclude (max {m['max_added_lines']}): move code into losus-roster packages")

    report(args.format, base, args.ref, commits, budget, m, errors, warnings)
    return 1 if errors else 0


def report(fmt, base, ref, commits, budget, m, errors, warnings):
    ok = not errors
    if fmt == "md":
        print(f"## Losus stack check: {'passed' if ok else 'failed'}\n")
        print(f"Base `{base}` · {len(commits)}/{m['max_commits']} commits · {budget}/{m['max_added_lines']} added lines\n")
        print("| # | Commit | Files |\n|---|---|---|")
        for i, c in enumerate(commits, 1):
            print(f"| {i} | `{c['sha'][:8]}` {c['subject']} | {len(c['files'])} |")
        for title, items in (("Errors", errors), ("Warnings", warnings)):
            if items:
                print(f"\n### {title}\n")
                for e in items:
                    print(f"- {e}")
    else:
        print(f"Losus stack on {base} ({ref}): {len(commits)} commit(s), {budget} added lines")
        for i, c in enumerate(commits, 1):
            print(f"  {i}. {c['sha'][:8]} {c['subject']}")
        for e in warnings:
            print(f"WARN  {e}")
        for e in errors:
            print(f"ERROR {e}")
        print("OK" if ok else "FAILED")


def cmd_list(args) -> int:
    base = base_tag(args.ref)
    for c in stack_commits(base, args.ref):
        print(f"{c['sha'][:8]} {c['subject']}")
        for f in c["files"]:
            print(f"           {f}")
    return 0


def cmd_sync(args) -> int:
    m = load_manifest()
    base = base_tag(args.ref)
    old = {e["subject"]: e for e in m["commits"]}
    new = []
    for c in stack_commits(base, args.ref):
        if c["subject"].startswith(FIXUP_PREFIXES):
            continue
        e = old.get(c["subject"], {"subject": c["subject"], "purpose": "TODO: describe why this fork change exists", "upstreamable": False})
        e["paths"] = sorted(f for f in c["files"] if f != str(MANIFEST))
        new.append(e)
    dropped = [s for s in old if s not in {e["subject"] for e in new}]
    m["commits"] = new
    MANIFEST.write_text(json.dumps(m, indent=2) + "\n")
    print(f"Manifest now lists {len(new)} commit(s).")
    for s in dropped:
        print(f"Removed (no longer in history): {s}")
    todo = [e["subject"] for e in new if e.get("purpose", "").startswith("TODO")]
    for s in todo:
        print(f"Needs a purpose: {s}")
    print("Commit the manifest change with: git commit --amend --no-edit  (or a fixup of the owning commit)")
    return 0


def cmd_precommit(_args) -> int:
    m = load_manifest()
    staged = git("diff", "--cached", "--name-only", "--diff-filter=ACMRD").splitlines()
    bad = path_violations(staged, m)
    if bad:
        print("Losus pre-commit: these staged paths can't be committed to the fork:")
        for b in bad:
            print(f"  {b}")
        print("Package code goes in the losus-roster repo. Unstage with: git restore --staged <path>")
        print("If a new fork-glue path is truly needed, add it to allowed_paths in .losus/stack.json.")
        return 1
    return 0


def cmd_commitmsg(args) -> int:
    m = load_manifest()
    subject = Path(args.file).read_text().splitlines()[0] if Path(args.file).read_text() else ""
    s = subject
    while s.startswith(FIXUP_PREFIXES):
        s = s.split(" ", 1)[1]
    if not s.startswith(m["prefix"]):
        print(f"Losus commit-msg: subject must start with '{m['prefix']}' (got: {subject!r})")
        return 1
    return 0


def cmd_install_hooks(_args) -> int:
    git("config", "core.hooksPath", ".losus/hooks")
    for h in Path(".losus/hooks").glob("*"):
        h.chmod(0o755)
    print("Git hooks installed from .losus/hooks")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Losus patch-stack guard")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check"); c.add_argument("--ref", default="HEAD")
    c.add_argument("--allow-dropped", action="store_true"); c.add_argument("--format", choices=["text", "md"], default="text")
    c.set_defaults(fn=cmd_check)
    l = sub.add_parser("list"); l.add_argument("--ref", default="HEAD"); l.set_defaults(fn=cmd_list)
    s = sub.add_parser("sync"); s.add_argument("--ref", default="HEAD"); s.set_defaults(fn=cmd_sync)
    sub.add_parser("precommit").set_defaults(fn=cmd_precommit)
    cm = sub.add_parser("commitmsg"); cm.add_argument("file"); cm.set_defaults(fn=cmd_commitmsg)
    sub.add_parser("install-hooks").set_defaults(fn=cmd_install_hooks)
    a = p.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
