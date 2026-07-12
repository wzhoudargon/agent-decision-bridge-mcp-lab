import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GOLDEN_CASES = ROOT / "tests" / "fixtures" / "agent_decision_bridge_golden_cases.json"
CURRENT_PRODUCT_FILES = (
    ROOT / "README.md",
    ROOT / "docs" / "user-guide.md",
    ROOT / "docs" / "connected-agent-user-flow.md",
    ROOT / "docs" / "conversation-product-mode.md",
    ROOT / "docs" / "security-public.md",
    ROOT / "docs" / "architecture.md",
    ROOT / "docs" / "plan.md",
    ROOT / "docs" / "connector-runbook.md",
    ROOT / "scripts" / "connected_agent_consultation_prompt.py",
    ROOT / "scripts" / "connected_agent_consultation_flow.py",
    ROOT / "scripts" / "connected_agent_capture_advice.py",
    ROOT / "scripts" / "prepare_consultation.py",
)


class ProductContractConsistencyTests(unittest.TestCase):
    def test_current_product_copy_does_not_use_three_state_import_taxonomy(self):
        combined = "\n".join(path.read_text(encoding="utf-8") for path in CURRENT_PRODUCT_FILES)

        self.assertNotIn("Adopt / Ask / Reject", combined)
        self.assertNotIn("`Adopt`, `Ask`, or `Reject`", combined)
        self.assertIn("Adopt / Adapt / Reject / Need info", combined)

    def test_golden_cases_use_canonical_state_domains(self):
        cases = json.loads(GOLDEN_CASES.read_text(encoding="utf-8"))
        ids = [case["id"] for case in cases]

        self.assertEqual(len(cases), 8)
        self.assertEqual(len(ids), len(set(ids)))

        allowed_workflows = {"ask-first", "connected-agent", "import", "auto-mcp-compatibility"}
        allowed_channels = {"manual", "user-web", "browser-automation", "direct-tool", "unknown"}
        forbidden_flat_states = {"waiting_for_agent", "ready_to_execute"}

        for case in cases:
            with self.subTest(case=case["id"]):
                expected = case["expected"]
                self.assertIn(expected["workflow"], allowed_workflows)
                self.assertIn(expected["advisor_channel"], allowed_channels)
                self.assertNotIn(expected["state"], forbidden_flat_states)
                self.assertFalse(expected["side_effects_allowed"])

    def test_first_tier_cases_create_packages_without_claiming_consultation(self):
        cases = json.loads(GOLDEN_CASES.read_text(encoding="utf-8"))
        ask_first = [case for case in cases if case["expected"]["workflow"] == "ask-first"]

        self.assertGreaterEqual(len(ask_first), 2)
        for case in ask_first:
            with self.subTest(case=case["id"]):
                expected = case["expected"]
                self.assertEqual(expected["state"], "consultation_package_ready")
                self.assertTrue(expected["create_package"])
                self.assertEqual(expected["risk"], "1/5")


if __name__ == "__main__":
    unittest.main()
