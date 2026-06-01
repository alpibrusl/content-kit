from __future__ import annotations

import pytest

from content_kit_core.writers import default_writer_name, get_writer
from content_kit_core.writers.openai_compat import OpenAICompatWriter

_WRITER_VARS = ("CONTENTKIT_WRITER", "BOOKKIT_WRITER", "PODCASTKIT_WRITER")
_BASE_URL_VARS = ("CONTENTKIT_LLM_BASE_URL", "BOOKKIT_LLM_BASE_URL")


def _clear(monkeypatch: pytest.MonkeyPatch, names) -> None:
    for name in names:
        monkeypatch.delenv(name, raising=False)


def test_default_writer_falls_back_to_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch, _WRITER_VARS)
    assert default_writer_name() == "ollama"


def test_default_writer_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch, _WRITER_VARS)
    monkeypatch.setenv("CONTENTKIT_WRITER", "openai_compat")
    assert default_writer_name() == "openai_compat"


def test_default_writer_honors_legacy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    # Pre-consolidation setups set BOOKKIT_WRITER / PODCASTKIT_WRITER; still honored.
    _clear(monkeypatch, _WRITER_VARS)
    monkeypatch.setenv("BOOKKIT_WRITER", "openai")
    assert default_writer_name() == "openai"


def test_get_writer_openai_compat_aliases() -> None:
    for name in ("openai_compat", "compat", "openai-compatible"):
        assert isinstance(get_writer(name), OpenAICompatWriter)


def test_get_writer_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown writer backend"):
        get_writer("nope")


def test_openai_compat_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch, _BASE_URL_VARS)
    monkeypatch.setenv("CONTENTKIT_LLM_BASE_URL", "http://localhost:9999/v1/")
    monkeypatch.setenv("CONTENTKIT_MODEL", "my-model")
    w = OpenAICompatWriter()
    assert w.base_url == "http://localhost:9999/v1"  # trailing slash stripped
    assert w.model == "my-model"


def test_openai_compat_honors_legacy_env(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch, _BASE_URL_VARS)
    monkeypatch.setenv("BOOKKIT_LLM_BASE_URL", "http://legacy:8080/v1")
    assert OpenAICompatWriter().base_url == "http://legacy:8080/v1"


def test_openai_compat_requires_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    _clear(monkeypatch, _BASE_URL_VARS)
    with pytest.raises(RuntimeError, match="CONTENTKIT_LLM_BASE_URL"):
        OpenAICompatWriter().complete("sys", "user")
