from openai import OpenAI
from collections import deque
import httpx
import re
import threading
import tiktoken

from core.urls import is_local_url

class Translator:
    def __init__(self, api_key=None, base_url=None, model="MBZUAI-IFM/K2-Think-nothink", target_lang="Chinese", extra_body=None, temperature=1.0, debug=False, thinking=None):
        """
        Translates text using an LLM.
        
        Args:
            api_key: API key loaded from the app's local credential store.
            base_url: Optional base URL (e.g. for local generic server like Ollama/LMStudio).
            model: Model name to use.
            target_lang: The target language for translation.
            thinking: DeepSeek V4 thinking mode — True/False to send
                {"thinking": {"type": "enabled"/"disabled"}}, None to omit the field.
        """
        self.target_lang = target_lang
        self.model = model
        self.extra_body = extra_body if isinstance(extra_body, dict) else None
        self.temperature = float(temperature) if temperature is not None else 1.0
        self.thinking = thinking if thinking in (True, False) else None
        
        if not api_key:
            if is_local_url(base_url):
                api_key = "dummy-key-for-local"
            else:
                raise RuntimeError(
                    "Translation API key is not configured. "
                    "Open Settings → Translation and enter an API key."
                )

        self.base_url = base_url

        # Only disable SSL verification for local servers (Ollama, LM Studio, etc.)
        verify_ssl = not is_local_url(base_url)
        http_client = httpx.Client(verify=verify_ssl)
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
            http_client=http_client,
            max_retries=0,
        )
        
        # Logging
        print(f"[Translator] Initialized:")
        print(f"  - Base URL: {base_url or 'https://api.openai.com/v1 (default)'}")
        print(f"  - Model: {model}")
        print(f"  - Target Language: {target_lang}")
        print(f"  - API Key Configured: {'yes' if api_key else 'no'}")
        
        # Sliding context window for sentence continuity (source, translation) capped by tokens
        self._encoding = tiktoken.get_encoding("o200k_base")
        self._context_window = deque()  # (source, translation, token_count)
        self._context_window_tokens = 0
        self._context_lock = threading.Lock()


        # Static system prompts
        self._translate_system_prompt = (
            "You are a professional real-time translator.\n\n"
            "You will receive:\n"
            "- TARGET_LANG: the language to translate into\n"
            "- CONTEXT: previous translation pairs (formatted as Source/Translation lines) "
            "for terminology consistency, or (empty)\n"
            "- DRAFT: unconfirmed ASR draft that may follow TEXT for disambiguation, or (empty)\n"
            "- TEXT: the text to translate\n\n"
            "Rules:\n"
            "1. Translate ONLY the TEXT into TARGET_LANG.\n"
            "2. Use CONTEXT only for terminology consistency. Do NOT repeat it.\n"
            "3. Use DRAFT only for disambiguation. Do NOT translate or include it.\n"
            "4. If TEXT is already in TARGET_LANG, output it as-is.\n"
            "5. Output ONLY the translation, nothing else."
        )

        # Variant for interim translations of still-growing sentences:
        # same rules, plus an explicit incomplete-fragment note. Interim
        # translations are never written into the context window.
        self._translate_interim_system_prompt = (
            self._translate_system_prompt + "\n"
            "6. TEXT is an interim fragment of a still-growing live sentence and may be "
            "incomplete. Translate only what is present; do not guess or complete missing parts."
        )

        if debug:
            print(f"[Translator] translate system_prompt:\n{self._translate_system_prompt}")

    def _count_tokens(self, text):
        return len(self._encoding.encode(text))

    def _format_context_pair(self, source, translation):
        return f"Source: \"{source}\"\\nTranslation: \"{translation}\"\\n"

    def commit_translation(self, source, translation, max_tokens=500):
        with self._context_lock:
            formatted = self._format_context_pair(source, translation)
            token_count = self._count_tokens(formatted)

            self._context_window.append((source, translation, token_count))
            self._context_window_tokens += token_count

            while (
                self._context_window
                and self._context_window_tokens > max_tokens
            ):
                _, _, removed_tokens = self._context_window.popleft()
                self._context_window_tokens -= removed_tokens

    def _strip_thinking(self, text):
        """Remove <think>...</think> tags from response (for reasoning models)"""
        # Remove think tags and their content
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        return cleaned.strip()

    def _merged_extra_body(self):
        """extra_body for requests: user JSON merged with the thinking toggle
        (the dedicated `thinking` setting wins over a thinking key in extra_body)."""
        merged = dict(self.extra_body) if self.extra_body else {}
        if self.thinking is not None:
            merged["thinking"] = {"type": "enabled" if self.thinking else "disabled"}
        return merged or None

    def _trim_for_log(self, text: str, max_len: int = 900) -> str:
        s = (text or "").replace("\n", "\\n")
        if len(s) <= max_len:
            return s
        return s[:max_len] + f"…(+{len(s) - max_len} chars)"

    def translate(
        self,
        text,
        use_context=True,
        *,
        trailing_context: str | None = None,
        debug: bool = False,
        interim: bool = False,
        record_context: bool = True,
    ):
        """
        Translates the given text. Returns the translated string.
        Uses previous transcription as context for better continuity.
        When interim=True, TEXT is a still-growing fragment: a special system
        prompt is used and the result is NOT written into the context window.
        Schedulers pass record_context=False and commit accepted final results
        after enforcing their deadline and ordering rules.
        """
        if not text or not text.strip():
            return ""

        # Build user prompt with fixed skeleton
        context_lines = ""
        with self._context_lock:
            context_window = list(self._context_window)
        if use_context and context_window:
            context_lines = "".join(
                self._format_context_pair(source, translation)
                for source, translation, _ in context_window
            ).strip()

        trailing_norm = ""
        if trailing_context and str(trailing_context).strip():
            trailing_norm = " ".join(str(trailing_context).strip().split())
            if len(trailing_norm) > 900:
                trailing_norm = trailing_norm[:900] + "…"

        user_prompt = (
            f"TARGET_LANG: {self.target_lang}\n"
            f"CONTEXT:\n{context_lines or '(empty)'}\n"
            f"DRAFT:\n{trailing_norm or '(empty)'}\n"
            f"TEXT:\n{text}"
        )

        if debug:
            print(f"[Translator] translate use_context={use_context} model={self.model}")
            print(f"[Translator] translate user_prompt={self._trim_for_log(user_prompt)}")

        create_kwargs = dict(
            model=self.model,
            messages=[
                {"role": "system", "content": self._translate_interim_system_prompt if interim else self._translate_system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=self.temperature,
            max_tokens=500,
            timeout=10.0,
        )
        extra_body = self._merged_extra_body()
        if extra_body:
            create_kwargs["extra_body"] = extra_body
        response = self.client.chat.completions.create(**create_kwargs)
        raw_result = response.choices[0].message.content.strip()
        if debug:
            print(f"[Translator] translate raw_result={self._trim_for_log(raw_result)}")
        # Strip thinking tags if present
        result = self._strip_thinking(raw_result)

        if debug:
            print(f"[Translator] translate normalized={self._trim_for_log(result)}")

        if not interim and record_context:
            self.commit_translation(text, result)

        return result
