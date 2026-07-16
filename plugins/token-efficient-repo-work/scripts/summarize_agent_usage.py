#!/usr/bin/env python3
"""Summarize saved Codex or Claude usage without invoking a model."""

import argparse
import json
import sys
from pathlib import Path


def is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def load_codex(path):
    totals = {}
    turns = 0
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON on line {number}: {exc.msg}") from exc
        if not isinstance(event, dict):
            raise ValueError(f"invalid event on line {number}: expected an object")
        if event.get("type") != "turn.completed":
            continue
        usage = event.get("usage")
        if not isinstance(usage, dict):
            raise ValueError(f"invalid turn.completed usage on line {number}")
        turns += 1
        for key, value in usage.items():
            if is_number(value):
                totals[key] = totals.get(key, 0) + value
    if not turns:
        raise ValueError("no turn.completed events found")
    return {"runtime": "codex", "turns": turns, "usage": totals}


def load_claude(path):
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc.msg}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("usage"), dict):
        raise ValueError("invalid Claude export: expected an object with usage")
    token_fields = ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")
    for field in token_fields:
        if field in data["usage"] and not is_number(data["usage"][field]):
            raise ValueError(f"invalid Claude export: {field} must be numeric")
    if not any(field in data["usage"] for field in token_fields):
        raise ValueError("invalid Claude export: no token counts found")
    report = {"runtime": "claude", "usage": data["usage"]}
    if "total_cost_usd" in data:
        if not is_number(data["total_cost_usd"]):
            raise ValueError("invalid Claude export: total_cost_usd must be numeric")
        report["total_cost_usd"] = data["total_cost_usd"]
    model_usage = data.get("modelUsage", data.get("model_usage"))
    if model_usage is not None:
        if not isinstance(model_usage, dict):
            raise ValueError("invalid Claude export: modelUsage must be an object")
        report["modelUsage"] = model_usage
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime", choices=("codex", "claude"))
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    try:
        report = load_codex(args.file) if args.runtime == "codex" else load_claude(args.file)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
