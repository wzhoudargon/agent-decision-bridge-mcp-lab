import tempfile
import unittest
import json
import time
from pathlib import Path

from server import connected_agent_server as srv


class FullAgentWorkspaceManagerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name) / "project"
        self.root.mkdir()
        (self.root / "README.md").write_text("hello full agent\n", encoding="utf-8")
        (self.root / ".env").write_text("API_KEY=secret\n", encoding="utf-8")
        (self.root / ".env.local").write_text("LOCAL_SECRET=secret\n", encoding="utf-8")
        (self.root / ".git").mkdir()
        (self.root / ".git" / "config").write_text("[remote]\n", encoding="utf-8")
        (self.root / ".ssh").mkdir()
        (self.root / ".ssh" / "id_rsa").write_text("private key\n", encoding="utf-8")
        (self.root / "config").mkdir()
        (self.root / "config" / "auth-token.json").write_text("not hard denied\n", encoding="utf-8")
        (self.root / "config" / "token.json").write_text("secret\n", encoding="utf-8")
        (self.root / "config" / "credentials.json").write_text("secret\n", encoding="utf-8")
        (self.root / "cert.pem").write_text("certificate\n", encoding="utf-8")
        (self.root / "src").mkdir()
        (self.root / "src" / "app.txt").write_text("alpha\nbeta\n", encoding="utf-8")
        (self.root / "src" / "tokenizer.py").write_text("safe word\n", encoding="utf-8")
        self.manager = srv.FullAgentWorkspaceManager([self.root])
        self.workspace = self.manager.open_workspace(str(self.root))["workspace_id"]

    def tearDown(self):
        self.tempdir.cleanup()

    def test_rejects_missing_allowed_roots(self):
        with self.assertRaises(ValueError):
            srv.FullAgentWorkspaceManager([])

    def test_rejects_home_as_allowed_root(self):
        with self.assertRaises(ValueError):
            srv.FullAgentWorkspaceManager([Path.home()])

    def test_lists_reads_writes_edits_searches_and_runs_bash(self):
        entries = self.manager.list_directory(self.workspace)
        self.assertIn("README.md", [entry["name"] for entry in entries])

        self.assertEqual(
            self.manager.read_file(self.workspace, "src/app.txt"),
            "alpha\nbeta\n",
        )

        write_result = self.manager.write_file(self.workspace, "notes/todo.txt", "ship\n")
        self.assertEqual(write_result["path"], "notes/todo.txt")
        self.assertEqual(self.manager.read_file(self.workspace, "notes/todo.txt"), "ship\n")

        edit_result = self.manager.edit_file(
            self.workspace,
            "src/app.txt",
            "beta",
            "gamma",
            expected_replacements=1,
        )
        self.assertEqual(edit_result["replacements"], 1)
        self.assertIn("gamma", self.manager.read_file(self.workspace, "src/app.txt"))

        self.assertIn("src/app.txt", self.manager.glob_paths(self.workspace, "src/*.txt"))
        matches = self.manager.grep(self.workspace, "gamma")
        self.assertEqual(matches[0]["path"], "src/app.txt")

        command = self.manager.run_bash(self.workspace, "printf ok")
        self.assertEqual(command["returncode"], 0)
        self.assertEqual(command["stdout"], "ok")
        self.assertEqual(command["risk_level"], "5/5")

    def test_full_agent_profile_blocks_protected_paths_by_default(self):
        entries = self.manager.list_directory(self.workspace)
        entry_names = [entry["name"] for entry in entries]
        self.assertNotIn(".env", entry_names)
        self.assertNotIn(".env.local", entry_names)
        self.assertNotIn(".git", entry_names)
        self.assertNotIn(".ssh", entry_names)

        self.assertEqual(
            self.manager.read_file(self.workspace, "src/tokenizer.py"),
            "safe word\n",
        )
        self.assertEqual(
            self.manager.read_file(self.workspace, "config/auth-token.json"),
            "not hard denied\n",
        )
        for path in (
            ".env",
            ".env.local",
            ".git/config",
            ".ssh/id_rsa",
            "config/token.json",
            "config/credentials.json",
            "cert.pem",
        ):
            with self.subTest(path=path):
                with self.assertRaises(srv.AccessDenied):
                    self.manager.read_file(self.workspace, path)

        for path in (".env", ".ssh/new-key", "config/token.json"):
            with self.subTest(path=path):
                with self.assertRaises(srv.AccessDenied):
                    self.manager.write_file(self.workspace, path, "nope\n")

        with self.assertRaises(srv.AccessDenied):
            self.manager.edit_file(self.workspace, ".env", "secret", "redacted")
        with self.assertRaises(srv.AccessDenied):
            self.manager.run_bash(self.workspace, "cat .env")

        self.assertEqual(self.manager.grep(self.workspace, "secret"), [])
        paths = self.manager.glob_paths(self.workspace, "**/*")
        self.assertIn("src/tokenizer.py", paths)
        self.assertIn("config/auth-token.json", paths)
        self.assertNotIn(".env", paths)
        self.assertNotIn("config/token.json", paths)

    def test_rejects_workspace_escape(self):
        with self.assertRaises(srv.AccessDenied):
            self.manager.read_file(self.workspace, "../outside.txt")

    def test_jsonrpc_tools_list_exposes_full_agent_tools(self):
        response = srv.handle_request(
            {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            self.manager,
        )

        names = [tool["name"] for tool in response["result"]["tools"]]
        self.assertEqual(
            names,
            ["open_workspace", "ls", "read", "read_lines", "write", "edit", "grep", "glob", "bash"],
        )

    def test_jsonrpc_denies_escape_as_tool_error(self):
        response = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "read",
                    "arguments": {
                        "workspace_id": self.workspace,
                        "path": "../outside.txt",
                    },
                },
            },
            self.manager,
        )

        self.assertTrue(response["result"]["isError"])
        self.assertIn("Access denied", response["result"]["content"][0]["text"])

    def test_jsonrpc_accepts_json_string_tool_arguments(self):
        response = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "open_workspace",
                    "arguments": json.dumps({"path": str(self.root)}),
                },
            },
            self.manager,
        )

        self.assertFalse(response["result"]["isError"])
        self.assertEqual(
            Path(response["result"]["structuredContent"]["root"]),
            self.root.resolve(),
        )

    def test_read_allows_normal_large_source_files_up_to_one_mb(self):
        content = "export const item = 'ok';\n" * 13_000
        large_source = self.root / "src" / "promptTemplates.js"
        large_source.write_text(content, encoding="utf-8")
        self.assertGreater(large_source.stat().st_size, 200_000)
        self.assertLess(large_source.stat().st_size, srv.MAX_READ_FILE_BYTES)

        self.assertEqual(
            self.manager.read_file(self.workspace, "src/promptTemplates.js"),
            content,
        )

    def test_jsonrpc_read_does_not_duplicate_content_in_structured_payload(self):
        source = self.root / "src" / "promptTemplates.js"
        content = "export const item = 'ok';\n" * 13_000
        source.write_text(content, encoding="utf-8")

        response = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 60,
                "method": "tools/call",
                "params": {
                    "name": "read",
                    "arguments": {
                        "workspace_id": self.workspace,
                        "path": "src/promptTemplates.js",
                    },
                },
            },
            self.manager,
        )

        self.assertFalse(response["result"]["isError"])
        self.assertEqual(response["result"]["content"][0]["text"], content)
        structured = response["result"]["structuredContent"]
        self.assertEqual(structured["path"], "src/promptTemplates.js")
        self.assertEqual(structured["bytes"], len(content.encode("utf-8")))
        self.assertNotIn("content", structured)

    def test_read_still_blocks_oversized_whole_file_but_read_lines_can_sample(self):
        huge_source = self.root / "src" / "huge.txt"
        huge_source.write_text(("alpha\n" * 220_000), encoding="utf-8")
        self.assertGreater(huge_source.stat().st_size, srv.MAX_READ_FILE_BYTES)

        with self.assertRaises(srv.AccessDenied):
            self.manager.read_file(self.workspace, "src/huge.txt")

        result = self.manager.read_lines(self.workspace, "src/huge.txt", 10, 12)
        self.assertEqual(result["path"], "src/huge.txt")
        self.assertEqual([item["line"] for item in result["lines"]], [10, 11, 12])
        self.assertEqual([item["text"] for item in result["lines"]], ["alpha", "alpha", "alpha"])
        self.assertFalse(result["truncated"])

    def test_jsonrpc_read_lines_caps_large_ranges(self):
        source = self.root / "src" / "many-lines.txt"
        source.write_text("".join(f"line {index}\n" for index in range(1, 800)), encoding="utf-8")

        response = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 59,
                "method": "tools/call",
                "params": {
                    "name": "read_lines",
                    "arguments": {
                        "workspace_id": self.workspace,
                        "path": "src/many-lines.txt",
                        "start_line": 1,
                        "end_line": 700,
                    },
                },
            },
            self.manager,
        )

        self.assertFalse(response["result"]["isError"])
        structured = response["result"]["structuredContent"]
        self.assertEqual(len(structured["lines"]), srv.MAX_READ_LINES)
        self.assertTrue(structured["truncated"])
        self.assertEqual(structured["lines"][0], {"line": 1, "text": "line 1"})

    def test_connected_agent_can_open_single_default_workspace_without_path(self):
        manager = srv.FullAgentWorkspaceManager(
            [self.root], profile=srv.PROFILE_CONNECTED_AGENT
        )

        response = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 55,
                "method": "tools/call",
                "params": {
                    "name": "open_default_workspace",
                    "arguments": {},
                },
            },
            manager,
        )

        self.assertFalse(response["result"]["isError"])
        self.assertEqual(
            Path(response["result"]["structuredContent"]["root"]),
            self.root.resolve(),
        )
        workspace_id = response["result"]["structuredContent"]["workspace_id"]
        self.assertEqual(manager.read_file(workspace_id, "README.md"), "hello full agent\n")

    def test_connected_agent_open_workspace_accepts_default_alias_for_stale_schema(self):
        manager = srv.FullAgentWorkspaceManager(
            [self.root], profile=srv.PROFILE_CONNECTED_AGENT
        )

        response = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 57,
                "method": "tools/call",
                "params": {
                    "name": "open_workspace",
                    "arguments": {"path": "default"},
                },
            },
            manager,
        )

        self.assertFalse(response["result"]["isError"])
        self.assertEqual(
            Path(response["result"]["structuredContent"]["root"]),
            self.root.resolve(),
        )
        workspace_id = response["result"]["structuredContent"]["workspace_id"]
        self.assertEqual(manager.read_file(workspace_id, "README.md"), "hello full agent\n")

    def test_connected_agent_default_alias_rejects_ambiguous_roots(self):
        second_root = Path(self.tempdir.name) / "second-project"
        second_root.mkdir()
        manager = srv.FullAgentWorkspaceManager(
            [self.root, second_root], profile=srv.PROFILE_CONNECTED_AGENT
        )

        response = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 58,
                "method": "tools/call",
                "params": {
                    "name": "open_workspace",
                    "arguments": {"path": "default"},
                },
            },
            manager,
        )

        self.assertTrue(response["result"]["isError"])
        self.assertIn(
            "default workspace alias requires exactly one configured allowed root",
            response["result"]["content"][0]["text"],
        )

    def test_connected_agent_rejects_default_workspace_when_ambiguous(self):
        second_root = Path(self.tempdir.name) / "second-project"
        second_root.mkdir()
        manager = srv.FullAgentWorkspaceManager(
            [self.root, second_root], profile=srv.PROFILE_CONNECTED_AGENT
        )

        response = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 56,
                "method": "tools/call",
                "params": {
                    "name": "open_default_workspace",
                    "arguments": {},
                },
            },
            manager,
        )

        self.assertTrue(response["result"]["isError"])
        self.assertIn(
            "requires exactly one configured allowed root",
            response["result"]["content"][0]["text"],
        )

    def test_jsonrpc_bad_tool_params_returns_tool_error_not_internal_error(self):
        response = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": "not an object",
            },
            self.manager,
        )

        self.assertNotIn("error", response)
        self.assertTrue(response["result"]["isError"])
        self.assertIn("Invalid tool call params", response["result"]["content"][0]["text"])

    def test_read_only_project_profile_exposes_only_read_tools_and_blocks_secrets(self):
        manager = srv.FullAgentWorkspaceManager(
            [self.root], profile=srv.PROFILE_READ_ONLY_PROJECT
        )
        workspace = manager.open_workspace(str(self.root))["workspace_id"]

        response = srv.handle_request(
            {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
            manager,
        )
        self.assertEqual(
            [tool["name"] for tool in response["result"]["tools"]],
            ["open_workspace", "ls", "read", "read_lines", "grep", "glob"],
        )

        entries = manager.list_directory(workspace)
        self.assertNotIn(".env", [entry["name"] for entry in entries])
        self.assertEqual(manager.read_file(workspace, "README.md"), "hello full agent\n")
        with self.assertRaises(srv.AccessDenied):
            manager.read_file(workspace, ".env")
        self.assertEqual(manager.grep(workspace, "secret"), [])

        write = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "write",
                    "arguments": {
                        "workspace_id": workspace,
                        "path": "notes.md",
                        "content": "nope",
                    },
                },
            },
            manager,
        )
        self.assertTrue(write["result"]["isError"])
        self.assertIn("not available", write["result"]["content"][0]["text"])

    def test_connected_agent_default_requires_approval_for_mutations(self):
        manager = srv.FullAgentWorkspaceManager(
            [self.root], profile=srv.PROFILE_CONNECTED_AGENT
        )
        workspace = manager.open_workspace(str(self.root))["workspace_id"]

        response = srv.handle_request(
            {"jsonrpc": "2.0", "id": 7, "method": "tools/list"},
            manager,
        )
        self.assertEqual(
            [tool["name"] for tool in response["result"]["tools"]],
            [
                "open_default_workspace",
                "open_workspace",
                "ls",
                "read",
                "read_lines",
                "write",
                "edit",
                "grep",
                "glob",
                "bash",
                "enable_danger_auto",
                "danger_auto_status",
                "disable_danger_auto",
                "grant_action_approval",
                "request_workspace_access",
                "grant_workspace_access",
            ],
        )
        self.assertEqual(manager.read_file(workspace, "README.md"), "hello full agent\n")

        write = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 8,
                "method": "tools/call",
                "params": {
                    "name": "write",
                    "arguments": {
                        "workspace_id": workspace,
                        "path": "notes.md",
                        "content": "needs approval",
                    },
                },
            },
            manager,
        )
        self.assertTrue(write["result"]["isError"])
        self.assertEqual(write["result"]["structuredContent"]["error"], "approval_required")
        self.assertEqual(write["result"]["structuredContent"]["approval_kind"], "one_action")
        approval_id = write["result"]["structuredContent"]["approval_id"]
        self.assertTrue(approval_id.startswith("approval-"))
        self.assertNotIn("dangerously trust connected agent", write["result"]["content"][0]["text"])

        grant = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 80,
                "method": "tools/call",
                "params": {
                    "name": "grant_action_approval",
                    "arguments": {
                        "approval_id": approval_id,
                        "confirmation": "确认，可以写入这个 notes.md",
                    },
                },
            },
            manager,
        )
        self.assertFalse(grant["result"]["isError"])
        self.assertEqual(grant["result"]["structuredContent"]["status"], "granted")

        written = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 81,
                "method": "tools/call",
                "params": {
                    "name": "write",
                    "arguments": {
                        "workspace_id": workspace,
                        "path": "notes.md",
                        "content": "needs approval",
                        "approval_id": approval_id,
                    },
                },
            },
            manager,
        )
        self.assertFalse(written["result"]["isError"])
        self.assertEqual(manager.read_file(workspace, "notes.md"), "needs approval")

        reused = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 82,
                "method": "tools/call",
                "params": {
                    "name": "write",
                    "arguments": {
                        "workspace_id": workspace,
                        "path": "notes.md",
                        "content": "needs approval",
                        "approval_id": approval_id,
                    },
                },
            },
            manager,
        )
        self.assertTrue(reused["result"]["isError"])
        self.assertEqual(reused["result"]["structuredContent"]["error"], "approval_required")

    def test_connected_agent_danger_auto_allows_safe_local_work_and_blocks_unsafe_bash(self):
        manager = srv.FullAgentWorkspaceManager(
            [self.root], profile=srv.PROFILE_CONNECTED_AGENT
        )
        workspace = manager.open_workspace(str(self.root))["workspace_id"]

        with self.assertRaises(srv.AccessDenied):
            manager.enable_danger_auto("please trust me")
        status = manager.enable_danger_auto(srv.DANGER_AUTO_PHRASE)
        self.assertTrue(status["danger_auto_enabled"])
        self.assertEqual(status["risk_level"], "5/5")

        write_result = manager.write_file(workspace, "notes/connected.txt", "ship\n")
        self.assertEqual(write_result["path"], "notes/connected.txt")
        edit_result = manager.edit_file(
            workspace,
            "notes/connected.txt",
            "ship",
            "shipped",
            expected_replacements=1,
        )
        self.assertEqual(edit_result["replacements"], 1)
        command = manager.run_bash(workspace, "printf ok")
        self.assertEqual(command["stdout"], "ok")

        for command in (
            "curl https://example.com",
            "pbpaste",
            "cat .env",
            "python3 -m pip install requests",
        ):
            with self.subTest(command=command):
                with self.assertRaises((srv.AccessDenied, srv.ApprovalRequired)):
                    manager.run_bash(workspace, command)

        git_push = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 9,
                "method": "tools/call",
                "params": {
                    "name": "bash",
                    "arguments": {
                        "workspace_id": workspace,
                        "command": "git push origin main",
                    },
                },
            },
            manager,
        )
        self.assertTrue(git_push["result"]["isError"])
        self.assertEqual(git_push["result"]["structuredContent"]["error"], "approval_required")

    def test_connected_agent_workspace_access_grant_and_idle_expiry(self):
        outside = Path(self.tempdir.name) / "outside"
        outside.mkdir()
        (outside / "TASK.md").write_text("outside task\n", encoding="utf-8")
        manager = srv.FullAgentWorkspaceManager(
            [self.root], profile=srv.PROFILE_CONNECTED_AGENT
        )

        with self.assertRaises(srv.AccessDenied):
            manager.open_workspace(str(outside))

        request = manager.request_workspace_access(str(outside), "read linked project", "read")
        self.assertEqual(request["status"], "approval_required")
        grant = manager.grant_workspace_access(str(outside), "read")
        self.assertEqual(grant["status"], "granted")

        outside_workspace = manager.open_workspace(str(outside))["workspace_id"]
        self.assertEqual(manager.read_file(outside_workspace, "TASK.md"), "outside task\n")

        manager.enable_danger_auto(srv.DANGER_AUTO_PHRASE)
        manager.session_last_activity = time.time() - srv.DANGER_AUTO_IDLE_SECONDS - 1
        status = manager.danger_auto_status()
        self.assertFalse(status["danger_auto_enabled"])
        self.assertEqual(status["temporary_allowed_roots"], [])


if __name__ == "__main__":
    unittest.main()
