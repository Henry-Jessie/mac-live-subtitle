import re

import httpx
import websocket
from openai import OpenAI

from core.urls import is_local_url


def test_funasr_connection(url: str, api_key: str) -> str:
    connection = websocket.create_connection(
        url,
        header=[f"Authorization: Bearer {api_key}"],
        timeout=10,
    )
    connection.close()
    return "API key accepted"


def test_translation_connection(
    *,
    base_url: str | None,
    api_key: str,
    model: str,
    target_lang: str,
    extra_body: dict | None,
    thinking: bool | None,
) -> str:
    http_client = httpx.Client(
        timeout=10,
        verify=not is_local_url(base_url),
    )
    try:
        client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=http_client,
        )
        request_extra_body = dict(extra_body) if extra_body else {}
        if thinking is not None:
            request_extra_body["thinking"] = {
                "type": "enabled" if thinking else "disabled"
            }
        create_kwargs = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Translate the user text into "
                        f"{target_lang}. Output only the translation."
                    ),
                },
                {
                    "role": "user",
                    "content": "Hello. This is a translation test.",
                },
            ],
            "temperature": 0,
            "max_tokens": 500,
            "timeout": 10.0,
        }
        if request_extra_body:
            create_kwargs["extra_body"] = request_extra_body
        response = client.chat.completions.create(**create_kwargs)
        text = (response.choices[0].message.content or "").strip()
        text = re.sub(
            r"<think>.*?</think>",
            "",
            text,
            flags=re.DOTALL,
        ).strip()
        if not text:
            raise RuntimeError("Empty response")
        return text
    finally:
        http_client.close()
