#!/usr/bin/env python3
"""Replace oversized Codex Bash results with a compact, redacted summary."""

import json
import os
import re
import sys
import time
from pathlib import Path


# ponytail: fixed limits keep this hook predictable; change 12k/9k only from eval evidence.
OUTPUT_THRESHOLD = 12_000
SUMMARY_LIMIT = 9_000
HELPERS = (
    "run_capped.py",
    "summarize_tests.py",
    "diff_summary.py",
    "safe_read.py",
    "scan_errors.py",
    "compact_logs.py",
    "summarize_json.py",
    "summarize_data.py",
)
ERROR_RE = re.compile(r"error|exception|traceback|failed|failure|fatal|panic", re.IGNORECASE)


def serialize(value):
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def save_raw(text):
    try:
        directory = Path.home() / ".codex" / "tmp"
        directory.mkdir(parents=True, exist_ok=True)
        stamp = f"{time.strftime('%Y%m%d-%H%M%S')}-{time.time_ns() % 1_000_000_000:09d}"
        path = directory / f"post-tool-{stamp}-{os.getpid()}.log"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        return str(path)
    except (OSError, UnicodeError):
        return "unavailable"


def clipped_line(line):
    return line if len(line) <= 80 else line[:77] + "..."


def summary(command, text, log_path, redact_text):
    lines = text.splitlines()
    head_indices = set(range(min(15, len(lines))))
    tail_start = max(len(lines) - 40, 0)
    tail_indices = set(range(tail_start, len(lines)))
    error_indices = [
        index
        for index, line in enumerate(lines)
        if index not in head_indices | tail_indices and ERROR_RE.search(line)
    ][:20]

    command_text = clipped_line(serialize(command).replace("\n", " "))
    sections = [
        f"Oversized Bash result compacted after execution.",
        f"Command: {command_text}",
        f"Original: {len(text)} chars, {len(lines)} lines",
        f"Full output: {log_path}",
        "",
        "Head (15 lines max):",
        *(clipped_line(lines[index]) for index in sorted(head_indices)),
    ]
    if error_indices:
        sections.extend(("", "Errors (20 lines max):"))
        sections.extend(clipped_line(lines[index]) for index in error_indices)
    sections.extend(("", "Tail (40 lines max):"))
    sections.extend(clipped_line(lines[index]) for index in sorted(tail_indices - head_indices))
    result = redact_text("\n".join(sections))
    return result[:SUMMARY_LIMIT]


def main():
    root = os.environ.get("PLUGIN_ROOT")
    if not root:
        return 0
    sys.path.insert(0, str(Path(root) / "scripts"))
    try:
        from _agent_utils import redact_text

        payload = json.load(sys.stdin)
    except (ImportError, json.JSONDecodeError, OSError, TypeError, ValueError):
        return 0

    if payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input")
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    command_text = serialize(command)
    if any(helper in command_text for helper in HELPERS):
        return 0
    text = serialize(payload.get("tool_response", ""))
    if len(text) <= OUTPUT_THRESHOLD:
        return 0

    reason = summary(command, text, save_raw(text), redact_text)
    print(json.dumps({"decision": "block", "reason": reason}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
