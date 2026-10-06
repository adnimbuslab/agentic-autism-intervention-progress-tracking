"""Extraction provider package — pluggable interface and concrete implementations."""

from __future__ import annotations

from src.backend.ml.extraction.base import ExtractionProvider
from src.backend.ml.extraction.finetuned_model import FineTunedExtractionProvider
from src.backend.ml.extraction.ollama_llm import OllamaExtractionProvider
from src.backend.ml.extraction.schemas import (
    ExtractionRequest,
    ExtractionResult,
    ExtractionStatus,
    ProviderInfo,
    SourceType,
)
from src.backend.ml.extraction.temporary_llm import TemporaryLLMExtractionProvider

__all__ = [
    "ExtractionProvider",
    "ExtractionRequest",
    "ExtractionResult",
    "ExtractionStatus",
    "FineTunedExtractionProvider",
    "OllamaExtractionProvider",
    "ProviderInfo",
    "SourceType",
    "TemporaryLLMExtractionProvider",
    "get_extraction_provider",
]


def get_extraction_provider(provider_type: str, **kwargs: object) -> ExtractionProvider:
    """Factory for creating extraction providers by type string."""
    if provider_type == "temporary_llm":
        return TemporaryLLMExtractionProvider(**kwargs)  # type: ignore[arg-type]
    if provider_type == "ollama":
        return OllamaExtractionProvider(**kwargs)  # type: ignore[arg-type]
    if provider_type == "finetuned_model":
        return FineTunedExtractionProvider()
    raise ValueError(f"Unknown extraction provider type: {provider_type}")
