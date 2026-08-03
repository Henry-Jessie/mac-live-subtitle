import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.translator import Translator


class TranslatorTests(unittest.TestCase):
    def test_provider_errors_propagate_to_pipeline(self):
        with (
            patch("core.translator.httpx.Client"),
            patch("core.translator.OpenAI") as openai_class,
            patch("core.translator.tiktoken.get_encoding"),
        ):
            translator = Translator(
                api_key="translation-secret",
                base_url="https://api.example.test/v1",
                model="test-model",
            )

        openai_class.return_value.chat.completions.create.side_effect = (
            RuntimeError("provider unavailable")
        )

        with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
            translator.translate("hello")

        self.assertEqual(
            openai_class.call_args.kwargs["max_retries"],
            0,
        )

    def test_context_can_be_committed_after_scheduler_accepts_result(self):
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="你好")
                )
            ]
        )
        with (
            patch("core.translator.httpx.Client"),
            patch("core.translator.OpenAI") as openai_class,
            patch("core.translator.tiktoken.get_encoding") as encoding,
        ):
            encoding.return_value.encode.return_value = [1]
            openai_class.return_value.chat.completions.create.return_value = (
                response
            )
            translator = Translator(
                api_key="translation-secret",
                base_url="https://api.example.test/v1",
                model="test-model",
            )

        translated = translator.translate(
            "hello",
            record_context=False,
        )

        self.assertEqual(translated, "你好")
        self.assertEqual(list(translator._context_window), [])

        translator.commit_translation("hello", translated)

        self.assertEqual(
            list(translator._context_window),
            [("hello", "你好", 1)],
        )


if __name__ == "__main__":
    unittest.main()
