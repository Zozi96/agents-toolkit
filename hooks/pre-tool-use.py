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

GIT_SUMMARY_OPTIONS = {"--name-only", "--name-status", "--numstat", "--oneline", "--shortstat", "--stat", "-s"}


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


def tokenize(command):
    try:
        lexer = shlex.shlex(command, posix=not is_powershell(), punctuation_chars="|;&<>")
        lexer.whitespace_split = True
        lexer.commenters = ""
        return list(lexer)
    except ValueError:
        return []


def shell_commands(command):
    current = []
    for token in tokenize(command):
        if token and set(token) <= {"|", ";", "&"}:
            if current:
                yield current
                current = []
        else:
            current.append(token)
    if current:
        yield current


def program_name(token):
    name = os.path.basename(token.strip("'\"")).lower()
    return re.sub(r"\.(?:bat|cmd|exe)$", "", name)


def runs_tests(command):
    for tokens in shell_commands(command):
        program = program_name(tokens[0])
        arguments = tokens[1:]
        if program == "pytest":
            return True
        if re.fullmatch(r"python(?:\d+(?:\.\d+)?)?|py", program):
            if program == "py" and arguments[:1] and re.fullmatch(r"-\d+(?:\.\d+)?", arguments[0]):
                arguments = arguments[1:]
            if arguments[:2] == ["-m", "pytest"]:
                return True
        if program in {"npm", "pnpm"} and (arguments[:1] == ["test"] or arguments[:2] == ["run", "test"]):
            return True
        if program in {"yarn", "go", "cargo", "dotnet"} and arguments[:1] == ["test"]:
            return True
    return False


def shell_segments(command):
    start = 0
    quote = None
    escaped = False
    index = 0
    while index < len(command):
        char = command[index]
        if escaped:
            escaped = False
        elif char in "\\`" and quote != "'":
            escaped = True
        elif quote:
            if char == quote:
                quote = None
        elif char in "'\"":
            quote = char
        elif char == ";" or command[index : index + 2] in ("&&", "||"):
            yield command[start:index]
            index += 1 if char == ";" else 2
            start = index
            continue
        index += 1
    yield command[start:]


def stdout_redirected(tokens):
    for index, token in enumerate(tokens):
        if token in {"&>", "&>>"}:
            return True
        if token in {">", ">>", ">&", ">>&"} and (index == 0 or tokens[index - 1] != "2"):
            return True
    return False


def bounded_filter(tokens):
    if not tokens:
        return False
    program = program_name(tokens[0])
    arguments = [argument.lower() for argument in tokens[1:]]
    if program == "wc":
        return True
    if program == "select-object":
        return any(
            argument == "-first" and index + 1 < len(arguments) and arguments[index + 1].isdigit()
            for index, argument in enumerate(arguments)
        )
    if program not in {"head", "tail"}:
        return False
    if program == "tail" and any(argument in {"-f", "--follow"} or argument.startswith("--follow=") for argument in arguments):
        return False
    for index, argument in enumerate(arguments):
        if argument in {"-c", "-n", "--bytes", "--lines"}:
            if index + 1 >= len(arguments) or not arguments[index + 1].isdigit():
                return False
        elif argument.startswith(("--bytes=", "--lines=")) and not argument.split("=", 1)[1].isdigit():
            return False
        elif re.fullmatch(r"-[cn][+-].*", argument):
            return False
    return True


def output_capped(segment):
    tokens = tokenize(segment)
    if stdout_redirected(tokens):
        return True
    pipelines = []
    current = []
    for token in tokens:
        if token in {"|", "|&"}:
            pipelines.append(current)
            current = []
        else:
            current.append(token)
    pipelines.append(current)
    return len(pipelines) > 1 and bounded_filter(pipelines[-1])


def big_plain_read(command, cwd):
    """Return the first uncapped large file read via cat, or None."""
    for segment in shell_segments(command):
        if output_capped(segment):
            continue
        for tokens in shell_commands(segment):
            if program_name(tokens[0]) != "cat":
                continue
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


def git_patch(tokens):
    if len(tokens) < 2 or program_name(tokens[0]) != "git":
        return False
    verb = tokens[1].lower()
    return verb in {"diff", "show"} or (verb == "log" and any(token in {"-p", "--patch"} for token in tokens[2:]))


def uncapped_git_patch(command):
    for segment in shell_segments(command):
        tokens = tokenize(segment)
        if not git_patch(tokens) or output_capped(segment):
            continue
        verb = tokens[1].lower()
        arguments = tokens[2:]
        options = arguments[: arguments.index("--")] if "--" in arguments else arguments
        explicit_patch = any(argument in {"-p", "--patch"} for argument in options)
        if verb != "log" and not explicit_patch and any(
            argument in GIT_SUMMARY_OPTIONS or argument.startswith("--stat=") for argument in options
        ):
            continue
        if verb == "show" and any(":" in argument for argument in options if not argument.startswith("-")):
            continue
        return segment.strip()
    return None


def check(command, cwd):
    # ponytail: skip multiline shell; use a real shell parser if newline routing becomes necessary.
    if "\n" in command or "\r" in command:
        return None
    if runs_tests(command):
        return (
            "Token-safe routing: run tests through the capped runner instead:\n"
            f"{helper_command('run_capped.py')} -- {shell_command(command)}"
        )

    git_command = uncapped_git_patch(command)
    if git_command:
        return (
            "Token-safe routing: summarize git changes instead:\n"
            f"{helper_command('diff_summary.py')} .\n"
            f"For capped patch output: {git_command} | "
            + ("Select-Object -First 200" if is_powershell() else "head -c 12000")
        )

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
    # Read stdin fully as bytes first: a decode abort mid-stream would leave
    # unread payload and break the harness's pipe write (EPIPE).
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, OSError, ValueError):
        return 0
    if not isinstance(payload, dict) or payload.get("tool_name") != "Bash":
        return 0
    command = (payload.get("tool_input") or {}).get("command") or ""
    cwd = payload.get("cwd") or os.getcwd()
    reason = check(command, cwd)
    if reason:
        deny(reason)
    return 0


if __name__ == "__main__":
    sys.exit(main())
