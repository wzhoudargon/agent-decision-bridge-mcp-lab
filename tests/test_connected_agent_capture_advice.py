import argparse
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import connected_agent_capture_advice as capture


class ConnectedAgentCaptureAdviceTests(unittest.TestCase):
    def make_args(self, tempdir: str, **overrides):
        defaults = {
            "question": "Should Connected Agent be considered ready?",
            "advisor": "ChatGPT Web",
            "source_channel": "user-web",
            "run_id": "connected-agent-product-review",
            "timestamp": "2026-06-24T08-10-00Z",
            "advice_file": None,
            "consultations_root": Path(tempdir) / "connected-agent-consultations",
        }
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_capture_saves_advice_and_renders_review_gate(self):
        with tempfile.TemporaryDirectory() as tempdir:
            advice_file = Path(tempdir) / "advice.md"
            advice_file.write_text(
                "Adopt: keep compact prompt.\nAdapt: improve status.\nReject: call it low risk.",
                encoding="utf-8",
            )
            args = self.make_args(tempdir, advice_file=advice_file)

            captured = capture.capture_advice(args)
            rendered = capture.render_review(captured)

            self.assertEqual(captured["run_id"], "connected-agent-product-review")
            self.assertEqual(captured["advisor_rounds"], "1")
            self.assertTrue(captured["advice_path"].is_file())
        self.assertIn("Current state: review_only", rendered)
        self.assertIn("File changes: executed (captured external advice only", rendered)
        self.assertIn("External advice is not authorization", rendered)
        self.assertIn("Adopt: keep compact prompt", rendered)

    def test_capture_counts_second_round_as_two_plus(self):
        with tempfile.TemporaryDirectory() as tempdir:
            first_file = Path(tempdir) / "first.md"
            second_file = Path(tempdir) / "second.md"
            first_file.write_text("First advice.", encoding="utf-8")
            second_file.write_text("Second advice.", encoding="utf-8")

            first = capture.capture_advice(
                self.make_args(
                    tempdir,
                    timestamp="2026-06-24T08-10-00Z",
                    advice_file=first_file,
                )
            )
            second = capture.capture_advice(
                self.make_args(
                    tempdir,
                    timestamp="2026-06-24T08-11-00Z",
                    advice_file=second_file,
                )
            )

            self.assertEqual(first["advisor_rounds"], "1")
            self.assertEqual(second["advisor_rounds"], "2+")
            self.assertTrue(second["advice_path"].is_file())

    def test_capture_refuses_obvious_secret_material(self):
        with tempfile.TemporaryDirectory() as tempdir:
            advice_file = Path(tempdir) / "advice.md"
            fake_api_key = "OPENAI_API_KEY=" + "sk-" + "abcdefghijklmnopqrstuvwxyz"
            advice_file.write_text(
                f"Here is a leaked token: {fake_api_key}",
                encoding="utf-8",
            )
            args = self.make_args(tempdir, advice_file=advice_file)

            with self.assertRaises(ValueError) as raised:
                capture.capture_advice(args)

        self.assertIn("secret material", str(raised.exception))

    def test_invalid_timestamp_is_rejected(self):
        with self.assertRaises(ValueError):
            capture.validate_timestamp("2026-06-24T08:10:00Z")


if __name__ == "__main__":
    unittest.main()
