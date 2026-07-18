import os
import json
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
sys.path.insert(0, str(ROOT / "scripts"))


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
        skill = ROOT / "plugins/token-efficient-repo-work/skills/token-efficient-repo-work"
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

    def test_pi_package_registers_extension_and_existing_skill(self):
        package = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))
        extension = (ROOT / "extensions/pi-agent/index.mjs").read_text(encoding="utf-8")

        self.assertIn("pi-package", package["keywords"])
        self.assertEqual(package["pi"]["extensions"], ["./extensions/pi-agent/index.mjs"])
        self.assertEqual(
            package["pi"]["skills"],
            ["./plugins/token-efficient-repo-work/skills"],
        )
        self.assertIn('@earendil-works/pi-coding-agent', package["peerDependencies"])
        self.assertIn('pi.on("session_start"', extension)
        self.assertIn('pi.on("before_agent_start"', extension)
        self.assertIn('pi.on("tool_call"', extension)
        self.assertIn("PI_PACKAGE_ROOT", extension)

        node = shutil.which("node")
        if not node:
            self.skipTest("node is not installed")
        result = subprocess.run(
            [node, "--test", str(ROOT / "tests/test_pi_extension.mjs")],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

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
        self.assertIn("${PLUGIN_ROOT:-}", handler["command"])
        self.assertIn("$env:PLUGIN_ROOT", handler["commandWindows"])
        bundled = sorted(path.name for path in (plugin / "scripts").glob("*.py"))
        self.assertGreaterEqual(len(bundled), 12)
        for name in bundled:
            self.assertEqual((plugin / "scripts" / name).read_bytes(), (ROOT / "scripts" / name).read_bytes(), name)
        for name in (
            "session-start.py",
            "session-start.ps1",
            "pre-tool-use.py",
            "pre-tool-use.ps1",
            "post-tool-use.py",
            "post-tool-use.ps1",
        ):
            self.assertEqual((plugin / "hooks" / name).read_bytes(), (ROOT / "hooks" / name).read_bytes(), name)

    def test_claude_plugin_package_is_registered(self):
        plugin = ROOT / "plugins/token-efficient-repo-work"
        manifest = json.loads((plugin / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        marketplace = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))
        hooks = json.loads((plugin / "hooks/hooks.json").read_text(encoding="utf-8"))

        self.assertEqual(manifest["name"], "token-efficient-repo-work")
        codex_manifest = json.loads((plugin / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["version"], codex_manifest["version"])
        self.assertEqual(marketplace["name"], "agents-toolkit")
        self.assertEqual(marketplace["plugins"][0]["source"], "./plugins/token-efficient-repo-work")
        entry = hooks["hooks"]["SessionStart"][0]
        self.assertEqual(entry["matcher"], "startup|clear|compact")
        self.assertIn("${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}", entry["hooks"][0]["command"])
        pre_tool = hooks["hooks"]["PreToolUse"][0]
        self.assertEqual(pre_tool["matcher"], "Bash")
        self.assertIn("pre-tool-use.py", pre_tool["hooks"][0]["command"])
        self.assertIn("pre-tool-use.ps1", pre_tool["hooks"][0]["commandWindows"])
        post_tool = hooks["hooks"]["PostToolUse"][0]
        self.assertEqual(post_tool["matcher"], "Bash")
        self.assertIn("post-tool-use.py", post_tool["hooks"][0]["command"])
        self.assertIn("post-tool-use.ps1", post_tool["hooks"][0]["commandWindows"])
        self.assertIn("${CLAUDE_PLUGIN_ROOT:-${PLUGIN_ROOT:-}}", post_tool["hooks"][0]["command"])
        self.assertIn("$env:CLAUDE_PLUGIN_ROOT", post_tool["hooks"][0]["commandWindows"])
        self.assertEqual(post_tool["hooks"][0]["timeout"], 5)

    def test_plugin_session_start_hook_accepts_claude_plugin_root(self):
        plugin = ROOT / "plugins/token-efficient-repo-work"
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp) / "repo"
            repo.mkdir()
            init_repo(repo)
            env = {k: v for k, v in os.environ.items() if k != "PLUGIN_ROOT"}
            result = subprocess.run(
                [PYTHON, str(plugin / "hooks/session-start.py")],
                input=json.dumps({"cwd": str(repo), "hook_event_name": "SessionStart"}),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={**env, "HOME": str(Path(tmp) / "empty-home"), "CLAUDE_PLUGIN_ROOT": str(plugin)},
                check=False,
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Repository Context", context)

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

    def test_session_start_compact_skips_repository_context(self):
        result = subprocess.run(
            [PYTHON, str(ROOT / "hooks/session-start.py")],
            input=json.dumps({"source": "compact", "cwd": str(ROOT)}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "PLUGIN_ROOT": str(ROOT)},
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
        self.assertLess(len(context), 500)
        self.assertNotIn("Repository Context", context)
        self.assertIn("agent_context.py", context)

    def test_session_start_startup_and_clear_use_bounded_repository_context(self):
        for source in ("startup", "clear"):
            with self.subTest(source=source):
                result = subprocess.run(
                    [PYTHON, str(ROOT / "hooks/session-start.py")],
                    input=json.dumps({"source": source, "cwd": str(ROOT)}),
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    env={**os.environ, "PLUGIN_ROOT": str(ROOT)},
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
                self.assertIn("Repository Context", context)
                self.assertLessEqual(len(context), 3800)

    def run_pre_tool_use(self, command, cwd=".", **extra_env):
        result = subprocess.run(
            [PYTHON, str(ROOT / "hooks/pre-tool-use.py")],
            input=json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, **extra_env},
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def run_post_tool_use(self, command, response, home, **extra_env):
        env = {k: v for k, v in os.environ.items() if k not in ("PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT")}
        # Windows resolves Path.home() from USERPROFILE, not HOME.
        env.update({"HOME": str(home), "USERPROFILE": str(home), "PLUGIN_ROOT": str(ROOT), **extra_env})
        result = subprocess.run(
            [PYTHON, str(ROOT / "hooks/post-tool-use.py")],
            input=json.dumps(
                {
                    "tool_name": "Bash",
                    "tool_input": {"command": command},
                    "tool_response": response,
                }
            ),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def test_hooks_drain_stdin_before_early_exit(self):
        # Regression: a hook exiting with unread payload bytes makes the
        # harness's write fail with "failed to write hook stdin: Broken pipe".
        filler = "x" * 2_000_000  # far beyond the 64 KiB pipe buffer
        cases = [
            ("hooks/post-tool-use.py", {"tool_name": "Bash", "tool_response": filler}),
            ("hooks/pre-tool-use.py", {"tool_name": "Other", "filler": filler}),
            ("hooks/session-start.py", {"source": "compact", "filler": filler}),
        ]
        env = {k: v for k, v in os.environ.items() if k not in ("PLUGIN_ROOT", "CLAUDE_PLUGIN_ROOT")}
        for script, payload in cases:
            with self.subTest(script=script):
                proc = subprocess.Popen(
                    [PYTHON, str(ROOT / script)],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                    env=env,
                )
                try:
                    try:
                        proc.stdin.write(json.dumps(payload).encode("utf-8"))
                        proc.stdin.close()
                    except OSError:
                        proc.kill()
                        self.fail(f"{script} exited without draining stdin (EPIPE)")
                finally:
                    stderr = proc.communicate(timeout=30)[1]
                self.assertEqual(proc.returncode, 0, stderr)

    def test_post_tool_use_small_output_is_silent_and_writes_no_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            self.assertEqual(self.run_post_tool_use("printf ok", "ok", home), "")
            self.assertEqual(list(home.rglob("post-tool-*.log")), [])

    def test_post_tool_use_ignores_output_from_existing_helpers(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            for command in (
                "./scripts/run_capped.py -- pytest",
                "python scripts/run_capped.py -- pytest",
                "env MODE=test python3 /tmp/run_capped.py -- pytest",
                "command python3 scripts/run_capped.py -- pytest",
                "bash -c 'python3 scripts/run_capped.py -- pytest'",
            ):
                self.assertEqual(self.run_post_tool_use(command, "x" * 12001, home), "", command)
            self.assertEqual(list(home.rglob("post-tool-*.log")), [])

    def test_post_tool_use_codex_large_output_is_silent_and_writes_no_log(self):
        lines = [f"HEAD-{index}" for index in range(15)]
        lines += ["password=very-secret", "fatal: middle exploded"]
        lines += ["filler-" + ("x" * 250) for _ in range(60)]
        lines += [f"TAIL-{index}" for index in range(40)]
        response = "\n".join(lines)
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            output = self.run_post_tool_use("build --all", response, home)
            self.assertEqual(output, "")
            self.assertEqual(list(home.rglob("post-tool-*.log")), [])

    def test_post_tool_use_claude_rejects_non_dict_response_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            output = self.run_post_tool_use(
                "build --all",
                "x" * 12001,
                home,
                PLUGIN_ROOT="",
                CLAUDE_PLUGIN_ROOT=str(ROOT),
            )
            self.assertEqual(output, "")
            self.assertEqual(list(home.rglob("post-tool-*.log")), [])

    def test_post_tool_use_claude_compacts_streams_with_exact_output_shape(self):
        response = {
            "stdout": "stdout-start\n" + ("out\n" * 1800),
            "stderr": "password=claude-secret\nfatal: build failed\n" + ("err\n" * 1800),
            "interrupted": True,
            "isImage": False,
        }
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            output = self.run_post_tool_use(
                "build --all",
                response,
                home,
                CLAUDE_PLUGIN_ROOT=str(ROOT),
            )
            result = json.loads(output)
            self.assertEqual(set(result), {"hookSpecificOutput"})
            hook_output = result["hookSpecificOutput"]
            self.assertEqual(set(hook_output), {"hookEventName", "updatedToolOutput"})
            self.assertEqual(hook_output["hookEventName"], "PostToolUse")
            updated = hook_output["updatedToolOutput"]
            self.assertEqual(set(updated), {"stdout", "stderr", "interrupted", "isImage"})
            self.assertIs(updated["interrupted"], True)
            self.assertIs(updated["isImage"], False)
            self.assertIn("stdout-start", updated["stdout"])
            self.assertIn("fatal: build failed", updated["stderr"])
            self.assertNotIn("claude-secret", updated["stderr"])
            self.assertLessEqual(len(updated["stdout"]) + len(updated["stderr"]), 9000)
            logs = list(home.rglob("post-tool-*.log"))
            self.assertEqual(len(logs), 1)
            self.assertIn("claude-secret", logs[0].read_text(encoding="utf-8"))
            if os.name == "posix":
                self.assertEqual(logs[0].stat().st_mode & 0o777, 0o600)

    def test_post_tool_use_claude_small_invalid_and_helper_results_are_silent(self):
        valid = {"stdout": "ok", "stderr": "", "interrupted": False, "isImage": False}
        invalid = {"stdout": "x" * 12001, "stderr": "", "interrupted": 0, "isImage": False}
        helper = {**valid, "stdout": "x" * 12001}
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            env = {"PLUGIN_ROOT": "", "CLAUDE_PLUGIN_ROOT": str(ROOT)}
            self.assertEqual(self.run_post_tool_use("printf ok", valid, home, **env), "")
            self.assertEqual(self.run_post_tool_use("build --all", invalid, home, **env), "")
            self.assertEqual(
                self.run_post_tool_use("python3 scripts/run_capped.py -- pytest", helper, home, **env),
                "",
            )
            self.assertEqual(list(home.rglob("post-tool-*.log")), [])

    def deny_reason(self, output):
        decision = json.loads(output)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        return decision["permissionDecisionReason"]

    def test_pre_tool_use_denies_raw_test_runners_with_replacement(self):
        reason = self.deny_reason(self.run_pre_tool_use("pytest -x tests/"))
        self.assertIn("run_capped.py", reason)
        expected = "pwsh -NoProfile -Command 'pytest -x tests/'" if os.name == "nt" else "sh -c 'pytest -x tests/'"
        self.assertIn(expected, reason)

    def test_pre_tool_use_emits_powershell_replacement(self):
        reason = self.deny_reason(
            self.run_pre_tool_use(
                "pytest -x tests/",
                PI_POWERSHELL="1",
                PLUGIN_ROOT=str(ROOT),
            )
        )
        self.assertIn("pwsh -NoProfile -Command 'pytest -x tests/'", reason)
        self.assertIn(str(ROOT / "scripts" / "run_capped.py"), reason)

    def test_pre_tool_use_test_replacement_preserves_exit_code(self):
        reason = self.deny_reason(self.run_pre_tool_use("pytest __definitely_missing_test__.py"))
        replacement = reason.splitlines()[-1].replace(
            '${CLAUDE_PLUGIN_ROOT:-$PLUGIN_ROOT}/scripts', str(ROOT / "scripts")
        )
        invocation = ["pwsh", "-NoProfile", "-Command", replacement] if os.name == "nt" else replacement
        result = subprocess.run(
            invocation,
            shell=os.name != "nt",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_pre_tool_use_allows_its_shell_operator_replacement(self):
        reason = self.deny_reason(self.run_pre_tool_use("cd tests && pytest __definitely_missing_test__.py"))
        self.assertEqual(self.run_pre_tool_use(reason.splitlines()[-1]), "")

    def test_pre_tool_use_allows_capped_tests(self):
        for command in (
            "pytest 2>&1 | python3 scripts/summarize_tests.py -",
            "pytest 2>&1 | tail -40",
            "pytest > out.txt 2>&1",
        ):
            self.assertIn("run_capped.py", self.deny_reason(self.run_pre_tool_use(command)), command)
        self.assertEqual(self.run_pre_tool_use("python3 scripts/run_capped.py -- pytest"), "")

    def test_pre_tool_use_denies_git_patch_dumps(self):
        for command in ("git diff", "git show HEAD", "git log -p -3"):
            self.assertIn("diff_summary.py", self.deny_reason(self.run_pre_tool_use(command)), command)

    def test_pre_tool_use_allows_generated_powershell_git_cap(self):
        reason = self.deny_reason(
            self.run_pre_tool_use("git diff", PI_POWERSHELL="1", PLUGIN_ROOT=str(ROOT))
        )
        replacement = reason.splitlines()[-1].replace("<path>", "README.md")
        self.assertEqual(
            self.run_pre_tool_use(replacement, PI_POWERSHELL="1", PLUGIN_ROOT=str(ROOT)),
            "",
        )

    def test_pre_tool_use_denies_git_diff_with_path(self):
        reason = self.deny_reason(self.run_pre_tool_use("git diff -- path/to/file"))
        self.assertIn("diff_summary.py", reason)

    def test_pre_tool_use_allows_capped_git_commands(self):
        for command in ("git diff --stat", "git log --oneline -5", "git show --name-only HEAD", "git status"):
            self.assertEqual(self.run_pre_tool_use(command), "", command)

    def test_pre_tool_use_allows_stdout_redirects_and_file_at_rev(self):
        for command in (
            "git diff > patch.diff",
            "cat a.sql b.sql > merged.sql",
            "git show HEAD:README.md",
            "git log --pretty=format:%h -5",
        ):
            self.assertEqual(self.run_pre_tool_use(command), "", command)
        # stderr-only redirect is not a cap: stdout still dumps to the terminal
        self.assertIn("diff_summary.py", self.deny_reason(self.run_pre_tool_use("git diff 2> err.log")))

    def test_pre_tool_use_routes_large_files_by_type(self):
        with tempfile.TemporaryDirectory() as tmp:
            big_text = Path(tmp) / "big.log"
            big_text.write_text("line\n" * 20000, encoding="utf-8")
            big_json = Path(tmp) / "big.json"
            big_json.write_text('{"k": "' + "v" * 60000 + '"}', encoding="utf-8")
            big_jsonl = Path(tmp) / "big.jsonl"
            big_jsonl.write_text('{"k": "' + "v" * 60000 + '"}\n', encoding="utf-8")
            small = Path(tmp) / "small.txt"
            small.write_text("ok\n", encoding="utf-8")

            reason = self.deny_reason(self.run_pre_tool_use(f"cat {big_text}", cwd=tmp))
            self.assertIn("safe_read.py", reason)
            self.assertIn("summarize_json.py", self.deny_reason(self.run_pre_tool_use("cat big.json", cwd=tmp)))
            self.assertIn("summarize_data.py", self.deny_reason(self.run_pre_tool_use("cat big.jsonl", cwd=tmp)))
            self.assertEqual(self.run_pre_tool_use("cat small.txt", cwd=tmp), "")
            self.assertEqual(self.run_pre_tool_use(f"cat {big_text} | head -50", cwd=tmp), "")

    def test_pre_tool_use_ignores_non_bash_tools(self):
        result = subprocess.run(
            [PYTHON, str(ROOT / "hooks/pre-tool-use.py")],
            input=json.dumps({"tool_name": "Read", "tool_input": {"file_path": "x"}}),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "")

    def test_redaction_covers_quoted_keys_pem_and_bare_tokens(self):
        from _agent_utils import is_sensitive_key, redact_text

        self.assertNotIn("hunter2", redact_text('{"password": "hunter2", "user": "z"}'))
        self.assertNotIn("sk-live", redact_text("'api_key': 'sk-live-abcdefghijklmnopqrstu'"))
        self.assertEqual(redact_text("MIIEowIBAAKCAQEA" + "a" * 48), "****")
        git_sha = "a" * 20 + "0" * 20
        self.assertEqual(redact_text(git_sha), git_sha)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", redact_text("using AKIAIOSFODNN7EXAMPLE for access"))
        self.assertNotIn("eyJzdWIi", redact_text("jwt eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0In0.abcDEF123"))
        self.assertNotIn("ghp_", redact_text("push with ghp_ABCDEFGHIJKLMNOPQRSTUV1234"))
        self.assertNotIn("xoxb-", redact_text("slack xoxb-123456789012-abcdef"))

        self.assertFalse(is_sensitive_key("author"))
        self.assertFalse(is_sensitive_key("author_name"))
        self.assertTrue(is_sensitive_key("auth_token"))
        self.assertTrue(is_sensitive_key("authorization"))

    def test_compact_logs_scans_explicit_sqlite_and_hidden_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "dump.sqlite"
            db.write_text("ok\nERROR boom\n", encoding="utf-8")
            hidden = Path(tmp) / ".hidden.log"
            hidden.write_text("ERROR hidden\n", encoding="utf-8")
            result = run_script("compact_logs.py", str(db), str(hidden), "--keyword", "error")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Scanned 2 files. Match groups: 2.", result.stdout)
        self.assertIn(">> 2: ERROR boom", result.stdout)
        self.assertIn(">> 1: ERROR hidden", result.stdout)

    def test_error_paths_exit_nonzero(self):
        missing = run_script("safe_read.py", "/nonexistent/definitely-missing.txt")
        self.assertEqual(missing.returncode, 2, missing.stdout)
        self.assertIn("Error reading", missing.stdout)

        bad_regex = run_script("compact_logs.py", "-", "--regex", "[", input_text="x\n")
        self.assertEqual(bad_regex.returncode, 2, bad_regex.stdout)

        bad_json = run_script("summarize_json.py", "-", input_text="not-json")
        self.assertEqual(bad_json.returncode, 2, bad_json.stdout)

    def test_summarize_json_stdin_respects_input_cap(self):
        result = run_script("summarize_json.py", "-", "--max-input-mb", "0", input_text='{"ok": true}')

        self.assertEqual(result.returncode, 2, result.stdout)
        self.assertIn("Use --force", result.stdout)

    def test_summarize_data_streams_stdin_csv(self):
        rows = "\n".join(f"aaa{i},bbb{i}" for i in range(500))
        result = run_script("summarize_data.py", "-", input_text="col_a,col_b\n" + rows + "\n")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Parsed Rows: 500", result.stdout)

    def test_diff_summary_normalizes_renames(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            init_repo(repo)
            src = repo / "src"
            src.mkdir()
            (src / "old_name.py").write_text("x = 1\n" * 30, encoding="utf-8")
            git(repo, "add", "src")
            git(repo, "commit", "-m", "add module")
            git(repo, "mv", "src/old_name.py", "src/new_name.py")
            (src / "new_name.py").write_text("x = 1\n" * 30 + "y = 2\n", encoding="utf-8")
            git(repo, "add", "src")
            git(repo, "commit", "-m", "rename module")

            result = run_script(
                "diff_summary.py", str(repo), "--base", "HEAD~1", "--no-untracked", "--max-hunks", "0"
            )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("src/new_name.py", result.stdout)
        self.assertNotIn("=>", result.stdout)
        self.assertNotIn("old_name.py", result.stdout)

    def test_run_capped_streams_large_output_capped(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_script(
                "run_capped.py",
                "--log-dir",
                tmp,
                "--",
                PYTHON,
                "-c",
                "print('\\n'.join(f'line {i}' for i in range(5000)))",
            )
            logs = list(Path(tmp).glob("run-*.log"))
            log_lines = logs[0].read_text(encoding="utf-8").splitlines()
            log_mode = logs[0].stat().st_mode & 0o777

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Output Lines: 5000", result.stdout)
        self.assertIn("   1: line 0", result.stdout)
        self.assertIn("   5000: line 4999", result.stdout)
        self.assertEqual(len(log_lines), 5000)
        if os.name != "nt":
            self.assertEqual(log_mode, 0o600)
        self.assertLessEqual(len(result.stdout), 13000)

    def test_run_capped_times_out_with_exit_124(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_script(
                "run_capped.py",
                "--timeout",
                "1",
                "--log-dir",
                tmp,
                "--",
                PYTHON,
                "-c",
                "import time; print('begin', flush=True); time.sleep(10)",
            )

        self.assertEqual(result.returncode, 124, result.stdout)
        self.assertIn("TIMEOUT", result.stdout)
        self.assertIn("begin", result.stdout)

    @unittest.skipIf(os.name == "nt", "POSIX process-group behavior")
    def test_run_capped_timeout_kills_process_group_after_parent_exits(self):
        with tempfile.TemporaryDirectory() as tmp:
            start = time.monotonic()
            result = run_script(
                "run_capped.py",
                "--timeout",
                "0.2",
                "--log-dir",
                tmp,
                "--",
                PYTHON,
                "-c",
                "import subprocess, sys, time; "
                "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(5)']); "
                "print('begin', flush=True)",
            )
            elapsed = time.monotonic() - start

        self.assertEqual(result.returncode, 124, result.stdout)
        self.assertLess(elapsed, 3)

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

    def test_summarize_tests_ignores_successful_error_named_tests(self):
        result = run_script(
            "summarize_tests.py",
            "-",
            input_text=(
                "test_error_path (tests.Example.test_error_path) ... ok\n"
                "test_failure_mode (tests.Example.test_failure_mode) ... ok\n"
            ),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("No explicit failures found", result.stdout)

    def test_summarize_tests_matches_common_failure_formats(self):
        result = run_script(
            "summarize_tests.py",
            "-",
            "--context",
            "0",
            input_text="1 failed\nerror: broken\nFailure: mismatch\nValueError: bad value\n",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for line in ("1 failed", "error: broken", "Failure: mismatch", "ValueError: bad value"):
            self.assertIn(line, result.stdout)

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
        self.assertNotIn(str(repo / "file.txt"), result.stdout)
        self.assertIn("Changed paths:\n  - file.txt", result.stdout)
        self.assertIn("outline.py <path>, then safe_read.py <path>", result.stdout)

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

    def test_evaluate_context_reports_budgets_sections_and_path_recall_without_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            init_repo(repo)
            (repo / "file.txt").write_text("old\nnew\n", encoding="utf-8")
            before = git(repo, "status", "--porcelain=v1").stdout

            result = run_script(
                "evaluate_context.py",
                str(repo),
                "--budgets",
                "1500,3000",
                "--repetitions",
                "2",
            )
            after = git(repo, "status", "--porcelain=v1").stdout

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(before, after)
        report = json.loads(result.stdout)
        self.assertEqual(report["budgets"], [1500, 3000])
        self.assertEqual(report["repetitions"], 2)
        self.assertEqual(report["changed_paths"], ["file.txt"])
        self.assertEqual(len(report["results"]), 2)
        self.assertEqual(report["results"][1]["path_recall"], 1.0)
        self.assertEqual(
            report["results"][1]["sections"],
            {"Git Diff Summary": True, "Next Token-Safe Steps": True, "Repository Map": True},
        )
        self.assertGreaterEqual(report["results"][0]["median_latency_ms"], 0)

    def test_evaluate_context_path_recall_does_not_match_filename_substrings(self):
        # Unit-level check: the previous integration variant relied on a 500-char
        # budget truncating the output before the untracked file, which broke on
        # runners with long temp paths (Windows).
        from evaluate_context import path_present

        output = "Files:\n  M       +1      -0 tracked   data.py\n"
        self.assertTrue(path_present("data.py", output))
        self.assertFalse(path_present("a.py", output))

    def test_summarize_agent_usage_parses_codex_and_claude_exports(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            codex = base / "codex.jsonl"
            codex.write_text(
                '\n'.join(
                    json.dumps(event)
                    for event in (
                        {"type": "turn.completed", "usage": {"input_tokens": 10, "cached_input_tokens": 3, "output_tokens": 4}},
                        {"type": "item.completed", "usage": {"input_tokens": 999}},
                        {"type": "turn.completed", "usage": {"input_tokens": 20, "reasoning_output_tokens": 5}},
                    )
                ),
                encoding="utf-8",
            )
            claude = base / "claude.json"
            claude.write_text(
                json.dumps(
                    {
                        "usage": {
                            "input_tokens": 12,
                            "output_tokens": 7,
                            "service_tier": "standard",
                            "server_tool_use": {"web_search_requests": 0},
                            "iterations": [{"type": "message", "input_tokens": 2}],
                        },
                        "total_cost_usd": 0.0042,
                        "modelUsage": {"claude-test": {"inputTokens": 12, "outputTokens": 7}},
                    }
                ),
                encoding="utf-8",
            )

            codex_result = run_script("summarize_agent_usage.py", "codex", str(codex))
            claude_result = run_script("summarize_agent_usage.py", "claude", str(claude))

        self.assertEqual(codex_result.returncode, 0, codex_result.stderr)
        self.assertEqual(
            json.loads(codex_result.stdout),
            {
                "runtime": "codex",
                "turns": 2,
                "usage": {"cached_input_tokens": 3, "input_tokens": 30, "output_tokens": 4, "reasoning_output_tokens": 5},
            },
        )
        self.assertEqual(claude_result.returncode, 0, claude_result.stderr)
        claude_report = json.loads(claude_result.stdout)
        self.assertEqual(claude_report["usage"]["input_tokens"], 12)
        self.assertEqual(claude_report["usage"]["service_tier"], "standard")
        self.assertEqual(claude_report["usage"]["iterations"][0]["type"], "message")
        self.assertEqual(claude_report["total_cost_usd"], 0.0042)
        self.assertIn("claude-test", claude_report["modelUsage"])

    def test_summarize_agent_usage_rejects_codex_export_without_completed_turns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "codex.jsonl"
            for content in ("{}\n", json.dumps({"type": "item.completed"}) + "\n"):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    result = run_script("summarize_agent_usage.py", "codex", str(path))
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("no turn.completed", result.stderr)

    def test_summarize_agent_usage_rejects_invalid_claude_usage_fields(self):
        cases = (
            ({"usage": {"input_tokens": True}}, "input_tokens must be numeric"),
            ({"usage": {"input_tokens": "12"}}, "input_tokens must be numeric"),
            ({"usage": {"input_tokens": 12}, "total_cost_usd": False}, "total_cost_usd"),
            ({"usage": {"input_tokens": 12}, "modelUsage": []}, "modelUsage"),
            ({"usage": {"input_tokens": 12}, "model_usage": []}, "modelUsage"),
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "claude.json"
            for payload, message in cases:
                with self.subTest(payload=payload):
                    path.write_text(json.dumps(payload), encoding="utf-8")
                    result = run_script("summarize_agent_usage.py", "claude", str(path))
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(message, result.stderr)

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
