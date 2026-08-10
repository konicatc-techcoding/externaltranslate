from __future__ import annotations

import asyncio

from backend.app.outputs.sender import ThrottledSender


class Recorder:
    """Collects deliveries and can be told to fail a number of times."""

    def __init__(self, failures: int = 0) -> None:
        self.sent: list[tuple[str, ...]] = []
        self.failures = failures
        self.delivered = asyncio.Event()

    async def __call__(self, payload: tuple[str, ...]) -> None:
        if self.failures > 0:
            self.failures -= 1
            raise RuntimeError("vMix 拒絕")
        self.sent.append(payload)
        self.delivered.set()


def build(
    recorder: Recorder, *, min_interval_ms: int = 200
) -> tuple[ThrottledSender, list[float]]:
    slept: list[float] = []

    async def sleep(seconds: float) -> None:
        slept.append(seconds)
        await asyncio.sleep(0)  # yield without spending real time

    return (
        ThrottledSender(recorder, min_interval_ms=min_interval_ms, sleep=sleep),
        slept,
    )


async def wait_for(recorder: Recorder, count: int) -> None:
    async def poll() -> None:
        while len(recorder.sent) < count:
            await asyncio.sleep(0)

    await asyncio.wait_for(poll(), timeout=2.0)


async def drain(sender: ThrottledSender, recorder: Recorder, count: int) -> None:
    await wait_for(recorder, count)
    await sender.aclose()


def test_a_burst_collapses_to_the_newest_state() -> None:
    # Fragments arrive several times a second; the ones in between were never
    # worth a network round trip.
    async def scenario() -> None:
        recorder = Recorder()
        sender, _slept = build(recorder)
        task = asyncio.create_task(sender.run())

        sender.submit(("第一",))
        sender.submit(("第一二",))
        sender.submit(("第一二三",))

        await drain(sender, recorder, 1)
        await task
        assert recorder.sent[-1] == ("第一二三",)

    asyncio.run(scenario())


def test_the_last_state_is_always_delivered() -> None:
    # Dropping updates that arrive too fast *without* sending the final one
    # leaves the caption a fragment behind for good. This is the failure mode
    # throttling usually ships with.
    async def scenario() -> None:
        recorder = Recorder()
        sender, _slept = build(recorder)
        task = asyncio.create_task(sender.run())

        sender.submit(("一",))
        await wait_for(recorder, 1)
        sender.submit(("一二",))  # arrives during the throttle window

        await drain(sender, recorder, 2)
        await asyncio.wait_for(task, timeout=2.0)
        assert recorder.sent[-1] == ("一二",)

    asyncio.run(scenario())


def test_flush_sends_the_pending_state_now() -> None:
    # Stopping translation has to blank the GT title, and that clear must not
    # wait behind a throttle window or be dropped by the shutdown.
    async def scenario() -> None:
        recorder = Recorder()
        sender, _slept = build(recorder, min_interval_ms=2000)
        task = asyncio.create_task(sender.run())

        sender.submit(("", ""))
        await sender.flush()
        await sender.aclose()
        await asyncio.wait_for(task, timeout=2.0)

        assert recorder.sent == [("", "")]

    asyncio.run(scenario())


def test_flush_swallows_a_failure() -> None:
    # A vMix that is already gone must not stop the pipeline from shutting down.
    async def scenario() -> None:
        recorder = Recorder(failures=1)
        sender, _slept = build(recorder)
        task = asyncio.create_task(sender.run())

        sender.submit(("", ""))
        await sender.flush()
        await sender.aclose()
        await asyncio.wait_for(task, timeout=2.0)

    asyncio.run(scenario())


def test_an_unchanged_payload_is_not_resent() -> None:
    async def scenario() -> None:
        recorder = Recorder()
        sender, _slept = build(recorder)
        task = asyncio.create_task(sender.run())

        sender.submit(("同樣的字",))
        await wait_for(recorder, 1)
        sender.submit(("同樣的字",))
        await asyncio.sleep(0)
        await sender.aclose()

        await asyncio.wait_for(task, timeout=2.0)
        assert recorder.sent == [("同樣的字",)]

    asyncio.run(scenario())


def test_it_waits_the_configured_interval_between_sends() -> None:
    async def scenario() -> None:
        recorder = Recorder()
        sender, slept = build(recorder, min_interval_ms=250)
        task = asyncio.create_task(sender.run())

        sender.submit(("一",))
        await drain(sender, recorder, 1)
        await task

        assert 0.25 in slept

    asyncio.run(scenario())


def test_a_failure_retries_with_backoff_and_still_delivers() -> None:
    async def scenario() -> None:
        recorder = Recorder(failures=2)
        sender, slept = build(recorder)
        task = asyncio.create_task(sender.run())

        sender.submit(("要送出去的字",))
        await drain(sender, recorder, 1)
        await task

        assert recorder.sent == [("要送出去的字",)]
        # bounded, growing, and never a tight loop
        assert slept[:2] == [0.5, 1.0]

    asyncio.run(scenario())


def test_a_failure_does_not_escape_to_the_caller() -> None:
    # submit() runs on the caption path. An exception there would take down
    # translation because vMix is unhappy.
    async def scenario() -> None:
        recorder = Recorder(failures=1)
        sender, _slept = build(recorder)
        task = asyncio.create_task(sender.run())

        sender.submit(("字",))  # returns immediately, no awaiting, no raising
        await drain(sender, recorder, 1)
        await task

    asyncio.run(scenario())


def test_closing_without_anything_pending_is_clean() -> None:
    async def scenario() -> None:
        recorder = Recorder()
        sender, _slept = build(recorder)
        task = asyncio.create_task(sender.run())
        await sender.aclose()
        await asyncio.wait_for(task, timeout=2.0)

        assert recorder.sent == []

    asyncio.run(scenario())


def test_submitting_after_close_is_ignored() -> None:
    async def scenario() -> None:
        recorder = Recorder()
        sender, _slept = build(recorder)
        task = asyncio.create_task(sender.run())
        await sender.aclose()
        await asyncio.wait_for(task, timeout=2.0)

        sender.submit(("太遲了",))
        await asyncio.sleep(0)
        assert recorder.sent == []

    asyncio.run(scenario())
