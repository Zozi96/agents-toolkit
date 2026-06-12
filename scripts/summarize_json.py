#!/usr/bin/env python3
"""
summarize_json.py

Summarizes large JSON objects without printing full content.

Examples:
  python summarize_json.py data.json
  cat response.json | python summarize_json.py -
"""

import argparse
import sys
import json
import os

from _agent_utils import is_sensitive_key, redact_text, truncate, truncate_line

def summarize_json_value(data, args, depth=0):
    indent = "  " * depth
    if depth > args.max_depth:
        return f"{indent}... (max depth {args.max_depth} reached)"
        
    if isinstance(data, dict):
        lines = [f"{indent}Object with {len(data)} keys:"]
        for i, (k, v) in enumerate(list(data.items())[:args.max_keys]):
            if isinstance(v, (dict, list)):
                lines.append(f"{indent}  {k}: {type(v).__name__}")
                lines.append(summarize_json_value(v, args, depth + 1))
            else:
                val = "****" if is_sensitive_key(k) else (truncate_line(redact_text(v), 50) if args.show_values else type(v).__name__)
                lines.append(f"{indent}  {k}: {val}")
        if len(data) > args.max_keys:
            lines.append(f"{indent}  ... and {len(data) - args.max_keys} more keys")
        return "\n".join(lines)
        
    elif isinstance(data, list):
        lines = [f"{indent}Array of length {len(data)}:"]
        for idx, item in enumerate(data[:args.sample_size]):
            lines.append(f"{indent}  [{idx}]:")
            lines.append(summarize_json_value(item, args, depth + 1))
        if len(data) > args.sample_size:
            lines.append(f"{indent}  ... and {len(data) - args.sample_size} more items")
        return "\n".join(lines)
    else:
        return f"{indent}{type(data).__name__}"

def main():
    parser = argparse.ArgumentParser(description="Summarize large JSON.")
    parser.add_argument('file', help="File to read, or - for stdin")
    parser.add_argument('--max-depth', type=int, default=4)
    parser.add_argument('--sample-size', type=int, default=3)
    parser.add_argument('--max-keys', type=int, default=50)
    parser.add_argument('--max-chars', '--max-output-chars', dest='max_chars', type=int, default=12000)
    parser.add_argument('--max-input-mb', type=float, default=10.0)
    parser.add_argument('--show-values', action='store_true')
    parser.add_argument('--force', action='store_true')
    args = parser.parse_args()

    content = ""
    if args.file == '-':
        content = sys.stdin.read()
    else:
        try:
            size_mb = os.path.getsize(args.file) / (1024 * 1024)
            if size_mb > args.max_input_mb and not args.force:
                print(f"Skipped {args.file}: {size_mb:.2f} MB > --max-input-mb {args.max_input_mb}. Use --force for targeted summary.")
                return
            with open(args.file, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
        except Exception as e:
            print(f"Error reading file: {e}")
            return

    try:
        data = json.loads(content)
    except json.JSONDecodeError as e:
        print(f"Failed to parse JSON: {e}")
        return

    summary = summarize_json_value(data, args)
    print(truncate(summary, args.max_chars))

if __name__ == "__main__":
    main()
