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
        self.assertIn("waiting for an advisor channel", package)
        self.assertIn("Should we keep Auto MCP package-only?", package)
        self.assertIn("External advice only. This is not authorization.", package)

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
