import argparse
import sys
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import decision_inbox_tunnel_window as tunnel_window


class DecisionInboxTunnelWindowTests(unittest.TestCase):
    def make_args(self, **overrides):
        defaults = {
            "mode": "auto-mcp",
            "port": 8765,
            "public_base_url": "https://decision-inbox.example.com",
            "task_id": None,
            "timeout": 5.0,
            "tailscale_bin": "tailscale",
            "socket": "/tmp/test-tailscale.sock",
            "skip_preflight": False,
        }
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_close_resets_tailscale_funnel(self):
        args = self.make_args()

        with mock.patch.object(tunnel_window, "run_tailscale", return_value=0) as run_tailscale:
            status = tunnel_window.close_window(args)

        self.assertEqual(status, 0)
        run_tailscale.assert_called_once_with(args, ["funnel", "reset"])


if __name__ == "__main__":
    unittest.main()
