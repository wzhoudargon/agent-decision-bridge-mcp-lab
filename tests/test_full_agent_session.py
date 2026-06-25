import argparse
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import full_agent_session as session


class FullAgentSessionTests(unittest.TestCase):
    def make_args(self, tempdir: str, **overrides):
        defaults = {
            "state_file": Path(tempdir) / "session.json",
            "host": "127.0.0.1",
            "port": 8765,
            "public_base_url": "https://full-agent.example.com",
            "allowed_roots": [str(Path(tempdir) / "workspace")],
            "tailscale_bin": "tailscale",
            "socket": "/tmp/test-tailscale.sock",
            "idle_timeout_seconds": session.DEFAULT_IDLE_TIMEOUT_SECONDS,
            "poll_seconds": 1.0,
            "startup_timeout": 1.0,
            "preflight_timeout": 1.0,
            "public_warmup_seconds": 5.0,
            "preflight_attempts": 3,
            "preflight_retry_seconds": 5.0,
            "server_log": Path(tempdir) / "server.log",
            "watchdog_log": Path(tempdir) / "watchdog.log",
            "oauth_state_file": None,
            "oauth_owner_token_file": None,
            "local_only": False,
            "skip_preflight": False,
            "check_public_health": False,
            "health_attempts": 3,
            "health_retry_seconds": 2.0,
            "no_watchdog": False,
        }
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_build_server_command_uses_explicit_full_agent_mode(self):
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir) / "workspace"
            args = self.make_args(tempdir, allowed_roots=[str(workspace)])

            command = session.build_server_command(args)

        self.assertIn("--mode", command)
        mode_index = command.index("--mode")
        self.assertEqual(command[mode_index + 1], "full-agent")
        self.assertIn("--allowed-root", command)
        self.assertIn(str(workspace), command)
        self.assertIn("--public-base-url", command)
        self.assertIn("https://full-agent.example.com", command)

    def test_open_requires_allowed_root(self):
        with tempfile.TemporaryDirectory() as tempdir:
            args = self.make_args(tempdir, allowed_roots=[])

            status = session.open_session(args)

        self.assertEqual(status, 2)

    def test_open_requires_public_url_unless_local_only(self):
        with tempfile.TemporaryDirectory() as tempdir:
            args = self.make_args(tempdir, public_base_url=None, local_only=False)

            status = session.open_session(args)

        self.assertEqual(status, 2)

    def test_status_closed_reports_public_health_skip_when_requested(self):
        with tempfile.TemporaryDirectory() as tempdir:
            args = self.make_args(tempdir, check_public_health=True)

            with mock.patch("builtins.print") as print_:
                status = session.status_session(args)

        self.assertEqual(status, 1)
        output = "\n".join(call.args[0] for call in print_.call_args_list)
        self.assertIn("Current state: full_agent_session_closed", output)
        self.assertIn("Public health: skipped_session_not_open", output)

    def test_status_rechecks_session_after_public_health(self):
        with tempfile.TemporaryDirectory() as tempdir:
            args = self.make_args(tempdir, check_public_health=True)
            state = {
                "server_pid": os.getpid(),
                "watchdog_pid": None,
                "last_activity": session.time.time(),
                "idle_timeout_seconds": 300,
                "local_mcp_url": "http://127.0.0.1:8765/mcp",
                "public_base_url": "https://full-agent.example.com",
            }
            session.save_state(args.state_file, state)

            def close_during_health(_args, _state, alive):
                args.state_file.unlink()
                return "Public health: failed preflight_passed=0/1 latest_failure=closed"

            with mock.patch.object(session, "public_health_report", side_effect=close_during_health):
                with mock.patch("builtins.print") as print_:
                    status = session.status_session(args)

        self.assertEqual(status, 1)
        output = "\n".join(call.args[0] for call in print_.call_args_list)
        self.assertIn("Current state: full_agent_session_open", output)
        self.assertIn("Current state after health check: full_agent_session_closed_or_stale", output)

    def test_public_warmup_waits_only_for_positive_values(self):
        with mock.patch.object(session.time, "sleep") as sleep:
            session.wait_for_public_warmup(0)
            session.wait_for_public_warmup(-1)
            session.wait_for_public_warmup(2.5)

        sleep.assert_called_once_with(2.5)

    def test_product_readiness_summary_separates_connector_and_advisor(self):
        summary = session.product_readiness_summary(preflight_ran=True)

        self.assertIn("connector_tools_verified=verified_by_preflight", summary)
        self.assertIn("advisor_channel_verified=not_checked_by_session_helper", summary)
        self.assertIn("session_online=yes", summary)
        self.assertIn("risk=5/5", summary)

    def test_flush_dns_cache_best_effort_uses_macos_cache_flush(self):
        with mock.patch.object(session.sys, "platform", "darwin"):
            with mock.patch.object(session.subprocess, "run") as run:
                session.flush_dns_cache_best_effort()

        run.assert_called_once()
        self.assertEqual(run.call_args.args[0], ["dscacheutil", "-flushcache"])

    def test_flush_dns_cache_best_effort_skips_non_macos(self):
        with mock.patch.object(session.sys, "platform", "linux"):
            with mock.patch.object(session.subprocess, "run") as run:
                session.flush_dns_cache_best_effort()

        run.assert_not_called()

    def test_preflight_retries_transient_failure(self):
        with tempfile.TemporaryDirectory() as tempdir:
            args = self.make_args(
                tempdir,
                preflight_attempts=2,
                preflight_retry_seconds=1.5,
            )

            with mock.patch.object(
                session,
                "run_preflight",
                side_effect=[RuntimeError("temporary failure"), None],
            ) as run_preflight:
                with mock.patch.object(session.time, "sleep") as sleep:
                    session.run_preflight_with_retries(args, "http://127.0.0.1:8765/mcp")

        self.assertEqual(run_preflight.call_count, 2)
        sleep.assert_called_once_with(1.5)

    def test_preflight_raises_after_attempts_exhausted(self):
        with tempfile.TemporaryDirectory() as tempdir:
            args = self.make_args(
                tempdir,
                preflight_attempts=2,
                preflight_retry_seconds=0,
            )

            with mock.patch.object(
                session,
                "run_preflight",
                side_effect=RuntimeError("still failing"),
            ) as run_preflight:
                with self.assertRaisesRegex(RuntimeError, "still failing"):
                    session.run_preflight_with_retries(args, "http://127.0.0.1:8765/mcp")

        self.assertEqual(run_preflight.call_count, 2)

    def test_save_state_uses_private_permissions_and_no_secret_values(self):
        with tempfile.TemporaryDirectory() as tempdir:
            state_file = Path(tempdir) / "session" / "state.json"
            state = {
                "server_pid": os.getpid(),
                "public_base_url": "https://full-agent.example.com",
                "allowed_roots": [str(Path(tempdir) / "workspace")],
                "last_activity": 1000,
                "idle_timeout_seconds": 300,
            }

            session.save_state(state_file, state)
            saved = json.loads(state_file.read_text(encoding="utf-8"))

            self.assertEqual(saved["public_base_url"], "https://full-agent.example.com")
            self.assertEqual(state_file.stat().st_mode & 0o777, 0o600)
            self.assertEqual(state_file.parent.stat().st_mode & 0o777, 0o700)
            self.assertNotIn("oauth", state_file.read_text(encoding="utf-8").lower())
            self.assertNotIn("token", state_file.read_text(encoding="utf-8").lower())

    def test_touch_updates_last_activity_for_live_server(self):
        with tempfile.TemporaryDirectory() as tempdir:
            args = self.make_args(tempdir)
            state = {
                "server_pid": os.getpid(),
                "public_base_url": "https://full-agent.example.com",
                "last_activity": 1000,
                "idle_timeout_seconds": 300,
            }
            session.save_state(args.state_file, state)

            with mock.patch.object(session.time, "time", return_value=1234):
                status = session.touch_session(args)

            saved = session.load_state(args.state_file)

        self.assertEqual(status, 0)
        self.assertEqual(saved["last_activity"], 1234)

    def test_open_existing_session_refreshes_last_activity_and_timeout(self):
        with tempfile.TemporaryDirectory() as tempdir:
            args = self.make_args(tempdir, idle_timeout_seconds=600)
            state = {
                "server_pid": os.getpid(),
                "public_base_url": "https://full-agent.example.com",
                "last_activity": 1000,
                "idle_timeout_seconds": 300,
            }
            session.save_state(args.state_file, state)

            with mock.patch.object(session.time, "time", return_value=1234):
                status = session.open_session(args)

            saved = session.load_state(args.state_file)

        self.assertEqual(status, 0)
        self.assertEqual(saved["last_activity"], 1234)
        self.assertEqual(saved["idle_timeout_seconds"], 600)

    def test_sweep_closes_idle_session(self):
        with tempfile.TemporaryDirectory() as tempdir:
            args = self.make_args(tempdir)
            state = {
                "server_pid": os.getpid(),
                "watchdog_pid": None,
                "tailscale_socket": None,
                "public_base_url": "https://full-agent.example.com",
                "last_activity": 1000,
                "idle_timeout_seconds": 300,
            }
            session.save_state(args.state_file, state)

            with mock.patch.object(session.time, "time", return_value=1401):
                with mock.patch.object(session, "close_session", return_value=0) as close:
                    status = session.sweep_session(args)

        self.assertEqual(status, 0)
        close.assert_called_once()
        self.assertTrue(close.call_args.kwargs["from_watchdog"])

    def test_close_resets_tailscale_funnel(self):
        with tempfile.TemporaryDirectory() as tempdir:
            args = self.make_args(tempdir)
            state = {
                "server_pid": os.getpid(),
                "watchdog_pid": None,
                "tailscale_bin": "tailscale",
                "tailscale_socket": "/tmp/test-tailscale.sock",
                "last_activity": 1000,
                "idle_timeout_seconds": 300,
            }
            session.save_state(args.state_file, state)

            with mock.patch.object(session, "run_tailscale_from_state", return_value=0) as run_tailscale:
                status = session.close_session(args)

        self.assertEqual(status, 0)
        run_tailscale.assert_called_once()
        self.assertEqual(run_tailscale.call_args.args[2], ["funnel", "reset"])

    def test_public_health_skips_when_session_closed(self):
        with tempfile.TemporaryDirectory() as tempdir:
            args = self.make_args(tempdir)

            report = session.public_health_report(args, {}, alive=False)

        self.assertEqual(report, "Public health: skipped_session_not_open")

    def test_public_health_reports_stable_when_all_preflights_pass(self):
        with tempfile.TemporaryDirectory() as tempdir:
            args = self.make_args(tempdir, health_attempts=2, health_retry_seconds=0)
            state = {
                "local_mcp_url": "http://127.0.0.1:8765/mcp",
                "public_base_url": "https://full-agent.example.com",
            }
            completed = subprocess.CompletedProcess(args=["preflight"], returncode=0, stdout="")

            with mock.patch.object(session, "run_preflight_for_state", return_value=completed):
                report = session.public_health_report(args, state, alive=True)

        self.assertEqual(report, "Public health: stable preflight_passed=2/2")

    def test_public_health_reports_intermittent_when_some_preflights_fail(self):
        with tempfile.TemporaryDirectory() as tempdir:
            args = self.make_args(tempdir, health_attempts=3, health_retry_seconds=0)
            state = {
                "local_mcp_url": "http://127.0.0.1:8765/mcp",
                "public_base_url": "https://full-agent.example.com",
            }
            ok = subprocess.CompletedProcess(args=["preflight"], returncode=0, stdout="")
            failed = subprocess.CompletedProcess(
                args=["preflight"],
                returncode=1,
                stdout=(
                    "Preflight result: failed\n"
                    "- public MCP endpoint is not reachable or not challenging as expected\n"
                ),
            )

            with mock.patch.object(
                session,
                "run_preflight_for_state",
                side_effect=[ok, failed, ok],
            ):
                report = session.public_health_report(args, state, alive=True)

        self.assertIn("Public health: intermittent preflight_passed=2/3", report)
        self.assertIn("public MCP endpoint is not reachable", report)


if __name__ == "__main__":
    unittest.main()
