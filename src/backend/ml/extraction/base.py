"""Extraction provider protocol — the pluggable interface for structured extraction."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.backend.ml.extraction.schemas import (
    ExtractionRequest,
    ExtractionResult,
    ProviderInfo,
)


@runtime_checkable
class ExtractionProvider(Protocol):
    """Protocol for structured observation extraction from text.

    Both TemporaryLLMExtractionProvider and FineTunedExtractionProvider
    implement this interface, returning the same ExtractionResult contract.
    """

    async def extract(self, request: ExtractionRequest) -> ExtractionResult:
        """Extract structured observations from the source text.

        App-known metadata fields (child_id, session_id, contributor_role,
        observation_date, setting) from the request must be preserved in
        the resulting StructuredObservation — they must not be generated
        by the LLM.
        """
        ...

    def get_info(self) -> ProviderInfo:
        """Return metadata about this provider."""
        ...
