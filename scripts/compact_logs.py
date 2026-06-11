#!/usr/bin/env python3
"""
compact_logs.py

Filters large logs by keyword, regex, level, tailing lines.

Examples:
  python compact_logs.py app.log --keyword error --limit 50
  python compact_logs.py app.log --tail 500
"""

import argparse
from collections import deque
import os
import re
import sys

from _agent_utils import iter_text_files, redact_text, truncate, truncate_line

def main():
    parser = argparse.ArgumentParser(description="Compact and filter logs.")
    parser.add_argument('paths', nargs='+', help="Files, dirs, or - for stdin")
    parser.add_argument('--keyword', action='append', default=[])
    parser.add_argument('--regex', type=str, default=None)
    parser.add_argument('--level', action='append', default=[])
    parser.add_argument('--tail', type=int, default=0)
    parser.add_argument('--limit', type=int, default=100)
    parser.add_argument('--context', type=int, default=0)
    parser.add_argument('--max-file-mb', type=float, default=50.0)
    parser.add_argument('--max-chars', '--max-output-chars', dest='max_chars', type=int, default=12000)
    parser.add_argument('--line-width', type=int, default=240)
    parser.add_argument('--case-sensitive', action='store_true')
    parser.add_argument('--all-keywords', action='store_true')
    args = parser.parse_args()

    files_to_scan = []
    if args.paths == ['-']:
        files_to_scan = ['-']
    else:
        files_to_scan = list(iter_text_files(args.paths, max_file_mb=args.max_file_mb, ignore_exts=set()))

    matches = []
    flags = 0 if args.case_sensitive else re.IGNORECASE
    try:
        compiled_regex = re.compile(args.regex, flags) if args.regex else None
    except re.error as e:
        print(f"Invalid regex: {e}")
        return
    keywords = [k if args.case_sensitive else k.lower() for k in args.keyword]
    levels = [l if args.case_sensitive else l.lower() for l in args.level]

    for filepath in files_to_scan:
        try:
            if filepath == '-':
                lines = sys.stdin
                close_lines = None
            elif args.tail > 0:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = list(deque(f, maxlen=args.tail))
                close_lines = None
            else:
                lines = open(filepath, 'r', encoding='utf-8', errors='ignore')
                close_lines = lines

            previous = deque(maxlen=args.context)
            after_remaining = 0
            active_context = []
            try:
                for line in lines:
                    line_to_check = line if args.case_sensitive else line.lower()

                    if after_remaining > 0:
                        active_context.append(truncate_line(redact_text(line.rstrip()), args.line_width))
                        after_remaining -= 1
                        if after_remaining == 0:
                            matches.append((filepath, "\n".join(active_context)))
                            active_context = []
                            if len(matches) >= args.limit:
                                break
                        previous.append(line.rstrip())
                        continue

                    if args.keyword:
                        if args.all_keywords:
                            if not all(k in line_to_check for k in keywords):
                                previous.append(line.rstrip())
                                continue
                        elif not any(k in line_to_check for k in keywords):
                            previous.append(line.rstrip())
                            continue

                    if args.level and not any(l in line_to_check for l in levels):
                        previous.append(line.rstrip())
                        continue

                    if compiled_regex and not compiled_regex.search(line):
                        previous.append(line.rstrip())
                        continue

                    active_context = [truncate_line(redact_text(prev_line), args.line_width) for prev_line in previous]
                    active_context.append(truncate_line(redact_text(line.rstrip()), args.line_width))
                    after_remaining = args.context
                    if after_remaining == 0:
                        matches.append((filepath, "\n".join(active_context)))
                        active_context = []
                        if len(matches) >= args.limit:
                            break
                    previous.clear()

                if active_context and len(matches) < args.limit:
                    matches.append((filepath, "\n".join(active_context)))
            finally:
                if close_lines:
                    close_lines.close()
        except Exception:
            pass
        if len(matches) >= args.limit: break

    output = [f"Scanned {len(files_to_scan)} files. Found {len(matches)} matches."]
    for f, c in matches:
        output.append(f"\n[{f}]\n{c}")
        
    print(truncate("\n".join(output), args.max_chars))

if __name__ == "__main__":
    main()
