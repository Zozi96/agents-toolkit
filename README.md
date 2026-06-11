# Agents Toolkit

Global instruction installer for Codex, Claude Code, Pi Agent, and Antigravity CLI.

It installs:

- `AGENTS.md` to `~/.codex/AGENTS.md`
- `AGENTS.md` to `~/.claude/CLAUDE.md`
- `AGENTS.md` to `~/.pi/agent/AGENTS.md`
- `AGENTS.md` to `~/.gemini/GEMINI.md`
- Python helpers from `scripts/*.py` to `~/.agents/scripts/`

Existing files are backed up before overwrite with `.bak.YYYYMMDD-HHMMSS`. Unchanged files are skipped.

## Remote Install

macOS/Linux:

```bash
curl -fsSL https://raw.githubusercontent.com/Zozi96/agents-toolkit/main/install-remote.sh | bash
```

Windows PowerShell:

```powershell
irm https://raw.githubusercontent.com/Zozi96/agents-toolkit/main/install-remote.ps1 | iex
```

Alternative for forks/custom branches:

```powershell
$env:RAW_BASE = "https://raw.githubusercontent.com/Zozi96/agents-toolkit/main"
irm "$env:RAW_BASE/install-remote.ps1" | iex
```

## Local Install

macOS/Linux:

```bash
./install-agents.sh
```

Windows PowerShell:

```powershell
.\install-agents.ps1
```

## Dry Run

macOS/Linux:

```bash
./install-agents.sh --dry-run
curl -fsSL https://raw.githubusercontent.com/Zozi96/agents-toolkit/main/install-remote.sh | bash -s -- --dry-run
```

Windows PowerShell:

```powershell
.\install-agents.ps1 -DryRun
$raw = "https://raw.githubusercontent.com/Zozi96/agents-toolkit/main"
& ([scriptblock]::Create((irm "$raw/install-remote.ps1"))) -RawBase $raw -DryRun
```

## Notes

- Antigravity global rules use `~/.gemini/GEMINI.md`.
- Antigravity shared skills are separate from these Python helpers.
- Python helpers are plain scripts used by the global rules to reduce token waste when inspecting repos, files, logs, test output, JSON, CSV, TSV, JSONL, and NDJSON.
- `safe_read.py` reads targeted line ranges, tails, heads, or search snippets with secret redaction by default.
