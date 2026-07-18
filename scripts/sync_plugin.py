#!/usr/bin/env python3
"""Refresh the self-contained plugin (Codex + Claude Code) from canonical toolkit files."""
import json
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / "plugins" / "token-efficient-repo-work"
HELPERS = (
    "_agent_utils.py",
    "agent_context.py",
    "compact_logs.py",
    "diff_summary.py",
    "evaluate_context.py",
    "outline.py",
    "repo_map.py",
    "run_capped.py",
    "safe_read.py",
    "scan_errors.py",
    "summarize_data.py",
    "summarize_agent_usage.py",
    "summarize_json.py",
    "summarize_tests.py",
)


def copy(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def main():
    for name in (
        "session-start.py",
        "session-start.ps1",
        "pre-tool-use.py",
        "pre-tool-use.ps1",
        "post-tool-use.py",
        "post-tool-use.ps1",
    ):
        copy(ROOT / "hooks" / name, PLUGIN / "hooks" / name)
    for helper in HELPERS:
        copy(ROOT / "scripts" / helper, PLUGIN / "scripts" / helper)
    codex_manifest = json.loads((PLUGIN / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
    claude_manifest_path = PLUGIN / ".claude-plugin/plugin.json"
    claude_text = claude_manifest_path.read_text(encoding="utf-8")
    claude_version = json.loads(claude_text)["version"]
    claude_text, replacements = re.subn(
        r'("version"\s*:\s*)' + re.escape(json.dumps(claude_version)),
        lambda match: match.group(1) + json.dumps(codex_manifest["version"]),
        claude_text,
        count=1,
    )
    if replacements != 1:
        raise ValueError("Claude manifest version field not found")
    claude_manifest_path.write_text(claude_text, encoding="utf-8")
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
                            # ponytail: if neither root var is set (seen on some
                            # Codex startups) skip instead of failing with exit 2.
                            # Drain stdin before any skip path: leaving the payload
                            # unread makes the harness's pipe write fail with
                            # "failed to write hook stdin: Broken pipe" (EPIPE).
                            "command": 'p="${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}"; y="$(command -v python3 || command -v python)"; if [ -n "$y" ] && [ -f "$p/hooks/session-start.py" ]; then exec "$y" "$p/hooks/session-start.py"; fi; cat >/dev/null 2>&1; exit 0',
                            "commandWindows": "pwsh -NoProfile -Command \"$r = if ($env:CLAUDE_PLUGIN_ROOT) { $env:CLAUDE_PLUGIN_ROOT } else { $env:PLUGIN_ROOT }; $s = if ($r) { Join-Path $r 'hooks/session-start.ps1' }; if ($s -and (Test-Path $s)) { & $s } else { $null = [Console]::In.ReadToEnd(); exit 0 }\"",
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
                            "command": 'p="${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}"; y="$(command -v python3 || command -v python)"; if [ -n "$y" ] && [ -f "$p/hooks/pre-tool-use.py" ]; then exec "$y" "$p/hooks/pre-tool-use.py"; fi; cat >/dev/null 2>&1; exit 0',
                            "commandWindows": "pwsh -NoProfile -Command \"$r = if ($env:CLAUDE_PLUGIN_ROOT) { $env:CLAUDE_PLUGIN_ROOT } else { $env:PLUGIN_ROOT }; $s = if ($r) { Join-Path $r 'hooks/pre-tool-use.ps1' }; if ($s -and (Test-Path $s)) { & $s } else { $null = [Console]::In.ReadToEnd(); exit 0 }\"",
                            "timeout": 5,
                            "statusMessage": "Checking token-safe command routing",
                        }
                    ]
                }
            ],
            "PostToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'p="${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}"; y="$(command -v python3 || command -v python)"; if [ -n "$y" ] && [ -f "$p/hooks/post-tool-use.py" ]; then exec "$y" "$p/hooks/post-tool-use.py"; fi; cat >/dev/null 2>&1; exit 0',
                            "commandWindows": "pwsh -NoProfile -Command \"$r = if ($env:CLAUDE_PLUGIN_ROOT) { $env:CLAUDE_PLUGIN_ROOT } else { $env:PLUGIN_ROOT }; $s = if ($r) { Join-Path $r 'hooks/post-tool-use.ps1' }; if ($s -and (Test-Path $s)) { & $s } else { $null = [Console]::In.ReadToEnd(); exit 0 }\"",
                            "timeout": 5,
                            "statusMessage": "Compacting oversized command output",
                        }
                    ],
                }
            ]
        }
    }
    (PLUGIN / "hooks/hooks.json").write_text(json.dumps(hooks, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
