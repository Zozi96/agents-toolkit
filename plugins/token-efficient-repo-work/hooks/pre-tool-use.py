#!/usr/bin/env python3
"""Deny reliably token-wasteful Bash commands, replying with the exact capped replacement.

Only high-precision interceptions: raw test runners, git patch dumps, and
plain reads of large files. Everything else passes untouched so the agent
workflow keeps its normal speed.
"""
import json
import os
import re
import shlex
import sys

BIG_FILE_BYTES = 48_000  # ~12K tokens of raw text

TEST_RUNNER = re.compile(
    r"(?:^|&&|\|\||;)\s*(?:python3?\s+-m\s+)?"
    r"(?:pytest|npm\s+(?:run\s+)?test|pnpm\s+(?:run\s+)?test|yarn\s+test|"
    r"go\s+test|cargo\s+test|dotnet\s+test)\b"
)
GIT_PATCH = re.compile(r"(?:^|&&|\|\||;)\s*git\s+(?:diff\b|show\b|log\s[^|;&]*(?:-p\b|--patch\b))")
GIT_CAPPED = re.compile(r"--stat|--shortstat|--name-only|--name-status|--oneline|--numstat|\s-s\b")
OUTPUT_CAPPED = re.compile(
    # Piped through a capping filter, or stdout redirected to a file
    # (zero terminal output = zero token cost). `2>&1` alone is not a cap.
    r"\|\s*(?:head|tail|sed|awk|wc|grep|rg)\b|(?:^|\s|;|&&|\|\|)(?:&>>?|1?>>?)\s*\S"
)
GIT_FILE_AT_REV = re.compile(r"git\s+show\s+[^|;&]*\S:\S")
HELPER_ROUTED = re.compile(
    r"summarize_tests|summarize_json|summarize_data|diff_summary|run_capped|"
    r"safe_read|outline|scan_errors|compact_logs"
)


def helpers_dir():
    root = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.environ.get("PLUGIN_ROOT")
    if root:
        return os.path.join(root, "scripts")
    return "${CLAUDE_PLUGIN_ROOT:-$PLUGIN_ROOT}/scripts"


def deny(reason):
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


def big_plain_read(command, cwd):
    """Return the first large file read via bare cat, or None."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        return None
    if not tokens or tokens[0] != "cat":
        return None
    for token in tokens[1:]:
        if token.startswith("-"):
            continue
        path = token if os.path.isabs(token) else os.path.join(cwd, token)
        try:
            if os.path.getsize(path) > BIG_FILE_BYTES:
                return path
        except OSError:
            continue
    return None


def check(command, cwd):
    if HELPER_ROUTED.search(command):
        return None
    helpers = helpers_dir()

    if TEST_RUNNER.search(command) and not OUTPUT_CAPPED.search(command):
        return (
            "Token-safe routing: pipe test output through the summarizer instead:\n"
            f'{command} 2>&1 | python3 "{helpers}/summarize_tests.py" -'
        )

    if (
        GIT_PATCH.search(command)
        and not GIT_CAPPED.search(command)
        and not OUTPUT_CAPPED.search(command)
        and not GIT_FILE_AT_REV.search(command)
    ):
        return (
            "Token-safe routing: summarize git changes instead:\n"
            f'python3 "{helpers}/diff_summary.py" .\n'
            f"For one file's hunks: {command} -- <path> | head -c 12000"
        )

    if not OUTPUT_CAPPED.search(command):
        path = big_plain_read(command, cwd)
        if path:
            if path.endswith((".json", ".jsonl", ".ndjson")):
                return (
                    "Token-safe routing: file is large; summarize its shape instead:\n"
                    f'python3 "{helpers}/summarize_json.py" "{path}"'
                )
            return (
                "Token-safe routing: file is large; outline it, then read only the relevant slice:\n"
                f'python3 "{helpers}/outline.py" "{path}"\n'
                f'python3 "{helpers}/safe_read.py" "{path}" --start N --end M'
            )
    return None


def main():
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError):
        return 0
    if payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    cwd = payload.get("cwd") or os.getcwd()
    reason = check(command, cwd)
    if reason:
        deny(reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
