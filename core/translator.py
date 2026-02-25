from openai import OpenAI, OpenAIError
from collections import deque
import httpx
import os
import re
import tiktoken
import json
import json_repair

class Translator:
    def __init__(self, api_key=None, base_url=None, model="MBZUAI-IFM/K2-Think-nothink", target_lang="Chinese", extra_body=None, temperature=1.0, debug=False):
        """
        Translates text using an LLM.
        
        Args:
            api_key: OpenAI API Key (or set OPENAI_API_KEY env var).
            base_url: Optional base URL (e.g. for local generic server like Ollama/LMStudio).
            model: Model name to use.
            target_lang: The target language for translation.
        """
        self.target_lang = target_lang
        self.model = model
        self.extra_body = extra_body if isinstance(extra_body, dict) else None
        self.temperature = float(temperature) if temperature is not None else 1.0
        
        # If no key provided, check env. If still none, we might be in local mode (no auth) or fail.
        # Some local servers don't need a valid key, but the client requires a string.
        if not api_key:
            api_key = os.getenv("OPENAI_API_KEY", "dummy-key-for-local")
            
        if not base_url:
            base_url = os.getenv("OPENAI_BASE_URL")

        self.base_url = base_url
        
        # Create HTTP client with SSL verification disabled (for self-signed certs)
        http_client = httpx.Client(verify=False)
        self.client = OpenAI(api_key=api_key, base_url=base_url, http_client=http_client)
        
        # Logging
        print(f"[Translator] Initialized:")
        print(f"  - Base URL: {base_url or 'https://api.openai.com/v1 (default)'}")
        print(f"  - Model: {model}")
        print(f"  - Target Language: {target_lang}")
        print(f"  - API Key: {api_key[:8]}...{api_key[-4:] if len(api_key) > 12 else '***'}")
        
        # Sliding context window for sentence continuity (source, translation) capped by tokens
        self._encoding = tiktoken.get_encoding("o200k_base")
        self._context_window = deque()  # (source, translation, token_count)
        self._context_window_tokens = 0

        # Backwards-compatible last pair
        self.previous_text = ""
        self.previous_translation = ""

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

        self._segment_system_prompt = (
            "You are a real-time subtitle segmenter and translator.\n\n"
            "You will receive:\n"
            "- TARGET_LANG: the language to translate into\n"
            "- TOKEN_COUNT: approximate token length of TEXT\n"
            "- TEXT: a growing transcript buffer from live speech recognition\n"
            "- CANDIDATES: ordered list of segments pre-split from TEXT by a heuristic algorithm\n"
            "- DRAFT: unconfirmed ASR draft that may follow TEXT (use ONLY for disambiguation)\n"
            "- CONTEXT: previous translation pairs for terminology consistency\n\n"
            "IMPORTANT: TEXT is a snapshot of an ongoing speech buffer. "
            "It may end mid-sentence. Any text you do NOT consume stays in the buffer "
            "and will be included in the next call with more words appended.\n\n"
            "Return ONLY valid JSON (no markdown fences, no explanation).\n\n"
            "Schema:\n"
            "{\n"
            "  \"completed\": [\n"
            "    { \"source\": \"...\", \"anchor\": \"...\", \"translation\": \"...\" }\n"
            "  ]\n"
            "}\n\n"
            "Rules:\n\n"
            "REVIEW — decide which candidates to emit:\n"
            "  CANDIDATES are proposed split points. Your job is to decide how many "
            "to emit from the front of the list (0, some, or all).\n"
            "  • Emit a candidate if it is a complete, self-contained unit.\n"
            "  • HOLD a candidate (do NOT emit) if DRAFT shows the candidate is "
            "incomplete. Example: candidate ends with \"2.\" and DRAFT starts with "
            "\"5 describes\" → \"2.\" is part of \"2.5\", hold it.\n"
            "  • You may MERGE adjacent candidates into one `completed` item if they "
            "form a single short sentence (keep subtitle readability).\n"
            "  • If CANDIDATES is empty, fall back to scanning TEXT directly "
            "(still use DRAFT for disambiguation):\n"
            "    - Emit up to the last sentence-ending punctuation (.!?。！？).\n"
            "    - If none and TOKEN_COUNT > 18, emit up to the last clause punctuation.\n"
            "    - Otherwise return {\"completed\": []}.\n\n"
            "HARD CONSTRAINTS:\n"
            "  • NEVER translate, consume, or include any part of DRAFT in source or translation.\n"
            "  • NEVER rewrite, rephrase, or insert/remove characters in source — copy verbatim from TEXT.\n"
            "  • completed items must consume TEXT from the beginning in order, with no gaps.\n\n"
            "COPYING — how to fill each item:\n"
            "  1. `source`: copied character-for-character from TEXT.\n"
            "  2. `anchor`: the last 5-8 words of `source`, copied verbatim.\n"
            "  3. `translation`: natural TARGET_LANG subtitle for that `source` segment. "
            "If source language == TARGET_LANG, copy `source` verbatim.\n\n"
            "EXAMPLES:\n\n"
            "CANDIDATES: [\"The company was founded in 2005.\", \"It later acquired\"]\n"
            "DRAFT: \"several startups in\"\n"
            "→ emit candidate 1 only. Candidate 2 is incomplete (DRAFT continues it).\n\n"
            "CANDIDATES: [\"Section 2.\"]\n"
            "DRAFT: \"5 describes the memory\"\n"
            "→ {\"completed\": []}  // \"2.\" + DRAFT \"5...\" = \"2.5\", hold.\n\n"
            "CANDIDATES: [\"Yes.\", \"I agree.\"]\n"
            "DRAFT: \"\"\n"
            "→ merge into one item: source=\"Yes. I agree.\"\n"
        )

        if debug:
            print(f"[Translator] translate system_prompt:\n{self._translate_system_prompt}")
            print(f"[Translator] segment_and_translate system_prompt:\n{self._segment_system_prompt}")

    def _count_tokens(self, text):
        return len(self._encoding.encode(text))

    def _format_context_pair(self, source, translation):
        return f"Source: \"{source}\"\\nTranslation: \"{translation}\"\\n"

    def _append_context_pair(self, source, translation, max_tokens=500):
        formatted = self._format_context_pair(source, translation)
        token_count = self._count_tokens(formatted)

        self._context_window.append((source, translation, token_count))
        self._context_window_tokens += token_count

        while self._context_window and self._context_window_tokens > max_tokens:
            _, _, removed_tokens = self._context_window.popleft()
            self._context_window_tokens -= removed_tokens

    def _strip_thinking(self, text):
        """Remove <think>...</think> tags from response (for reasoning models)"""
        # Remove think tags and their content
        cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        return cleaned.strip()

    def _trim_for_log(self, text: str, max_len: int = 900) -> str:
        s = (text or "").replace("\n", "\\n")
        if len(s) <= max_len:
            return s
        return s[:max_len] + f"…(+{len(s) - max_len} chars)"

    def _dump_for_log(self, data, max_len: int = 1400) -> str:
        try:
            return self._trim_for_log(json.dumps(data, ensure_ascii=False), max_len=max_len)
        except Exception:
            return self._trim_for_log(str(data), max_len=max_len)

    def segment_and_translate(
        self,
        text,
        *,
        token_count: int,
        candidates: list[str] | None = None,
        draft_continuation: str | None = None,
        use_context=True,
        timeout_s=10.0,
        debug: bool = False,
    ) -> dict:
        """
        Review heuristic candidate segments and translate confirmed ones.

        Returns:
            dict: {"completed":[{"source": str, "anchor": str, "translation": str}, ...]}
        """
        if not text or not str(text).strip():
            return {"completed": []}

        try:
            token_count = int(token_count)
        except Exception:
            token_count = 0
        text_norm = " ".join(str(text).strip().split())

        context_lines = ""
        if use_context and self._context_window:
            context_lines = "".join(
                self._format_context_pair(source, translation)
                for source, translation, _ in self._context_window
            ).strip()

        # Build CANDIDATES block
        candidates_block = ""
        if candidates:
            numbered = "\n".join(f"  {i+1}. \"{c}\"" for i, c in enumerate(candidates))
            candidates_block = f"CANDIDATES (heuristic pre-split):\n{numbered}\n\n"

        draft_norm = ""
        if draft_continuation and str(draft_continuation).strip():
            draft_norm = " ".join(str(draft_continuation).strip().split())
            if len(draft_norm) > 900:
                draft_norm = draft_norm[:900] + "\u2026"

        user_prompt = (
            f"TOKEN_COUNT: {token_count}\n"
            f"TARGET_LANG: {self.target_lang}\n"
            "TEXT:\n"
            f"{text_norm}\n\n"
            + candidates_block
            + (
                "DRAFT:\n"
                f"{draft_norm}\n\n"
                if draft_norm
                else "DRAFT:\n(empty)\n\n"
            )
            + "CONTEXT:\n"
            f"{context_lines if context_lines else '(empty)'}\n\n"
            "Return JSON only."
        )

        try:
            if debug:
                print(
                    f"[Translator] segment_and_translate token_count={token_count} "
                    f"use_context={use_context} model={self.model}"
                )
                print(f"[Translator] segment_and_translate user_prompt={self._trim_for_log(user_prompt)}")

            create_kwargs = dict(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._segment_system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=self.temperature,
                max_tokens=800,
                timeout=timeout_s,
                response_format={"type": "json_object"},
            )
            if self.extra_body:
                create_kwargs["extra_body"] = self.extra_body
            response = self.client.chat.completions.create(**create_kwargs)
            raw_result = (response.choices[0].message.content or "").strip()
            if debug:
                print(f"[Translator] segment_and_translate raw_result={self._trim_for_log(raw_result)}")
            cleaned = self._strip_thinking(raw_result)

            try:
                data = json_repair.loads(cleaned)
            except Exception:
                if debug:
                    print(f"[Translator] segment_and_translate json_repair failed cleaned={self._trim_for_log(cleaned)}")
                return {"completed": []}

            if debug:
                print(f"[Translator] segment_and_translate parsed_data={self._dump_for_log(data)}")

            if not isinstance(data, dict):
                return {"completed": []}

            completed = data.get("completed")
            if not isinstance(completed, list):
                return {"completed": []}

            normalized: list[dict] = []
            for item in completed:
                if not isinstance(item, dict):
                    continue
                source = item.get("source")
                anchor = item.get("anchor")
                translation = item.get("translation")
                if not isinstance(source, str) or not isinstance(anchor, str) or not isinstance(translation, str):
                    continue
                if not source.strip() or not anchor.strip():
                    continue
                normalized.append({"source": source, "anchor": anchor, "translation": translation})

            for item in normalized:
                src = (item.get("source") or "").strip()
                tr = (item.get("translation") or "").strip()
                if src and tr:
                    self._append_context_pair(src, tr)

            if debug:
                print(f"[Translator] segment_and_translate normalized={self._dump_for_log({'completed': normalized})}")
            return {"completed": normalized}

        except OpenAIError as e:
            print(f"Segment+Translate Error: {e}")
            return {"completed": []}
        except Exception as e:
            print(f"Unexpected Segment+Translate Error: {e}")
            return {"completed": []}

    def translate(self, text, use_context=True, *, trailing_context: str | None = None, debug: bool = False):
        """
        Translates the given text. Returns the translated string.
        Uses previous transcription as context for better continuity.
        """
        if not text or not text.strip():
            return ""

        # Build user prompt with fixed skeleton
        context_lines = ""
        if use_context and self._context_window:
            context_lines = "".join(
                self._format_context_pair(source, translation)
                for source, translation, _ in self._context_window
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

        try:
            if debug:
                print(f"[Translator] translate use_context={use_context} model={self.model}")
                print(f"[Translator] translate user_prompt={self._trim_for_log(user_prompt)}")

            create_kwargs = dict(
                model=self.model,
                messages=[
                    {"role": "system", "content": self._translate_system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=self.temperature,
                max_tokens=500,
                timeout=10.0,
            )
            if self.extra_body:
                create_kwargs["extra_body"] = self.extra_body
            response = self.client.chat.completions.create(**create_kwargs)
            raw_result = response.choices[0].message.content.strip()
            if debug:
                print(f"[Translator] translate raw_result={self._trim_for_log(raw_result)}")
            # Strip thinking tags if present
            result = self._strip_thinking(raw_result)

            data = None
            try:
                data = json_repair.loads(result)
            except Exception:
                data = None
            if debug:
                print(f"[Translator] translate parsed_data={self._dump_for_log(data)}")
                print(f"[Translator] translate normalized={self._trim_for_log(result)}")
            
            # Store for next translation context
            self.previous_text = text
            self.previous_translation = result
            self._append_context_pair(text, result)
            
            return result
        except OpenAIError as e:
            print(f"Translation Error: {e}")
            return f"[Error: {e}]"
        except Exception as e:
            print(f"Unexpected Error: {e}")
            return text

if __name__ == "__main__":
    # Test
    print("Testing Translator (simulated)...")
    # This will likely fail if no real server is running, so we wrap in try
    t = Translator(target_lang="Spanish")
    print(t.translate("Hello world"))
