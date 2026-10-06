"""Tests for batch construction -- provider routing and admission policy.

The routing test exists because a frontier comparator arm is only meaningful if
it enters the batch through the same contract as the local models. If the
Claude arm needed its own code path, the resulting numbers would compare two
pipelines rather than two models.
"""

from __future__ import annotations

from src.backend.ml.extraction.ollama_llm import OllamaExtractionProvider
from src.backend.ml.extraction.temporary_llm import TemporaryLLMExtractionProvider
from tests.eval.extraction.build_annotation_batch import build_provider


class TestProviderRouting:
    def test_a_claude_name_routes_to_the_anthropic_provider(self) -> None:
        provider = build_provider("claude-opus-5")

        assert isinstance(provider, TemporaryLLMExtractionProvider)
        assert provider.get_info().model_id == "claude-opus-5"

    def test_any_other_name_routes_to_ollama(self) -> None:
        provider = build_provider("qwen2.5:7b")

        assert isinstance(provider, OllamaExtractionProvider)

    def test_both_providers_satisfy_the_same_contract(self) -> None:
        """The property that lets local and frontier arms share one run."""
        local = build_provider("qwen2.5:7b")
        frontier = build_provider("claude-opus-5")

        for provider in (local, frontier):
            assert hasattr(provider, "extract")
            assert hasattr(provider, "get_info")

    def test_a_missing_api_key_is_not_an_error_at_construction(self, monkeypatch) -> None:
        """The SDK resolves credentials from several sources, not just the env var."""
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

        assert isinstance(build_provider("claude-opus-5"), TemporaryLLMExtractionProvider)
