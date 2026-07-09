import json
import base64
import hashlib
import http.client
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server import decision_inbox_http_server as http_srv


FIXTURE_TASK = ROOT / "decision-inbox" / "tasks" / "phase-1-package-only-mcp-review"


class DecisionInboxHttpServerTests(unittest.TestCase):
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
            auth_token="test-token",
            allowed_origins=["https://chatgpt.com"],
        )
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base_url = f"http://127.0.0.1:{self.server.server_port}/mcp"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.tempdir.cleanup()

    def test_post_initialize_returns_json_response(self):
        response = self._post(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25", "capabilities": {}},
            }
        )

        self.assertEqual(response["result"]["protocolVersion"], "2025-11-25")
        self.assertEqual(response["result"]["capabilities"], {"tools": {"listChanged": False}})

    def test_post_notification_returns_accepted_without_body(self):
        request = self._request(
            {
                "jsonrpc": "2.0",
                "method": "notifications/initialized",
            }
        )

        with urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 202)
            self.assertEqual(response.read(), b"")

    def test_tools_call_round_trip_writes_advice(self):
        result = self._post(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "submit_advice",
                    "arguments": {
                        "task_id": "phase-1-package-only-mcp-review",
                        "advisor": "HTTP Test",
                        "content": (
                            "# HTTP Advice\n\nSynthetic.\n\n"
                            "External advice only. This is not authorization."
                        ),
                        "timestamp": "2026-06-18T15-00-00Z",
                    },
                },
            }
        )["result"]

        self.assertFalse(result["isError"])
        self.assertEqual(
            result["structuredContent"]["relative_path"],
            "phase-1-package-only-mcp-review/advice/2026-06-18T15-00-00Z-http-test.md",
        )
        self.assertTrue(
            (
                self.tasks_root
                / "phase-1-package-only-mcp-review"
                / "advice"
                / "2026-06-18T15-00-00Z-http-test.md"
            ).exists()
        )

    def test_invalid_task_id_returns_tool_error(self):
        result = self._post(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "get_decision_package",
                    "arguments": {"task_id": "../README"},
                },
            }
        )["result"]

        self.assertTrue(result["isError"])
        self.assertIn("Access denied", result["content"][0]["text"])

    def test_get_mcp_returns_method_not_allowed(self):
        request = Request(
            self.base_url,
            method="GET",
            headers={"Accept": "text/event-stream", "Authorization": "Bearer test-token"},
        )

        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=5)

        self.assertEqual(caught.exception.code, 405)

    def test_missing_auth_token_is_rejected(self):
        request = self._request({"jsonrpc": "2.0", "id": 4, "method": "tools/list"})
        request.remove_header("Authorization")

        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=5)

        self.assertEqual(caught.exception.code, 401)

    def test_query_auth_token_is_accepted(self):
        response = self._post(
            {"jsonrpc": "2.0", "id": 6, "method": "tools/list"},
            url=f"{self.base_url}?access_token=test-token",
            headers={"Authorization": None},
        )

        self.assertIn("tools", response["result"])

    def test_default_auto_mcp_mode_exposes_only_decision_inbox_tools(self):
        response = self._post({"jsonrpc": "2.0", "id": 8, "method": "tools/list"})

        self.assertEqual(
            [tool["name"] for tool in response["result"]["tools"]],
            [
                "list_decision_tasks",
                "get_decision_package",
                "submit_advice",
                "get_task_status",
            ],
        )

    def test_ask_first_mode_does_not_start_http_server(self):
        with mock.patch("builtins.print") as print_:
            status = http_srv.main(["--mode", "ask-first"])

        self.assertEqual(status, 0)
        output = "\n".join(call.args[0] for call in print_.call_args_list)
        self.assertIn("Ask First mode", output)
        self.assertIn("No HTTP MCP server was started", output)

    def test_invalid_origin_is_rejected(self):
        request = self._request({"jsonrpc": "2.0", "id": 5, "method": "tools/list"})
        request.add_header("Origin", "https://evil.example")

        with self.assertRaises(HTTPError) as caught:
            urlopen(request, timeout=5)

        self.assertEqual(caught.exception.code, 403)

    def test_invalid_host_is_rejected(self):
        body = json.dumps({"jsonrpc": "2.0", "id": 7, "method": "tools/list"}).encode(
            "utf-8"
        )
        connection = http.client.HTTPConnection(
            "127.0.0.1", self.server.server_port, timeout=5
        )
        self.addCleanup(connection.close)

        connection.request(
            "POST",
            "/mcp",
            body=body,
            headers={
                "Host": "evil.example",
                "Content-Type": "application/json",
                "Accept": "application/json, text/event-stream",
                "Authorization": "Bearer test-token",
                "MCP-Protocol-Version": "2025-11-25",
            },
        )
        response = connection.getresponse()

        self.assertEqual(response.status, 403)

    def test_public_base_url_derives_allowed_public_host(self):
        public_server = http_srv.create_server(
            host="127.0.0.1",
            port=0,
            tasks_root=self.tasks_root,
            auth_token="test-token",
            allowed_origins=["https://chatgpt.com"],
            public_base_url="https://decision-inbox.example.com/",
        )
        thread = threading.Thread(target=public_server.serve_forever, daemon=True)
        thread.start()
        try:
            self.assertIn("decision-inbox.example.com", public_server.allowed_hosts)
            self.assertEqual(
                http_srv.public_mcp_url(public_server.public_base_url),
                "https://decision-inbox.example.com/mcp",
            )
        finally:
            public_server.shutdown()
            public_server.server_close()
            thread.join(timeout=2)

    def test_public_base_url_must_be_https_origin_without_mcp_path(self):
        invalid_values = [
            "http://decision-inbox.example.com",
            "https://decision-inbox.example.com/mcp",
            "https://decision-inbox.example.com?access_token=test-token",
        ]

        for value in invalid_values:
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    http_srv.normalize_public_base_url(value)

    def test_full_agent_mode_requires_allowed_root(self):
        with self.assertRaises(ValueError):
            http_srv.create_server(
                host="127.0.0.1",
                port=0,
                tasks_root=self.tasks_root,
                auth_token="test-token",
                allowed_origins=["https://chatgpt.com"],
                mode=http_srv.MODE_FULL_AGENT,
            )

    def test_connected_agent_mode_requires_allowed_root(self):
        with self.assertRaises(ValueError):
            http_srv.create_server(
                host="127.0.0.1",
                port=0,
                tasks_root=self.tasks_root,
                auth_token="test-token",
                allowed_origins=["https://chatgpt.com"],
                mode=http_srv.MODE_CONNECTED_AGENT,
            )

    def test_read_only_project_mode_requires_allowed_root(self):
        with self.assertRaises(ValueError):
            http_srv.create_server(
                host="127.0.0.1",
                port=0,
                tasks_root=self.tasks_root,
                auth_token="test-token",
                allowed_origins=["https://chatgpt.com"],
                mode=http_srv.MODE_READ_ONLY_PROJECT,
            )

    def test_full_agent_mode_creates_oauth_state_file_when_configured(self):
        project_root = Path(self.tempdir.name) / "project"
        project_root.mkdir()
        state_file = Path(self.tempdir.name) / "full-agent-oauth-state.json"

        full_server = http_srv.create_server(
            host="127.0.0.1",
            port=0,
            tasks_root=self.tasks_root,
            auth_token=None,
            allowed_origins=["https://chatgpt.com"],
            oauth_owner_token="owner",
            oauth_state_file=state_file,
            mode=http_srv.MODE_FULL_AGENT,
            allowed_roots=[project_root],
        )
        full_server.server_close()

        self.assertTrue(state_file.is_file())
        self.assertEqual(state_file.stat().st_mode & 0o777, 0o600)

    def test_full_agent_resolve_owner_token_generates_default_file(self):
        owner_file = Path(self.tempdir.name) / "auth" / "oauth-owner-token"
        with mock.patch.object(http_srv, "DEFAULT_FULL_AGENT_OWNER_TOKEN_FILE", owner_file):
            token, path, created = http_srv.resolve_owner_token(
                http_srv.MODE_FULL_AGENT,
                None,
                None,
            )

        self.assertTrue(created)
        self.assertEqual(path, owner_file)
        self.assertEqual(owner_file.stat().st_mode & 0o777, 0o600)
        self.assertEqual(owner_file.read_text(encoding="utf-8").strip(), token)

    def test_full_agent_oauth_state_file_none_disables_persistence(self):
        self.assertIsNone(
            http_srv.resolve_oauth_state_file(http_srv.MODE_FULL_AGENT, "none")
        )

    def test_full_agent_oauth_challenge_uses_full_agent_scope(self):
        project_root = Path(self.tempdir.name) / "project-oauth-scope"
        project_root.mkdir()
        full_server = http_srv.create_server(
            host="127.0.0.1",
            port=0,
            tasks_root=self.tasks_root,
            auth_token=None,
            allowed_origins=["https://chatgpt.com"],
            oauth_owner_token="owner",
            public_base_url="https://decision-inbox.example.com",
            mode=http_srv.MODE_FULL_AGENT,
            allowed_roots=[project_root],
        )
        thread = threading.Thread(target=full_server.serve_forever, daemon=True)
        thread.start()
        try:
            status, headers, _ = self._http_request(
                "POST",
                "/mcp",
                port=full_server.server_port,
                body=json.dumps(
                    {"jsonrpc": "2.0", "id": 29, "method": "tools/list"}
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(status, 401)
            self.assertIn('scope="full-agent"', headers["WWW-Authenticate"])
        finally:
            full_server.shutdown()
            full_server.server_close()
            thread.join(timeout=2)

    def test_connected_agent_oauth_challenge_uses_connected_agent_scope(self):
        project_root = Path(self.tempdir.name) / "project-connected-oauth-scope"
        project_root.mkdir()
        connected_server = http_srv.create_server(
            host="127.0.0.1",
            port=0,
            tasks_root=self.tasks_root,
            auth_token=None,
            allowed_origins=["https://chatgpt.com"],
            oauth_owner_token="owner",
            public_base_url="https://decision-inbox.example.com",
            mode=http_srv.MODE_CONNECTED_AGENT,
            allowed_roots=[project_root],
        )
        thread = threading.Thread(target=connected_server.serve_forever, daemon=True)
        thread.start()
        try:
            status, headers, _ = self._http_request(
                "POST",
                "/mcp",
                port=connected_server.server_port,
                body=json.dumps(
                    {"jsonrpc": "2.0", "id": 39, "method": "tools/list"}
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(status, 401)
            self.assertIn('scope="connected-agent"', headers["WWW-Authenticate"])
        finally:
            connected_server.shutdown()
            connected_server.server_close()
            thread.join(timeout=2)

    def test_read_only_project_oauth_challenge_uses_read_only_scope(self):
        project_root = Path(self.tempdir.name) / "project-read-only-oauth-scope"
        project_root.mkdir()
        read_only_server = http_srv.create_server(
            host="127.0.0.1",
            port=0,
            tasks_root=self.tasks_root,
            auth_token=None,
            allowed_origins=["https://chatgpt.com"],
            oauth_owner_token="owner",
            public_base_url="https://decision-inbox.example.com",
            mode=http_srv.MODE_READ_ONLY_PROJECT,
            allowed_roots=[project_root],
        )
        thread = threading.Thread(target=read_only_server.serve_forever, daemon=True)
        thread.start()
        try:
            status, headers, _ = self._http_request(
                "POST",
                "/mcp",
                port=read_only_server.server_port,
                body=json.dumps(
                    {"jsonrpc": "2.0", "id": 33, "method": "tools/list"}
                ).encode("utf-8"),
                headers={"Content-Type": "application/json"},
            )
            self.assertEqual(status, 401)
            self.assertIn('scope="read-only-project"', headers["WWW-Authenticate"])
        finally:
            read_only_server.shutdown()
            read_only_server.server_close()
            thread.join(timeout=2)

    def test_full_agent_mode_exposes_full_agent_tools_over_http(self):
        project_root = Path(self.tempdir.name) / "project-http"
        project_root.mkdir()
        (project_root / "README.md").write_text("full agent http\n", encoding="utf-8")
        (project_root / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
        full_server = http_srv.create_server(
            host="127.0.0.1",
            port=0,
            tasks_root=self.tasks_root,
            auth_token="full-token",
            allowed_origins=["https://chatgpt.com"],
            mode=http_srv.MODE_FULL_AGENT,
            allowed_roots=[project_root],
        )
        thread = threading.Thread(target=full_server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{full_server.server_port}/mcp"
        try:
            tools = self._post_json(
                base,
                {"jsonrpc": "2.0", "id": 30, "method": "tools/list"},
                headers={"Authorization": "Bearer full-token"},
            )
            self.assertEqual(
                [tool["name"] for tool in tools["result"]["tools"]],
                [
                    "open_workspace",
                    "ls",
                    "read",
                    "read_lines",
                    "write",
                    "edit",
                    "grep",
                    "glob",
                    "bash",
                ],
            )
            opened = self._post_json(
                base,
                {
                    "jsonrpc": "2.0",
                    "id": 31,
                    "method": "tools/call",
                    "params": {
                        "name": "open_workspace",
                        "arguments": {"path": str(project_root)},
                    },
                },
                headers={"Authorization": "Bearer full-token"},
            )
            workspace_id = opened["result"]["structuredContent"]["workspace_id"]
            read = self._post_json(
                base,
                {
                    "jsonrpc": "2.0",
                    "id": 32,
                    "method": "tools/call",
                    "params": {
                        "name": "read",
                        "arguments": {
                            "workspace_id": workspace_id,
                            "path": "README.md",
                        },
                    },
                },
                headers={"Authorization": "Bearer full-token"},
            )
            self.assertIn("full agent http", read["result"]["content"][0]["text"])
            protected = self._post_json(
                base,
                {
                    "jsonrpc": "2.0",
                    "id": 33,
                    "method": "tools/call",
                    "params": {
                        "name": "read",
                        "arguments": {
                            "workspace_id": workspace_id,
                            "path": ".env",
                        },
                    },
                },
                headers={"Authorization": "Bearer full-token"},
            )
            self.assertTrue(protected["result"]["isError"])
            self.assertIn("protected", protected["result"]["content"][0]["text"])
        finally:
            full_server.shutdown()
            full_server.server_close()
            thread.join(timeout=2)

    def test_connected_agent_mode_exposes_danger_auto_tools_over_http(self):
        project_root = Path(self.tempdir.name) / "project-connected-http"
        project_root.mkdir()
        (project_root / "README.md").write_text("connected agent http\n", encoding="utf-8")
        connected_server = http_srv.create_server(
            host="127.0.0.1",
            port=0,
            tasks_root=self.tasks_root,
            auth_token="connected-token",
            allowed_origins=["https://chatgpt.com"],
            mode=http_srv.MODE_CONNECTED_AGENT,
            allowed_roots=[project_root],
        )
        thread = threading.Thread(target=connected_server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{connected_server.server_port}/mcp"
        try:
            tools = self._post_json(
                base,
                {"jsonrpc": "2.0", "id": 40, "method": "tools/list"},
                headers={"Authorization": "Bearer connected-token"},
            )
            self.assertEqual(
                [tool["name"] for tool in tools["result"]["tools"]],
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
            opened = self._post_json(
                base,
                {
                    "jsonrpc": "2.0",
                    "id": 41,
                    "method": "tools/call",
                    "params": {
                        "name": "open_default_workspace",
                        "arguments": {},
                    },
                },
                headers={"Authorization": "Bearer connected-token"},
            )
            workspace_id = opened["result"]["structuredContent"]["workspace_id"]
            denied = self._post_json(
                base,
                {
                    "jsonrpc": "2.0",
                    "id": 42,
                    "method": "tools/call",
                    "params": {
                        "name": "write",
                        "arguments": {
                            "workspace_id": workspace_id,
                            "path": "notes.md",
                            "content": "requires approval",
                        },
                    },
                },
                headers={"Authorization": "Bearer connected-token"},
            )
            self.assertTrue(denied["result"]["isError"])
            self.assertEqual(denied["result"]["structuredContent"]["error"], "approval_required")
            approval_id = denied["result"]["structuredContent"]["approval_id"]
            granted = self._post_json(
                base,
                {
                    "jsonrpc": "2.0",
                    "id": 43,
                    "method": "tools/call",
                    "params": {
                        "name": "grant_action_approval",
                        "arguments": {
                            "approval_id": approval_id,
                            "confirmation": "确认允许这次写入",
                        },
                    },
                },
                headers={"Authorization": "Bearer connected-token"},
            )
            self.assertFalse(granted["result"]["isError"])
            self.assertEqual(granted["result"]["structuredContent"]["status"], "granted")
            written = self._post_json(
                base,
                {
                    "jsonrpc": "2.0",
                    "id": 44,
                    "method": "tools/call",
                    "params": {
                        "name": "write",
                        "arguments": {
                            "workspace_id": workspace_id,
                            "path": "notes.md",
                            "content": "requires approval",
                            "approval_id": approval_id,
                        },
                    },
                },
                headers={"Authorization": "Bearer connected-token"},
            )
            self.assertFalse(written["result"]["isError"])

            enabled = self._post_json(
                base,
                {
                    "jsonrpc": "2.0",
                    "id": 45,
                    "method": "tools/call",
                    "params": {
                        "name": "enable_danger_auto",
                        "arguments": {"phrase": "dangerously trust connected agent"},
                    },
                },
                headers={"Authorization": "Bearer connected-token"},
            )
            self.assertTrue(enabled["result"]["structuredContent"]["danger_auto_enabled"])
        finally:
            connected_server.shutdown()
            connected_server.server_close()
            thread.join(timeout=2)

    def test_full_agent_mcp_request_refreshes_session_activity_file(self):
        project_root = Path(self.tempdir.name) / "project-session-activity"
        project_root.mkdir()
        session_activity_file = Path(self.tempdir.name) / "session.json"
        session_activity_file.write_text(
            json.dumps({"last_activity": 1000, "idle_timeout_seconds": 600}),
            encoding="utf-8",
        )
        full_server = http_srv.create_server(
            host="127.0.0.1",
            port=0,
            tasks_root=self.tasks_root,
            auth_token="full-token",
            allowed_origins=["https://chatgpt.com"],
            mode=http_srv.MODE_FULL_AGENT,
            allowed_roots=[project_root],
            session_activity_file=session_activity_file,
        )
        thread = threading.Thread(target=full_server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{full_server.server_port}/mcp"
        try:
            with mock.patch.object(http_srv.time, "time", return_value=2000.0):
                self._post_json(
                    base,
                    {"jsonrpc": "2.0", "id": 34, "method": "tools/list"},
                    headers={"Authorization": "Bearer full-token"},
                )

            saved = json.loads(session_activity_file.read_text(encoding="utf-8"))
            self.assertEqual(saved["last_activity"], 2000.0)
            self.assertEqual(saved["idle_timeout_seconds"], 600)
            self.assertEqual(session_activity_file.stat().st_mode & 0o777, 0o600)
        finally:
            full_server.shutdown()
            full_server.server_close()
            thread.join(timeout=2)

    def test_read_only_project_mode_exposes_only_read_tools_over_http(self):
        project_root = Path(self.tempdir.name) / "project-read-only-http"
        project_root.mkdir()
        (project_root / "README.md").write_text("read only http\n", encoding="utf-8")
        (project_root / ".env").write_text("TOKEN=secret\n", encoding="utf-8")
        read_only_server = http_srv.create_server(
            host="127.0.0.1",
            port=0,
            tasks_root=self.tasks_root,
            auth_token="read-token",
            allowed_origins=["https://chatgpt.com"],
            mode=http_srv.MODE_READ_ONLY_PROJECT,
            allowed_roots=[project_root],
        )
        thread = threading.Thread(target=read_only_server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{read_only_server.server_port}/mcp"
        try:
            tools = self._post_json(
                base,
                {"jsonrpc": "2.0", "id": 34, "method": "tools/list"},
                headers={"Authorization": "Bearer read-token"},
            )
            self.assertEqual(
                [tool["name"] for tool in tools["result"]["tools"]],
                ["open_workspace", "ls", "read", "read_lines", "grep", "glob"],
            )
            opened = self._post_json(
                base,
                {
                    "jsonrpc": "2.0",
                    "id": 35,
                    "method": "tools/call",
                    "params": {
                        "name": "open_workspace",
                        "arguments": {"path": str(project_root)},
                    },
                },
                headers={"Authorization": "Bearer read-token"},
            )
            workspace_id = opened["result"]["structuredContent"]["workspace_id"]
            denied = self._post_json(
                base,
                {
                    "jsonrpc": "2.0",
                    "id": 36,
                    "method": "tools/call",
                    "params": {
                        "name": "bash",
                        "arguments": {
                            "workspace_id": workspace_id,
                            "command": "printf nope",
                        },
                    },
                },
                headers={"Authorization": "Bearer read-token"},
            )
            self.assertTrue(denied["result"]["isError"])
            self.assertIn("not available", denied["result"]["content"][0]["text"])
        finally:
            read_only_server.shutdown()
            read_only_server.server_close()
            thread.join(timeout=2)

    def test_oauth_owner_password_flow_issues_bearer_token_for_mcp(self):
        oauth_server, thread = self._start_oauth_server()
        base = f"http://127.0.0.1:{oauth_server.server_port}"
        verifier = "test-code-verifier-for-decision-inbox"
        challenge = _pkce_challenge(verifier)
        redirect_uri = "https://chatgpt.com/aip/test-callback"
        try:
            protected_resource = self._get_json(
                f"{base}/.well-known/oauth-protected-resource/mcp"
            )
            self.assertEqual(
                protected_resource["resource"],
                "https://decision-inbox.example.com/mcp",
            )
            self.assertEqual(
                protected_resource["authorization_servers"],
                ["https://decision-inbox.example.com"],
            )

            metadata = self._get_json(f"{base}/.well-known/oauth-authorization-server")
            self.assertEqual(
                metadata["registration_endpoint"],
                "https://decision-inbox.example.com/oauth/register",
            )

            client = self._post_json(
                f"{base}/oauth/register",
                {
                    "client_name": "ChatGPT Test",
                    "redirect_uris": [redirect_uri],
                },
                expected_status=201,
            )
            client_id = client["client_id"]

            authorize_params = {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "resource": "https://decision-inbox.example.com/mcp",
                "scope": "decision-inbox",
                "state": "state-123",
            }
            page_status, page_headers, page_body = self._http_request(
                "GET", f"/oauth/authorize?{urlencode(authorize_params)}", port=oauth_server.server_port
            )
            self.assertEqual(page_status, 200)
            self.assertIn(
                "Connect Agent Decision Bridge Auto MCP Controlled Advisor",
                page_body.decode("utf-8"),
            )
            self.assertNotIn("test-owner-password", page_body.decode("utf-8"))

            authorize_form = dict(authorize_params)
            authorize_form["owner_token"] = "test-owner-password"
            status, headers, _ = self._http_request(
                "POST",
                "/oauth/authorize",
                body=urlencode(authorize_form).encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                port=oauth_server.server_port,
            )
            self.assertEqual(status, 302)
            location = headers["Location"]
            parsed_redirect = urlparse(location)
            redirect_query = parse_qs(parsed_redirect.query)
            self.assertEqual(redirect_query["state"], ["state-123"])
            code = redirect_query["code"][0]

            tokens = self._post_form(
                f"{base}/oauth/token",
                {
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "code": code,
                    "code_verifier": verifier,
                    "resource": "https://decision-inbox.example.com/mcp",
                },
            )
            self.assertEqual(tokens["token_type"], "bearer")
            self.assertIn("access_token", tokens)
            self.assertIn("refresh_token", tokens)

            tools = self._post_json(
                f"{base}/mcp",
                {"jsonrpc": "2.0", "id": 20, "method": "tools/list"},
                headers={"Authorization": f"Bearer {tokens['access_token']}"},
            )
            self.assertEqual(
                [tool["name"] for tool in tools["result"]["tools"]],
                [
                    "list_decision_tasks",
                    "get_decision_package",
                    "submit_advice",
                    "get_task_status",
                ],
            )
        finally:
            oauth_server.shutdown()
            oauth_server.server_close()
            thread.join(timeout=2)

    def test_oauth_access_token_is_not_accepted_as_query_token(self):
        oauth_server, thread = self._start_oauth_server()
        try:
            oauth_server.oauth_access_tokens["oauth-access"] = {
                "client_id": "client",
                "scopes": ["decision-inbox"],
                "resource": "https://decision-inbox.example.com/mcp",
                "expires_at": 4102444800,
            }
            request = Request(
                f"http://127.0.0.1:{oauth_server.server_port}/mcp?access_token=oauth-access",
                data=json.dumps({"jsonrpc": "2.0", "id": 21, "method": "tools/list"}).encode(
                    "utf-8"
                ),
                method="POST",
                headers={
                    "Content-Type": "application/json",
                    "Accept": "application/json, text/event-stream",
                    "MCP-Protocol-Version": "2025-11-25",
                },
            )
            with self.assertRaises(HTTPError) as caught:
                urlopen(request, timeout=5)
            self.assertEqual(caught.exception.code, 401)
        finally:
            oauth_server.shutdown()
            oauth_server.server_close()
            thread.join(timeout=2)

    def test_oauth_state_file_persists_refresh_tokens_across_restart(self):
        state_file = Path(self.tempdir.name) / "oauth-state.json"
        oauth_server, thread = self._start_oauth_server(oauth_state_file=state_file)
        base = f"http://127.0.0.1:{oauth_server.server_port}"
        verifier = "persistent-test-code-verifier"
        redirect_uri = "https://chatgpt.com/aip/test-callback"
        try:
            client = self._post_json(
                f"{base}/oauth/register",
                {
                    "client_name": "ChatGPT Persistent Test",
                    "redirect_uris": [redirect_uri],
                },
                expected_status=201,
            )
            client_id = client["client_id"]
            authorize_form = {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "code_challenge": _pkce_challenge(verifier),
                "code_challenge_method": "S256",
                "resource": "https://decision-inbox.example.com/mcp",
                "scope": "decision-inbox",
                "owner_token": "test-owner-password",
            }
            status, headers, _ = self._http_request(
                "POST",
                "/oauth/authorize",
                body=urlencode(authorize_form).encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                port=oauth_server.server_port,
            )
            self.assertEqual(status, 302)
            code = parse_qs(urlparse(headers["Location"]).query)["code"][0]
            tokens = self._post_form(
                f"{base}/oauth/token",
                {
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "code": code,
                    "code_verifier": verifier,
                    "resource": "https://decision-inbox.example.com/mcp",
                },
            )
        finally:
            oauth_server.shutdown()
            oauth_server.server_close()
            thread.join(timeout=2)

        self.assertTrue(state_file.is_file())
        self.assertEqual(state_file.stat().st_mode & 0o777, 0o600)
        state_payload = json.loads(state_file.read_text(encoding="utf-8"))
        self.assertIn(tokens["refresh_token"], state_payload["oauth_refresh_tokens"])
        self.assertNotIn("oauth_authorization_codes", state_payload)

        restarted_server, restarted_thread = self._start_oauth_server(
            oauth_state_file=state_file
        )
        restarted_base = f"http://127.0.0.1:{restarted_server.server_port}"
        try:
            refreshed_tokens = self._post_form(
                f"{restarted_base}/oauth/token",
                {
                    "grant_type": "refresh_token",
                    "client_id": client_id,
                    "refresh_token": tokens["refresh_token"],
                    "resource": "https://decision-inbox.example.com/mcp",
                },
            )
            self.assertIn("access_token", refreshed_tokens)
            tools = self._post_json(
                f"{restarted_base}/mcp",
                {"jsonrpc": "2.0", "id": 22, "method": "tools/list"},
                headers={"Authorization": f"Bearer {refreshed_tokens['access_token']}"},
            )
            self.assertIn("tools", tools["result"])
        finally:
            restarted_server.shutdown()
            restarted_server.server_close()
            restarted_thread.join(timeout=2)

    def test_read_optional_secret_file_strips_value(self):
        secret_file = Path(self.tempdir.name) / "owner-token"
        secret_file.write_text(" owner-password\n", encoding="utf-8")

        self.assertEqual(
            http_srv.read_optional_secret_file(str(secret_file), "TEST_SECRET_FILE"),
            "owner-password",
        )

    def _post(self, payload, url=None, headers=None):
        request = self._request(payload, url=url, headers=headers)
        with urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.headers.get_content_type(), "application/json")
            return json.loads(response.read().decode("utf-8"))

    def _start_oauth_server(self, **kwargs):
        oauth_server = http_srv.create_server(
            host="127.0.0.1",
            port=0,
            tasks_root=self.tasks_root,
            auth_token=None,
            allowed_origins=["https://chatgpt.com"],
            public_base_url="https://decision-inbox.example.com",
            oauth_owner_token="test-owner-password",
            **kwargs,
        )
        thread = threading.Thread(target=oauth_server.serve_forever, daemon=True)
        thread.start()
        return oauth_server, thread

    def _get_json(self, url):
        with urlopen(Request(url, method="GET"), timeout=5) as response:
            self.assertEqual(response.headers.get_content_type(), "application/json")
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, url, payload, headers=None, expected_status=200):
        request_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "MCP-Protocol-Version": "2025-11-25",
        }
        request_headers.update(headers or {})
        request = Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            method="POST",
            headers=request_headers,
        )
        with urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, expected_status)
            self.assertEqual(response.headers.get_content_type(), "application/json")
            return json.loads(response.read().decode("utf-8"))

    def _post_form(self, url, values, expected_status=200):
        request = Request(
            url,
            data=urlencode(values).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urlopen(request, timeout=5) as response:
            self.assertEqual(response.status, expected_status)
            self.assertEqual(response.headers.get_content_type(), "application/json")
            return json.loads(response.read().decode("utf-8"))

    def _http_request(self, method, path, port, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        self.addCleanup(connection.close)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        body_bytes = response.read()
        return response.status, dict(response.getheaders()), body_bytes

    def _request(self, payload, url=None, headers=None):
        body = json.dumps(payload).encode("utf-8")
        request_headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "Authorization": "Bearer test-token",
            "MCP-Protocol-Version": "2025-11-25",
        }
        if headers:
            for key, value in headers.items():
                if value is None:
                    request_headers.pop(key, None)
                else:
                    request_headers[key] = value
        return Request(
            url or self.base_url,
            data=body,
            method="POST",
            headers=request_headers,
        )


def _pkce_challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


if __name__ == "__main__":
    unittest.main()
