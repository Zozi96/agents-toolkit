#!/usr/bin/env python3
"""
summarize_tests.py

Summarizes huge test outputs without passing everything to Codex.

Examples:
  pytest > output.txt 2>&1
  python summarize_tests.py output.txt
"""

import argparse
import sys
import re

from _agent_utils import collect_match_snippets, numbered_lines, open_text_source, truncate

def main():
    parser = argparse.ArgumentParser(description="Summarize test outputs.")
    parser.add_argument('file', help="File to read, or - for stdin")
    parser.add_argument('--limit', type=int, default=30)
    parser.add_argument('--context', type=int, default=2)
    parser.add_argument('--max-chars', '--max-output-chars', dest='max_chars', type=int, default=12000)
    parser.add_argument('--line-width', type=int, default=240)
    args = parser.parse_args()

    framework = "Unknown"
    fail_regex = re.compile(r'(FAIL|FAILED|ERROR|Exception|Error:|Expected|Received)', re.IGNORECASE)
    total_lines = 0

    def iter_test_lines(source):
        nonlocal framework, total_lines
        for line_no, line in numbered_lines(source):
            total_lines += 1
            low = line.lower()
            if framework == "Unknown":
                if "pytest" in low: framework = "pytest"
                elif "vitest" in low: framework = "vitest"
                elif "jest" in low: framework = "jest"
                elif "dotnet test" in low or "xunit" in low or "nunit" in low: framework = "dotnet"
            yield line_no, line

    try:
        with open_text_source(args.file) as source:
            failures = collect_match_snippets(
                iter_test_lines(source),
                lambda line: bool(fail_regex.search(line)),
                context=args.context,
                limit=args.limit,
                line_width=args.line_width,
            )
    except OSError as e:
        print(f"Error reading {args.file}: {e}")
        sys.exit(2)

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
