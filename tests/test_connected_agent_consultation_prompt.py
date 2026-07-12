import sys
import unittest
from io import StringIO
from pathlib import Path
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts import connected_agent_consultation_prompt as prompt


class ConnectedAgentConsultationPromptTests(unittest.TestCase):
    def test_default_prompt_uses_self_directed_project_inspection(self):
        text = prompt.render_prompt(
            question="Review whether the skill is ready.",
            allowed_root="/tmp/example-project",
        )

        self.assertIn("Agent Decision Bridge Connected Agent", text)
        self.assertIn("deterministic workspace-open rule", text)
        self.assertIn("If open_default_workspace is visible", text)
        self.assertIn('call it exactly once with path "default"', text)
        self.assertIn("required legacy-schema compatibility path", text)
        self.assertIn("Never claim that a server change", text)
        self.assertIn("verify that the returned root", text)
        self.assertIn("Never guess or request a /Users/... path", text)
        self.assertNotIn("/tmp/example-project", text)
        self.assertIn("Use a chat mode where Apps/MCP connector tools are visible", text)
        self.assertIn("tool-capable ChatGPT mode", text)
        self.assertIn("Inspect only task-relevant project files", text)
        self.assertIn("ls, glob, grep, read, and read_lines", text)
        self.assertIn("skip node_modules, dist/build outputs", text)
        self.assertIn("read_lines for bounded 1-based line ranges", text)
        self.assertIn(".env and .env.* files", text)
        self.assertIn("token.json, credentials.json", text)
        self.assertNotIn("Read exactly these 3 files", text)
        self.assertNotIn("docs/security-public.md", text)
        self.assertNotIn("docs/security.md", text)
        self.assertNotIn("PROJECT_CONTEXT.md", text)
        self.assertIn("Do not use Python", text)
        self.assertIn("For any write, edit, or bash action", text)
        self.assertIn("Only call that tool after the user approves", text)
        self.assertIn("dangerously trust connected agent", text)
        self.assertIn("Only call enable_danger_auto if the user typed", text)
        self.assertIn("exactly which files were listed, searched, read, denied, or failed", text)
        self.assertIn("Danger Auto is 5/5", text)

    def test_explicit_file_prompt_uses_exact_file_list(self):
        text = prompt.render_prompt(
            question="Review these files.",
            allowed_root="/tmp/example-project",
            files=["README.md", "docs/security-public.md"],
        )

        self.assertIn("Read exactly these 2 files", text)
        self.assertIn("README.md", text)
        self.assertIn("docs/security-public.md", text)

    def test_deep_prompt_includes_larger_review_set(self):
        text = prompt.render_prompt(
            question="Review deeply.",
            allowed_root="/tmp/example-project",
            files=prompt.DEEP_REVIEW_FILES,
        )

        self.assertIn("Read exactly these 5 files", text)
        self.assertIn("PROJECT_CONTEXT.md", text)
        self.assertIn("docs/architecture.md", text)

    def test_rejects_sensitive_file_requests(self):
        for path in (
            ".env",
            ".env.local",
            ".git/config",
            ".ssh/id_rsa",
            "config/token.json",
            "config/credentials.json",
            "cert.pem",
            "../README.md",
        ):
            with self.subTest(path=path):
                with self.assertRaises(ValueError):
                    prompt.render_prompt(
                        question="Review",
                        allowed_root="/tmp/example-project",
                        files=[path],
                    )

    def test_allows_noncredential_token_named_source_files(self):
        text = prompt.render_prompt(
            question="Review",
            allowed_root="/tmp/example-project",
            files=["src/tokenizer.py", "config/auth-token.json"],
        )

        self.assertIn("src/tokenizer.py", text)
        self.assertIn("config/auth-token.json", text)

    def test_copy_to_clipboard_uses_pbcopy_without_printing_secret_values(self):
        completed = mock.Mock(returncode=0)

        with mock.patch.object(prompt.shutil, "which", return_value="/usr/bin/pbcopy"):
            with mock.patch.object(prompt.subprocess, "run", return_value=completed) as run:
                prompt.copy_to_clipboard("safe prompt")

        run.assert_called_once_with(["pbcopy"], input="safe prompt", text=True)

    def test_copy_to_clipboard_reports_missing_pbcopy(self):
        with mock.patch.object(prompt.shutil, "which", return_value=None):
            with self.assertRaisesRegex(RuntimeError, "pbcopy is not available"):
                prompt.copy_to_clipboard("safe prompt")

    def test_main_prints_prompt_even_when_clipboard_fails(self):
        stdout = StringIO()
        stderr = StringIO()

        with mock.patch.object(prompt, "copy_to_clipboard", side_effect=RuntimeError("no clipboard")):
            with redirect_stdout(stdout), redirect_stderr(stderr):
                status = prompt.main([
                    "--allowed-root",
                    "/tmp/example-project",
                    "--clipboard",
                    "Review",
                ])

        self.assertEqual(status, 1)
        self.assertIn("Clipboard: failed (no clipboard)", stderr.getvalue())
        self.assertIn("Prompt:", stdout.getvalue())
        self.assertIn("Inspect only task-relevant project files", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
