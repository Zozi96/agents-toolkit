# Agents Toolkit

Extension for Pi, Claude Code, and Codex: compact repository inspection, redacted context, and token-capped command output.

## Pi Agent Extension Install

Install from GitHub:

```bash
pi install git:github.com/Zozi96/agents-toolkit
pi list
```

For local development from this repository:

```bash
pi install .
pi list
```

Start a new Pi session after installing. The package loads the existing skill, injects compact repository context, and blocks raw Bash commands that should use a capped helper. Python 3 is required. Pi already truncates oversized tool output natively, so the Claude-only `PostToolUse` compactor is not duplicated.

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
codex plugin list
```

For local development from this repository:

```bash
codex plugin marketplace add .
codex plugin add token-efficient-repo-work@agents-toolkit
codex plugin list
```

Update an existing installation:

```bash
python3 ~/.codex/skills/.system/plugin-creator/scripts/update_plugin_cachebuster.py plugins/token-efficient-repo-work
python3 scripts/sync_plugin.py
python3 ~/.codex/skills/.system/plugin-creator/scripts/validate_plugin.py plugins/token-efficient-repo-work
python3 -m unittest discover -s tests
# Commit and publish the validated changes, then:
codex plugin marketplace upgrade agents-toolkit
codex plugin add token-efficient-repo-work@agents-toolkit
```

Start a new thread after reinstalling so Codex picks up the refreshed plugin.

`codex plugin list` only confirms that the plugin is installed and enabled; it does not trust command hooks. Open `/hooks`, review and trust `SessionStart`, `PreToolUse`, and `PostToolUse` individually, then start a new Codex task. The `PreToolUse` hook denies clearly token-wasteful Bash commands (raw test runners, git patch dumps, `cat` of large files) and replies with the exact capped replacement.

The plugin is self-contained under `plugins/token-efficient-repo-work/`. Run `python3 scripts/sync_plugin.py` after changing canonical helpers or hooks.

## Token-Saving Model

The plugin bundles `SessionStart`, `PreToolUse`, and `PostToolUse` hooks, the `token-efficient-repo-work` skill,
and Python helpers. It does not install or modify `AGENTS.md`, `CLAUDE.md`, or
global instruction files.

Codex uses `PreToolUse` routing and its native result handling; its `PostToolUse` hook is silent. For Claude, `PostToolUse` replaces Bash output above 12,000 characters with redacted `stdout` and `stderr` summaries of at most 9,000 characters total and keeps the complete private log under `~/.codex/tmp/`. Smaller output and existing helper output pass unchanged, preserving the channels exactly as Claude reports them (some Claude Code versions merge process stderr into `stdout`).

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
| `evaluate_context.py` | Offline context-size, latency, section-presence, and changed-path recall evaluation. |
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
| `summarize_agent_usage.py` | Parse saved Codex JSONL or Claude JSON usage without calling a model. |

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
python3 scripts/run_capped.py -- pytest
python3 scripts/diff_summary.py --max-output-chars 12000
python3 scripts/diff_summary.py --base main --max-output-chars 12000
python3 scripts/diff_summary.py --staged
python3 scripts/summarize_json.py response.json --max-depth 3 --max-input-mb 10
python3 scripts/summarize_data.py data.csv --sample-rows 5
```

`agent_context.py` imprime `Next Token-Safe Steps` para dirigir la siguiente acción hacia lecturas pequeñas (por ejemplo `safe_read.py`) antes de ampliar el scope.

Evaluate context budgets offline (no model calls or quota use):

```bash
python3 scripts/evaluate_context.py . --budgets 1500,3000,4500 --repetitions 3
```

Capture real usage, then parse it locally:

```bash
codex exec --ephemeral --json "task" > ~/.codex/tmp/codex-usage.jsonl
python3 scripts/summarize_agent_usage.py codex ~/.codex/tmp/codex-usage.jsonl
claude -p "task" --output-format json --setting-sources "" > ~/.codex/tmp/claude-usage.json
python3 scripts/summarize_agent_usage.py claude ~/.codex/tmp/claude-usage.json
```

The two agent commands consume quota. Use `--bare` instead when authenticating Claude with
`ANTHROPIC_API_KEY`; `evaluate_context.py` and `summarize_agent_usage.py` do not invoke models.

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

Install the local plugin with Codex (these commands do not validate or trust its hooks):

```bash
codex plugin marketplace add .
codex plugin add token-efficient-repo-work@agents-toolkit
```

Then follow the installed/enabled and hook trust checks in [Codex Plugin Install](#codex-plugin-install).
