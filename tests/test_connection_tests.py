import unittest
from types import SimpleNamespace
from unittest.mock import patch

from core.connection_tests import test_translation_connection


class ConnectionTests(unittest.TestCase):
    @patch("core.connection_tests.OpenAI")
    @patch("core.connection_tests.httpx.Client")
    def test_translation_test_uses_runtime_thinking_settings(
        self,
        http_client_class,
        openai_class,
    ):
        response = SimpleNamespace(
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content="你好")
                )
            ]
        )
        openai_class.return_value.chat.completions.create.return_value = (
            response
        )
        extra_body = {"custom": "value"}

        result = test_translation_connection(
            base_url="https://api.example.test/v1",
            api_key="secret",
            model="test-model",
            target_lang="Chinese",
            extra_body=extra_body,
            thinking=False,
        )

        self.assertEqual(result, "你好")
        request = (
            openai_class.return_value.chat.completions.create.call_args.kwargs
        )
        self.assertEqual(request["max_tokens"], 500)
        self.assertEqual(
            request["extra_body"],
            {
                "custom": "value",
                "thinking": {"type": "disabled"},
            },
        )
        self.assertEqual(extra_body, {"custom": "value"})
        http_client_class.return_value.close.assert_called_once_with()

    @patch("core.connection_tests.OpenAI")
    @patch("core.connection_tests.httpx.Client")
    def test_translation_test_omits_default_thinking(
        self,
        _http_client_class,
        openai_class,
    ):
        openai_class.return_value.chat.completions.create.return_value = (
            SimpleNamespace(
                choices=[
                    SimpleNamespace(
                        message=SimpleNamespace(content="你好")
                    )
                ]
            )
        )

        test_translation_connection(
            base_url="https://api.example.test/v1",
            api_key="secret",
            model="test-model",
            target_lang="Chinese",
            extra_body=None,
            thinking=None,
        )

        request = (
            openai_class.return_value.chat.completions.create.call_args.kwargs
        )
        self.assertNotIn("extra_body", request)


if __name__ == "__main__":
    unittest.main()
