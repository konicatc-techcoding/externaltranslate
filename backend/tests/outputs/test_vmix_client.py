from __future__ import annotations

import asyncio
import socket

import pytest

from backend.app.outputs.vmix import VmixClient, VmixError
from backend.tests.outputs.fake_vmix import FakeInput, FakeVmix

_TITLE = FakeInput(
    guid="877bb3e7-58bd-46a1-85ce-0d673aec6bf5",
    number=1,
    name="字幕標題",
    text_fields=("Line1.Text", "Line2.Text"),
)
_CAMERA = FakeInput(
    guid="11111111-2222-3333-4444-555555555555",
    number=2,
    name="Cam 1",
    kind="Capture",
)


def client_for(server: FakeVmix, *, timeout_ms: int = 1000) -> VmixClient:
    return VmixClient(host=server.host, port=server.port, timeout_ms=timeout_ms)


def test_inputs_are_discovered_with_their_text_fields() -> None:
    with FakeVmix([_TITLE, _CAMERA]) as server:
        inputs = asyncio.run(client_for(server).inputs())

    assert [item.name for item in inputs] == ["字幕標題", "Cam 1"]
    assert inputs[0].guid == _TITLE.guid
    # Field names are what the operator has to create in the Title Editor.
    assert inputs[0].text_fields == ("Line1.Text", "Line2.Text")
    assert inputs[1].text_fields == ()


def test_set_text_sends_the_documented_parameters() -> None:
    with FakeVmix([_TITLE]) as server:
        asyncio.run(
            client_for(server).set_text(_TITLE.guid, "Line1.Text", "今天天氣很好")
        )
        calls = list(server.calls)

    assert len(calls) == 1
    assert calls[0].input == _TITLE.guid
    assert calls[0].field == "Line1.Text"
    assert calls[0].value == "今天天氣很好"


@pytest.mark.parametrize(
    "value",
    [
        "中文與 space",
        "a&b=c",
        "百分之 100%",
        "第一行\r\n第二行",
        "「引號」＋符號",
        "",
    ],
)
def test_values_survive_the_round_trip(value: str) -> None:
    # Hand-built query strings are where this integration breaks first.
    with FakeVmix([_TITLE]) as server:
        asyncio.run(client_for(server).set_text(_TITLE.guid, "Line1.Text", value))
        calls = list(server.calls)

    assert calls[0].value == value


def test_a_slow_vmix_times_out_and_is_retryable() -> None:
    with FakeVmix([_TITLE]) as server:
        server.set_mode("slow")
        with pytest.raises(VmixError) as caught:
            asyncio.run(client_for(server, timeout_ms=150).inputs())

    assert caught.value.retryable is True


def test_a_server_error_is_retryable() -> None:
    with FakeVmix([_TITLE]) as server:
        server.set_mode("server_error")
        with pytest.raises(VmixError) as caught:
            asyncio.run(client_for(server).inputs())

    assert caught.value.retryable is True


def test_a_client_error_is_not_retryable() -> None:
    with FakeVmix([_TITLE]) as server:
        server.set_mode("not_found")
        with pytest.raises(VmixError) as caught:
            asyncio.run(client_for(server).inputs())

    assert caught.value.retryable is False


def test_a_dropped_connection_is_retryable() -> None:
    with FakeVmix([_TITLE]) as server:
        server.set_mode("close")
        with pytest.raises(VmixError) as caught:
            asyncio.run(client_for(server).inputs())

    assert caught.value.retryable is True


def test_unparseable_xml_fails_without_raising_a_parser_error() -> None:
    with FakeVmix([_TITLE]) as server:
        server.set_mode("garbage")
        with pytest.raises(VmixError):
            asyncio.run(client_for(server).inputs())


def test_nothing_listening_is_retryable() -> None:
    # vMix simply not running is the most common state of all.
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = int(probe.getsockname()[1])

    with pytest.raises(VmixError) as caught:
        asyncio.run(
            VmixClient(host="127.0.0.1", port=free_port, timeout_ms=500).inputs()
        )

    assert caught.value.retryable is True


def test_the_error_message_never_leaks_the_caption_text() -> None:
    # Status details and logs are metadata-only; a failure carrying the
    # sentence being translated would defeat that.
    with FakeVmix([_TITLE]) as server:
        server.set_mode("server_error")
        with pytest.raises(VmixError) as caught:
            asyncio.run(
                client_for(server).set_text(_TITLE.guid, "Line1.Text", "機密逐字稿")
            )

    assert "機密逐字稿" not in str(caught.value)
