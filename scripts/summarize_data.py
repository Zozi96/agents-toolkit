#!/usr/bin/env python3
"""
summarize_data.py

Summarizes CSV, TSV, or JSONL files without pandas or external dependencies.

Examples:
  python summarize_data.py trades.csv
  python summarize_data.py data.tsv
"""

import argparse
from collections import Counter
import csv
import json
import os
import sys
from io import StringIO

from _agent_utils import is_sensitive_key, redact_obj, redact_text, truncate, truncate_line

def main():
    parser = argparse.ArgumentParser(description="Summarize data files.")
    parser.add_argument('file', help="Data file to read, or - for stdin")
    parser.add_argument('--max-rows', type=int, default=50000)
    parser.add_argument('--sample-rows', type=int, default=10)
    parser.add_argument('--top-values', type=int, default=5)
    parser.add_argument('--max-columns', type=int, default=80)
    parser.add_argument('--delimiter', type=str, default=None)
    parser.add_argument('--max-chars', '--max-output-chars', dest='max_chars', type=int, default=12000)
    args = parser.parse_args()

    if args.file != '-' and args.file.lower().endswith('.xlsx'):
        print("Excel files (.xlsx) not supported without dependencies. Export to CSV.")
        return

    output = []
    ext = os.path.splitext(args.file)[1].lower() if args.file != '-' else '.csv'
    
    try:
        if ext in ('.jsonl', '.ndjson'):
            source = sys.stdin if args.file == '-' else open(args.file, 'r', encoding='utf-8', errors='ignore')
            with source as f:
                rows = []
                keys = Counter()
                parsed_rows = 0
                for i, line in enumerate(f):
                    if i >= args.max_rows: break
                    if line.strip():
                        try:
                            row = json.loads(line)
                            parsed_rows += 1
                            if len(rows) < args.sample_rows:
                                rows.append(redact_obj(row))
                            if isinstance(row, dict):
                                keys.update(row.keys())
                        except json.JSONDecodeError:
                            pass
            
            output.append(f"JSONL/NDJSON File: {args.file}")
            output.append(f"Parsed Rows: {parsed_rows}")
            if rows:
                output.append(f"Keys found: {[k for k, _ in keys.most_common(args.max_columns)]}")
                output.append("Sample Objects:")
                for row in rows[:args.sample_rows]:
                    output.append(truncate_line(json.dumps(row, indent=2), 1000))
        else:
            source = StringIO(sys.stdin.read()) if args.file == '-' else open(args.file, 'r', encoding='utf-8', errors='ignore')
            with source as f:
                sample = f.read(4096)
                f.seek(0)
                
                dialect = None
                if args.delimiter:
                    dialect = csv.excel()
                    dialect.delimiter = args.delimiter
                else:
                    try:
                        dialect = csv.Sniffer().sniff(sample)
                    except:
                        dialect = csv.excel()
                
                reader = csv.reader(f, dialect)
                headers = next(reader, [])
                rows = []
                parsed_rows = 0
                value_counts = [Counter() for _ in headers[:args.max_columns]]
                for i, r in enumerate(reader):
                    if i >= args.max_rows: break
                    parsed_rows += 1
                    if len(rows) < args.sample_rows:
                        rows.append(r)
                    for idx, v in enumerate(r[:args.max_columns]):
                        if idx < len(value_counts) and len(value_counts[idx]) <= args.top_values * 4:
                            header = headers[idx] if idx < len(headers) else ""
                            value_counts[idx]["****" if is_sensitive_key(header) else redact_text(v)] += 1
                    
            output.append(f"CSV/TSV File: {args.file}")
            output.append(f"Delimiter: {repr(dialect.delimiter)}")
            output.append(f"Columns ({len(headers)}): {headers[:args.max_columns]}")
            output.append(f"Parsed Rows: {parsed_rows}")
            
            if rows:
                output.append("\nSample Rows:")
                for row_num, row in enumerate(rows[:args.sample_rows], 1):
                    output.append(f"  Row {row_num}:")
                    for h, v in zip(headers[:args.max_columns], row[:args.max_columns]):
                        safe_value = "****" if is_sensitive_key(h) else redact_text(v)
                        output.append(f"    {h}: {truncate_line(safe_value, 100)}")
                if args.top_values > 0:
                    output.append("\nTop Values:")
                    for h, counts in zip(headers[:args.max_columns], value_counts):
                        if counts:
                            output.append(f"  {h}: {counts.most_common(args.top_values)}")
                
    except Exception as e:
        output.append(f"Error reading data: {e}")

    print(truncate("\n".join(output), args.max_chars))

if __name__ == "__main__":
    main()
