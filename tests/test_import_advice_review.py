import shutil
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import import_advice_review as review


FIXTURE_TASK = ROOT / "decision-inbox" / "tasks" / "phase-1-package-only-mcp-review"


class ImportAdviceReviewTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.tasks_root = Path(self.tempdir.name) / "tasks"
        self.tasks_root.mkdir()
        shutil.copytree(FIXTURE_TASK, self.tasks_root / "phase-1-package-only-mcp-review")
        for path in (
            self.tasks_root / "phase-1-package-only-mcp-review" / "advice"
        ).glob("*.md"):
            path.unlink()

    def tearDown(self):
        self.tempdir.cleanup()

    def test_finds_latest_advice_file(self):
        advice_dir = self.tasks_root / "phase-1-package-only-mcp-review" / "advice"
        (advice_dir / "2026-06-18T10-00-00Z-chatgpt.md").write_text(
            "older", encoding="utf-8"
        )
        latest = advice_dir / "2026-06-18T10-01-00Z-chatgpt.md"
        latest.write_text("newer", encoding="utf-8")

        found = review.find_latest_advice(
            self.tasks_root, "phase-1-package-only-mcp-review"
        )

        self.assertEqual(found, latest)

    def test_missing_advice_raises_clear_error(self):
        with self.assertRaises(review.NoAdviceFound):
            review.find_latest_advice(self.tasks_root, "phase-1-package-only-mcp-review")

    def test_renders_review_only_import_gate(self):
        advice_dir = self.tasks_root / "phase-1-package-only-mcp-review" / "advice"
        advice_file = advice_dir / "2026-06-18T10-02-00Z-chatgpt.md"
        advice_file.write_text(
            "# Advisor Advice\n\nRecommendation: keep package-only v1.",
            encoding="utf-8",
        )

        rendered = review.render_import_review(
            self.tasks_root, "phase-1-package-only-mcp-review", advice_file
        )

        self.assertIn("Current state: review_only", rendered)
        self.assertIn("Risk status: needs_info", rendered)
        self.assertIn("File changes: none", rendered)
        self.assertIn("Commands run: read_only_only", rendered)
        self.assertIn("Advisor rounds used: 1", rendered)
        self.assertIn("Decision loop recommendation: need_local_fact_check", rendered)
        self.assertIn("Recommendation: keep package-only v1.", rendered)
        self.assertIn("| External recommendation | Local fact check | Decision |", rendered)
        self.assertIn("Advisor output is not authorization", rendered)


if __name__ == "__main__":
    unittest.main()
