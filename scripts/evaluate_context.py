#!/usr/bin/env python3
"""Measure agent_context output offline without invoking a model."""

import argparse
import json
import os
import re
import statistics
import subprocess
import sys
import time
from pathlib import Path


SECTIONS = ("Git Diff Summary", "Next Token-Safe Steps", "Repository Map")


def path_present(path, output):
    return re.search(rf"(?:^|\s){re.escape(path)}$", output, re.MULTILINE) is not None


def positive_csv(value):
    try:
        budgets = [int(item) for item in value.split(",")]
    except ValueError as exc:
        raise argparse.ArgumentTypeError("budgets must be comma-separated integers") from exc
    if not budgets or any(budget <= 0 for budget in budgets):
        raise argparse.ArgumentTypeError("budgets must be greater than zero")
    return budgets


def changed_paths(repo):
    result = subprocess.run(
        ["git", "-C", str(repo), "status", "--porcelain=v1"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git status failed")
    paths = []
    for line in result.stdout.splitlines():
        path = line[3:]
        if " -> " in path:
            path = path.rsplit(" -> ", 1)[1]
        paths.append(path.strip('"'))
    return paths[:3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("path", nargs="?", default=".", help="Git repository to evaluate")
    parser.add_argument("--budgets", type=positive_csv, default=[1500, 3000, 4500])
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if args.repetitions <= 0:
        parser.error("--repetitions must be greater than zero")

    repo = Path(args.path).resolve()
    try:
        paths = changed_paths(repo)
    except RuntimeError as exc:
        parser.error(str(exc))
    context_script = Path(__file__).with_name("agent_context.py")
    results = []
    for budget in args.budgets:
        latencies = []
        output = ""
        for _ in range(args.repetitions):
            started = time.perf_counter()
            run = subprocess.run(
                [sys.executable, str(context_script), str(repo), "--max-output-chars", str(budget)],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                check=False,
            )
            latencies.append((time.perf_counter() - started) * 1000)
            if run.returncode != 0:
                parser.error(run.stderr.strip() or "agent_context.py failed")
            output = run.stdout.rstrip("\n")
        found = sum(path_present(path, output) for path in paths)
        results.append(
            {
                "budget": budget,
                "chars": len(output),
                "lines": len(output.splitlines()),
                "median_latency_ms": round(statistics.median(latencies), 3),
                "sections": {section: section in output for section in SECTIONS},
                "path_recall": round(found / len(paths), 3) if paths else 1.0,
            }
        )

    print(
        json.dumps(
            {
                "repository": str(repo),
                "budgets": args.budgets,
                "repetitions": args.repetitions,
                "changed_paths": paths,
                "results": results,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
