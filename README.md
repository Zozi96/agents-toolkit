# Agents Toolkit

Plugin for Claude Code and Codex: compact repository inspection, redacted context, and token-capped command output.

## Claude Code Plugin Install

Install from GitHub:

```
/plugin marketplace add Zozi96/agents-toolkit
/plugin install token-efficient-repo-work@agents-toolkit
```

For local development from this repository:

```
/plugin marketplace add .
/plugin install token-efficient-repo-work@agents-toolkit
```

Restart the session so the `SessionStart` hook injects `Repository Context`. Validate packaging with:

```bash
claude plugin validate plugins/token-efficient-repo-work
claude plugin validate .
```

## Codex Plugin Install

Install from GitHub:

```bash
codex plugin marketplace add Zozi96/agents-toolkit
codex plugin add token-efficient-repo-work@agents-toolkit
```

For local development from this repository:

```bash
codex plugin marketplace add .
codex plugin add token-efficient-repo-work@agents-toolkit
```

Update an existing installation:

```bash
codex plugin marketplace upgrade agents-toolkit
codex plugin add token-efficient-repo-work@agents-toolkit
```

Start a new Codex task after installation. Review and trust the bundled `SessionStart` hook with `/hooks`; plugin installation does not automatically trust command hooks.

The plugin is self-contained under `plugins/token-efficient-repo-work/`. Run `python3 scripts/sync_plugin.py` after changing canonical helpers, hooks, or the skill.

## Token-Saving Model

The plugin bundles a `SessionStart` hook, the `token-efficient-repo-work` skill,
and Python helpers. It does not install or modify `AGENTS.md`, `CLAUDE.md`, or
global instruction files.

Recommended inspection ladder:

1. Get medium context with one command.
2. Search for targeted symbols or errors.
3. Outline the file structure to find the right slice.
4. Read only the relevant file slice.
5. Run unknown-size commands through `run_capped.py`; the full log stays in `~/.codex/tmp/`.
6. Read raw files or full logs only when the helper summary is insufficient.

Example:

```bash
python3 scripts/agent_context.py . --max-output-chars 12000
rg -n "symbol_or_error" . --glob '!node_modules' --glob '!.git' | head -c 12000
python3 scripts/safe_read.py path/to/file.py --start 40 --end 120
```

## Helper Scripts

All helpers use only the Python standard library and redact likely secrets by
default.

| Helper | Use it for |
| --- | --- |
| `agent_context.py` | One-command medium repo context: map + diff summary, optional error scan, and token-safe follow-up suggestions. |
| `repo_map.py` | Compact repository orientation before broad exploration. |
| `outline.py` | Code structure (defs, classes, exports) with line numbers and without bodies, for a file or directory. Locate the right slice before reading content. |
| `run_capped.py` | Run a command, keep the full raw output in `~/.codex/tmp/`, and print only exit code, head, tail, and error lines. |
| `safe_read.py` | Small redacted slices, heads, tails, and search snippets from text files or stdin. |
| `scan_errors.py` | Finding likely failures in logs, command output, or repositories. |
| `compact_logs.py` | Filtering logs by keyword, regex, level, tail, and context. |
| `summarize_tests.py` | Compressing pytest, Jest, Vitest, dotnet, and similar test output. |
| `diff_summary.py` | Summarizing staged, unstaged, untracked, or base-ref Git changes without full diffs. |
| `summarize_json.py` | Summarizing large JSON shape without dumping values; large files require `--force`. |
| `summarize_data.py` | Summarizing CSV, TSV, JSONL, and NDJSON files without pandas. |

Common commands:

```bash
python3 scripts/agent_context.py . --max-output-chars 12000
python3 scripts/agent_context.py . --scan-errors --max-output-chars 12000
python3 scripts/outline.py src/ --max-files 40
python3 scripts/run_capped.py -- npm run build
python3 scripts/safe_read.py app.py --head 80
python3 scripts/safe_read.py server.log --find traceback --context 3
python3 scripts/scan_errors.py output.txt --context 2 --limit 30
python3 scripts/compact_logs.py app.log --keyword error --tail 500
pytest 2>&1 | python3 scripts/summarize_tests.py -
python3 scripts/diff_summary.py --max-output-chars 12000
python3 scripts/diff_summary.py --base main --max-output-chars 12000
python3 scripts/diff_summary.py --staged
python3 scripts/summarize_json.py response.json --max-depth 3 --max-input-mb 10
python3 scripts/summarize_data.py data.csv --sample-rows 5
```

`agent_context.py` imprime `Next Token-Safe Steps` para dirigir la siguiente acción hacia lecturas pequeñas (por ejemplo `safe_read.py`) antes de ampliar el scope.

`scan_errors.py`, `compact_logs.py`, and `summarize_tests.py` use consistent
snippet markers: context lines start with spaces and match lines start with
`>>`. Unreadable files are summarized compactly instead of being skipped
silently.

## Validation

Refresh the self-contained plugin and validate helper syntax:

```bash
python3 scripts/sync_plugin.py
python3 -m py_compile scripts/*.py
python3 scripts/agent_context.py . --max-output-chars 12000
python3 scripts/diff_summary.py --max-output-chars 12000
python3 scripts/diff_summary.py --base HEAD --max-output-chars 12000
```

Run the helper tests:

```bash
python3 -m unittest discover -s tests
```

Validate local plugin installation with Codex:

```bash
codex plugin marketplace add .
codex plugin add token-efficient-repo-work@agents-toolkit
```
