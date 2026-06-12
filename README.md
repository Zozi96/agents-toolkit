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

## Token-Saving Model

`AGENTS.md` is intentionally compact because it is installed into each coding
agent's global instruction context. Longer explanations and recipes live here
instead of in the runtime rules.

Recommended inspection ladder:

1. Map the repo before broad exploration.
2. Search for targeted symbols or errors.
3. Read only the relevant file slice.
4. Capture large outputs to `~/.codex/tmp/` and summarize them.
5. Read raw files or full logs only when the helper summary is insufficient.

Example:

```bash
python3 ~/.agents/scripts/repo_map.py . --max-output-chars 12000
rg -n "symbol_or_error" . --glob '!node_modules' --glob '!.git' | head -c 12000
python3 ~/.agents/scripts/safe_read.py path/to/file.py --start 40 --end 120
```

## Helper Scripts

All helpers use only the Python standard library and redact likely secrets by
default.

| Helper | Use it for |
| --- | --- |
| `repo_map.py` | Compact repository orientation before broad exploration. |
| `safe_read.py` | Small redacted slices, heads, tails, and search snippets from text files or stdin. |
| `scan_errors.py` | Finding likely failures in logs, command output, or repositories. |
| `compact_logs.py` | Filtering logs by keyword, regex, level, tail, and context. |
| `summarize_tests.py` | Compressing pytest, Jest, Vitest, dotnet, and similar test output. |
| `diff_summary.py` | Summarizing staged, unstaged, untracked, or base-ref Git changes without full diffs. |
| `summarize_json.py` | Summarizing large JSON shape without dumping values; large files require `--force`. |
| `summarize_data.py` | Summarizing CSV, TSV, JSONL, and NDJSON files without pandas. |

Common commands:

```bash
python3 ~/.agents/scripts/safe_read.py app.py --head 80
python3 ~/.agents/scripts/safe_read.py server.log --find traceback --context 3
python3 ~/.agents/scripts/scan_errors.py output.txt --context 2 --limit 30
python3 ~/.agents/scripts/compact_logs.py app.log --keyword error --tail 500
pytest 2>&1 | python3 ~/.agents/scripts/summarize_tests.py -
python3 ~/.agents/scripts/diff_summary.py --max-output-chars 12000
python3 ~/.agents/scripts/diff_summary.py --base main --max-output-chars 12000
python3 ~/.agents/scripts/diff_summary.py --staged
python3 ~/.agents/scripts/summarize_json.py response.json --max-depth 3 --max-input-mb 10
python3 ~/.agents/scripts/summarize_data.py data.csv --sample-rows 5
```

`scan_errors.py`, `compact_logs.py`, and `summarize_tests.py` use consistent
snippet markers: context lines start with spaces and match lines start with
`>>`. Unreadable files are summarized compactly instead of being skipped
silently.

## Validation

Check the runtime instruction budget:

```bash
wc -c AGENTS.md README.md
```

Validate helper syntax:

```bash
python3 -m py_compile scripts/*.py
python3 scripts/diff_summary.py --max-output-chars 12000
python3 scripts/diff_summary.py --base HEAD --max-output-chars 12000
```

Run the helper tests:

```bash
python3 -m unittest discover -s tests
```

Validate the installer without touching global files:

```bash
./install-agents.sh --dry-run
```
