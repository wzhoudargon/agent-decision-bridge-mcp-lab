import tempfile
import unittest
from pathlib import Path

from server import full_agent_server as srv


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
            ["open_workspace", "ls", "read", "write", "edit", "grep", "glob", "bash"],
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
            ["open_workspace", "ls", "read", "grep", "glob"],
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


if __name__ == "__main__":
    unittest.main()
