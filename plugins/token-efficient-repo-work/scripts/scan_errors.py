#!/usr/bin/env python3
"""
scan_errors.py

Searches for relevant errors in logs, outputs, text files or repositories
without printing everything.

Examples:
  python scan_errors.py .
  python scan_errors.py logs/app.log --limit 30
  python scan_errors.py output.txt --context 2
"""

import argparse
import os
import re
import sys

from _agent_utils import (
    collect_match_snippets,
    compact_error,
    iter_text_files,
    normalize_exts,
    numbered_lines,
    open_text_source,
    truncate,
)

DEFAULT_PATTERNS = [
    'ERROR', 'Exception', 'Traceback', 'Failed', 'Failure', 'Fatal', 'Panic',
    'Unhandled', 'TypeError', 'ReferenceError', 'NullReferenceException',
    'AssertionError', 'Timeout', 'ECONNREFUSED', 'ECONNRESET', 'EADDRINUSE',
    'Segmentation fault', 'OutOfMemory', 'Stack overflow'
]

WARNING_PATTERNS = ['WARN', 'Warning', 'Deprecated']

def main():
    parser = argparse.ArgumentParser(description="Scan for errors.")
    parser.add_argument('path', nargs='?', default='.', help="File, dir, or - for stdin")
    parser.add_argument('--limit', type=int, default=50)
    parser.add_argument('--context', type=int, default=0)
    parser.add_argument('--max-file-mb', type=float, default=10.0)
    parser.add_argument('--max-chars', '--max-output-chars', dest='max_chars', type=int, default=12000)
    parser.add_argument('--line-width', type=int, default=240)
    parser.add_argument('--include-warnings', action='store_true')
    parser.add_argument('--regex', type=str, default=None)
    parser.add_argument('--extensions', type=str, default=None)
    args = parser.parse_args()

    patterns = DEFAULT_PATTERNS.copy()
    if args.include_warnings:
        patterns.extend(WARNING_PATTERNS)
        
    regexes = [re.compile(re.escape(p), re.IGNORECASE) for p in patterns]
    if args.regex:
        try:
            regexes.append(re.compile(args.regex, re.IGNORECASE))
        except re.error as e:
            print(f"Invalid regex: {e}")
            sys.exit(2)
            
    allowed_exts = normalize_exts(args.extensions)

    files_to_scan = []
    base_path = os.path.abspath(args.path)
    if args.path == '-':
        files_to_scan = ['-']
    else:
        files_to_scan = list(iter_text_files([base_path], allowed_exts=allowed_exts, max_file_mb=args.max_file_mb))

    total_scanned = 0
    matches = []
    skipped = []
    
    for filepath in files_to_scan:
        try:
            total_scanned += 1
            rel = "stdin" if filepath == '-' else os.path.relpath(filepath, base_path) if os.path.isdir(base_path) else os.path.basename(filepath)
            with open_text_source(filepath) as source:
                snippets = collect_match_snippets(
                    numbered_lines(source),
                    lambda line: any(r.search(line) for r in regexes),
                    context=args.context,
                    limit=args.limit - len(matches),
                    line_width=args.line_width,
                )
            matches.extend((rel, "\n".join(snippet)) for snippet in snippets)
        except Exception as exc:
            skipped.append(compact_error(filepath, exc))
        if len(matches) >= args.limit:
            break

    output = [f"Scanned {total_scanned} files. Match groups: {len(matches)}."]
    if skipped:
        output.append(f"Skipped {len(skipped)} unreadable files. First: {skipped[0]}")
    current_file = None
    for filepath, content in matches:
        if filepath != current_file:
            output.append(f"\n--- {filepath} ---")
            current_file = filepath
        output.append(content)
        
    print(truncate("\n".join(output), args.max_chars))

if __name__ == "__main__":
    main()
