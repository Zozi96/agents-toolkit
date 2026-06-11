#!/usr/bin/env python3
"""
summarize_tests.py

Summarizes huge test outputs without passing everything to Codex.

Examples:
  pytest > output.txt 2>&1
  python summarize_tests.py output.txt
"""

import argparse
from collections import deque
import sys
import re

from _agent_utils import redact_text, truncate, truncate_line

def main():
    parser = argparse.ArgumentParser(description="Summarize test outputs.")
    parser.add_argument('file', help="File to read, or - for stdin")
    parser.add_argument('--limit', type=int, default=30)
    parser.add_argument('--context', type=int, default=2)
    parser.add_argument('--max-chars', '--max-output-chars', dest='max_chars', type=int, default=12000)
    parser.add_argument('--line-width', type=int, default=240)
    args = parser.parse_args()

    if args.file == '-':
        source = sys.stdin
        close_source = False
    else:
        try:
            source = open(args.file, 'r', encoding='utf-8', errors='ignore')
            close_source = True
        except Exception as e:
            print(f"Error reading {args.file}: {e}")
            return

    framework = "Unknown"
    failures = []
    fail_regex = re.compile(r'(FAIL|FAILED|ERROR|Exception|Error:|Expected|Received)', re.IGNORECASE)
    total_lines = 0
    previous = deque(maxlen=args.context)
    after_remaining = 0
    active_snippet = None

    try:
        for line in source:
            total_lines += 1
            low = line.lower()
            if framework == "Unknown":
                if "pytest" in low: framework = "pytest"
                elif "vitest" in low: framework = "vitest"
                elif "jest" in low: framework = "jest"
                elif "dotnet test" in low or "xunit" in low or "nunit" in low: framework = "dotnet"

            if after_remaining > 0:
                active_snippet.append(truncate_line(redact_text(line.rstrip()), args.line_width))
                after_remaining -= 1
                if after_remaining == 0:
                    failures.append(active_snippet)
                    active_snippet = None
                    if len(failures) >= args.limit:
                        break
                previous.append(line.rstrip())
                continue

            if fail_regex.search(line):
                active_snippet = [truncate_line(redact_text(prev), args.line_width) for prev in previous]
                active_snippet.append(truncate_line(redact_text(line.rstrip()), args.line_width))
                after_remaining = args.context
                if after_remaining == 0:
                    failures.append(active_snippet)
                    active_snippet = None
                    if len(failures) >= args.limit:
                        break
                previous.clear()
            else:
                previous.append(line.rstrip())
    finally:
        if close_source:
            source.close()

    if active_snippet and len(failures) < args.limit:
        failures.append(active_snippet)

    output = [f"Probable Framework: {framework}", f"Total Lines Parsed: {total_lines}"]
    
    if failures:
        output.append(f"Found ~{len(failures)} failures/errors (showing up to {args.limit}):")
        for idx, fail in enumerate(failures, 1):
            output.append(f"\n--- Failure {idx} ---")
            output.extend(fail)
    else:
        output.append("No explicit failures found in output.")

    print(truncate("\n".join(output), args.max_chars))

if __name__ == "__main__":
    main()
