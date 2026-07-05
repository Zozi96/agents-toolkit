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
    def test_agents_rules_stay_compact(self):
        self.assertLessEqual((ROOT / "AGENTS.md").stat().st_size, 3500)

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
        self.assertIn("Scanned 1 files. Found 1 matches.", result.stdout)
        self.assertIn("--- stdin ---", result.stdout)
        self.assertIn(">> 2: ERROR token=****", result.stdout)
        self.assertNotIn("abc123", result.stdout)

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
        self.assertIn("Scanned 1 files. Found 1 matches.", result.stdout)
        self.assertIn("   1: info token=****", result.stdout)
        self.assertIn(">> 2: error crash", result.stdout)
        self.assertNotIn("abc123", result.stdout)

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
            (base / "node_modules").mkdir()
            (base / "node_modules" / "ignored.js").write_text("x\n", encoding="utf-8")

            first = run_script("repo_map.py", str(base), "--max-output-chars", "12000")
            second = run_script("repo_map.py", str(base), "--max-output-chars", "12000")

        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertEqual(first.stdout, second.stdout)
        self.assertLess(first.stdout.index("a.py"), first.stdout.index("b.py"))
        self.assertNotIn("ignored.js", first.stdout)
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


    def test_merge_md_blocks_preserves_plugin_blocks(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "src.md"
            dest = tmp_path / "dest.md"
            src.write_text("# Rules\n\nbody\n", encoding="utf-8")
            dest.write_text(
                "# Old rules\n\n"
                "<!-- context7 -->\nuse context7\n<!-- context7 -->\n\n"
                "<!-- kg:start -->\ngraph rules\n<!-- kg:end -->\n",
                encoding="utf-8",
            )

            result = run_script("merge_md_blocks.py", str(src), str(dest))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("# Rules", result.stdout)
        self.assertIn("<!-- context7 -->\nuse context7\n<!-- context7 -->", result.stdout)
        self.assertIn("<!-- kg:start -->\ngraph rules\n<!-- kg:end -->", result.stdout)
        self.assertNotIn("# Old rules", result.stdout)

    def test_merge_md_blocks_skips_blocks_already_in_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "src.md"
            dest = tmp_path / "dest.md"
            src.write_text("# Rules\n\n<!-- context7 -->\nnew\n<!-- context7 -->\n", encoding="utf-8")
            dest.write_text("<!-- context7 -->\nold\n<!-- context7 -->\n", encoding="utf-8")

            result = run_script("merge_md_blocks.py", str(src), str(dest))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("<!-- context7 -->"), 2)
        self.assertNotIn("old", result.stdout)

    def test_merge_md_blocks_replaces_only_managed_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            src = tmp_path / "src.md"
            dest = tmp_path / "dest.md"
            src.write_text("# New rules\n", encoding="utf-8")
            dest.write_text(
                "# Unmarked notes written by another tool\n\n"
                "<!-- agents-toolkit:start -->\n# Old rules\n<!-- agents-toolkit:end -->\n\n"
                "trailing plugin text without any markers\n",
                encoding="utf-8",
            )

            result = run_script("merge_md_blocks.py", str(src), str(dest))

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("# Unmarked notes written by another tool", result.stdout)
        self.assertIn("trailing plugin text without any markers", result.stdout)
        self.assertIn("<!-- agents-toolkit:start -->\n# New rules\n<!-- agents-toolkit:end -->", result.stdout)
        self.assertNotIn("# Old rules", result.stdout)


if __name__ == "__main__":
    unittest.main()
