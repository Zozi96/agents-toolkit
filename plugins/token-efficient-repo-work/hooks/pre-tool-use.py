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
    r"\|\s*(?:head|tail|sed|awk|wc|grep|rg)\b|\|\s*select-object\s+-first\b|"
    r"(?:^|\s|;|&&|\|\|)(?:&>>?|1?>>?)\s*\S",
    re.IGNORECASE,
)
GIT_FILE_AT_REV = re.compile(r"git\s+show\s+[^|;&]*\S:\S")
HELPER_ROUTED = re.compile(
    r"summarize_json|summarize_data|diff_summary|run_capped|"
    r"safe_read|outline|scan_errors|compact_logs"
)


def helpers_dir():
    root = os.environ.get("CLAUDE_PLUGIN_ROOT") or os.environ.get("PLUGIN_ROOT")
    if root:
        return os.path.join(root, "scripts")
    return "${CLAUDE_PLUGIN_ROOT:-$PLUGIN_ROOT}/scripts"


def is_powershell():
    return os.name == "nt" or os.environ.get("PI_POWERSHELL") == "1"


def powershell_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def helper_command(name):
    helpers = helpers_dir()
    if is_powershell():
        return f"& {powershell_quote(sys.executable)} {powershell_quote(os.path.join(helpers, name))}"
    return f'python3 "{helpers}/{name}"'


def shell_command(command):
    if is_powershell():
        return f"pwsh -NoProfile -Command {powershell_quote(command)}"
    return f"sh -c {shlex.quote(command)}"


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
        # Non-POSIX mode on Windows: keep backslashes in paths like D:\repo\f.log
        tokens = shlex.split(command, posix=os.name != "nt")
    except ValueError:
        return None
    if not tokens or tokens[0] != "cat":
        return None
    for token in tokens[1:]:
        token = token.strip("\"'")
        if not token or token.startswith("-"):
            continue
        path = token if os.path.isabs(token) else os.path.join(cwd, token)
        try:
            if os.path.getsize(path) > BIG_FILE_BYTES:
                return path
        except OSError:
            continue
    return None


def check(command, cwd):
    if "run_capped.py" in command:
        return None
    if TEST_RUNNER.search(command):
        return (
            "Token-safe routing: run tests through the capped runner instead:\n"
            f"{helper_command('run_capped.py')} -- {shell_command(command)}"
        )
    if HELPER_ROUTED.search(command):
        return None

    if (
        GIT_PATCH.search(command)
        and not GIT_CAPPED.search(command)
        and not OUTPUT_CAPPED.search(command)
        and not GIT_FILE_AT_REV.search(command)
    ):
        return (
            "Token-safe routing: summarize git changes instead:\n"
            f"{helper_command('diff_summary.py')} .\n"
            f"For one file's hunks: {command} -- <path> | "
            + ("Select-Object -First 200" if is_powershell() else "head -c 12000")
        )

    if not OUTPUT_CAPPED.search(command):
        path = big_plain_read(command, cwd)
        if path:
            if path.endswith(".json"):
                return (
                    "Token-safe routing: file is large; summarize its shape instead:\n"
                    f"{helper_command('summarize_json.py')} {powershell_quote(path) if is_powershell() else shlex.quote(path)}"
                )
            if path.endswith((".jsonl", ".ndjson")):
                return (
                    "Token-safe routing: file is large; summarize its rows instead:\n"
                    f"{helper_command('summarize_data.py')} {powershell_quote(path) if is_powershell() else shlex.quote(path)}"
                )
            return (
                "Token-safe routing: file is large; outline it, then read only the relevant slice:\n"
                f"{helper_command('outline.py')} {powershell_quote(path) if is_powershell() else shlex.quote(path)}\n"
                f"{helper_command('safe_read.py')} {powershell_quote(path) if is_powershell() else shlex.quote(path)} --start N --end M"
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
