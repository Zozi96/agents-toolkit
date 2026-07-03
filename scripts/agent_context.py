#!/usr/bin/env python3
"""One-command medium context for coding agents."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

from _agent_utils import redact_text, truncate, truncate_line


SCRIPT_DIR = Path(__file__).resolve().parent


def helper(name: str, path: str, args: list[str], title: str) -> str:
    command = [sys.executable, str(SCRIPT_DIR / name), path, *args]
    result = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode == 0:
        return result.stdout.strip()

    message = result.stderr.strip() or result.stdout.strip() or "unavailable"
    return f"{title}\nUnavailable: {truncate_line(redact_text(message), 240)}"


def build_next_steps(path: str, diff_summary: str, scan_summary: str | None) -> str:
    rows = re.findall(r"^  \S+\s+\S+\s+\S+\s+\S+\s+(.+)$", diff_summary, re.MULTILINE)
    changed_files = [row for row in rows if row != "path"][:3]
    steps: list[str] = ["Next Token-Safe Steps:"]

    if changed_files:
        steps.append("- Inspect candidate files first (outline, then targeted safe_read):")
        for filename in changed_files:
            full_path = os.path.normpath(os.path.join(path, filename))
            steps.append(f"  - python3 ~/.agents/scripts/outline.py {full_path}")
            steps.append(f"  - python3 ~/.agents/scripts/safe_read.py {full_path} --head 160")
    else:
        steps.append("- No local file deltas detected.")
        steps.append(
            "  - rg -n \"symbol_or_error\" . --glob '!node_modules' --glob '!.git' | head -c 12000"
        )
        steps.append("  - Then outline.py <likely_file>, then safe_read.py <likely_file> --start N --end M")

    if scan_summary and re.search(r"Found\s+\d+\s+matches", scan_summary):
        steps.append("- Refine matched logs before reading full files:")
        steps.append("  - scan_errors.py <path> --context 2 --limit 30 --max-output-chars 12000")

    return "\n".join(steps)


def main() -> None:
    parser = argparse.ArgumentParser(description="Print compact repo context for agents.")
    parser.add_argument("path", nargs="?", default=".", help="Repository path")
    parser.add_argument("--max-chars", "--max-output-chars", dest="max_chars", type=int, default=12000)
    parser.add_argument("--scan-errors", action="store_true", help="Append compact error scan")
    args = parser.parse_args()

    path = os.path.abspath(args.path)
    diff_section = helper(
        "diff_summary.py",
        path,
        ["--max-output-chars", str(args.max_chars)],
        "Git Diff Summary",
    )
    sections = [
        f"Agent Context: {path}",
        helper("repo_map.py", path, ["--max-output-chars", str(args.max_chars)], "Repository Map"),
        diff_section,
    ]

    scan_section: str | None = None
    if args.scan_errors:
        scan_section = helper(
            "scan_errors.py",
            path,
            ["--limit", "30", "--context", "1", "--max-output-chars", str(args.max_chars)],
            "Error Scan",
        )
        sections.append(scan_section)

    sections.append(build_next_steps(path, diff_section, scan_section))
    print(truncate("\n\n".join(section for section in sections if section), args.max_chars))


if __name__ == "__main__":
    main()
