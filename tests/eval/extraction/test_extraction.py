from __future__ import annotations

from datetime import date

import pytest

from src.backend.ml.extraction import (
    FineTunedExtractionProvider,
    TemporaryLLMExtractionProvider,
    get_extraction_provider,
)
from src.backend.ml.extraction.schemas import (
    ExtractionRequest,
    SourceType,
)
from src.backend.schemas.observation_schema import ContributorRole, Setting


def _make_request() -> ExtractionRequest:
    return ExtractionRequest(
        source_type=SourceType.CONVERSATIONAL,
        text="Child waved hello.",
        child_id="child_1",
        session_id="session_1",
        contributor_role=ContributorRole.INTERVENTIONIST,
        observation_date=date(2024, 1, 15),
        setting=Setting.CLINIC,
    )


@pytest.mark.eval
class TestProviderFactory:
    def test_factory_temporary_llm(self) -> None:
        provider = get_extraction_provider("temporary_llm", api_key="test-key")
        assert isinstance(provider, TemporaryLLMExtractionProvider)

    def test_factory_finetuned(self) -> None:
        provider = get_extraction_provider("finetuned_model")
        assert isinstance(provider, FineTunedExtractionProvider)

    def test_factory_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown extraction provider"):
            get_extraction_provider("nonexistent")


@pytest.mark.eval
class TestFineTunedStub:
    # @spec EXTRACT-030
    async def test_finetuned_extract_raises(self) -> None:
        provider = FineTunedExtractionProvider()
        with pytest.raises(NotImplementedError, match="not yet available"):
            await provider.extract(_make_request())

    # @spec EXTRACT-031
    def test_finetuned_unavailable(self) -> None:
        provider = FineTunedExtractionProvider()
        info = provider.get_info()
        assert info.is_available is False
        assert info.provider_type == "finetuned_model"


@pytest.mark.eval
class TestTemporaryLLMProviderInfo:
    def test_provider_info_fields(self) -> None:
        provider = TemporaryLLMExtractionProvider(api_key="test-key")
        info = provider.get_info()
        assert info.name == "temporary_llm_extraction"
        assert info.provider_type == "temporary_llm"
        assert info.is_available is True
        assert info.version == "1.0.0"

    def test_custom_model_in_info(self) -> None:
        provider = TemporaryLLMExtractionProvider(api_key="test-key", model="claude-opus-4-20250514")
        info = provider.get_info()
        assert info.model_id == "claude-opus-4-20250514"
