import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import prepare_consultation as consult


class PrepareConsultationTests(unittest.TestCase):
    def test_creates_auto_mcp_consultation_package(self):
        with tempfile.TemporaryDirectory() as tempdir:
            tasks_root = Path(tempdir) / "tasks"
            result = consult.create_consultation_task(
                tasks_root=tasks_root,
                question="Should we keep Auto MCP package-only?",
                mode="auto-mcp",
                task_id="auto-mcp-package-only-review",
                advisor_channel="unknown",
            )

            metadata = json.loads(result["metadata_path"].read_text(encoding="utf-8"))
            package = result["package_path"].read_text(encoding="utf-8")

        self.assertEqual(result["task_id"], "auto-mcp-package-only-review")
        self.assertEqual(metadata["status"], "package_ready")
        self.assertEqual(metadata["product_mode"], "auto-mcp")
        self.assertEqual(metadata["advisor_channel"], "unknown")
        self.assertEqual(metadata["language"], "en")
        self.assertIn("A prepared package does not mean the advisor has already been consulted.", package)
        self.assertIn("Should we keep Auto MCP package-only?", package)
        self.assertIn("Adopt / Adapt / Reject / Need info", package)
        self.assertIn("External advice only. This is not authorization.", package)

    def test_cli_defaults_to_ask_first_and_auto_language(self):
        args = consult.parse_args(["请咨询 GPT Pro"])

        self.assertEqual(args.mode, "ask-first")
        self.assertEqual(args.language, "auto")
        self.assertIsNone(args.advisor_channel)

    def test_main_defaults_ask_first_to_manual_channel(self):
        with tempfile.TemporaryDirectory() as tempdir:
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                exit_code = consult.main(
                    [
                        "--tasks-root",
                        str(Path(tempdir) / "tasks"),
                        "--task-id",
                        "default-ask-first",
                        "请咨询 GPT Pro",
                    ]
                )

        self.assertEqual(exit_code, 0)
        self.assertIn("Mode: ask-first", output.getvalue())
        self.assertIn("Advisor channel: manual", output.getvalue())
        self.assertIn("Language: zh", output.getvalue())
        self.assertIn("has not been consulted yet", output.getvalue())

    def test_cli_rejects_workspace_modes_that_do_not_create_packages(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                consult.parse_args(["--mode", "connected-agent", "Review this project."])

    def test_creates_chinese_ask_first_package_and_truthful_handoff(self):
        with tempfile.TemporaryDirectory() as tempdir:
            result = consult.create_consultation_task(
                tasks_root=Path(tempdir) / "tasks",
                question="这个 skill 还有哪里可以优化？",
                mode="ask-first",
                task_id="skill-review-zh",
                advisor_channel="manual",
            )
            metadata = json.loads(result["metadata_path"].read_text(encoding="utf-8"))
            package = result["package_path"].read_text(encoding="utf-8")
            status = consult.render_status(result)

        self.assertEqual(metadata["language"], "zh")
        self.assertIn("## 给外部模型的说明", package)
        self.assertIn("## 目标", package)
        self.assertIn("Adopt / Adapt / Reject / Need info", package)
        self.assertIn("The target advisor has not been consulted yet", status)
        self.assertIn("Upload or paste the complete package.md", status)
        self.assertIn("cannot resolve the local task id", status)

    def test_workspace_connector_modes_do_not_create_packages(self):
        with tempfile.TemporaryDirectory() as tempdir:
            for mode in ("connected-agent", "read-only-project", "full-agent"):
                with self.subTest(mode=mode):
                    with self.assertRaises(ValueError) as caught:
                        consult.create_consultation_task(
                            tasks_root=Path(tempdir) / "tasks",
                            question="Review the skill product architecture.",
                            mode=mode,
                            task_id=f"{mode}-product-review",
                            allowed_roots=[str(Path(tempdir) / "workspace")],
                            advisor_channel="user-web",
                        )
                    self.assertIn("does not create a decision package", str(caught.exception))

    def test_rejects_invalid_task_id(self):
        with tempfile.TemporaryDirectory() as tempdir:
            with self.assertRaises(ValueError):
                consult.create_consultation_task(
                    tasks_root=Path(tempdir) / "tasks",
                    question="Test",
                    mode="auto-mcp",
                    task_id="../escape",
                )

    def test_direct_tool_channel_does_not_emit_manual_prompt(self):
        with tempfile.TemporaryDirectory() as tempdir:
            result = consult.create_consultation_task(
                tasks_root=Path(tempdir) / "tasks",
                question="Test direct channel.",
                mode="auto-mcp",
                task_id="direct-channel-test",
                advisor_channel="direct-tool",
            )

            status = consult.render_status(result)

        self.assertIn("Advisor channel: direct-tool", status)
        self.assertNotIn("Advisor prompt:", status)


if __name__ == "__main__":
    unittest.main()
