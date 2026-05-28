"""Tests for the streaming path through providers and agents."""

from pathlib import Path
from typing import Generator

import pytest

from src.agents.base import BaseAgent
from src.agents.builder import BuilderAgent
from src.orchestrator import BuildOrchestrator
from src.providers.base import BaseProvider, ProviderConfig


class FakeStreamingProvider(BaseProvider):
    def __init__(self, chunks=None, raise_on_stream=None):
        super().__init__(ProviderConfig(name="fake", model="test"))
        self._chunks = list(chunks or [])
        self._raise_on_stream = raise_on_stream
        self._fallback_response = "".join(c for c in self._chunks if c)

    def chat(self, messages, system="", **options):
        return self._fallback_response

    def stream(self, messages, system="", **options) -> Generator[str, None, None]:
        if self._raise_on_stream:
            raise self._raise_on_stream
        yield from self._chunks


def test_invoke_streaming_accumulates_and_invokes_callback(tmp_path):
    provider = FakeStreamingProvider(chunks=["hello ", "world", "!"])
    agent = BaseAgent(provider, project_root=tmp_path)

    received: list[str] = []
    result = agent.invoke_streaming("ping", on_chunk=received.append)

    assert result == "hello world!"
    assert received == ["hello ", "world", "!"]


def test_invoke_streaming_falls_back_when_stream_fails_immediately(tmp_path):
    # Stream raises before yielding anything → should fall back to chat()
    provider = FakeStreamingProvider(
        chunks=["fallback response"],
        raise_on_stream=ConnectionError("Connection refused"),
    )
    agent = BaseAgent(provider, project_root=tmp_path)

    result = agent.invoke_streaming("ping")
    assert result == "fallback response"


def test_invoke_streaming_skips_empty_chunks(tmp_path):
    provider = FakeStreamingProvider(chunks=["a", "", "b", None])
    agent = BaseAgent(provider, project_root=tmp_path)

    received: list[str] = []
    result = agent.invoke_streaming("ping", on_chunk=received.append)

    assert result == "ab"
    assert received == ["a", "b"]


def test_invoke_streaming_swallows_callback_errors(tmp_path):
    provider = FakeStreamingProvider(chunks=["a", "b", "c"])
    agent = BaseAgent(provider, project_root=tmp_path)

    def bad_callback(_chunk):
        raise RuntimeError("callback exploded")

    # Should not raise — callback errors are isolated from the stream
    result = agent.invoke_streaming("ping", on_chunk=bad_callback)
    assert result == "abc"


def test_stream_with_retry_recovers_from_transient_error():
    class FlakyProvider(BaseProvider):
        def __init__(self):
            super().__init__(ProviderConfig(name="fake", model="test"))
            self.calls = 0

        def chat(self, messages, system="", **options):
            return ""

        def stream(self, messages, system="", **options):
            self.calls += 1
            if self.calls == 1:
                raise ConnectionError("Connection refused")
            yield "ok"

    p = FlakyProvider()
    chunks = list(p.stream_with_retry([{"role": "user", "content": "hi"}]))
    assert chunks == ["ok"]
    assert p.calls == 2


def test_builder_backend_streaming_forwards_chunks(tmp_path):
    response = (
        '{"files":[{"path":"backend/main.py","content":"from fastapi import FastAPI\\n"}],'
        '"contracts":{"api":[],"models":[],"events":[]}}'
    )
    provider = FakeStreamingProvider(chunks=[response[:20], response[20:]])
    agent = BuilderAgent(provider, project_root=tmp_path)
    received: list[str] = []

    result = agent.build_task(
        {"specialization": "backend", "name": "Build backend", "files": ["backend/main.py"]},
        spec="# Project: Test",
        rules="",
        decisions={"stack": {"framework": "fastapi"}},
        on_chunk=received.append,
    )

    assert result == response
    assert "".join(received) == response


def test_orchestrator_stream_callback_disabled_during_parallel_build():
    class FakeUI:
        def __init__(self):
            self.started = False

        def stream_stop(self):
            pass

        def stream_start(self, _label):
            self.started = True

        def stream_chunk(self, _text):
            pass

    orch = BuildOrchestrator.__new__(BuildOrchestrator)
    orch.ui = FakeUI()
    orch._parallel_build_active = True

    callback = orch._build_stream_callback("backend", 1)

    assert callback is None
    assert orch.ui.started is False
