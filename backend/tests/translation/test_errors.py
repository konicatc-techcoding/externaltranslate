from __future__ import annotations

from backend.app.translation.base import TranslationProviderError


def test_provider_error_exposes_retryable_classification() -> None:
    transient = TranslationProviderError("暫時性錯誤", retryable=True)
    permanent = TranslationProviderError("永久性錯誤", retryable=False)

    assert transient.retryable is True
    assert permanent.retryable is False
