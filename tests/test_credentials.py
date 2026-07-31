import json
import tempfile
import unittest
from pathlib import Path

from core.credentials import CredentialStore


class CredentialStoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.path = (
            Path(self.temporary_directory.name)
            / "Mac Live Subtitle"
            / "credentials.json"
        )
        self.store = CredentialStore(self.path)

    def tearDown(self):
        self.temporary_directory.cleanup()

    def test_saves_reads_and_deletes_provider_keys(self):
        self.store.save("asr.dashscope", "  asr-secret  ")
        self.store.save("translation.deepseek", "translation-secret")

        self.assertTrue(self.store.exists("asr.dashscope"))
        self.assertEqual(self.store.get("asr.dashscope"), "asr-secret")
        self.assertEqual(
            self.store.get("translation.deepseek"),
            "translation-secret",
        )
        self.assertEqual(
            json.loads(self.path.read_text(encoding="utf-8")),
            {
                "asr.dashscope": "asr-secret",
                "translation.deepseek": "translation-secret",
            },
        )
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.path.parent.stat().st_mode & 0o777, 0o700)

        self.store.delete("asr.dashscope")

        self.assertFalse(self.store.exists("asr.dashscope"))
        self.assertIsNone(self.store.get("asr.dashscope"))
        self.assertEqual(
            self.store.get("translation.deepseek"),
            "translation-secret",
        )

    def test_rejects_invalid_file_structure(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("[]", encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "Invalid credentials file"):
            self.store.get("asr.dashscope")


if __name__ == "__main__":
    unittest.main()
