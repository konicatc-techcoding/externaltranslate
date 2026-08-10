from __future__ import annotations

import asyncio

from backend.app.outputs.vmix import VmixClient
from backend.app.outputs.vmix_output import VmixOutput
from backend.tests.outputs.fake_vmix import FakeInput, FakeVmix

_TITLE = FakeInput(
    guid="877bb3e7-58bd-46a1-85ce-0d673aec6bf5",
    number=1,
    name="字幕標題",
    text_fields=("Line1.Text", "Line2.Text"),
)


def build(server: FakeVmix, *, fields: tuple[str, ...] = ("Line1.Text", "Line2.Text")):
    client = VmixClient(host=server.host, port=server.port, timeout_ms=500)
    return VmixOutput(
        client,
        input_guid=_TITLE.guid,
        fields=list(fields),
        min_interval_ms=50,
    )


async def until(predicate, timeout: float = 2.0) -> None:
    async def poll() -> None:
        while not predicate():
            await asyncio.sleep(0.005)

    await asyncio.wait_for(poll(), timeout=timeout)


def test_each_line_goes_to_its_own_field() -> None:
    async def scenario() -> None:
        with FakeVmix([_TITLE]) as server:
            output = build(server)
            await output.start()
            output.publish(["第一行", "第二行"])
            await until(lambda: len(server.calls) >= 2)
            await output.aclose()

            written = {call.field: call.value for call in server.calls}

        assert written["Line1.Text"] == "第一行"
        assert written["Line2.Text"] == "第二行"

    asyncio.run(scenario())


def test_unused_fields_are_blanked() -> None:
    # Otherwise the previous sentence's second line stays on screen under the
    # new first line, which reads as one sentence.
    async def scenario() -> None:
        with FakeVmix([_TITLE]) as server:
            output = build(server)
            await output.start()
            output.publish(["只有一行"])
            await until(lambda: len(server.calls) >= 2)
            await output.aclose()

            written = {call.field: call.value for call in server.calls}

        assert written["Line1.Text"] == "只有一行"
        assert written["Line2.Text"] == ""

    asyncio.run(scenario())


def test_more_lines_than_fields_keeps_the_newest() -> None:
    # The window slides, so the most recent lines are the ones worth showing.
    async def scenario() -> None:
        with FakeVmix([_TITLE]) as server:
            output = build(server, fields=("Line1.Text",))
            await output.start()
            output.publish(["舊的一行", "新的一行"])
            await until(lambda: len(server.calls) >= 1)
            await output.aclose()

            written = {call.field: call.value for call in server.calls}

        assert written["Line1.Text"] == "新的一行"

    asyncio.run(scenario())


def test_a_single_field_joins_the_lines() -> None:
    async def scenario() -> None:
        with FakeVmix([_TITLE]) as server:
            output = build(server, fields=("Caption.Text",))
            output.set_single_field_join(True)
            await output.start()
            output.publish(["第一行", "第二行"])
            await until(lambda: len(server.calls) >= 1)
            await output.aclose()

            value = server.calls[-1].value

        assert value == "第一行\r\n第二行"

    asyncio.run(scenario())


def test_clear_blanks_every_field() -> None:
    async def scenario() -> None:
        with FakeVmix([_TITLE]) as server:
            output = build(server)
            await output.start()
            output.publish(["還在說話"])
            await until(lambda: len(server.calls) >= 2)

            await output.clear()
            await output.aclose()

            tail = server.calls[-2:]

        assert [call.value for call in tail] == ["", ""]

    asyncio.run(scenario())


def test_a_missing_input_is_reported_before_anything_is_sent() -> None:
    async def scenario() -> None:
        with FakeVmix([_TITLE]) as server:
            client = VmixClient(host=server.host, port=server.port, timeout_ms=500)
            output = VmixOutput(
                client,
                input_guid="00000000-0000-0000-0000-000000000000",
                fields=["Line1.Text"],
                min_interval_ms=50,
            )

            ready = await output.start()
            await output.aclose()

        # Sending to a GUID that is gone would either do nothing or, worse,
        # be silently accepted; refusing to start says so instead.
        assert ready is False
        assert output.last_error is not None

    asyncio.run(scenario())


def test_publishing_never_raises_when_vmix_is_down() -> None:
    async def scenario() -> None:
        with FakeVmix([_TITLE]) as server:
            output = build(server)
            await output.start()
            server.set_mode("server_error")

            output.publish(["翻譯繼續"])  # must not raise
            await asyncio.sleep(0.05)
            await output.aclose()

    asyncio.run(scenario())
