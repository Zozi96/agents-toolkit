import os
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def run_script(script, *args, input_text=None, cwd=ROOT):
    return subprocess.run(
        [PYTHON, str(ROOT / "scripts" / script), *args],
        input=input_text,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        check=False,
    )


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )


def init_repo(path):
    git(path, "init")
    git(path, "config", "user.email", "test@example.invalid")
    git(path, "config", "user.name", "Test User")
    (path / "file.txt").write_text("old\n", encoding="utf-8")
    git(path, "add", "file.txt")
    git(path, "commit", "-m", "initial")


class ScriptSmokeTests(unittest.TestCase):
    def test_legacy_instruction_installers_are_removed(self):
        for path in (
            "AGENTS.md",
            "install-agents.sh",
            "install-agents.ps1",
            "install-remote.sh",
            "install-remote.ps1",
            "scripts/merge_hooks.py",
            "scripts/merge_md_blocks.py",
        ):
            self.assertFalse((ROOT / path).exists(), path)

    def test_token_efficient_skill_is_complete_and_compact(self):
        skill = ROOT / "skills" / "token-efficient-repo-work"
        instructions = (skill / "SKILL.md").read_text(encoding="utf-8")
        metadata = (skill / "agents" / "openai.yaml").read_text(encoding="utf-8")

        self.assertNotIn("TODO", instructions)
        self.assertLessEqual(len(instructions), 6000)
        self.assertIn("name: token-efficient-repo-work", instructions)
        self.assertIn("## Windows PowerShell", instructions)
        self.assertIn('Join-Path $helpers "agent_context.py"', instructions)
        self.assertIn('Get-Command py -ErrorAction SilentlyContinue', instructions)
        self.assertIn('& $python @pythonArgs', instructions)
        self.assertIn("$token-efficient-repo-work", metadata)

    def test_codex_plugin_package_is_self_contained_and_synced(self):
        plugin = ROOT / "plugins/token-efficient-repo-work"
        manifest = json.loads((plugin / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        marketplace = json.loads((ROOT / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
        hooks = json.loads((plugin / "hooks/hooks.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "token-efficient-repo-work")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertIsInstance(manifest["interface"]["defaultPrompt"], list)
        self.assertEqual(marketplace["name"], "agents-toolkit")
        self.assertEqual(
            marketplace["plugins"][0]["source"]["path"],
            "./plugins/token-efficient-repo-work",
        )
        handler = hooks["hooks"]["SessionStart"][0]["hooks"][0]
        self.assertIn("${PLUGIN_ROOT}", handler["command"])
        self.assertIn("$env:PLUGIN_ROOT", handler["commandWindows"])
        self.assertEqual(
            (plugin / "skills/token-efficient-repo-work/SKILL.md").read_bytes(),
            (ROOT / "skills/token-efficient-repo-work/SKILL.md").read_bytes(),
        )
        for name in ("agent_context.py", "safe_read.py", "run_capped.py", "summarize_tests.py"):
            self.assertEqual((plugin / "scripts" / name).read_bytes(), (ROOT / "scripts" / name).read_bytes())

    def test_plugin_session_start_hook_uses_bundled_helpers(self):
        plugin = ROOT / "plugins/token-efficient-repo-work"
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            init_repo(repo)
            result = subprocess.run(
                [PYTHON, str(plugin / "hooks/session-start.py")],
                input=json.dumps({"cwd": str(repo), "hook_event_name": "SessionStart"}),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**os.environ, "HOME": str(Path(tmp) / "empty-home"), "PLUGIN_ROOT": str(plugin)},
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Repository Context", context)

    def test_safe_read_redacts_and_marks_matches(self):
        result = run_script(
            "safe_read.py",
            "-",
            "--find",
            "ERROR",
            "--context",
            "1",
            input_text="ok\nERROR password=abc123\nafter\n",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("   1: ok", result.stdout)
        self.assertIn(">> 2: ERROR password=****", result.stdout)
        self.assertNotIn("abc123", result.stdout)

    def test_scan_errors_stdin_context(self):
        result = run_script(
            "scan_errors.py",
            "-",
            "--context",
            "1",
            input_text="ok\nERROR token=abc123\nafter\n",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Scanned 1 files. Match groups: 1.", result.stdout)
        self.assertIn("--- stdin ---", result.stdout)
        self.assertIn(">> 2: ERROR token=****", result.stdout)
        self.assertNotIn("abc123", result.stdout)

    def test_safe_read_marks_consecutive_matches_in_one_group(self):
        result = run_script(
            "safe_read.py",
            "-",
            "--find",
            "ERROR",
            "--context",
            "1",
            input_text="ERROR first\nERROR second\nok\n",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(">> 1: ERROR first", result.stdout)
        self.assertIn(">> 2: ERROR second", result.stdout)

    def test_compact_logs_stdin_context(self):
        result = run_script(
            "compact_logs.py",
            "-",
            "--keyword",
            "error",
            "--context",
            "1",
            input_text="info token=abc123\nerror crash\nafter\n",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Scanned 1 files. Match groups: 1.", result.stdout)
        self.assertIn("   1: info token=****", result.stdout)
        self.assertIn(">> 2: error crash", result.stdout)
        self.assertNotIn("abc123", result.stdout)

    def test_compact_logs_tail_preserves_original_line_numbers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "app.log"
            path.write_text("one\ntwo\nerror three\nfour\nerror five\n", encoding="utf-8")
            result = run_script("compact_logs.py", str(path), "--tail", "3", "--keyword", "error")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(">> 3: error three", result.stdout)
        self.assertIn(">> 5: error five", result.stdout)

    def test_summarize_tests_streams_failure_context(self):
        result = run_script(
            "summarize_tests.py",
            "-",
            "--context",
            "1",
            input_text="pytest\nsetup\nFAILED test_example.py::test_it\nExpected 1\n",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Probable Framework: pytest", result.stdout)
        self.assertIn("Total Lines Parsed: 4", result.stdout)
        self.assertIn(">> 3: FAILED test_example.py::test_it", result.stdout)

    def test_summarize_json_redacts_and_limits_input(self):
        result = run_script(
            "summarize_json.py",
            "-",
            "--show-values",
            input_text='{"token":"abc123","items":[{"name":"one"}]}',
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("token: ****", result.stdout)
        self.assertIn("name: one", result.stdout)
        self.assertNotIn("abc123", result.stdout)

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "large.json"
            path.write_text('{"ok": true}', encoding="utf-8")
            limited = run_script("summarize_json.py", str(path), "--max-input-mb", "0")
            self.assertIn("Use --force", limited.stdout)

    def test_summarize_data_reports_invalid_jsonl(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.jsonl"
            path.write_text('{"a":1}\nnot-json\n{"password":"secret"}\n', encoding="utf-8")
            result = run_script("summarize_data.py", str(path))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Parsed Rows: 2", result.stdout)
        self.assertIn("Invalid JSON Lines Skipped: 1", result.stdout)
        self.assertNotIn("secret", result.stdout)

    def test_outline_python_and_typescript(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "app.py").write_text(
                "import os\n\nclass Widget:\n    def render(self):\n        return 1\n",
                encoding="utf-8",
            )
            (base / "util.ts").write_text(
                "export const fetchData = async (url: string) => {\n  return url;\n};\n",
                encoding="utf-8",
            )

            result = run_script("outline.py", str(base))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("3: class Widget:", result.stdout)
        self.assertIn("4:     def render(self):", result.stdout)
        self.assertIn("1: export const fetchData", result.stdout)
        self.assertNotIn("import os", result.stdout)
        self.assertNotIn("return 1", result.stdout)

    def test_run_capped_summarizes_redacts_and_keeps_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_script(
                "run_capped.py",
                "--log-dir",
                tmp,
                "--",
                PYTHON,
                "-c",
                "print('start'); print('ERROR token=abc123')",
            )
            logs = list(Path(tmp).glob("run-*.log"))
            log_text = logs[0].read_text(encoding="utf-8") if logs else ""

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Exit Code: 0", result.stdout)
        self.assertIn(">> 2: ERROR token=****", result.stdout)
        self.assertNotIn("abc123", result.stdout)
        self.assertEqual(len(logs), 1)
        self.assertIn("token=abc123", log_text)

    def test_run_capped_propagates_exit_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_script(
                "run_capped.py",
                "--log-dir",
                tmp,
                "--",
                PYTHON,
                "-c",
                "import sys; sys.exit(3)",
            )

        self.assertEqual(result.returncode, 3, result.stderr)
        self.assertIn("Exit Code: 3", result.stdout)

    def test_repo_map_is_deterministic_and_ignores_heavy_dirs(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "b.py").write_text("print('b')\n", encoding="utf-8")
            (base / "a.py").write_text("print('a')\n", encoding="utf-8")
            (base / "token=do-not-print.py").write_text("x = 1\n", encoding="utf-8")
            (base / "node_modules").mkdir()
            (base / "node_modules" / "ignored.js").write_text("x\n", encoding="utf-8")

            first = run_script("repo_map.py", str(base), "--max-output-chars", "12000")
            second = run_script("repo_map.py", str(base), "--max-output-chars", "12000")

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertLess(first.stdout.index("a.py"), first.stdout.index("b.py"))
        self.assertNotIn("ignored.js", first.stdout)
        self.assertNotIn("do-not-print", first.stdout)
        self.assertIn("Stack Detected: Python", first.stdout)

    def test_agent_context_reports_repo_and_git_without_secrets(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            init_repo(repo)
            (repo / "note.txt").write_text("api_token=abc123\n", encoding="utf-8")

            result = run_script("agent_context.py", str(repo), "--max-output-chars", "12000")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Agent Context:", result.stdout)
        self.assertIn("Repository Map", result.stdout)
        self.assertIn("Git Diff Summary", result.stdout)
        self.assertIn("note.txt", result.stdout)
        self.assertNotIn("abc123", result.stdout)

    def test_agent_context_recommends_safe_read_for_changed_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            init_repo(repo)
            (repo / "file.txt").write_text("old\nnew\n", encoding="utf-8")

            result = run_script("agent_context.py", str(repo), "--max-output-chars", "12000")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Next Token-Safe Steps", result.stdout)
        self.assertIn("safe_read.py", result.stdout)
        self.assertIn("file.txt", result.stdout)

    def test_agent_context_preserves_actions_with_small_output_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            init_repo(repo)
            src = repo / "src"
            src.mkdir()
            for index in range(40):
                (src / f"long_feature_module_name_{index:03d}.py").write_text("x = 1\n", encoding="utf-8")
            git(repo, "add", "src")
            git(repo, "commit", "-m", "add modules")
            (repo / "file.txt").write_text("old\nnew\n", encoding="utf-8")

            result = run_script("agent_context.py", str(repo), "--max-output-chars", "1000")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLessEqual(len(result.stdout.rstrip("\n")), 1000)
        self.assertIn("Git Diff Summary", result.stdout)
        self.assertIn("file.txt", result.stdout)
        self.assertIn("Next Token-Safe Steps", result.stdout)

    def test_agent_context_recommends_symbol_search_when_clean(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            init_repo(repo)

            result = run_script("agent_context.py", str(repo), "--max-output-chars", "12000")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Next Token-Safe Steps", result.stdout)
        self.assertIn("No local file deltas detected.", result.stdout)
        self.assertIn("rg -n \"symbol_or_error\"", result.stdout)

    def test_diff_summary_reports_working_tree_and_redacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            init_repo(repo)
            (repo / "file.txt").write_text("old\npassword=abc123\n", encoding="utf-8")
            (repo / "staged.txt").write_text("staged\n", encoding="utf-8")
            git(repo, "add", "staged.txt")
            (repo / "note.txt").write_text("api_token=abc123\n", encoding="utf-8")

            result = run_script("diff_summary.py", str(repo), "--max-output-chars", "12000")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Mode: working tree", result.stdout)
        self.assertIn("staged.txt", result.stdout)
        self.assertIn("file.txt", result.stdout)
        self.assertIn("note.txt", result.stdout)
        self.assertIn("password=****", result.stdout)
        self.assertIn("api_token=****", result.stdout)
        self.assertNotIn("abc123", result.stdout)

    def test_diff_summary_omits_generated_binary_untracked(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            init_repo(repo)
            cache = repo / "__pycache__"
            cache.mkdir()
            (cache / "ignored.pyc").write_bytes(b"\0pyc")
            (repo / "note.txt").write_text("api_token=abc123\n", encoding="utf-8")

            result = run_script("diff_summary.py", str(repo), "--max-output-chars", "12000")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("note.txt", result.stdout)
        self.assertIn("Untracked files omitted: 1", result.stdout)
        self.assertNotIn("__pycache__", result.stdout)
        self.assertNotIn("ignored.pyc", result.stdout)
        self.assertNotIn("abc123", result.stdout)

    def test_diff_summary_staged_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            init_repo(repo)
            (repo / "file.txt").write_text("changed\n", encoding="utf-8")
            (repo / "staged.txt").write_text("staged\n", encoding="utf-8")
            git(repo, "add", "staged.txt")
            (repo / "note.txt").write_text("untracked\n", encoding="utf-8")

            result = run_script("diff_summary.py", str(repo), "--staged")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("staged.txt", result.stdout)
        self.assertNotIn("file.txt", result.stdout)
        self.assertNotIn("note.txt", result.stdout)

    def test_diff_summary_no_untracked(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            init_repo(repo)
            (repo / "note.txt").write_text("untracked\n", encoding="utf-8")

            result = run_script("diff_summary.py", str(repo), "--no-untracked")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("note.txt", result.stdout)
        self.assertIn("(none)", result.stdout)

    def test_diff_summary_base_ref(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            init_repo(repo)
            (repo / "file.txt").write_text("old\nnew\n", encoding="utf-8")
            git(repo, "add", "file.txt")
            git(repo, "commit", "-m", "change file")

            result = run_script("diff_summary.py", str(repo), "--base", "HEAD~1", "--no-untracked")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Mode: base comparison (HEAD~1...HEAD)", result.stdout)
        self.assertIn("file.txt", result.stdout)
        self.assertIn("+1 -0", result.stdout)


if __name__ == "__main__":
    unittest.main()
