# Global Private Codex Rules

Goal: correct, private, small context, reversible work.

## Workflow

1. Understand exact task.
2. Get compact context first:

```bash
python3 ~/.agents/scripts/agent_context.py . --max-output-chars 12000
```

3. Search targeted symbols/errors:

```bash
rg -n "symbol_or_error" . --glob '!node_modules' --glob '!.git' | head -c 12000
```

4. Read only needed slices:

```bash
python3 ~/.agents/scripts/safe_read.py path --start 1 --end 120
```

5. Si `agent_context.py` devuelve `Next Token-Safe Steps`, ejecuta esa ruta primero y reevalúa la lectura del output antes de abrir archivos completos.

## Privacy

Keep scratch, maps, notes, summaries, large output outside repos unless asked:

- Helpers: `~/.agents/scripts/`
- Temp output: `~/.codex/tmp/`

Do not create repo-local private files by default: `repo_map.txt`, `codex-notes.md`, `.codex-local/`, debug dumps. Do not edit git ignore/config just to hide them.

Treat `.env*`, keys, tokens, cookies, auth headers, private keys, cloud creds, DB dumps as secret. Do not print full secrets. Show key names, redacted values, or targeted safe lines only. Redact as `****`.

## Git Safety

Do not mutate git state unless asked. Forbidden by default: `git add`, `git commit`, `git reset`, `git clean`, `git checkout`, `git switch`, `git stash`, history rewrites, remote changes, branch/tag deletion, git ignore/config edits.

Read-only git ok; cap output:

```bash
git status --short 2>&1 | head -c 6000
git diff --stat 2>&1 | head -c 6000
git diff --name-only 2>&1 | head -c 6000
git log --oneline -20 2>&1 | head -c 6000
```

Never revert/overwrite user changes unless explicitly asked.

## Output Discipline

Cap unknown/recursive/large output:

```bash
COMMAND 2>&1 | head -c 6000
```

Prefer helpers before raw files:

| Need | Helper |
| --- | --- |
| First repo context | `agent_context.py` |
| Repo map | `repo_map.py` |
| Sensitive/large text | `safe_read.py` |
| Logs/errors | `scan_errors.py`, `compact_logs.py` |
| Tests | `summarize_tests.py` |
| Diff | `diff_summary.py` |
| JSON | `summarize_json.py` |
| CSV/TSV/JSONL | `summarize_data.py` |

Skip generated/heavy/binary paths by default: `.git`, `node_modules`, `.venv`, `venv`, `env`, `dist`, `build`, `target`, `bin`, `obj`, `coverage`, `.next`, `.nuxt`, `.cache`, `__pycache__`, `vendor`, archives, media, DBs, locks.

## Editing

Preserve architecture, names, formatting. Avoid unrelated refactors, deps, generated files, whole-repo formatters. Before broad edits, state scope. After edits, report files + validation.

## Testing

Use smallest useful validation. Summarize noisy tests:

```bash
pytest 2>&1 | python3 ~/.agents/scripts/summarize_tests.py -
npm test 2>&1 | python3 ~/.agents/scripts/summarize_tests.py -
dotnet test 2>&1 | python3 ~/.agents/scripts/summarize_tests.py -
```

On failure: summarize failing tests, first relevant error, file/line refs, next smallest diagnostic step.

## Response

Be concise. Prefer paths, line refs, commands, validation status. Do not paste full source/logs/data unless asked. Say what was not validated.
