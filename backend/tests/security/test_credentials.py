from __future__ import annotations

import pytest

from backend.app.security.credentials import (
    CredentialStorageUnavailable,
    MemoryCredentialStore,
    UnavailablePersistentCredentialStore,
)


def test_memory_store_sets_reads_and_clears_key_without_leaking_repr() -> None:
    store = MemoryCredentialStore()

    assert store.status().configured is False
    store.set_api_key("test-api-key-value")

    assert store.get_api_key() == "test-api-key-value"
    assert store.status().configured is True
    assert "test-api-key-value" not in repr(store)

    store.clear_api_key()
    assert store.get_api_key() is None
    assert store.status().configured is False


def test_unavailable_persistent_store_fails_explicitly() -> None:
    store = UnavailablePersistentCredentialStore(
        reason="Windows Credential Manager 尚未在 Stage 0 啟用。"
    )

    assert store.status().available is False
    assert store.status().persistent is True
    with pytest.raises(CredentialStorageUnavailable, match="尚未在 Stage 0 啟用"):
        store.set_api_key("test-api-key-value")
