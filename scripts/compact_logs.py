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
import re

from _agent_utils import (
    collect_match_snippets,
    compact_error,
    iter_text_files,
    numbered_lines,
    open_text_source,
    truncate,
)

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
            def line_matches(line):
                line_to_check = line if args.case_sensitive else line.lower()
                if args.keyword:
                    if args.all_keywords and not all(k in line_to_check for k in keywords):
                        return False
                    if not args.all_keywords and not any(k in line_to_check for k in keywords):
                        return False
                if args.level and not any(l in line_to_check for l in levels):
                    return False
                if compiled_regex and not compiled_regex.search(line):
                    return False
                return True

            if filepath != '-' and args.tail > 0:
                with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = list(deque(f, maxlen=args.tail))
                snippets = collect_match_snippets(
                    numbered_lines(lines),
                    line_matches,
                    context=args.context,
                    limit=args.limit - len(matches),
                    line_width=args.line_width,
                )
            else:
                with open_text_source(filepath) as source:
                    snippets = collect_match_snippets(
                        numbered_lines(source),
                        line_matches,
                        context=args.context,
                        limit=args.limit - len(matches),
                        line_width=args.line_width,
                    )
            matches.extend((filepath, "\n".join(snippet)) for snippet in snippets)
        except Exception as exc:
            matches.append((filepath, f"Skipped unreadable file: {compact_error(filepath, exc)}"))
        if len(matches) >= args.limit: break

    output = [f"Scanned {len(files_to_scan)} files. Found {len(matches)} matches."]
    for f, c in matches:
        output.append(f"\n[{f}]\n{c}")
        
    print(truncate("\n".join(output), args.max_chars))

if __name__ == "__main__":
    main()
