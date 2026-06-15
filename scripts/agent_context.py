#!/usr/bin/env python3
"""One-command medium context for coding agents."""

from __future__ import annotations

import argparse
import os
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Print compact repo context for agents.")
    parser.add_argument("path", nargs="?", default=".", help="Repository path")
    parser.add_argument("--max-chars", "--max-output-chars", dest="max_chars", type=int, default=12000)
    parser.add_argument("--scan-errors", action="store_true", help="Append compact error scan")
    args = parser.parse_args()

    path = os.path.abspath(args.path)
    sections = [
        f"Agent Context: {path}",
        helper("repo_map.py", path, ["--max-output-chars", str(args.max_chars)], "Repository Map"),
        helper("diff_summary.py", path, ["--max-output-chars", str(args.max_chars)], "Git Diff Summary"),
    ]

    if args.scan_errors:
        sections.append(
            helper(
                "scan_errors.py",
                path,
                ["--limit", "30", "--context", "1", "--max-output-chars", str(args.max_chars)],
                "Error Scan",
            )
        )

    print(truncate("\n\n".join(section for section in sections if section), args.max_chars))


if __name__ == "__main__":
    main()
