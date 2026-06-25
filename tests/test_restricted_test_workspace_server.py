import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server import restricted_test_workspace_server as srv


class RestrictedWorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.workspace = srv.RestrictedWorkspace(
            ROOT / "test-workspace" / "synthetic-project"
        )

    def test_lists_only_synthetic_files(self):
        self.assertEqual(
            self.workspace.list_files(),
            [
                "sample-file-tree.txt",
                "sample-open-question.md",
                "sample-project-notes.md",
            ],
        )

    def test_reads_allowed_synthetic_file(self):
        content = self.workspace.read_file("sample-open-question.md")

        self.assertIn("Synthetic Open Question", content)
        self.assertIn("archived synthetic tasks", content)

    def test_rejects_parent_directory_escape(self):
        with self.assertRaises(srv.AccessDenied):
            self.workspace.read_file("../README.md")

    def test_rejects_absolute_path(self):
        with self.assertRaises(srv.AccessDenied):
            self.workspace.read_file(str(ROOT / "README.md"))

    def test_rejects_hidden_path_segment(self):
        with self.assertRaises(srv.AccessDenied):
            self.workspace.read_file(".env")

    def test_rejects_missing_file_without_leaking_other_paths(self):
        with self.assertRaises(FileNotFoundError):
            self.workspace.read_file("missing.md")


class JsonRpcMcpTests(unittest.TestCase):
    def setUp(self):
        self.workspace = srv.RestrictedWorkspace(
            ROOT / "test-workspace" / "synthetic-project"
        )

    def test_initialize_declares_tools_capability(self):
        response = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2025-11-25",
                    "capabilities": {},
                    "clientInfo": {"name": "unit-test", "version": "1.0.0"},
                },
            },
            self.workspace,
        )

        self.assertEqual(response["jsonrpc"], "2.0")
        self.assertEqual(response["id"], 1)
        self.assertEqual(response["result"]["protocolVersion"], "2025-11-25")
        self.assertIn("tools", response["result"]["capabilities"])

    def test_tools_list_exposes_read_only_tools(self):
        response = srv.handle_request(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            self.workspace,
        )

        names = [tool["name"] for tool in response["result"]["tools"]]
        self.assertEqual(names, ["list_synthetic_files", "read_synthetic_file"])

    def test_tools_call_lists_files_as_text_and_structured_content(self):
        response = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "list_synthetic_files", "arguments": {}},
            },
            self.workspace,
        )

        result = response["result"]
        self.assertFalse(result.get("isError", False))
        self.assertIn("sample-project-notes.md", result["content"][0]["text"])
        self.assertEqual(
            result["structuredContent"]["files"],
            [
                "sample-file-tree.txt",
                "sample-open-question.md",
                "sample-project-notes.md",
            ],
        )

    def test_tools_call_reads_allowed_file(self):
        response = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "read_synthetic_file",
                    "arguments": {"path": "sample-project-notes.md"},
                },
            },
            self.workspace,
        )

        result = response["result"]
        self.assertFalse(result.get("isError", False))
        self.assertIn("Synthetic Project Notes", result["content"][0]["text"])
        self.assertEqual(
            result["structuredContent"]["path"], "sample-project-notes.md"
        )

    def test_tools_call_returns_tool_error_for_denied_file(self):
        response = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "read_synthetic_file",
                    "arguments": {"path": "../README.md"},
                },
            },
            self.workspace,
        )

        result = response["result"]
        self.assertTrue(result["isError"])
        self.assertIn("Access denied", result["content"][0]["text"])

    def test_unknown_tool_returns_tool_error(self):
        response = srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {"name": "write_file", "arguments": {}},
            },
            self.workspace,
        )

        result = response["result"]
        self.assertTrue(result["isError"])
        self.assertIn("Unknown tool", result["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
