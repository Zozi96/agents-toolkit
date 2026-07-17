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
import signal
import subprocess
import sys
import threading
import time
from collections import deque
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
    os.makedirs(args.log_dir, exist_ok=True)
    stamp = f"{datetime.now():%Y%m%d-%H%M%S}-{time.time_ns() % 1_000_000_000:09d}"
    log_path = os.path.join(args.log_dir, f"run-{stamp}-{os.getpid()}.log")
    fd = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    log = os.fdopen(fd, "w", encoding="utf-8")
    process_group = (
        {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
        if os.name == "nt"
        else {"start_new_session": True}
    )
    try:
        proc = subprocess.Popen(
            command,
            text=True,
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            **process_group,
        )
    except Exception as exc:
        log.close()
        os.unlink(log_path)
        if isinstance(exc, FileNotFoundError):
            print(f"Command not found: {truncate_line(redact_text(str(exc)), args.line_width)}")
            sys.exit(127)
        raise

    timed_out = threading.Event()

    def kill_on_timeout() -> None:
        timed_out.set()
        try:
            if os.name == "nt":
                if proc.poll() is not None:
                    return
                subprocess.run(
                    ["taskkill", "/PID", str(proc.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            else:
                os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass
        if proc.poll() is None:
            try:
                proc.kill()
            except OSError:
                pass

    timer = threading.Timer(args.timeout, kill_on_timeout)
    timer.start()

    # Stream: full raw output goes to the log file; only head, tail, and
    # capped error lines stay in memory regardless of output size.
    head: list[tuple[int, str]] = []
    tail: deque[tuple[int, str]] = deque(maxlen=args.tail)
    error_lines: list[tuple[int, str]] = []
    error_total = 0
    line_count = 0
    try:
        with log:
            for raw in proc.stdout or []:
                log.write(raw)
                line_count += 1
                line = raw.rstrip("\n")
                if len(head) < args.head:
                    head.append((line_count, line))
                tail.append((line_count, line))
                if ERROR_RE.search(line):
                    error_total += 1
                    if len(error_lines) < args.errors:
                        error_lines.append((line_count, line))
        exit_code = proc.wait()
    finally:
        timer.cancel()
        timer.join()
    duration = time.monotonic() - start

    sections = [
        f"Command: {truncate_line(redact_text(' '.join(command)), args.line_width)}",
        f"Exit Code: {'TIMEOUT after ' + str(args.timeout) + 's' if timed_out.is_set() else exit_code}",
        f"Duration: {duration:.1f}s",
        f"Output Lines: {line_count}",
        f"Full Log (raw, not redacted): {log_path}",
    ]

    if line_count <= args.head + args.tail:
        if line_count:
            sections.append("\nOutput:")
            shown = head + [(no, line) for no, line in tail if no > len(head)]
            sections.extend(fmt(no, line, args.line_width) for no, line in shown)
    else:
        sections.append(f"\nHead ({args.head} lines):")
        sections.extend(fmt(no, line, args.line_width) for no, line in head)
        sections.append(f"\nTail ({args.tail} lines):")
        sections.extend(fmt(no, line, args.line_width) for no, line in tail)

    if error_lines:
        sections.append(f"\nError Lines ({error_total} total, showing {len(error_lines)}):")
        sections.extend(
            fmt(line_no, line, args.line_width, match=True)
            for line_no, line in error_lines
        )

    print(truncate("\n".join(sections), args.max_chars))
    sys.exit(124 if timed_out.is_set() else exit_code)


if __name__ == "__main__":
    main()
