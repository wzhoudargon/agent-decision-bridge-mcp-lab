import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from server import decision_inbox_store as store


FIXTURE_TASK = ROOT / "decision-inbox" / "tasks" / "phase-1-package-only-mcp-review"


class DecisionInboxStoreTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.tasks_root = Path(self.tempdir.name) / "tasks"
        self.tasks_root.mkdir()
        shutil.copytree(FIXTURE_TASK, self.tasks_root / "phase-1-package-only-mcp-review")
        shutil.copytree(FIXTURE_TASK, self.tasks_root / "_template")
        self._clear_generated_markdown("phase-1-package-only-mcp-review")
        self._clear_generated_markdown("_template")
        self.inbox = store.DecisionInboxStore(self.tasks_root)

    def tearDown(self):
        self.tempdir.cleanup()

    def _clear_generated_markdown(self, task_id):
        task_dir = self.tasks_root / task_id
        for folder in ("advice", "fact-check-requests"):
            for path in (task_dir / folder).glob("*.md"):
                path.unlink()

    def test_lists_package_ready_tasks_and_skips_templates(self):
        tasks = self.inbox.list_decision_tasks()

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0]["task_id"], "phase-1-package-only-mcp-review")
        self.assertEqual(tasks[0]["status"], "package_ready")
        self.assertEqual(tasks[0]["advisor_rounds"], 0)

    def test_reads_decision_package(self):
        package = self.inbox.get_decision_package("phase-1-package-only-mcp-review")

        self.assertIn("Package-only Decision Inbox MCP v1 Review Package", package)
        self.assertIn("Advisor output is not user authorization", package)

    def test_get_task_status_counts_advice_and_fact_check_requests(self):
        task_dir = self.tasks_root / "phase-1-package-only-mcp-review"
        (task_dir / "advice" / "2026-06-18T10-00-00Z-chatgpt.md").write_text(
            "advice", encoding="utf-8"
        )
        (task_dir / "fact-check-requests" / "2026-06-18T10-01-00Z.md").write_text(
            "check", encoding="utf-8"
        )

        status = self.inbox.get_task_status("phase-1-package-only-mcp-review")

        self.assertEqual(status["task_id"], "phase-1-package-only-mcp-review")
        self.assertEqual(status["advice_count"], 1)
        self.assertEqual(status["fact_check_request_count"], 1)
        self.assertEqual(status["status"], "package_ready")

    def test_submit_advice_creates_markdown_under_advice_only(self):
        result = self.inbox.submit_advice(
            task_id="phase-1-package-only-mcp-review",
            advisor="ChatGPT Web",
            content=(
                "# Recommendation\n\nStay package-only.\n\n"
                "External advice only. This is not authorization."
            ),
            timestamp="2026-06-18T10-02-00Z",
        )

        self.assertEqual(
            result["relative_path"],
            "phase-1-package-only-mcp-review/advice/2026-06-18T10-02-00Z-chatgpt-web.md",
        )
        self.assertEqual(result["task_id"], "phase-1-package-only-mcp-review")
        self.assertEqual(result["advisor"], "ChatGPT Web")
        self.assertEqual(result["timestamp"], "2026-06-18T10-02-00Z")
        self.assertEqual(result["not_authorization"], "required_marker_present")
        written = self.tasks_root / result["relative_path"]
        self.assertIn("This is not authorization", written.read_text(encoding="utf-8"))
        self.assertTrue((self.tasks_root / "phase-1-package-only-mcp-review" / "package.md").exists())
        self.assertTrue((self.tasks_root / "phase-1-package-only-mcp-review" / "metadata.json").exists())

    def test_submit_advice_rejects_missing_not_authorization_marker(self):
        with self.assertRaises(ValueError):
            self.inbox.submit_advice(
                task_id="phase-1-package-only-mcp-review",
                advisor="ChatGPT Web",
                content="# Recommendation\n\nStay package-only.",
                timestamp="2026-06-18T10-02-01Z",
            )

    def test_submit_advice_rejects_blank_advisor(self):
        with self.assertRaises(ValueError):
            self.inbox.submit_advice(
                task_id="phase-1-package-only-mcp-review",
                advisor=" ",
                content="External advice only. This is not authorization.",
                timestamp="2026-06-18T10-02-02Z",
            )

    def test_request_local_fact_check_creates_markdown_under_fact_check_requests_only(self):
        result = self.inbox.request_local_fact_check(
            task_id="phase-1-package-only-mcp-review",
            content="Please confirm whether package.md exists.",
            timestamp="2026-06-18T10-03-00Z",
        )

        self.assertEqual(
            result["relative_path"],
            "phase-1-package-only-mcp-review/fact-check-requests/2026-06-18T10-03-00Z.md",
        )
        written = self.tasks_root / result["relative_path"]
        self.assertEqual(written.read_text(encoding="utf-8"), "Please confirm whether package.md exists.")

    def test_rejects_invalid_task_ids(self):
        invalid_ids = [
            "../phase-1-package-only-mcp-review",
            "/tmp/task",
            ".hidden",
            "_template",
            "Phase One",
            "phase/one",
            "phase.one",
        ]

        for task_id in invalid_ids:
            with self.subTest(task_id=task_id):
                with self.assertRaises(store.AccessDenied):
                    self.inbox.get_decision_package(task_id)

    def test_rejects_missing_task(self):
        with self.assertRaises(store.TaskNotFound):
            self.inbox.get_decision_package("missing-task")

    def test_submit_advice_uses_exclusive_create_and_does_not_overwrite(self):
        self.inbox.submit_advice(
            task_id="phase-1-package-only-mcp-review",
            advisor="ChatGPT",
            content="first. External advice only. This is not authorization.",
            timestamp="2026-06-18T10-04-00Z",
        )

        with self.assertRaises(FileExistsError):
            self.inbox.submit_advice(
                task_id="phase-1-package-only-mcp-review",
                advisor="ChatGPT",
                content="second. External advice only. This is not authorization.",
                timestamp="2026-06-18T10-04-00Z",
            )

    def test_metadata_must_match_task_id(self):
        task_dir = self.tasks_root / "phase-1-package-only-mcp-review"
        metadata = json.loads((task_dir / "metadata.json").read_text(encoding="utf-8"))
        metadata["task_id"] = "different-task"
        (task_dir / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

        with self.assertRaises(store.MetadataError):
            self.inbox.get_task_status("phase-1-package-only-mcp-review")


if __name__ == "__main__":
    unittest.main()
