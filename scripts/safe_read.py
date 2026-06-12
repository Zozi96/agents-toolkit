#!/usr/bin/env python3
"""
safe_read.py

Reads a small, redacted slice of a file or stdin. Use before opening files that
may be large or sensitive.

Examples:
  python safe_read.py app.py --start 40 --end 90
  python safe_read.py server.log --find traceback --context 3
  some-command 2>&1 | python safe_read.py - --tail 120
"""

from __future__ import annotations

import argparse
from collections import deque
import os
import re
import sys

from _agent_utils import collect_match_snippets, redact_text, truncate, truncate_line


def emit_line(line_no: int, line: str, args: argparse.Namespace) -> str:
    text = line.rstrip("\n")
    if not args.show_secrets:
        text = redact_text(text)
    text = truncate_line(text, args.line_width)
    return text if args.no_line_numbers else f"{line_no}: {text}"


def iter_source(args: argparse.Namespace):
    if args.file == "-":
        for idx, line in enumerate(sys.stdin, 1):
            yield idx, line
        return

    try:
        size_mb = os.path.getsize(args.file) / (1024 * 1024)
    except OSError as exc:
        print(f"Error reading {args.file}: {exc}")
        return

    if size_mb > args.max_file_mb and not args.force:
        print(f"Skipped {args.file}: {size_mb:.2f} MB > --max-file-mb {args.max_file_mb}. Use --force for targeted read.")
        return

    try:
        with open(args.file, "r", encoding="utf-8", errors="ignore") as handle:
            for idx, line in enumerate(handle, 1):
                yield idx, line
    except OSError as exc:
        print(f"Error reading {args.file}: {exc}")


def select_range(args: argparse.Namespace):
    start = args.start or 1
    end = args.end
    if args.head:
        start = 1
        end = args.head
    selected = []
    if args.tail:
        tail = deque(maxlen=args.tail)
        for line_no, line in iter_source(args):
            tail.append((line_no, line))
        selected = list(tail)
    else:
        max_lines = args.max_lines
        for line_no, line in iter_source(args):
            if line_no < start:
                continue
            if end is not None and line_no > end:
                break
            selected.append((line_no, line))
            if len(selected) >= max_lines:
                break
    return [emit_line(line_no, line, args) for line_no, line in selected]


def select_matches(args: argparse.Namespace):
    flags = 0 if args.case_sensitive else re.IGNORECASE
    patterns = []
    for item in args.find:
        patterns.append(re.compile(re.escape(item), flags))
    if args.regex:
        try:
            patterns.append(re.compile(args.regex, flags))
        except re.error as exc:
            return [f"Invalid regex: {exc}"]

    snippets = collect_match_snippets(
        iter_source(args),
        lambda line: any(pattern.search(line) for pattern in patterns),
        context=args.context,
        limit=args.max_lines,
        line_width=args.line_width,
        line_numbers=not args.no_line_numbers,
        show_secrets=args.show_secrets,
    )
    results = []
    for snippet in snippets:
        results.extend(snippet)
        results.append("")
        if len(results) >= args.max_lines:
            break
    return results[:args.max_lines]


def main() -> None:
    parser = argparse.ArgumentParser(description="Read a small, redacted file slice.")
    parser.add_argument("file", help="File to read, or - for stdin")
    parser.add_argument("--start", type=int, default=None)
    parser.add_argument("--end", type=int, default=None)
    parser.add_argument("--head", type=int, default=None)
    parser.add_argument("--tail", type=int, default=None)
    parser.add_argument("--find", action="append", default=[])
    parser.add_argument("--regex", default=None)
    parser.add_argument("--context", type=int, default=0)
    parser.add_argument("--max-lines", type=int, default=120)
    parser.add_argument("--max-file-mb", type=float, default=2.0)
    parser.add_argument("--max-chars", "--max-output-chars", dest="max_chars", type=int, default=12000)
    parser.add_argument("--line-width", type=int, default=240)
    parser.add_argument("--case-sensitive", action="store_true")
    parser.add_argument("--no-line-numbers", action="store_true")
    parser.add_argument("--show-secrets", action="store_true")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if args.find or args.regex:
        lines = select_matches(args)
    else:
        if not any([args.start, args.end, args.head, args.tail]):
            args.head = args.max_lines
        lines = select_range(args)
    print(truncate("\n".join(lines), args.max_chars))


if __name__ == "__main__":
    main()
