from __future__ import annotations

import asyncio
import http.client
from dataclasses import dataclass
from urllib.parse import urlencode
from xml.etree import ElementTree

# A vMix state document is a few kilobytes. Reading without a bound would let
# a wrong host (or a compromised one) hand us an unbounded body to parse.
_MAX_RESPONSE_BYTES = 4 * 1024 * 1024

# HTTP statuses worth trying again: vMix restarting, a transient proxy, or
# rate limiting. Everything else in 4xx means we asked for the wrong thing.
_RETRYABLE_STATUSES = frozenset({408, 409, 425, 429})


class VmixError(RuntimeError):
    """A vMix request failed.

    Messages are metadata only. The caption text never appears in one: these
    strings reach the status feed and the log, which are guaranteed free of
    transcript content.
    """

    def __init__(self, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.retryable = retryable


@dataclass(frozen=True, slots=True)
class VmixInput:
    """One vMix input, identified the only stable way it can be.

    The GUID is the identity; `number` is a position that changes whenever
    inputs are added or removed, and `name` is whatever the operator typed.
    """

    guid: str
    number: int
    name: str
    kind: str
    text_fields: tuple[str, ...]


class VmixClient:
    """Minimal vMix Web API client: read the state, set one text field.

    Uses `http.client` on a worker thread rather than adding an HTTP
    dependency. The call is a single short GET, throttled to a few per second,
    so the thread hop costs nothing worth a new package in the PyInstaller
    bundle — and owning the connection means the socket closes deterministically.
    """

    def __init__(self, *, host: str, port: int, timeout_ms: int = 1000) -> None:
        self._host = host
        self._port = port
        self._timeout = timeout_ms / 1000

    @property
    def base_url(self) -> str:
        return f"http://{self._host}:{self._port}/api/"

    async def inputs(self) -> list[VmixInput]:
        """Read the current inputs, with the text field names of each."""
        body = await self._get({})
        return _parse_inputs(body)

    async def set_text(self, input_guid: str, field: str, value: str) -> None:
        await self._get(
            {
                "Function": "SetText",
                "Input": input_guid,
                "SelectedName": field,
                "Value": value,
            }
        )

    async def _get(self, params: dict[str, str]) -> bytes:
        path = "/api/" + ("?" + urlencode(params) if params else "")
        return await asyncio.to_thread(self._fetch, path)

    def _fetch(self, path: str) -> bytes:
        # `http.client` rather than `urlopen`: the connection is ours, so the
        # socket closes in a `finally` even when the connect itself fails.
        # urlopen leaves that to the garbage collector, which surfaces as an
        # unraisable warning at an unrelated moment.
        connection = http.client.HTTPConnection(
            self._host, self._port, timeout=self._timeout
        )
        try:
            connection.request("GET", path)
            response = connection.getresponse()
            body = bytes(response.read(_MAX_RESPONSE_BYTES))
            if response.status >= 400:
                retryable = (
                    response.status >= 500 or response.status in _RETRYABLE_STATUSES
                )
                raise VmixError(
                    f"vMix 回應 HTTP {response.status}。", retryable=retryable
                )
            return body
        except TimeoutError:
            raise VmixError(
                f"連線 vMix（{self._host}:{self._port}）逾時。", retryable=True
            ) from None
        except http.client.HTTPException as exc:
            # A truncated or malformed response: vMix restarting mid-request.
            raise VmixError(
                f"vMix 回應不完整（{type(exc).__name__}）。", retryable=True
            ) from None
        except OSError as exc:
            # Connection refused is the normal state when vMix is not running.
            raise VmixError(
                f"無法連線到 vMix（{self._host}:{self._port}）：{type(exc).__name__}",
                retryable=True,
            ) from None
        finally:
            connection.close()


def _parse_inputs(body: bytes) -> list[VmixInput]:
    try:
        root = ElementTree.fromstring(body.decode("utf-8", errors="replace"))
    except ElementTree.ParseError:
        raise VmixError("vMix 回應不是有效的 XML。", retryable=True) from None

    inputs: list[VmixInput] = []
    for element in root.findall("./inputs/input"):
        guid = element.get("key")
        if not guid:
            continue  # without an identity we cannot address it safely
        fields = tuple(
            name
            for node in element.findall("text")
            if (name := node.get("name")) is not None and name
        )
        inputs.append(
            VmixInput(
                guid=guid,
                number=_as_int(element.get("number")),
                name=element.get("title") or element.get("shortTitle") or guid,
                kind=element.get("type") or "",
                text_fields=fields,
            )
        )
    return inputs


def _as_int(value: str | None) -> int:
    try:
        return int(value) if value is not None else 0
    except ValueError:
        return 0
