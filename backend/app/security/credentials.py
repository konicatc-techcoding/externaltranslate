from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class CredentialStorageUnavailable(RuntimeError):
    """Raised when a requested credential backend is not available."""


@dataclass(frozen=True)
class CredentialStatus:
    available: bool
    persistent: bool
    configured: bool
    detail: str


class CredentialStore(Protocol):
    def get_api_key(self) -> str | None: ...

    def set_api_key(self, api_key: str) -> None: ...

    def clear_api_key(self) -> None: ...

    def status(self) -> CredentialStatus: ...


class MemoryCredentialStore:
    """Keep the Gemini API key only in process memory."""

    def __init__(self) -> None:
        self._api_key: str | None = None

    def __repr__(self) -> str:
        return f"{type(self).__name__}(configured={self._api_key is not None})"

    def get_api_key(self) -> str | None:
        return self._api_key

    def set_api_key(self, api_key: str) -> None:
        self._api_key = api_key

    def clear_api_key(self) -> None:
        self._api_key = None

    def status(self) -> CredentialStatus:
        return CredentialStatus(
            available=True,
            persistent=False,
            configured=self._api_key is not None,
            detail="API Key 目前只保存在程序記憶體中。",
        )


class UnavailablePersistentCredentialStore:
    """Explicit boundary until Windows Credential Manager is implemented."""

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def get_api_key(self) -> str | None:
        raise CredentialStorageUnavailable(self._reason)

    def set_api_key(self, api_key: str) -> None:
        del api_key
        raise CredentialStorageUnavailable(self._reason)

    def clear_api_key(self) -> None:
        raise CredentialStorageUnavailable(self._reason)

    def status(self) -> CredentialStatus:
        return CredentialStatus(
            available=False,
            persistent=True,
            configured=False,
            detail=self._reason,
        )
