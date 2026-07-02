import argparse
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import decision_inbox_preflight as preflight
from server import decision_inbox_http_server as http_srv


FIXTURE_TASK = ROOT / "decision-inbox" / "tasks" / "phase-1-package-only-mcp-review"


class DecisionInboxPreflightTests(unittest.TestCase):
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
        self.server = http_srv.create_server(
            host="127.0.0.1",
            port=0,
            tasks_root=self.tasks_root,
            auth_token="preflight-token",
            allowed_origins=["https://chatgpt.com"],
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.local_url = f"http://127.0.0.1:{self.server.server_port}/mcp"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tempdir.cleanup()

    def test_auto_mcp_preflight_accepts_four_tool_allowlist(self):
        args = argparse.Namespace(
            mode="auto-mcp",
            local_url=self.local_url,
            public_base_url=None,
            mcp_url=None,
            task_id="phase-1-package-only-mcp-review",
            token_env="PREFLIGHT_TEST_TOKEN",
            token_file=Path(self.tempdir.name) / "missing-token",
            oauth_state_file=Path(self.tempdir.name) / "missing-state.json",
            timeout=5.0,
            require_public=False,
        )
        with mock.patch.dict(os.environ, {"PREFLIGHT_TEST_TOKEN": "preflight-token"}):
            lines, ok = preflight.build_report(args)

        report = "\n".join(lines)
        self.assertTrue(ok, report)
        self.assertIn("Expected connector tools: list_decision_tasks, get_decision_package, submit_advice, get_task_status", report)
        self.assertIn("Authenticated tools/list: ok expected_allowlist", report)
        self.assertIn("Auto MCP disallowed tool check: ok none_found", report)
        self.assertNotIn("request_local_fact_check, get_task_status", report)
        self.assertNotIn("preflight-token", report)

    def test_tool_allowlist_mismatch_reports_observed_tools_without_token(self):
        args = argparse.Namespace(
            mode="full-agent",
            local_url=self.local_url,
            public_base_url=None,
            mcp_url=None,
            task_id=None,
            token_env="PREFLIGHT_TEST_TOKEN",
            token_file=Path(self.tempdir.name) / "missing-token",
            oauth_state_file=Path(self.tempdir.name) / "missing-state.json",
            timeout=5.0,
            require_public=False,
        )
        with mock.patch.dict(os.environ, {"PREFLIGHT_TEST_TOKEN": "preflight-token"}):
            lines, ok = preflight.build_report(args)

        report = "\n".join(lines)
        self.assertFalse(ok, report)
        self.assertIn("failed tool_allowlist_mismatch", report)
        self.assertIn("observed=list_decision_tasks, get_decision_package", report)
        self.assertNotIn("preflight-token", report)

    def test_connected_agent_expected_scope_and_tools(self):
        self.assertEqual(preflight.expected_oauth_scope("connected-agent"), "connected-agent")
        self.assertEqual(preflight.risk_coefficient("connected-agent"), "3-5")
        self.assertIn("enable_danger_auto", preflight.expected_tool_names("connected-agent"))
        self.assertIn("grant_workspace_access", preflight.expected_tool_names("connected-agent"))

    def test_ask_first_preflight_skips_mcp_probe(self):
        args = argparse.Namespace(
            mode="ask-first",
            local_url="http://127.0.0.1:9/mcp",
            public_base_url=None,
            mcp_url=None,
            task_id=None,
            token_env="PREFLIGHT_TEST_TOKEN",
            token_file=Path(self.tempdir.name) / "missing-token",
            oauth_state_file=Path(self.tempdir.name) / "missing-state.json",
            timeout=0.01,
            require_public=False,
        )

        lines, ok = preflight.build_report(args)

        report = "\n".join(lines)
        self.assertTrue(ok, report)
        self.assertIn("Current state: preflight_skipped", report)
        self.assertIn("Expected connector tools: none", report)
        self.assertIn("Risk coefficient: 1/5", report)

    def test_resolve_public_mcp_url_rejects_query_tokens(self):
        with self.assertRaises(ValueError):
            preflight.resolve_public_mcp_url(
                None, "https://decision-inbox.example.com/mcp?access_token=secret"
            )

    def test_load_oauth_access_token_selects_nonexpired_scope_without_printing_value(self):
        state_file = Path(self.tempdir.name) / "oauth-state.json"
        state_file.write_text(
            json.dumps(
                {
                    "oauth_access_tokens": {
                        "expired-token": {
                            "scopes": ["decision-inbox"],
                            "expires_at": time.time() - 1,
                        },
                        "valid-token": {
                            "scopes": ["decision-inbox"],
                            "expires_at": time.time() + 60,
                        },
                    }
                }
            ),
            encoding="utf-8",
        )

        token, source = preflight.load_oauth_access_token(state_file, "decision-inbox")

        self.assertEqual(token, "valid-token")
        self.assertIn("oauth_state_access_token", source)
        self.assertNotIn("expired-token", preflight.credential_status(token, source))
        self.assertNotIn("valid-token", preflight.credential_status(token, source))

    def test_parse_curl_response_extracts_last_header_block(self):
        raw = (
            b"HTTP/1.1 200 Connection established\r\n\r\n"
            b"HTTP/2 401\r\n"
            b"www-authenticate: Bearer scope=\"full-agent\"\r\n"
            b"content-length: 0\r\n"
            b"\r\n"
        )

        status, headers, body = preflight.parse_curl_response(raw)

        self.assertEqual(status, 401)
        self.assertEqual(headers["www-authenticate"], 'Bearer scope="full-agent"')
        self.assertEqual(body, b"")

    def test_curl_fallback_refuses_authorization_header(self):
        self.assertFalse(
            preflight.curl_fallback_is_safe({"Authorization": "Bearer secret"})
        )
        self.assertTrue(preflight.curl_fallback_is_safe({"Accept": "application/json"}))


if __name__ == "__main__":
    unittest.main()
