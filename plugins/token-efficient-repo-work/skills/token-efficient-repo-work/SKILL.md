---
name: token-efficient-repo-work
description: Inspect and diagnose software repositories with minimal context across POSIX shells and Windows PowerShell by routing code exploration, large files, logs, tests, diffs, JSON, CSV, TSV, JSONL, and unknown-size commands through token-capped, redacting helpers. Use when Codex needs to understand a codebase, locate relevant code, review changes, analyze failures, or process potentially large or sensitive local output without loading raw data into context.
---

# Token-Efficient Repo Work

Minimize context without sacrificing evidence. Use bundled helpers from `$PLUGIN_ROOT/scripts` when installed as a plugin; otherwise use `~/.agents/scripts`. Do not rewrite them.

## Workflow

1. Prefer an available indexed code graph, repository memory, or context-processing tool. Use the helpers as the deterministic fallback.
2. Resolve the helper directory, then reuse `Repository Context` injected by the `SessionStart` hook when present. Do not rerun orientation unless that context is missing, stale, or insufficient. Otherwise run:

   ```bash
   helpers="${PLUGIN_ROOT:-$HOME/.agents}/scripts"
   python3 "$helpers/agent_context.py" . --max-output-chars 12000
   ```

3. Follow `Next Token-Safe Steps`. Search the exact symbol or error before broad reading:

   ```bash
   rg -n "symbol_or_error" . --glob '!node_modules' --glob '!.git' | head -c 12000
   ```

4. Outline the likely file, then read only the relevant slice:

   ```bash
   python3 "$helpers/outline.py" path
   python3 "$helpers/safe_read.py" path --start 1 --end 120
   ```

5. Expand one rung at a time only when the current evidence is insufficient. Stop as soon as the task is answerable.

## Windows PowerShell

Detect Windows PowerShell through `$PSVersionTable`. Use these equivalents instead of Bash syntax:

```powershell
$helpers = if ($env:PLUGIN_ROOT) { Join-Path $env:PLUGIN_ROOT "scripts" } else { Join-Path $HOME ".agents/scripts" }
$python = if (Get-Command py -ErrorAction SilentlyContinue) { "py" }
    elseif (Get-Command python -ErrorAction SilentlyContinue) { "python" }
    elseif (Get-Command python3 -ErrorAction SilentlyContinue) { "python3" }
    else { throw "Python 3 is required" }
$pythonArgs = if ($python -eq "py") { @("-3") } else { @() }
& $python @pythonArgs (Join-Path $helpers "agent_context.py") . --max-output-chars 12000
rg -n "symbol_or_error" . --glob "!node_modules" --glob "!.git" |
    ForEach-Object { if ($_.Length -gt 240) { $_.Substring(0, 240) } else { $_ } } |
    Select-Object -First 50
& $python @pythonArgs (Join-Path $helpers "outline.py") path
& $python @pythonArgs (Join-Path $helpers "safe_read.py") path --start 1 --end 120
```

Pipe tests and cap unknown commands in PowerShell as follows:

```powershell
pytest 2>&1 | & $python @pythonArgs (Join-Path $helpers "summarize_tests.py") -
& $python @pythonArgs (Join-Path $helpers "run_capped.py") -- COMMAND
```

Keep temporary output under `$HOME/.codex/tmp`.

## Route by Input

| Input | Helper |
| --- | --- |
| Repository orientation | `agent_context.py` |
| File or directory structure | `outline.py` |
| Targeted file slice or match | `safe_read.py` |
| Unknown-size command | `run_capped.py` |
| Error-heavy logs or output | `scan_errors.py` |
| Keyword, level, regex, or tail log filtering | `compact_logs.py` |
| Test output | `summarize_tests.py` |
| Git changes | `diff_summary.py` |
| JSON shape | `summarize_json.py` |
| CSV, TSV, JSONL, or NDJSON | `summarize_data.py` |

Pipe noisy tests into the summarizer:

```bash
pytest 2>&1 | python3 "$helpers/summarize_tests.py" -
```

Run other noisy commands through the capped runner:

```bash
python3 "$helpers/run_capped.py" -- COMMAND
```

## Guardrails

- Preserve redaction defaults. Never request secrets unless the user explicitly requires the raw value and it is safe to reveal.
- Keep scratch files and full logs outside repositories, preferably under `~/.codex/tmp/`.
- Cap recursive or unknown output before observing it.
- Prefer line references, paths, counts, and the first relevant error over raw dumps.
- Preserve user changes and keep Git operations read-only unless the user authorizes mutation.
- If a helper is missing, use the repository-local `scripts/` copy when available. Otherwise use the smallest native capped fallback and report the missing helper; do not install implicitly.

## Report

Return the conclusion first, then cite the smallest evidence needed: paths, line numbers, command status, and anything not validated. Do not paste full source, logs, or datasets unless requested.
