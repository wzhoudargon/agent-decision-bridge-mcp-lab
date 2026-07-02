import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import level3_consultation_flow as flow


def completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["cmd"], returncode=returncode, stdout=stdout, stderr="")


class Level3ConsultationFlowTests(unittest.TestCase):
    def test_prepare_opens_checks_health_and_copies_prompt(self):
        stdout = StringIO()
        results = [
            completed("Current state: full_agent_session_open\n"),
            completed("Public health: stable preflight_passed=3/3\n"),
            completed("Current state: connected_agent_prompt_ready\nClipboard: copied\n"),
        ]

        with mock.patch.object(flow, "run_command", side_effect=results) as run:
            with redirect_stdout(stdout):
                status = flow.main(
                    [
                        "prepare",
                        "--allowed-root",
                        "/tmp/example-project",
                        "--public-base-url",
                        "https://example.test",
                        "--advisor-channel",
                        "user-web",
                        "--advisor-health",
                        "ready",
                        "Review readiness.",
                    ]
                )

        self.assertEqual(status, 0)
        self.assertEqual(run.call_count, 3)
        output = stdout.getvalue()
        self.assertIn("Current state: connected_agent_flow_ready_for_advisor", output)
        self.assertIn("Risk while session remains open: 3/5-5/5", output)
        self.assertIn("use GPT-5.5 Thinking", output)
        self.assertIn("Do not use GPT-5.5 Pro", output)
        self.assertIn("Next step for the user:", output)
        self.assertIn("paste the answer back into Codex", output)
        prompt_command = run.call_args_list[2].args[0]
        self.assertIn("--clipboard", prompt_command)
        self.assertIn("Review readiness.", prompt_command)

    def test_prepare_waits_by_default_until_advisor_channel_is_ready(self):
        stdout = StringIO()

        with mock.patch.object(flow, "run_command") as run:
            with redirect_stdout(stdout):
                status = flow.main(
                    [
                        "prepare",
                        "--allowed-root",
                        "/tmp/example-project",
                        "--public-base-url",
                        "https://example.test",
                        "Review readiness.",
                    ]
                )

        self.assertEqual(status, 2)
        run.assert_not_called()
        output = stdout.getvalue()
        self.assertIn("waiting_for_advisor_channel", output)
        self.assertIn("Risk if opened: 3/5-5/5", output)
        self.assertIn("GPT Pro has not been consulted yet", output)

    def test_prepare_waits_when_advisor_channel_not_ready(self):
        stdout = StringIO()

        with mock.patch.object(flow, "run_command") as run:
            with redirect_stdout(stdout):
                status = flow.main(
                    [
                        "prepare",
                        "--allowed-root",
                        "/tmp/example-project",
                        "--public-base-url",
                        "https://example.test",
                        "--advisor-channel",
                        "browser-automation",
                        "--advisor-health",
                        "blank",
                        "Review readiness.",
                    ]
                )

        self.assertEqual(status, 2)
        run.assert_not_called()
        self.assertIn("waiting_for_advisor_channel", stdout.getvalue())
        self.assertIn("GPT Pro has not been consulted yet", stdout.getvalue())

    def test_browser_automation_handoff_warns_that_computer_is_controlled(self):
        stdout = StringIO()
        results = [
            completed("Current state: full_agent_session_open\n"),
            completed("Public health: stable preflight_passed=3/3\n"),
            completed("Current state: connected_agent_prompt_ready\nClipboard: copied\n"),
        ]

        with mock.patch.object(flow, "run_command", side_effect=results):
            with redirect_stdout(stdout):
                status = flow.main(
                    [
                        "prepare",
                        "--allowed-root",
                        "/tmp/example-project",
                        "--public-base-url",
                        "https://example.test",
                        "--advisor-channel",
                        "browser-automation",
                        "--advisor-health",
                        "ready",
                        "Review readiness.",
                    ]
                )

        self.assertEqual(status, 0)
        output = stdout.getvalue()
        self.assertIn("Browser automation warning", output)
        self.assertIn("use GPT-5.5 Thinking", output)
        self.assertIn("浏览器自动化会临时控制你的电脑 UI", output)
        self.assertIn("请不要操作鼠标键盘", output)

    def test_prepare_closes_when_public_health_is_not_stable(self):
        stdout = StringIO()
        results = [
            completed("Current state: full_agent_session_open\n"),
            completed("Public health: intermittent preflight_passed=1/3 latest_failure=timeout\n"),
            completed("Public health: failed preflight_passed=0/3 latest_failure=timeout\n", returncode=1),
            completed("Current state: full_agent_session_closed\n"),
            completed("Current state: full_agent_session_closed\nPublic health: skipped_session_not_open\n", returncode=1),
        ]

        with mock.patch.object(flow, "run_command", side_effect=results) as run:
            with redirect_stdout(stdout):
                status = flow.main(
                    [
                        "prepare",
                        "--allowed-root",
                        "/tmp/example-project",
                        "--public-base-url",
                        "https://example.test",
                        "--advisor-channel",
                        "user-web",
                        "--advisor-health",
                        "ready",
                        "Review readiness.",
                    ]
                )

        self.assertEqual(status, 1)
        self.assertEqual(run.call_count, 5)
        output = stdout.getvalue()
        self.assertIn("running recovery check 1/1", output)
        self.assertIn("public health is not stable", output)
        self.assertIn("Close verification:", output)
        self.assertIn("GPT Pro has not been consulted yet", output)

    def test_prepare_recovers_when_second_health_check_is_stable(self):
        stdout = StringIO()
        results = [
            completed("Current state: full_agent_session_open\n"),
            completed("Public health: intermittent preflight_passed=2/3 latest_failure=timeout\n"),
            completed("Public health: stable preflight_passed=3/3\n"),
            completed("Current state: connected_agent_prompt_ready\nClipboard: copied\n"),
        ]

        with mock.patch.object(flow, "run_command", side_effect=results) as run:
            with redirect_stdout(stdout):
                status = flow.main(
                    [
                        "prepare",
                        "--allowed-root",
                        "/tmp/example-project",
                        "--public-base-url",
                        "https://example.test",
                        "--advisor-channel",
                        "user-web",
                        "--advisor-health",
                        "ready",
                        "Review readiness.",
                    ]
                )

        self.assertEqual(status, 0)
        self.assertEqual(run.call_count, 4)
        output = stdout.getvalue()
        self.assertIn("running recovery check 1/1", output)
        self.assertIn("Current state: connected_agent_flow_ready_for_advisor", output)

    def test_prepare_does_not_recover_after_failed_health(self):
        stdout = StringIO()
        results = [
            completed("Current state: full_agent_session_open\n"),
            completed("Public health: failed preflight_passed=0/3 latest_failure=timeout\n", returncode=1),
            completed("Current state: full_agent_session_closed\n"),
            completed("Current state: full_agent_session_closed\nPublic health: skipped_session_not_open\n", returncode=1),
        ]

        with mock.patch.object(flow, "run_command", side_effect=results) as run:
            with redirect_stdout(stdout):
                status = flow.main(
                    [
                        "prepare",
                        "--allowed-root",
                        "/tmp/example-project",
                        "--public-base-url",
                        "https://example.test",
                        "--advisor-channel",
                        "user-web",
                        "--advisor-health",
                        "ready",
                        "Review readiness.",
                    ]
                )

        self.assertEqual(status, 1)
        self.assertEqual(run.call_count, 4)
        output = stdout.getvalue()
        self.assertNotIn("running recovery check", output)
        self.assertIn("public health is not stable", output)
        self.assertIn("GPT Pro has not been consulted yet", output)

    def test_build_prompt_command_allows_no_clipboard(self):
        args = flow.parse_args(
            [
                "prepare",
                "--allowed-root",
                "/tmp/example-project",
                "--public-base-url",
                "https://example.test",
                "--advisor-channel",
                "user-web",
                "--advisor-health",
                "ready",
                "--no-clipboard",
                "Review readiness.",
            ]
        )

        command = flow.build_prompt_command(args)

        self.assertNotIn("--clipboard", command)
        self.assertIn("Review readiness.", command)

    def test_prepare_closes_when_prompt_generation_fails(self):
        stdout = StringIO()
        results = [
            completed("Current state: full_agent_session_open\n"),
            completed("Public health: stable preflight_passed=3/3\n"),
            completed("Clipboard: failed\n", returncode=1),
            completed("Current state: full_agent_session_closed\n"),
            completed("Current state: full_agent_session_closed\nPublic health: skipped_session_not_open\n", returncode=1),
        ]

        with mock.patch.object(flow, "run_command", side_effect=results) as run:
            with redirect_stdout(stdout):
                status = flow.main(
                    [
                        "prepare",
                        "--allowed-root",
                        "/tmp/example-project",
                        "--public-base-url",
                        "https://example.test",
                        "--advisor-channel",
                        "user-web",
                        "--advisor-health",
                        "ready",
                        "Review readiness.",
                    ]
                )

        self.assertEqual(status, 1)
        self.assertEqual(run.call_count, 5)
        output = stdout.getvalue()
        self.assertIn("prompt generation failed; closing the Connected Agent window", output)
        self.assertIn("Close verification:", output)
        self.assertIn("GPT Pro has not been consulted yet", output)

    def test_capture_saves_advice_and_refreshes_idle_window_by_default(self):
        stdout = StringIO()
        results = [
            completed("Current state: review_only\nCaptured advice.\n"),
            completed("Current state: full_agent_session_touched\nRisk coefficient while open: 3/5-5/5\n"),
        ]

        with mock.patch.object(flow.sys, "stdin", StringIO("Adopt: keep user-web.\n")):
            with mock.patch.object(flow, "run_command", side_effect=results) as run:
                with redirect_stdout(stdout):
                    status = flow.main(
                        [
                            "capture",
                            "--advisor",
                            "ChatGPT Web",
                            "--source-channel",
                            "user-web",
                            "--run-id",
                            "level3-final-round",
                            "Review Level 3 maturity.",
                        ]
                    )

        self.assertEqual(status, 0)
        self.assertEqual(run.call_count, 2)
        capture_call = run.call_args_list[0]
        capture_command = capture_call.args[0]
        self.assertIn(str(flow.LEVEL3_CAPTURE), capture_command)
        self.assertIn("Review Level 3 maturity.", capture_command)
        self.assertEqual(capture_call.kwargs["input_text"], "Adopt: keep user-web.\n")
        output = stdout.getvalue()
        self.assertIn("Current state: connected_agent_flow_review_ready", output)
        self.assertIn("Idle window refresh:", output)
        self.assertIn("Risk after capture: 3/5-5/5 until idle shutdown closes the session", output)
        self.assertIn("Idle shutdown: 1200 seconds after last Connected Agent use", output)
        self.assertIn("Next step: classify captured advice", output)

    def test_capture_can_close_immediately_when_explicitly_requested(self):
        stdout = StringIO()
        results = [
            completed("Current state: review_only\nCaptured advice.\n"),
            completed("Current state: full_agent_session_closed\n"),
            completed("Current state: full_agent_session_closed\nPublic health: skipped_session_not_open\n", returncode=1),
        ]

        with mock.patch.object(flow.sys, "stdin", StringIO("Adopt: keep user-web.\n")):
            with mock.patch.object(flow, "run_command", side_effect=results) as run:
                with redirect_stdout(stdout):
                    status = flow.main(
                        [
                            "capture",
                            "--advisor",
                            "ChatGPT Web",
                            "--source-channel",
                            "user-web",
                            "--close-after-capture",
                            "Review Level 3 maturity.",
                        ]
                    )

        self.assertEqual(status, 0)
        self.assertEqual(run.call_count, 3)
        output = stdout.getvalue()
        self.assertIn("--close-after-capture was set", output)
        self.assertIn("Risk after close: 2/5", output)

    def test_capture_refreshes_idle_window_even_when_capture_fails(self):
        stdout = StringIO()
        results = [
            completed("", returncode=1),
            completed("Current state: full_agent_session_touched\nRisk coefficient while open: 3/5-5/5\n"),
        ]

        with mock.patch.object(flow.sys, "stdin", StringIO("")):
            with mock.patch.object(flow, "run_command", side_effect=results) as run:
                with redirect_stdout(stdout):
                    status = flow.main(
                        [
                            "capture",
                            "--advisor",
                            "ChatGPT Web",
                            "--source-channel",
                            "user-web",
                            "Review Level 3 maturity.",
                        ]
                    )

        self.assertEqual(status, 1)
        self.assertEqual(run.call_count, 2)
        output = stdout.getvalue()
        self.assertIn("Idle window refresh:", output)
        self.assertIn("Reason: advice capture failed", output)


if __name__ == "__main__":
    unittest.main()
