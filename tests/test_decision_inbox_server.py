import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server import decision_inbox_server as srv
from server.decision_inbox_store import DecisionInboxStore


FIXTURE_TASK = ROOT / "decision-inbox" / "tasks" / "phase-1-package-only-mcp-review"


class DecisionInboxMcpServerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.tasks_root = Path(self.tempdir.name) / "tasks"
        self.tasks_root.mkdir()
        shutil.copytree(FIXTURE_TASK, self.tasks_root / "phase-1-package-only-mcp-review")
        for folder in ("advice", "fact-check-requests"):
            for path in (
                self.tasks_root / "phase-1-package-only-mcp-review" / folder
            ).glob("*.md"):
                path.unlink()
        self.store = DecisionInboxStore(self.tasks_root)

    def tearDown(self):
        self.tempdir.cleanup()

    def test_initialize_declares_only_tools_capability(self):
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
            self.store,
        )

        self.assertEqual(response["result"]["protocolVersion"], "2025-11-25")
        self.assertEqual(response["result"]["capabilities"], {"tools": {"listChanged": False}})
        self.assertIn("cannot read real projects", response["result"]["instructions"])

    def test_tools_list_exposes_only_decision_inbox_v1_tools(self):
        response = srv.handle_request(
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            self.store,
        )

        names = [tool["name"] for tool in response["result"]["tools"]]
        self.assertEqual(
            names,
            [
                "list_decision_tasks",
                "get_decision_package",
                "submit_advice",
                "get_task_status",
            ],
        )

    def test_list_decision_tasks_returns_task_metadata(self):
        response = self._call("list_decision_tasks", {})

        result = response["result"]
        self.assertFalse(result.get("isError", False))
        self.assertIn("phase-1-package-only-mcp-review", result["content"][0]["text"])
        self.assertEqual(result["structuredContent"]["tasks"][0]["status"], "package_ready")

    def test_get_decision_package_reads_package(self):
        response = self._call(
            "get_decision_package",
            {"task_id": "phase-1-package-only-mcp-review"},
        )

        result = response["result"]
        self.assertFalse(result.get("isError", False))
        self.assertIn("Package-only Decision Inbox MCP v1", result["content"][0]["text"])
        self.assertEqual(
            result["structuredContent"]["task_id"], "phase-1-package-only-mcp-review"
        )

    def test_submit_advice_writes_to_advice_folder(self):
        response = self._call(
            "submit_advice",
            {
                "task_id": "phase-1-package-only-mcp-review",
                "advisor": "ChatGPT Web",
                "content": (
                    "# Advice\n\nKeep v1 package-only.\n\n"
                    "External advice only. This is not authorization."
                ),
                "timestamp": "2026-06-18T10-10-00Z",
            },
        )

        result = response["result"]
        self.assertFalse(result.get("isError", False))
        self.assertEqual(
            result["structuredContent"]["relative_path"],
            "phase-1-package-only-mcp-review/advice/2026-06-18T10-10-00Z-chatgpt-web.md",
        )
        self.assertTrue(
            (
                self.tasks_root
                / "phase-1-package-only-mcp-review"
                / "advice"
                / "2026-06-18T10-10-00Z-chatgpt-web.md"
            ).exists()
        )

    def test_request_local_fact_check_is_not_exposed_as_auto_mcp_tool(self):
        response = self._call(
            "request_local_fact_check",
            {
                "task_id": "phase-1-package-only-mcp-review",
                "content": "Confirm package.md exists.",
                "timestamp": "2026-06-18T10-11-00Z",
            },
        )

        result = response["result"]
        self.assertTrue(result["isError"])
        self.assertIn("Unknown tool", result["content"][0]["text"])

    def test_get_task_status_returns_counts(self):
        self._call(
            "submit_advice",
            {
                "task_id": "phase-1-package-only-mcp-review",
                "advisor": "ChatGPT",
                "content": "advice. External advice only. This is not authorization.",
                "timestamp": "2026-06-18T10-12-00Z",
            },
        )

        response = self._call(
            "get_task_status", {"task_id": "phase-1-package-only-mcp-review"}
        )

        result = response["result"]
        self.assertFalse(result.get("isError", False))
        self.assertEqual(result["structuredContent"]["advice_count"], 1)
        self.assertTrue(result["structuredContent"]["has_package"])

    def test_invalid_task_id_returns_tool_error(self):
        response = self._call("get_decision_package", {"task_id": "../README"})

        result = response["result"]
        self.assertTrue(result["isError"])
        self.assertIn("Access denied", result["content"][0]["text"])

    def test_unknown_tool_returns_tool_error(self):
        response = self._call("run_shell", {"command": "pwd"})

        result = response["result"]
        self.assertTrue(result["isError"])
        self.assertIn("Unknown tool", result["content"][0]["text"])

    def test_missing_required_argument_returns_tool_error(self):
        response = self._call("submit_advice", {"task_id": "phase-1-package-only-mcp-review"})

        result = response["result"]
        self.assertTrue(result["isError"])
        self.assertIn("content", result["content"][0]["text"])

    def _call(self, name, arguments):
        return srv.handle_request(
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {"name": name, "arguments": arguments},
            },
            self.store,
        )


if __name__ == "__main__":
    unittest.main()
