import threading
import time
from concurrent.futures import ThreadPoolExecutor


FIRST_TRANSLATION_DELAY_SECONDS = 5.0
INTERIM_SUCCESS_COOLDOWN_SECONDS = 3.0
TRANSLATION_TIMEOUT_SECONDS = 10.0


def _thread_timer(delay, callback):
    timer = threading.Timer(delay, callback)
    timer.daemon = True
    timer.start()
    return timer


class TranslationScheduler:
    """Schedule provisional and final translations on separate lanes."""

    def __init__(
        self,
        *,
        translate,
        commit_final,
        on_interim,
        on_final,
        on_final_failure,
        clock=time.monotonic,
        call_later=_thread_timer,
        interim_executor=None,
        final_executor=None,
        request_timeout=TRANSLATION_TIMEOUT_SECONDS,
    ):
        self._translate = translate
        self._commit_final = commit_final
        self._on_interim = on_interim
        self._on_final = on_final
        self._on_final_failure = on_final_failure
        self._clock = clock
        self._call_later = call_later
        self._request_timeout = float(request_timeout)

        self._interim_executor = interim_executor or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="translation-interim",
        )
        self._final_executor = final_executor or ThreadPoolExecutor(
            max_workers=1,
            thread_name_prefix="translation-final",
        )

        self._lock = threading.Lock()
        self._pending_interim = None
        self._interim_active = False
        self._timer = None
        self._first_delay_consumed = False
        self._first_due_at = None
        self._last_success_at = None
        self._final_delivered_id = 0
        self._closed = False

    def submit_interim(self, sentence_id: int, text: str) -> None:
        normalized = (text or "").strip()
        if not normalized:
            return
        with self._lock:
            if self._closed:
                return
            self._pending_interim = (int(sentence_id), normalized)
            if (
                not self._first_delay_consumed
                and self._first_due_at is None
            ):
                self._first_due_at = (
                    self._clock() + FIRST_TRANSLATION_DELAY_SECONDS
                )
            self._schedule_interim_locked()

    def submit_final(self, sentence_id: int, text: str) -> None:
        normalized = (text or "").strip()
        if not normalized:
            return
        sid = int(sentence_id)
        with self._lock:
            if self._closed:
                return
            if (
                self._pending_interim is not None
                and self._pending_interim[0] == sid
            ):
                self._pending_interim = None
                self._cancel_timer_locked()
            self._consume_first_delay_locked()
            self._final_executor.submit(self._run_final, sid, normalized)

    def shutdown(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            self._pending_interim = None
            self._cancel_timer_locked()
        self._interim_executor.shutdown(
            wait=False,
            cancel_futures=True,
        )
        self._final_executor.shutdown(
            wait=False,
            cancel_futures=True,
        )

    def _consume_first_delay_locked(self) -> None:
        self._first_delay_consumed = True
        self._first_due_at = None

    def _cancel_timer_locked(self) -> None:
        if self._timer is None:
            return
        self._timer.cancel()
        self._timer = None

    def _schedule_interim_locked(self, *, force: bool = False) -> None:
        if force:
            self._cancel_timer_locked()
        if (
            self._closed
            or self._pending_interim is None
            or self._interim_active
        ):
            return

        now = self._clock()
        if force:
            due_at = now
        elif self._first_due_at is not None:
            due_at = self._first_due_at
        elif self._last_success_at is None:
            due_at = now
        else:
            due_at = (
                self._last_success_at
                + INTERIM_SUCCESS_COOLDOWN_SECONDS
            )

        if now >= due_at:
            self._dispatch_interim_locked()
        elif self._timer is None:
            self._timer = self._call_later(
                due_at - now,
                self._timer_fired,
            )

    def _timer_fired(self) -> None:
        with self._lock:
            self._timer = None
            self._schedule_interim_locked()

    def _dispatch_interim_locked(self) -> None:
        sentence_id, text = self._pending_interim
        self._pending_interim = None
        self._cancel_timer_locked()
        self._consume_first_delay_locked()
        self._interim_active = True
        self._interim_executor.submit(
            self._run_interim,
            sentence_id,
            text,
        )

    def _run_interim(self, sentence_id: int, text: str) -> None:
        started_at = self._clock()
        try:
            translated = self._translate(text, True)
            error = None
        except Exception as exc:
            translated = ""
            error = exc
        finished_at = self._clock()
        expired = finished_at - started_at > self._request_timeout

        if error is not None:
            print(
                "[Translation] Interim translation failed: "
                f"{type(error).__name__}: {error}"
            )
        elif expired:
            print(
                "[Translation] Interim translation exceeded "
                f"{self._request_timeout:g} seconds"
            )

        with self._lock:
            self._interim_active = False
            if self._closed:
                return
            if error is None and not expired:
                self._last_success_at = finished_at
                if sentence_id > self._final_delivered_id:
                    self._on_interim(sentence_id, translated)
                self._schedule_interim_locked()
            else:
                self._last_success_at = None
                self._schedule_interim_locked(force=True)

    def _run_final(self, sentence_id: int, text: str) -> None:
        started_at = self._clock()
        try:
            translated = self._translate(text, False)
            error = None
        except Exception as exc:
            translated = ""
            error = exc
        finished_at = self._clock()
        expired = finished_at - started_at > self._request_timeout

        if error is not None:
            print(
                "[Translation] Final translation failed: "
                f"{type(error).__name__}: {error}"
            )
        elif expired:
            print(
                "[Translation] Final translation exceeded "
                f"{self._request_timeout:g} seconds"
            )

        with self._lock:
            if self._closed:
                return
            if error is None and not expired:
                self._commit_final(text, translated)
                self._last_success_at = finished_at
                self._final_delivered_id = max(
                    self._final_delivered_id,
                    sentence_id,
                )
                self._on_final(sentence_id, text, translated)
                force_next = False
            else:
                self._last_success_at = None
                self._on_final_failure(sentence_id, text)
                force_next = True
            self._schedule_interim_locked(force=force_next)
