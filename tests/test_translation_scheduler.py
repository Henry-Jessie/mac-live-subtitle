import unittest

from core.translation_scheduler import TranslationScheduler


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


class ManualTimer:
    def __init__(self, clock, delay, callback):
        self.clock = clock
        self.due_at = clock() + delay
        self.callback = callback
        self.cancelled = False
        self.fired = False

    def cancel(self):
        self.cancelled = True

    def fire(self):
        if not self.cancelled:
            self.fired = True
            self.callback()


class ManualTimers:
    def __init__(self, clock):
        self.clock = clock
        self.items = []

    def call_later(self, delay, callback):
        timer = ManualTimer(self.clock, delay, callback)
        self.items.append(timer)
        return timer

    def active(self):
        return [
            timer
            for timer in self.items
            if not timer.cancelled and not timer.fired
        ]


class ManualExecutor:
    def __init__(self):
        self.jobs = []
        self.closed = False

    def submit(self, function, *args):
        self.jobs.append((function, args))

    def take_next(self):
        function, args = self.jobs.pop(0)
        return lambda: function(*args)

    def run_next(self):
        self.take_next()()

    def shutdown(self, *, wait, cancel_futures):
        self.closed = True
        if cancel_futures:
            self.jobs.clear()


class SchedulerHarness:
    def __init__(self, translate=None):
        self.clock = FakeClock()
        self.timers = ManualTimers(self.clock)
        self.interim_executor = ManualExecutor()
        self.final_executor = ManualExecutor()
        self.interim_results = []
        self.final_results = []
        self.final_failures = []
        self.commits = []
        self.calls = []
        self.translate = translate or self._translate
        self.scheduler = TranslationScheduler(
            translate=self.translate,
            commit_final=lambda source, translated: self.commits.append(
                (source, translated)
            ),
            on_interim=lambda sid, translated: self.interim_results.append(
                (sid, translated)
            ),
            on_final=lambda sid, source, translated: self.final_results.append(
                (sid, source, translated)
            ),
            on_final_failure=lambda sid, source: self.final_failures.append(
                (sid, source)
            ),
            clock=self.clock,
            call_later=self.timers.call_later,
            interim_executor=self.interim_executor,
            final_executor=self.final_executor,
        )

    def _translate(self, text, interim):
        self.calls.append((text, interim))
        return f"translated:{text}"

    def fire_at(self, due_at):
        self.clock.advance(due_at - self.clock())
        next(
            timer
            for timer in self.timers.active()
            if timer.due_at == due_at
        ).fire()


class TranslationSchedulerTests(unittest.TestCase):
    def test_first_delay_translates_only_latest_pending_interim(self):
        harness = SchedulerHarness()

        harness.scheduler.submit_interim(1, "first")
        harness.clock.advance(2)
        harness.scheduler.submit_interim(1, "latest")

        self.assertEqual(harness.interim_executor.jobs, [])
        harness.fire_at(5)
        self.assertEqual(len(harness.interim_executor.jobs), 1)

        harness.interim_executor.run_next()

        self.assertEqual(harness.calls, [("latest", True)])
        self.assertEqual(
            harness.interim_results,
            [(1, "translated:latest")],
        )

    def test_success_starts_three_second_interim_cooldown(self):
        harness = SchedulerHarness()
        harness.scheduler.submit_interim(1, "first")
        harness.fire_at(5)
        harness.interim_executor.run_next()

        harness.clock.advance(1)
        harness.scheduler.submit_interim(1, "next")

        self.assertEqual(harness.interim_executor.jobs, [])
        harness.fire_at(8)
        self.assertEqual(len(harness.interim_executor.jobs), 1)

    def test_expired_interim_dispatches_pending_without_cooldown(self):
        harness = None

        def translate(text, interim):
            if text == "slow":
                harness.clock.advance(11)
            return f"translated:{text}"

        harness = SchedulerHarness(translate=translate)
        harness.scheduler.submit_interim(1, "slow")
        harness.fire_at(5)
        harness.scheduler.submit_interim(1, "pending")

        harness.interim_executor.run_next()

        self.assertEqual(harness.interim_results, [])
        self.assertEqual(len(harness.interim_executor.jobs), 1)
        harness.interim_executor.run_next()
        self.assertEqual(
            harness.interim_results,
            [(1, "translated:pending")],
        )

    def test_interim_after_timeout_is_immediately_eligible(self):
        harness = None

        def translate(text, interim):
            if text == "slow":
                harness.clock.advance(11)
            return f"translated:{text}"

        harness = SchedulerHarness(translate=translate)
        harness.scheduler.submit_interim(1, "slow")
        harness.fire_at(5)
        harness.interim_executor.run_next()

        harness.scheduler.submit_interim(1, "new event")

        self.assertEqual(len(harness.interim_executor.jobs), 1)

    def test_final_bypasses_first_delay_and_consumes_it_once(self):
        harness = SchedulerHarness()
        harness.scheduler.submit_interim(1, "draft")
        harness.clock.advance(2)

        harness.scheduler.submit_final(1, "complete")

        self.assertTrue(harness.timers.items[0].cancelled)
        self.assertEqual(len(harness.final_executor.jobs), 1)
        harness.final_executor.run_next()
        harness.scheduler.submit_interim(2, "next sentence")

        self.assertEqual(len(harness.interim_executor.jobs), 0)
        active_timer = harness.timers.active()[0]
        self.assertEqual(active_timer.due_at, 5)

    def test_pending_final_does_not_block_new_interim(self):
        harness = SchedulerHarness()

        harness.scheduler.submit_final(1, "complete")
        harness.scheduler.submit_interim(2, "next draft")

        self.assertEqual(len(harness.final_executor.jobs), 1)
        self.assertEqual(len(harness.interim_executor.jobs), 1)

    def test_final_wins_when_it_returns_before_active_interim(self):
        harness = SchedulerHarness()
        harness.scheduler.submit_interim(1, "draft")
        harness.fire_at(5)
        harness.scheduler.submit_final(1, "complete")

        harness.final_executor.run_next()
        harness.interim_executor.run_next()

        self.assertEqual(
            harness.final_results,
            [(1, "complete", "translated:complete")],
        )
        self.assertEqual(harness.interim_results, [])

    def test_interim_may_display_before_final_returns(self):
        harness = SchedulerHarness()
        harness.scheduler.submit_interim(1, "draft")
        harness.fire_at(5)
        harness.scheduler.submit_final(1, "complete")

        harness.interim_executor.run_next()
        harness.final_executor.run_next()

        self.assertEqual(
            harness.interim_results,
            [(1, "translated:draft")],
        )
        self.assertEqual(
            harness.final_results,
            [(1, "complete", "translated:complete")],
        )

    def test_finals_commit_in_submission_order(self):
        harness = SchedulerHarness()

        harness.scheduler.submit_final(1, "one")
        harness.scheduler.submit_final(2, "two")
        harness.final_executor.run_next()
        harness.final_executor.run_next()

        self.assertEqual(
            harness.commits,
            [
                ("one", "translated:one"),
                ("two", "translated:two"),
            ],
        )

    def test_failed_final_does_not_suppress_late_interim(self):
        def translate(text, interim):
            if not interim:
                raise RuntimeError("provider unavailable")
            return f"translated:{text}"

        harness = SchedulerHarness(translate=translate)
        harness.scheduler.submit_interim(1, "draft")
        harness.fire_at(5)
        harness.scheduler.submit_final(1, "complete")

        harness.final_executor.run_next()
        harness.interim_executor.run_next()

        self.assertEqual(harness.final_failures, [(1, "complete")])
        self.assertEqual(
            harness.interim_results,
            [(1, "translated:draft")],
        )

    def test_shutdown_rejects_late_results_and_new_jobs(self):
        harness = SchedulerHarness()
        harness.scheduler.submit_interim(1, "draft")
        harness.fire_at(5)
        running_job = harness.interim_executor.take_next()

        harness.scheduler.shutdown()
        running_job()
        harness.scheduler.submit_interim(1, "late")
        harness.scheduler.submit_final(1, "late final")

        self.assertEqual(harness.interim_results, [])
        self.assertEqual(harness.interim_executor.jobs, [])
        self.assertEqual(harness.final_executor.jobs, [])


if __name__ == "__main__":
    unittest.main()
