import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import connected_agent_status


class ConnectedAgentStatusTests(unittest.TestCase):
    def test_reports_gate_session_and_funnel_status(self):
        session = subprocess.CompletedProcess(
            args=["python", "connected_agent_session.py", "status"],
            returncode=1,
            stdout=(
                "Current state: connected_agent_session_closed\n"
                "Risk coefficient now: 2/5 if persistent OAuth state remains, otherwise 1/5\n"
            ),
        )
        funnel = subprocess.CompletedProcess(
            args=["tailscale", "funnel", "status"],
            returncode=0,
            stdout="No serve config\n",
        )

        with mock.patch.object(connected_agent_status, "run_status", side_effect=[session, funnel]):
            with mock.patch.object(sys, "argv", [
                "connected_agent_status.py",
                "--advisor-channel",
                "browser-automation",
                "--advisor-health",
                "needs-browser-restart",
            ]):
                with mock.patch("builtins.print") as print_:
                    status = connected_agent_status.main()

        self.assertEqual(status, 2)
        output = print_.call_args.args[0]
        self.assertIn("Connected Agent product status:", output)
        self.assertIn("Can use now: not yet.", output)
        self.assertIn("Exposure now: closed.", output)
        self.assertIn(
            "Normal flow: prepare -> ChatGPT Web with Connected Agent connector -> capture -> 20-minute idle close.",
            output,
        )
        self.assertIn("Connected Agent readiness:", output)
        self.assertIn("Current state: waiting_for_advisor_channel", output)
        self.assertIn("restart the browser after user confirmation", output)
        self.assertIn("Current state: connected_agent_session_closed", output)
        self.assertIn("No serve config", output)

    def test_summary_reports_ready_to_open(self):
        summary = connected_agent_status.summarize_state(
            "Current state: connected_agent_session_closed\n",
            "No serve config\n",
            "\n".join(
                [
                    "Current state: ready_to_open_connected_agent",
                    "Requested mode: connected-agent",
                    "Risk if opened: 3/5-5/5",
                ]
            ),
        )

        self.assertIn("Can use now: yes", summary)
        self.assertIn("short Connected Agent task window", summary)
        self.assertIn("Exposure now: closed.", summary)


if __name__ == "__main__":
    unittest.main()
