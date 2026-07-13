import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import conversation_product_gate as gate


class ConversationProductGateTests(unittest.TestCase):
    def test_full_agent_waits_when_chatgpt_web_is_blank(self):
        result = gate.evaluate_gate(
            mode="full-agent",
            advisor_channel="browser-automation",
            advisor_health="blank",
            session_state="not_open",
        )

        self.assertEqual(result["exit_code"], 2)
        self.assertIn("Current state: waiting_for_advisor_channel", result["message"])
        self.assertIn("Risk if opened: 5/5", result["message"])
        self.assertIn("rendered blank", result["message"])
        self.assertIn("GPT Pro has not been consulted yet", result["message"])

    def test_full_agent_ready_only_when_advisor_channel_is_ready(self):
        result = gate.evaluate_gate(
            mode="full-agent",
            advisor_channel="browser-automation",
            advisor_health="ready",
            session_state="not_open",
        )

        self.assertEqual(result["exit_code"], 0)
        self.assertIn("Current state: ready_to_open_full_agent", result["message"])
        self.assertIn("Open Full-Agent only for the active consultation window", result["message"])

    def test_connected_agent_ready_when_advisor_channel_is_ready(self):
        result = gate.evaluate_gate(
            mode="connected-agent",
            advisor_channel="user-web",
            advisor_health="ready",
            session_state="not_open",
        )

        self.assertEqual(result["exit_code"], 0)
        self.assertIn("Current state: ready_to_open_connected_agent", result["message"])
        self.assertIn("Risk if opened: 4/5-5/5", result["message"])
        self.assertIn("Open the Connected Agent connector window", result["message"])

    def test_full_agent_reports_browser_restart_recovery(self):
        result = gate.evaluate_gate(
            mode="full-agent",
            advisor_channel="browser-automation",
            advisor_health="needs-browser-restart",
            session_state="not_open",
        )

        self.assertEqual(result["exit_code"], 2)
        self.assertIn("Current state: waiting_for_advisor_channel", result["message"])
        self.assertIn("restart the browser after user confirmation", result["message"])
        self.assertIn("confirm browser restart if needed", result["message"])

    def test_manual_does_not_need_live_advisor_channel(self):
        result = gate.evaluate_gate(
            mode="manual",
            advisor_channel="unknown",
            advisor_health="unknown",
        )

        self.assertEqual(result["exit_code"], 0)
        self.assertIn("Current state: manual_package_available", result["message"])
        self.assertIn("Risk if opened: 1/5", result["message"])
        self.assertIn("GPT Pro has not been consulted yet", result["message"])


if __name__ == "__main__":
    unittest.main()
