from __future__ import annotations

import pytest

from bookkit.writers import default_writer_name, get_writer
from bookkit.writers.openai_compat import OpenAICompatWriter


def test_default_writer_falls_back_to_ollama(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOOKKIT_WRITER", raising=False)
    assert default_writer_name() == "ollama"


def test_default_writer_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOOKKIT_WRITER", "openai_compat")
    assert default_writer_name() == "openai_compat"


def test_get_writer_openai_compat_aliases() -> None:
    for name in ("openai_compat", "compat", "openai-compatible"):
        assert isinstance(get_writer(name), OpenAICompatWriter)


def test_get_writer_unknown_raises() -> None:
    with pytest.raises(ValueError, match="Unknown writer backend"):
        get_writer("nope")


def test_openai_compat_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BOOKKIT_LLM_BASE_URL", "http://localhost:9999/v1/")
    monkeypatch.setenv("BOOKKIT_MODEL", "my-model")
    w = OpenAICompatWriter()
    assert w.base_url == "http://localhost:9999/v1"  # trailing slash stripped
    assert w.model == "my-model"


def test_openai_compat_requires_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("BOOKKIT_LLM_BASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="BOOKKIT_LLM_BASE_URL"):
        OpenAICompatWriter().complete("sys", "user")
