#!/usr/bin/env python3
"""Merge the toolkit hook into hooks.json while preserving other hooks."""
import json
import sys


MARKER = ".agents/hooks/session-start.py"


def load(path, missing_ok=False):
    try:
        with open(path, encoding="utf-8") as fh:
            value = json.load(fh)
    except FileNotFoundError:
        if missing_ok:
            return {}
        raise
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def merge(source, destination):
    result = dict(destination)
    hooks = dict(result.get("hooks") or {})
    for event, source_groups in (source.get("hooks") or {}).items():
        kept = []
        for group in hooks.get(event, []):
            group = dict(group)
            handlers = [
                handler
                for handler in group.get("hooks", [])
                if MARKER not in str(handler.get("command", ""))
            ]
            if handlers:
                group["hooks"] = handlers
                kept.append(group)
        hooks[event] = kept + source_groups
    result["hooks"] = hooks
    return result


def main(argv):
    if len(argv) not in (3, 4):
        print("Usage: merge_hooks.py SOURCE DESTINATION [OUT]", file=sys.stderr)
        return 2
    try:
        merged = merge(load(argv[1]), load(argv[2], missing_ok=True))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    text = json.dumps(merged, indent=2) + "\n"
    if len(argv) == 4:
        with open(argv[3], "w", encoding="utf-8") as fh:
            fh.write(text)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
