import argparse
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import decision_inbox_doctor as doctor


class DecisionInboxDoctorTests(unittest.TestCase):
    def test_token_status_redacts_value(self):
        status = doctor.token_status("secret-token-value", "env:DECISION_INBOX_MCP_TOKEN")

        self.assertIn("present", status)
        self.assertIn("length=18", status)
        self.assertIn("value=redacted", status)
        self.assertNotIn("secret-token-value", status)

    def test_estimates_local_only_as_low_risk(self):
        risk, reason = doctor.estimate_risk(None, None, "http://127.0.0.1:8765/mcp")

        self.assertEqual(risk, 1)
        self.assertIn("local-only", reason)

    def test_estimates_public_url_without_token_as_high_risk(self):
        risk, reason = doctor.estimate_risk(
            "https://decision-inbox.example.com",
            None,
            "http://127.0.0.1:8765/mcp",
        )

        self.assertEqual(risk, 4)
        self.assertIn("without bearer-token or OAuth owner-password auth", reason)

    def test_estimates_public_url_with_oauth_owner_password_as_medium_risk(self):
        risk, reason = doctor.estimate_risk(
            "https://decision-inbox.example.com",
            None,
            "http://127.0.0.1:8765/mcp",
            oauth_owner_token="owner-password",
        )

        self.assertEqual(risk, 3)
        self.assertIn("public tunnel", reason)

    def test_estimates_local_persistent_oauth_state_as_low_medium_risk(self):
        risk, reason = doctor.estimate_risk(
            None,
            None,
            "http://127.0.0.1:8765/mcp",
            oauth_state_file_present=True,
        )

        self.assertEqual(risk, 2)
        self.assertIn("OAuth state", reason)

    def test_estimates_full_agent_as_highest_risk(self):
        risk, reason = doctor.estimate_risk(
            None,
            None,
            "http://127.0.0.1:8765/mcp",
            mode="full-agent",
        )

        self.assertEqual(risk, 5)
        self.assertIn("shell execution", reason)

    def test_secret_file_status_does_not_read_value(self):
        with tempfile.TemporaryDirectory() as tempdir:
            secret_file = Path(tempdir) / "oauth-state.json"
            secret_file.write_text("secret-token-value", encoding="utf-8")
            secret_file.chmod(0o600)

            status = doctor.secret_file_status(secret_file)

        self.assertIn("present", status)
        self.assertIn("mode=0600", status)
        self.assertIn("value=not_read", status)
        self.assertNotIn("secret-token-value", status)

    def test_load_token_prefers_environment_over_file(self):
        with tempfile.TemporaryDirectory() as tempdir:
            token_file = Path(tempdir) / "token"
            token_file.write_text("file-token", encoding="utf-8")
            with mock.patch.dict(os.environ, {"DECISION_INBOX_MCP_TOKEN": "env-token"}):
                token, source = doctor.load_token("DECISION_INBOX_MCP_TOKEN", token_file)

        self.assertEqual(token, "env-token")
        self.assertEqual(source, "env:DECISION_INBOX_MCP_TOKEN")

    def test_build_report_does_not_print_token_value(self):
        args = argparse.Namespace(
            local_url="http://127.0.0.1:8765/mcp",
            public_base_url="https://decision-inbox.example.com",
            token_env="DECISION_INBOX_MCP_TOKEN",
            token_file=None,
            oauth_owner_token_env="DECISION_INBOX_OAUTH_OWNER_TOKEN",
            oauth_owner_token_file=None,
            oauth_state_file=None,
            timeout=0.01,
            skip_probe=True,
        )
        with mock.patch.dict(os.environ, {"DECISION_INBOX_MCP_TOKEN": "secret-token"}):
            report = "\n".join(doctor.build_report(args))

        self.assertIn("Risk coefficient: 3/5", report)
        self.assertIn("https://decision-inbox.example.com/mcp", report)
        self.assertIn("value=redacted", report)
        self.assertNotIn("secret-token", report)

    def test_build_report_does_not_print_oauth_owner_password_value(self):
        args = argparse.Namespace(
            local_url="http://127.0.0.1:8765/mcp",
            public_base_url="https://decision-inbox.example.com",
            token_env="DECISION_INBOX_MCP_TOKEN",
            token_file=None,
            oauth_owner_token_env="DECISION_INBOX_OAUTH_OWNER_TOKEN",
            oauth_owner_token_file=None,
            oauth_state_file=None,
            timeout=0.01,
            skip_probe=True,
        )
        with mock.patch.dict(
            os.environ,
            {
                "DECISION_INBOX_MCP_TOKEN": "",
                "DECISION_INBOX_OAUTH_OWNER_TOKEN": "secret-owner-password",
            },
        ):
            report = "\n".join(doctor.build_report(args))

        self.assertIn("Risk coefficient: 3/5", report)
        self.assertIn("OAuth Owner password status: present", report)
        self.assertNotIn("secret-owner-password", report)

    def test_build_report_full_agent_uses_full_agent_defaults(self):
        args = argparse.Namespace(
            mode="full-agent",
            local_url="http://127.0.0.1:8765/mcp",
            public_base_url=None,
            token_env="DECISION_INBOX_MCP_TOKEN",
            token_file=None,
            oauth_owner_token_env="DECISION_INBOX_OAUTH_OWNER_TOKEN",
            oauth_owner_token_file=None,
            oauth_state_file=None,
            timeout=0.01,
            skip_probe=True,
        )

        report = "\n".join(doctor.build_report(args))

        self.assertIn("Mode: full-agent", report)
        self.assertIn("Risk coefficient: 5/5", report)
        self.assertIn(".local/share/agent-decision-bridge/oauth-state.json", report)


if __name__ == "__main__":
    unittest.main()
