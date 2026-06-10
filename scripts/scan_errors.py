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
from collections import deque
import os
import re

DEFAULT_IGNORE_DIRS = {
    'node_modules', '.venv', 'venv', 'dist', 'build', 'coverage', '.next', '.nuxt',
    'target', 'bin', 'obj', '.git', '.cache', '__pycache__', '.pytest_cache',
    '.mypy_cache', '.ruff_cache', 'archive', 'vendor', 'tmp', 'temp'
}
DEFAULT_IGNORE_EXTS = {
    '.png', '.jpg', '.jpeg', '.gif', '.webp', '.ico', '.pdf', '.zip', '.gz',
    '.tar', '.rar', '.7z', '.exe', '.dll', '.so', '.dylib', '.bin', '.db',
    '.sqlite', '.sqlite3', '.pyc', '.pyo', '.class', '.o'
}

DEFAULT_PATTERNS = [
    'ERROR', 'Exception', 'Traceback', 'Failed', 'Failure', 'Fatal', 'Panic',
    'Unhandled', 'TypeError', 'ReferenceError', 'NullReferenceException',
    'AssertionError', 'Timeout', 'ECONNREFUSED', 'ECONNRESET', 'EADDRINUSE',
    'Segmentation fault', 'OutOfMemory', 'Stack overflow'
]

WARNING_PATTERNS = ['WARN', 'Warning', 'Deprecated']

def truncate(text, max_chars):
    if len(text) > max_chars:
        return text[:max_chars] + "\n...[TRUNCATED]"
    return text

def truncate_line(line, length=240):
    return line if len(line) <= length else line[:length] + "..."

def main():
    parser = argparse.ArgumentParser(description="Scan for errors.")
    parser.add_argument('path', nargs='?', default='.', help="File or dir")
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
            return
            
    allowed_exts = set(e.strip().lower() for e in args.extensions.split(',')) if args.extensions else None

    files_to_scan = []
    base_path = os.path.abspath(args.path)
    if os.path.isfile(base_path):
        files_to_scan.append(base_path)
    else:
        for root, dirs, files in os.walk(base_path):
            dirs[:] = [d for d in dirs if d not in DEFAULT_IGNORE_DIRS and not d.startswith('.')]
            for f in files:
                ext = os.path.splitext(f)[1].lower()
                if ext in DEFAULT_IGNORE_EXTS: continue
                if allowed_exts and ext not in allowed_exts and ext != '': continue
                files_to_scan.append(os.path.join(root, f))

    total_scanned = 0
    matches = []
    
    for filepath in files_to_scan:
        try:
            if os.path.getsize(filepath) / (1024 * 1024) > args.max_file_mb:
                continue
            total_scanned += 1

            previous = deque(maxlen=args.context)
            after_remaining = 0
            active_context = []
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                for i, line in enumerate(f):
                    line_no = i + 1
                    if after_remaining > 0:
                        active_context.append(f"   {line_no}: {truncate_line(line.rstrip(), args.line_width)}")
                        after_remaining -= 1
                        if after_remaining == 0:
                            rel = os.path.relpath(filepath, base_path) if os.path.isdir(base_path) else os.path.basename(filepath)
                            matches.append((rel, "\n".join(active_context)))
                            active_context = []
                            if len(matches) >= args.limit:
                                break
                        previous.append((line_no, line.rstrip()))
                        continue

                    if any(r.search(line) for r in regexes):
                        active_context = [
                            f"   {n}: {truncate_line(prev_line, args.line_width)}"
                            for n, prev_line in previous
                        ]
                        active_context.append(f">> {line_no}: {truncate_line(line.rstrip(), args.line_width)}")
                        after_remaining = args.context
                        if after_remaining == 0:
                            rel = os.path.relpath(filepath, base_path) if os.path.isdir(base_path) else os.path.basename(filepath)
                            matches.append((rel, "\n".join(active_context)))
                            active_context = []
                            if len(matches) >= args.limit:
                                break
                        previous.clear()
                    else:
                        previous.append((line_no, line.rstrip()))

            if active_context and len(matches) < args.limit:
                rel = os.path.relpath(filepath, base_path) if os.path.isdir(base_path) else os.path.basename(filepath)
                matches.append((rel, "\n".join(active_context)))
        except Exception:
            pass
        if len(matches) >= args.limit:
            break

    output = [f"Scanned {total_scanned} files. Found {len(matches)} matches."]
    current_file = None
    for filepath, content in matches:
        if filepath != current_file:
            output.append(f"\n--- {filepath} ---")
            current_file = filepath
        output.append(content)
        
    print(truncate("\n".join(output), args.max_chars))

if __name__ == "__main__":
    main()
