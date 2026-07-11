#!/usr/bin/env python3
"""
run_capped.py

Runs a command, saves the full raw output to a private log outside the repo,
and prints only a compact redacted summary: exit code, head, tail, and error
lines. Use for builds, installs, and anything with unknown output size.

Examples:
  python run_capped.py -- npm run build
  python run_capped.py --tail 60 -- pytest -x
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import time
from datetime import datetime

from _agent_utils import redact_text, truncate, truncate_line

ERROR_RE = re.compile(r"(?i)\b(error|exception|traceback|failed|failure|fatal|panic)\b")


def fmt(line_no: int, line: str, width: int, match: bool = False) -> str:
    marker = ">>" if match else "  "
    return f"{marker} {line_no}: {truncate_line(redact_text(line), width)}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a command; keep full log privately, print compact summary.",
        usage="run_capped.py [options] -- COMMAND [ARGS...]",
    )
    parser.add_argument("--head", type=int, default=15)
    parser.add_argument("--tail", type=int, default=40)
    parser.add_argument("--errors", type=int, default=20, help="Max error lines to show")
    parser.add_argument("--timeout", type=float, default=600)
    parser.add_argument("--log-dir", default=os.path.expanduser("~/.codex/tmp"))
    parser.add_argument("--line-width", type=int, default=240)
    parser.add_argument("--max-chars", "--max-output-chars", dest="max_chars", type=int, default=12000)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()

    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        parser.error("no command given; use: run_capped.py [options] -- COMMAND [ARGS...]")

    start = time.monotonic()
    timed_out = False
    try:
        result = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=args.timeout,
            check=False,
        )
        output, exit_code = result.stdout or "", result.returncode
    except FileNotFoundError as exc:
        print(f"Command not found: {truncate_line(redact_text(str(exc)), args.line_width)}")
        sys.exit(127)
    except subprocess.TimeoutExpired as exc:
        raw = exc.output or ""
        output = raw.decode("utf-8", errors="ignore") if isinstance(raw, bytes) else raw
        exit_code, timed_out = None, True
    duration = time.monotonic() - start

    os.makedirs(args.log_dir, exist_ok=True)
    log_path = os.path.join(
        args.log_dir, f"run-{datetime.now():%Y%m%d-%H%M%S}-{os.getpid()}.log"
    )
    with open(log_path, "w", encoding="utf-8") as handle:
        handle.write(output)

    lines = output.splitlines()
    sections = [
        f"Command: {truncate_line(redact_text(' '.join(command)), args.line_width)}",
        f"Exit Code: {'TIMEOUT after ' + str(args.timeout) + 's' if timed_out else exit_code}",
        f"Duration: {duration:.1f}s",
        f"Output Lines: {len(lines)}",
        f"Full Log (raw, not redacted): {log_path}",
    ]

    if len(lines) <= args.head + args.tail:
        if lines:
            sections.append("\nOutput:")
            sections.extend(fmt(i, line, args.line_width) for i, line in enumerate(lines, 1))
    else:
        sections.append(f"\nHead ({args.head} lines):")
        sections.extend(fmt(i, line, args.line_width) for i, line in enumerate(lines[: args.head], 1))
        sections.append(f"\nTail ({args.tail} lines):")
        offset = len(lines) - args.tail
        sections.extend(
            fmt(offset + i, line, args.line_width)
            for i, line in enumerate(lines[-args.tail:], 1)
        )

    error_lines = [
        (line_no, line)
        for line_no, line in enumerate(lines, 1)
        if ERROR_RE.search(line)
    ]
    if error_lines:
        sections.append(f"\nError Lines ({len(error_lines)} total, showing {min(len(error_lines), args.errors)}):")
        sections.extend(
            fmt(line_no, line, args.line_width, match=True)
            for line_no, line in error_lines[: args.errors]
        )

    print(truncate("\n".join(sections), args.max_chars))
    sys.exit(124 if timed_out else exit_code)


if __name__ == "__main__":
    main()
