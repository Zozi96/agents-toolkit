#!/usr/bin/env python3
"""Refresh the self-contained plugin (Codex + Claude Code) from canonical toolkit files."""
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "token-efficient-repo-work"
HELPERS = (
    "_agent_utils.py",
    "agent_context.py",
    "compact_logs.py",
    "diff_summary.py",
    "outline.py",
    "repo_map.py",
    "run_capped.py",
    "safe_read.py",
    "scan_errors.py",
    "summarize_data.py",
    "summarize_json.py",
    "summarize_tests.py",
)


def copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main():
    for name in ("session-start.py", "session-start.ps1", "pre-tool-use.py", "pre-tool-use.ps1"):
        copy(ROOT / "hooks" / name, PLUGIN / "hooks" / name)
    for helper in HELPERS:
        copy(ROOT / "scripts" / helper, PLUGIN / "scripts" / helper)
    hooks = {
        "hooks": {
            "SessionStart": [
                {
                    # Skip "resume": the context injected at startup is still
                    # in the conversation; re-inject only when it was lost.
                    "matcher": "startup|clear|compact",
                    "hooks": [
                        {
                            "type": "command",
                            # Shell fallbacks keep one hooks.json for both agents:
                            # Claude Code exports CLAUDE_PLUGIN_ROOT, Codex exports
                            # PLUGIN_ROOT; python3 may be plain python on Windows.
                            "command": '"$(command -v python3 || command -v python)" "${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT}}/hooks/session-start.py"',
                            "commandWindows": "pwsh -NoProfile -Command \"$r = if ($env:CLAUDE_PLUGIN_ROOT) { $env:CLAUDE_PLUGIN_ROOT } else { $env:PLUGIN_ROOT }; & (Join-Path $r 'hooks/session-start.ps1')\"",
                            "timeout": 15,
                            "statusMessage": "Loading token-safe repository context",
                        }
                    ]
                }
            ],
            "PreToolUse": [
                {
                    # Deny reliably token-wasteful Bash commands (raw test
                    # runners, git patch dumps, cat of large files) and reply
                    # with the exact capped replacement so the agent retries
                    # in one step. High-precision only; everything else passes.
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": '"$(command -v python3 || command -v python)" "${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT}}/hooks/pre-tool-use.py"',
                            "commandWindows": "pwsh -NoProfile -Command \"$r = if ($env:CLAUDE_PLUGIN_ROOT) { $env:CLAUDE_PLUGIN_ROOT } else { $env:PLUGIN_ROOT }; & (Join-Path $r 'hooks/pre-tool-use.ps1')\"",
                            "timeout": 5,
                            "statusMessage": "Checking token-safe command routing",
                        }
                    ]
                }
            ]
        }
    }
    (PLUGIN / "hooks/hooks.json").write_text(json.dumps(hooks, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
