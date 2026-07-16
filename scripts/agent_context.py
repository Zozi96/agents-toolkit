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
        steps.append("- Changed paths:")
        for filename in changed_files:
            steps.append(f"  - {filename}")
        steps.append("- Run outline.py <path>, then safe_read.py <path> --start N --end M.")
    else:
        steps.append("- No local file deltas detected.")
        steps.append(
            "  - rg -n \"symbol_or_error\" . --glob '!node_modules' --glob '!.git' | head -c 12000"
        )
        steps.append("  - Then outline.py <likely_file>, then safe_read.py <likely_file> --start N --end M")

    if scan_summary and re.search(r"Match groups:\s*[1-9]\d*", scan_summary):
        steps.append("- Refine matched logs before reading full files:")
        steps.append("  - scan_errors.py <path> --context 2 --limit 30 --max-output-chars 12000")

    return "\n".join(steps)


def main() -> None:
    parser = argparse.ArgumentParser(description="Print compact repo context for agents.")
    parser.add_argument("path", nargs="?", default=".", help="Repository path")
    parser.add_argument("--max-chars", "--max-output-chars", dest="max_chars", type=int, default=12000)
    parser.add_argument("--scan-errors", action="store_true", help="Append compact error scan")
    args = parser.parse_args()
    if args.max_chars <= 0:
        parser.error("--max-output-chars must be greater than zero")

    path = os.path.abspath(args.path)
    section_budget = max(256, args.max_chars // (3 if args.scan_errors else 2))
    diff_section = helper(
        "diff_summary.py",
        path,
        ["--max-output-chars", str(section_budget)],
        "Git Diff Summary",
    )

    scan_section: str | None = None
    if args.scan_errors:
        scan_section = helper(
            "scan_errors.py",
            path,
            ["--limit", "30", "--context", "1", "--max-output-chars", str(section_budget)],
            "Error Scan",
        )

    sections = [
        f"Agent Context: {redact_text(path)}",
        diff_section,
        build_next_steps(path, diff_section, scan_section),
    ]
    if scan_section:
        sections.append(scan_section)
    sections.append(
        helper(
            "repo_map.py",
            path,
            ["--max-output-chars", str(section_budget), "--max-files", "15"],
            "Repository Map",
        )
    )
    print(truncate("\n\n".join(section for section in sections if section), args.max_chars))


if __name__ == "__main__":
    main()
