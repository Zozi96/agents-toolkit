#!/usr/bin/env python3
"""
diff_summary.py

Summarizes Git changes without dumping full diffs.

Examples:
  python diff_summary.py
  python diff_summary.py --base main
  python diff_summary.py --staged
"""

from __future__ import annotations

import argparse
import os
import subprocess
from dataclasses import dataclass

from _agent_utils import redact_text, truncate, truncate_line


@dataclass
class FileChange:
    path: str
    status: str
    additions: int = 0
    deletions: int = 0
    source: str = ""

    @property
    def total(self) -> int:
        return self.additions + self.deletions


def run_git(repo: str, args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", "-C", repo, *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip() or "git command failed"
        raise SystemExit(f"Error: {truncate_line(redact_text(message), 240)}")
    return result


def repo_root(path: str) -> str:
    result = run_git(path, ["rev-parse", "--show-toplevel"])
    return result.stdout.strip()


def parse_int(value: str) -> int:
    return 0 if value == "-" else int(value or "0")


def parse_numstat(repo: str, diff_args: list[str], source: str) -> dict[str, FileChange]:
    result = run_git(repo, ["diff", "--numstat", *diff_args])
    changes: dict[str, FileChange] = {}
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        additions, deletions, path = parts[0], parts[1], parts[-1]
        changes[path] = FileChange(
            path=path,
            status="M",
            additions=parse_int(additions),
            deletions=parse_int(deletions),
            source=source,
        )
    return changes


def apply_name_status(repo: str, diff_args: list[str], changes: dict[str, FileChange]) -> None:
    result = run_git(repo, ["diff", "--name-status", *diff_args])
    for line in result.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        path = parts[-1]
        change = changes.setdefault(path, FileChange(path=path, status=status[:1]))
        change.status = status


def tracked_changes(repo: str, diff_args: list[str], source: str) -> list[FileChange]:
    changes = parse_numstat(repo, diff_args, source)
    apply_name_status(repo, diff_args, changes)
    return list(changes.values())


def untracked_changes(repo: str) -> list[FileChange]:
    result = run_git(repo, ["ls-files", "--others", "--exclude-standard"])
    changes = []
    for path in result.stdout.splitlines():
        if path:
            changes.append(FileChange(path=path, status="??", source="untracked"))
    return changes


def combine_changes(groups: list[list[FileChange]], max_files: int) -> list[FileChange]:
    combined: dict[tuple[str, str], FileChange] = {}
    for group in groups:
        for change in group:
            key = (change.path, change.source)
            if key in combined:
                existing = combined[key]
                existing.additions += change.additions
                existing.deletions += change.deletions
                if change.status != "M":
                    existing.status = change.status
            else:
                combined[key] = change
    ordered = sorted(combined.values(), key=lambda item: (-item.total, item.path, item.source))
    return ordered[:max_files]


def hunk_lines(repo: str, diff_args: list[str], source: str, max_hunks: int, line_width: int) -> list[str]:
    if max_hunks <= 0:
        return []
    result = run_git(repo, ["diff", "--unified=3", "--no-ext-diff", *diff_args])
    output: list[str] = []
    hunk_count = 0
    current_file = None
    in_hunk = False
    hunk_body_lines = 0

    for raw in result.stdout.splitlines():
        if raw.startswith("diff --git "):
            current_file = raw
            in_hunk = False
            hunk_body_lines = 0
            continue
        if raw.startswith("@@ "):
            hunk_count += 1
            if hunk_count > max_hunks:
                break
            if current_file:
                output.append(f"\n--- {source}: {truncate_line(redact_text(current_file), line_width)}")
                current_file = None
            output.append(truncate_line(redact_text(raw), line_width))
            in_hunk = True
            hunk_body_lines = 0
            continue
        if in_hunk:
            if raw.startswith("@@ "):
                continue
            if raw.startswith((" ", "+", "-")) and not raw.startswith(("+++", "---")):
                if hunk_body_lines < 12:
                    output.append(truncate_line(redact_text(raw), line_width))
                hunk_body_lines += 1

    if hunk_count > max_hunks:
        output.append(f"... truncated after {max_hunks} hunks")
    return output


def untracked_preview(repo: str, changes: list[FileChange], max_hunks: int, line_width: int) -> list[str]:
    if max_hunks <= 0:
        return []
    output: list[str] = []
    shown = 0
    for change in changes:
        if shown >= max_hunks:
            break
        path = os.path.join(repo, change.path)
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                lines = handle.readlines()
        except OSError:
            continue
        output.append(f"\n--- untracked: {change.path}")
        for idx, line in enumerate(lines[:12], 1):
            output.append(truncate_line(redact_text(f"+{idx}: {line.rstrip()}"), line_width))
        if len(lines) > 12:
            output.append("... truncated untracked preview")
        shown += 1
    return output


def format_table(changes: list[FileChange], line_width: int) -> list[str]:
    if not changes:
        return ["  (none)"]
    rows = ["  status  +lines  -lines  source      path"]
    for change in changes:
        rows.append(
            "  "
            f"{change.status:<6} "
            f"{change.additions:>6} "
            f"{change.deletions:>6} "
            f"{change.source:<11} "
            f"{truncate_line(redact_text(change.path), line_width)}"
        )
    return rows


def format_largest(changes: list[FileChange], line_width: int) -> list[str]:
    largest = [change for change in changes if change.total > 0][:5]
    if not largest:
        return ["  (none)"]
    return [
        f"  {change.total:>6} lines  {truncate_line(redact_text(change.path), line_width)} ({change.source})"
        for change in largest
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize Git diffs without full diff output.")
    parser.add_argument("path", nargs="?", default=".", help="Repository path, defaults to current directory")
    parser.add_argument("--base", help="Compare HEAD against a base ref with git diff BASE...HEAD")
    parser.add_argument("--staged", action="store_true", help="Only summarize staged changes")
    parser.add_argument("--no-untracked", action="store_true", help="Hide untracked files")
    parser.add_argument("--max-files", type=int, default=80)
    parser.add_argument("--max-hunks", type=int, default=5)
    parser.add_argument("--max-chars", "--max-output-chars", dest="max_chars", type=int, default=12000)
    parser.add_argument("--line-width", type=int, default=240)
    args = parser.parse_args()

    repo = repo_root(args.path)
    groups: list[list[FileChange]] = []
    hunk_output: list[str] = []
    mode = "working tree"

    if args.base:
        mode = f"base comparison ({args.base}...HEAD)"
        diff_args = [f"{args.base}...HEAD"]
        base_changes = tracked_changes(repo, diff_args, "base")
        groups.append(base_changes)
        hunk_output.extend(hunk_lines(repo, diff_args, "base", args.max_hunks, args.line_width))
        if not args.no_untracked:
            groups.append(untracked_changes(repo))
    else:
        staged = tracked_changes(repo, ["--cached"], "staged")
        groups.append(staged)
        hunk_output.extend(hunk_lines(repo, ["--cached"], "staged", args.max_hunks, args.line_width))
        if not args.staged:
            unstaged = tracked_changes(repo, [], "unstaged")
            groups.append(unstaged)
            remaining_hunks = max(0, args.max_hunks - len([line for line in hunk_output if line.startswith("@@ ")]))
            hunk_output.extend(hunk_lines(repo, [], "unstaged", remaining_hunks, args.line_width))
            if not args.no_untracked:
                untracked = untracked_changes(repo)
                groups.append(untracked)
                remaining_hunks = max(0, args.max_hunks - len([line for line in hunk_output if line.startswith("@@ ")]))
                hunk_output.extend(untracked_preview(repo, untracked, remaining_hunks, args.line_width))

    changes = combine_changes(groups, args.max_files)
    total_add = sum(change.additions for change in changes)
    total_del = sum(change.deletions for change in changes)
    total_untracked = sum(1 for change in changes if change.source == "untracked")

    output = [
        "Git Diff Summary",
        f"Repository: {repo}",
        f"Mode: {mode}",
        f"Files shown: {len(changes)}",
        f"Line changes shown: +{total_add} -{total_del}",
    ]
    if total_untracked:
        output.append(f"Untracked files shown: {total_untracked}")
    output.extend(["", "Files:", *format_table(changes, args.line_width)])
    output.extend(["", "Largest Changes:", *format_largest(changes, args.line_width)])
    if hunk_output:
        output.extend(["", "First Hunks:", *hunk_output])
    elif changes:
        output.extend(["", "First Hunks:", "  (no textual hunks shown)"])

    print(truncate("\n".join(output), args.max_chars))


if __name__ == "__main__":
    main()
