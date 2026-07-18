#!/usr/bin/env python3
"""Replace oversized Claude Bash results with compact summaries."""

import json
import os
import re
import shlex
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
ASSIGNMENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")


def serialize(value):
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, indent=2)
    return str(value)


def invokes_helper(command):
    try:
        lexer = shlex.shlex(command, posix=True, punctuation_chars="|;&")
        lexer.whitespace_split = True
        lexer.commenters = ""
        tokens = list(lexer)
    except ValueError:
        return False

    segments = []
    current = []
    for token in tokens:
        if token and set(token) <= {"|", ";", "&"}:
            if current:
                segments.append(current)
                current = []
        else:
            current.append(token)
    if current:
        segments.append(current)

    for segment in segments:
        index = 0
        while index < len(segment) and ASSIGNMENT_RE.match(segment[index]):
            index += 1
        while index < len(segment) and Path(segment[index]).name in {
            "command", "exec", "env", "nohup", "sudo", "time"
        }:
            index += 1
            while index < len(segment) and (segment[index].startswith("-") or ASSIGNMENT_RE.match(segment[index])):
                index += 1
        if index >= len(segment):
            continue

        program = Path(segment[index]).name
        if program in HELPERS:
            return True
        if program in {"sh", "bash", "zsh"} and "-c" in segment[index + 1 :]:
            shell_index = segment.index("-c", index + 1)
            if shell_index + 1 < len(segment) and invokes_helper(segment[shell_index + 1]):
                return True
        if re.fullmatch(r"python(?:\d+(?:\.\d+)?)?|py", program):
            for argument in segment[index + 1 :]:
                if argument.startswith("-"):
                    continue
                if Path(argument).name in HELPERS:
                    return True
                break
    return False


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


def summary(command, text, log_path, redact_text, limit=SUMMARY_LIMIT):
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
    return result[:limit]


def main():
    # Drain stdin before any early exit: unread payload bytes make the
    # harness's write fail with "failed to write hook stdin: Broken pipe".
    try:
        raw = sys.stdin.buffer.read()
    except OSError:
        raw = b""

    plugin_root = os.environ.get("PLUGIN_ROOT")
    claude_root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    root = plugin_root or claude_root
    if not root:
        return 0
    sys.path.insert(0, str(Path(root) / "scripts"))
    try:
        from _agent_utils import redact_text

        payload = json.loads(raw.decode("utf-8", errors="replace"))
    except (ImportError, json.JSONDecodeError, TypeError, ValueError):
        return 0

    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    tool_input = payload.get("tool_input")
    command = tool_input.get("command", "") if isinstance(tool_input, dict) else ""
    command_text = serialize(command)
    if invokes_helper(command_text):
        return 0
    response = payload.get("tool_response", "")
    claude_keys = {"stdout", "stderr", "interrupted", "isImage"}
    looks_like_claude = isinstance(response, dict) and bool(claude_keys & response.keys())
    valid_claude = (
        looks_like_claude
        and isinstance(response.get("stdout"), str)
        and isinstance(response.get("stderr"), str)
        and type(response.get("interrupted")) is bool
        and type(response.get("isImage")) is bool
    )

    # Claude may run inside a Codex-started process and inherit PLUGIN_ROOT.
    # Prefer its documented Bash response shape over ambiguous environment aliases.
    if claude_root and looks_like_claude:
        if not valid_claude:
            return 0
    elif plugin_root:
        return 0
    else:
        return 0
    stdout = response["stdout"]
    stderr = response["stderr"]
    if len(stdout) + len(stderr) <= OUTPUT_THRESHOLD:
        return 0

    log_path = save_raw(serialize(response))
    stream_count = bool(stdout) + bool(stderr)
    budget = SUMMARY_LIMIT if stream_count == 1 else SUMMARY_LIMIT // 2
    updated = {
        "stdout": summary(command, stdout, log_path, redact_text, budget) if stdout else "",
        "stderr": summary(command, stderr, log_path, redact_text, budget) if stderr else "",
        "interrupted": response["interrupted"],
        "isImage": response["isImage"],
    }
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PostToolUse",
                    "updatedToolOutput": updated,
                }
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
