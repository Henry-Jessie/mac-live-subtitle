import threading
from concurrent.futures import ThreadPoolExecutor

from core.config import config

# ---------------------------------------------------------------------------
# Heuristic splitting constants & helpers (shared by _try_heuristic_split,
# _compute_candidates, and dispatch_llm_if_needed)
# ---------------------------------------------------------------------------

_SENTENCE_END_CHARS = {
    ".", "\uff0e", "!", "?", "\u3002", "\uff01", "\uff1f",
    "\u203c", "\u2047", "\u2048", "\u2049", "\u061f", "\uff61", "\u2026",
}
_CLAUSE_CHARS = {
    ",", ";", ":", "\uff0c", "\uff1b", "\uff1a", "\u3001",
    "\u2014", "\u2013", "\u2015", "\u2212", "-",
}
_TRAILING_CLOSERS = {'"', "'", ")", "]", "}", "\u201d", "\u2019", "\u300d", "\u300b", "\u3011", "\uff09"}
_COMMON_ABBREV = {
    "mr", "mrs", "ms", "dr", "prof", "sr", "jr", "st", "vs", "etc",
    "e.g", "i.e", "no", "fig", "dept", "inc", "ltd", "co", "corp",
}


def _next_nonspace_idx(s: str, start: int) -> int:
    for j in range(start, len(s)):
        if not s[j].isspace():
            return j
    return -1


def _ends_with_dotted_abbr(s: str, idx: int) -> bool:
    j = idx
    count = 0
    while j >= 1 and s[j] in (".", "\uff0e") and s[j - 1].isalpha():
        count += 1
        j -= 2
        if j < 0 or s[j] not in (".", "\uff0e"):
            break
    return count >= 2


def _is_non_sentence_period(s: str, idx: int) -> bool:
    if idx < 0 or idx >= len(s):
        return True
    if idx + 1 < len(s) and s[idx + 1] in (".", "\uff0e"):
        return True
    if 0 < idx < (len(s) - 1) and s[idx - 1].isdigit() and s[idx + 1].isdigit():
        return True
    if 0 < idx < (len(s) - 1) and s[idx - 1].isalnum() and s[idx + 1].isalnum():
        return True
    # Period at end of buffer preceded by digit — likely an
    # incomplete decimal (e.g. "2." waiting for "1" from ASR).
    if idx > 0 and s[idx - 1].isdigit():
        tail = s[idx + 1:]
        if not tail or tail.isspace():
            return True

    j = idx - 1
    while j >= 0 and s[j].isalpha():
        j -= 1
    word = s[j + 1 : idx].lower()
    if word and word in _COMMON_ABBREV:
        nxt = _next_nonspace_idx(s, idx + 1)
        if nxt >= 0 and s[nxt].isalnum():
            return True

    if _ends_with_dotted_abbr(s, idx):
        nxt = _next_nonspace_idx(s, idx + 1)
        if nxt >= 0 and s[nxt].isalnum():
            return True

    return False


def _find_sentence_end(s: str) -> int:
    i = 0
    while i < len(s):
        ch = s[i]
        if ch in _SENTENCE_END_CHARS:
            if ch in (".", "\uff0e") and _is_non_sentence_period(s, i):
                i += 1
                continue
            j = i + 1
            while j < len(s) and s[j] in _SENTENCE_END_CHARS:
                j += 1
            while j < len(s) and s[j] in _TRAILING_CLOSERS:
                j += 1
            return j
        i += 1
    return 0


def _is_non_clause_punct(s: str, idx: int, ch: str) -> bool:
    if ch in (",", "\uff0c") and 0 < idx < (len(s) - 1) and s[idx - 1].isdigit() and s[idx + 1].isdigit():
        return True
    if ch in (":", "\uff1a") and 0 < idx < (len(s) - 1) and s[idx - 1].isdigit() and s[idx + 1].isdigit():
        return True
    if ch == "-" and 0 < idx < (len(s) - 1) and s[idx - 1].isalnum() and s[idx + 1].isalnum():
        return True
    return False


def _find_clause_end(s: str) -> int:
    for i in range(len(s) - 1, -1, -1):
        ch = s[i]
        if ch not in _CLAUSE_CHARS:
            continue
        if _is_non_clause_punct(s, i, ch):
            continue
        return i + 1
    return 0


def compute_candidates(text: str, token_enc) -> list[str]:
    """Run heuristic splitting on *text* and return candidate segments.

    Pure function — no side effects, no state mutation.
    """
    candidates: list[str] = []
    buf = (text or "").strip()
    if not buf:
        return candidates

    while buf:
        try:
            toks = token_enc.encode(buf)
            tok = len(toks)
        except Exception:
            toks = None
            tok = len(buf.split())

        cut_end = _find_sentence_end(buf)
        if cut_end <= 0:
            if tok > 30 and toks is not None:
                prefix = token_enc.decode(toks[:18])
                cut_end = len(prefix)
            elif tok > 18:
                cut_end = _find_clause_end(buf)

        if cut_end <= 0:
            break

        seg = buf[:cut_end].strip()
        buf = buf[cut_end:].lstrip()

        if not seg or not any(ch.isalnum() for ch in seg):
            continue
        candidates.append(seg)

    # Whatever remains is the un-split tail (returned via the caller
    # knowing the original text).
    return candidates


# ---------------------------------------------------------------------------


class StreamingSegmenter:
    def __init__(
        self,
        pipeline,
        *,
        label: str,
        join_with_space: bool,
        strip_parts: bool,
    ):
        self.pipeline = pipeline
        self.label = (label or "").strip() or "ASR"
        self.join_with_space = bool(join_with_space)
        self.strip_parts = bool(strip_parts)

        self.state_lock = threading.Lock()
        self.sentence_id = 1
        self.pending_confirmed = ""
        self.interim_text = ""
        self.llm_in_flight = False
        self.llm_snapshot = ""
        self.last_display = ""

        self.translation_debug = False
        try:
            self.translation_debug = bool(self.pipeline._translation_debug_enabled())
        except Exception:
            self.translation_debug = False

        self.token_enc = None
        if getattr(self.pipeline, "translator", None) is not None:
            try:
                import tiktoken

                self.token_enc = getattr(self.pipeline.translator, "_encoding", None) or tiktoken.get_encoding(
                    "o200k_base"
                )
            except Exception:
                self.token_enc = None

        self.use_llm_segmenter = (
            getattr(self.pipeline, "translator", None) is not None
            and hasattr(self.pipeline.translator, "segment_and_translate")
            and bool(getattr(config, "use_llm_segmenter", False))
        )

        self.translate_executor = ThreadPoolExecutor(max_workers=1)

    def shutdown(self) -> None:
        try:
            self.translate_executor.shutdown(wait=False)
        except Exception:
            pass

    def _trim_for_log(self, text: str, max_len: int = 180) -> str:
        s = (text or "").replace("\n", "\\n")
        if len(s) <= max_len:
            return s
        return s[:max_len] + f"\u2026(+{len(s) - max_len} chars)"

    def _emit_live(self, *, line_id: int, confirmed: str, interim: str) -> None:
        if self.join_with_space:
            a = (confirmed or "").strip()
            b = (interim or "").strip()
            if a and b:
                live = f"{a} {b}"
                confirmed_out = a + " "
                interim_out = b
            elif a:
                live = a
                confirmed_out = a
                interim_out = ""
            else:
                live = b
                confirmed_out = ""
                interim_out = b
        elif self.strip_parts:
            a = (confirmed or "").strip()
            b = (interim or "").strip()
            live = (a + b).strip()
            confirmed_out = a
            interim_out = b
        else:
            a = confirmed or ""
            b = interim or ""
            live = (a + b).strip()
            confirmed_out = a
            interim_out = b

        if not (live or "").strip():
            return

        with self.state_lock:
            if live == self.last_display:
                return
            self.last_display = live

        try:
            self.pipeline.signals.update_live_text.emit(int(line_id), confirmed_out, interim_out)
        except Exception:
            pass

    def update(
        self,
        *,
        append_confirmed: str | None = None,
        append_separator: str = " ",
        append_strip: bool = True,
        interim: str | None = None,
        interim_strip: bool = True,
        clear_interim: bool = False,
        emit: bool = True,
    ) -> tuple[bool, int, str, str]:
        appended = False
        with self.state_lock:
            if append_confirmed is not None:
                part = append_confirmed.strip() if append_strip else append_confirmed
                if part:
                    if self.pending_confirmed:
                        if append_separator:
                            self.pending_confirmed = (
                                (self.pending_confirmed + append_separator + part).strip()
                                if append_strip
                                else (self.pending_confirmed + append_separator + part)
                            )
                        else:
                            self.pending_confirmed = self.pending_confirmed + part
                    else:
                        self.pending_confirmed = part.strip() if append_strip else part
                    appended = True

            if clear_interim:
                self.interim_text = ""
            elif interim is not None:
                self.interim_text = interim.strip() if interim_strip else interim

            lid = self.sentence_id
            snap = self.pending_confirmed
            it = self.interim_text

        if emit:
            self._emit_live(line_id=lid, confirmed=snap, interim=it)

        return appended, lid, snap, it

    @staticmethod
    def _local_cut_end(text: str) -> int:
        s = (text or "").strip()
        if not s:
            return 0
        for chars in (".!?\u3002\uff01\uff1f", ",;:\uff0c\uff1b\uff1a"):
            idx = max((s.rfind(ch) for ch in chars), default=-1)
            if idx >= 0:
                return idx + 1
        sp = s.rfind(" ")
        if sp > 0:
            return sp
        return len(s)

    # ------------------------------------------------------------------
    # Heuristic-only path (no LLM)
    # ------------------------------------------------------------------

    def _try_heuristic_split(self, *, force_flush: bool = False) -> None:
        if getattr(self.pipeline, "translator", None) is None or self.token_enc is None:
            return

        token_enc = self.token_enc
        translate_executor = self.translate_executor

        while getattr(self.pipeline, "running", False):
            with self.state_lock:
                buf0 = self.pending_confirmed
                cur_id = self.sentence_id
                cur_interim = self.interim_text

            if not (buf0 or "").strip():
                return

            leading = len(buf0) - len(buf0.lstrip())
            buf = buf0.lstrip()
            try:
                toks = token_enc.encode(buf)
                tok = len(toks)
            except Exception:
                toks = None
                tok = len(buf.split())

            cut_end = _find_sentence_end(buf)
            if cut_end <= 0:
                if tok > 30 and toks is not None:
                    prefix = token_enc.decode(toks[:18])
                    cut_end = len(prefix)
                elif tok > 18:
                    cut_end = _find_clause_end(buf)
                else:
                    if force_flush:
                        cut_end = len(buf)
                    else:
                        return

            if cut_end <= 0:
                return

            seg = buf[:cut_end].strip()
            remainder_confirmed = buf[cut_end:].lstrip()
            if not seg:
                with self.state_lock:
                    if self.pending_confirmed == buf0:
                        self.pending_confirmed = self.pending_confirmed[leading + cut_end :].lstrip()
                        self.last_display = ""
                continue

            if not any(ch.isalnum() for ch in seg):
                with self.state_lock:
                    if self.pending_confirmed == buf0:
                        self.pending_confirmed = self.pending_confirmed[leading + cut_end :].lstrip()
                        self.last_display = ""
                continue

            trailing_context = (remainder_confirmed + " " + (cur_interim or "")).strip()
            if trailing_context and len(trailing_context) > 900:
                trailing_context = trailing_context[:900] + "\u2026"

            try:
                self.pipeline.signals.update_text.emit(cur_id, seg, "(translating...)")
            except Exception:
                pass
            try:
                translate_executor.submit(self.pipeline._run_translation, seg, cur_id, trailing_context or None)
            except Exception:
                pass

            with self.state_lock:
                if self.pending_confirmed != buf0:
                    return
                self.pending_confirmed = self.pending_confirmed[leading + cut_end :].lstrip()
                self.sentence_id = cur_id + 1
                self.last_display = ""
                lid = self.sentence_id
                pc = self.pending_confirmed
                it = self.interim_text
            self._emit_live(line_id=lid, confirmed=pc, interim=it)

    def try_split(self, *, force_flush: bool = False) -> None:
        if self.use_llm_segmenter:
            return
        self._try_heuristic_split(force_flush=force_flush)

    # ------------------------------------------------------------------
    # LLM path (heuristic candidates → LLM review + translate)
    # ------------------------------------------------------------------

    def dispatch_llm_if_needed(self, snapshot: str, *, force_flush: bool = False) -> None:
        if not self.use_llm_segmenter:
            return
        if not getattr(self.pipeline, "running", False):
            return

        snap = (snapshot or "").strip()
        if not snap:
            return

        token_enc = self.token_enc
        try:
            tok = len(token_enc.encode(snap)) if token_enc is not None else len(snap.split())
        except Exception:
            tok = len(snap.split())
        if tok < 18 and not force_flush:
            return

        # Compute heuristic candidate segments for the LLM to review.
        candidates = compute_candidates(snap, token_enc) if token_enc is not None else []

        if not candidates and not force_flush:
            return

        if not candidates and force_flush:
            self.flush_pending_local()
            return

        with self.state_lock:
            if self.llm_in_flight:
                return
            self.llm_in_flight = True
            self.llm_snapshot = snap
            draft = self.interim_text

        print(
            f"[{self.label}] LLM dispatch tok={tok} "
            f"candidates={len(candidates)} "
            f"snap={self._trim_for_log(snap, 120)}"
        )

        def _job():
            return self.pipeline.translator.segment_and_translate(
                snap,
                token_count=tok,
                candidates=candidates,
                draft_continuation=draft,
                use_context=True,
                timeout_s=10.0,
                debug=self.translation_debug,
            )

        fut = self.translate_executor.submit(_job)

        def _on_done(f, *, snap=snap, tok=tok):
            try:
                result = f.result()
            except Exception:
                result = {"completed": []}

            with self.state_lock:
                self.llm_in_flight = False
                self.llm_snapshot = ""
                cur_pending = self.pending_confirmed
                cur_sentence_id = self.sentence_id

            if not getattr(self.pipeline, "running", False):
                return
            if not cur_pending.startswith(snap):
                return

            completed = []
            if isinstance(result, dict):
                completed = result.get("completed") or []
            if not isinstance(completed, list):
                completed = []

            if not completed and tok >= 24:
                cut_end = self._local_cut_end(snap)
                seg = snap[:cut_end].strip() if cut_end > 0 else ""
                if seg:
                    tr = self.pipeline.translator.translate(seg, debug=self.translation_debug)
                    try:
                        self.pipeline.signals.update_text.emit(cur_sentence_id, seg, (tr or "").strip())
                    except Exception:
                        pass
                    with self.state_lock:
                        if not self.pending_confirmed.startswith(snap):
                            return
                        self.pending_confirmed = self.pending_confirmed[cut_end:].lstrip(
                            " \t\n\r.!?\u3002\uff01\uff1f,;:\uff0c\uff1b\uff1a"
                        )
                        self.interim_text = ""
                        self.sentence_id = cur_sentence_id + 1
                        self.last_display = ""
                        lid = self.sentence_id
                        pc = self.pending_confirmed
                        it = self.interim_text
                    self._emit_live(line_id=lid, confirmed=pc, interim=it)
                return

            if not completed:
                return

            last_item = completed[-1] if completed else {}
            anchor = last_item.get("anchor") if isinstance(last_item, dict) else ""
            if not isinstance(anchor, str):
                anchor = ""

            idx = snap.find(anchor) if anchor else -1
            if idx >= 0:
                cut_end = idx + len(anchor)
            else:
                cut_end = 0
                for item in completed:
                    if not isinstance(item, dict):
                        continue
                    src = item.get("source")
                    if isinstance(src, str):
                        cut_end += len(src)
                cut_end = min(cut_end, len(snap))

            emissions: list[tuple[int, str, str]] = []
            next_id = cur_sentence_id
            for item in completed:
                if not isinstance(item, dict):
                    continue
                src = item.get("source")
                tr = item.get("translation")
                if not isinstance(src, str) or not src.strip():
                    continue
                if not isinstance(tr, str):
                    tr = ""
                emissions.append((next_id, src.strip(), tr.strip()))
                next_id += 1

            if not emissions:
                return

            with self.state_lock:
                if not self.pending_confirmed.startswith(snap):
                    return
                self.pending_confirmed = self.pending_confirmed[cut_end:].lstrip(
                    " \t\n\r.!?\u3002\uff01\uff1f,;:\uff0c\uff1b\uff1a"
                )
                self.interim_text = ""
                self.sentence_id = next_id
                self.last_display = ""

            for cid, src, tr in emissions:
                try:
                    self.pipeline.signals.update_text.emit(cid, src, tr)
                except Exception:
                    pass

            with self.state_lock:
                lid = self.sentence_id
                pc = self.pending_confirmed
                it = self.interim_text
            self._emit_live(line_id=lid, confirmed=pc, interim=it)

        fut.add_done_callback(_on_done)

    def flush_pending_local(self) -> None:
        if getattr(self.pipeline, "translator", None) is None:
            return

        with self.state_lock:
            self.llm_in_flight = False
            self.llm_snapshot = ""
            text = self.pending_confirmed
            self.pending_confirmed = ""
            self.interim_text = ""
            self.last_display = ""
            cur_id = self.sentence_id

        s = (text or "").strip()
        while s:
            cut_end = self._local_cut_end(s)
            seg = s[:cut_end].strip() if cut_end > 0 else ""
            if not seg:
                break
            tr = self.pipeline.translator.translate(seg, debug=self.translation_debug)
            try:
                self.pipeline.signals.update_text.emit(cur_id, seg, (tr or "").strip())
            except Exception:
                pass
            cur_id += 1
            s = s[cut_end:].lstrip()

        with self.state_lock:
            self.sentence_id = cur_id
