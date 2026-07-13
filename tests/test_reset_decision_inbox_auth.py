import tempfile
import unittest
from pathlib import Path
from unittest import mock


from scripts import reset_decision_inbox_auth as reset_auth


class ResetDecisionInboxAuthTests(unittest.TestCase):
    def test_remove_path_deletes_file_without_reading_it(self):
        with tempfile.TemporaryDirectory() as tempdir:
            target = Path(tempdir) / "oauth-state.json"
            target.write_text("secret-token-value", encoding="utf-8")

            status = reset_auth.remove_path(target)

            self.assertEqual(status, "removed")
            self.assertFalse(target.exists())

    def test_remove_path_refuses_directory(self):
        with tempfile.TemporaryDirectory() as tempdir:
            target = Path(tempdir)

            status = reset_auth.remove_path(target)

            self.assertEqual(status, "refused_directory")
            self.assertTrue(target.exists())

    def test_connected_agent_defaults_removes_connected_agent_files(self):
        with tempfile.TemporaryDirectory() as tempdir:
            state_file = Path(tempdir) / "oauth-state.json"
            owner_file = Path(tempdir) / "oauth-owner-token"
            state_file.write_text("state", encoding="utf-8")
            owner_file.write_text("owner", encoding="utf-8")
            with mock.patch.object(reset_auth, "DEFAULT_CONNECTED_AGENT_STATE_FILE", state_file):
                with mock.patch.object(
                    reset_auth,
                    "DEFAULT_CONNECTED_AGENT_OWNER_TOKEN_FILE",
                    owner_file,
                ):
                    reset_auth.main(["--connected-agent-defaults"])

            self.assertFalse(state_file.exists())
            self.assertFalse(owner_file.exists())

    def test_legacy_full_agent_defaults_flag_still_works(self):
        with tempfile.TemporaryDirectory() as tempdir:
            state_file = Path(tempdir) / "oauth-state.json"
            owner_file = Path(tempdir) / "oauth-owner-token"
            state_file.write_text("state", encoding="utf-8")
            owner_file.write_text("owner", encoding="utf-8")
            with mock.patch.object(reset_auth, "DEFAULT_CONNECTED_AGENT_STATE_FILE", state_file):
                with mock.patch.object(
                    reset_auth,
                    "DEFAULT_CONNECTED_AGENT_OWNER_TOKEN_FILE",
                    owner_file,
                ):
                    reset_auth.main(["--full-agent-defaults"])

            self.assertFalse(state_file.exists())
            self.assertFalse(owner_file.exists())


if __name__ == "__main__":
    unittest.main()
