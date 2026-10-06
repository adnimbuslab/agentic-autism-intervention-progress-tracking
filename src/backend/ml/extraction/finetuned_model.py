"""Fine-tuned foundation model extraction provider stub."""

from __future__ import annotations

from src.backend.ml.extraction.schemas import (
    ExtractionRequest,
    ExtractionResult,
    ProviderInfo,
)


class FineTunedExtractionProvider:
    """Placeholder for the future fine-tuned extraction provider."""

    # @spec EXTRACT-030
    async def extract(self, request: ExtractionRequest) -> ExtractionResult:
        """Not yet implemented -- awaiting fine-tuned model training."""
        raise NotImplementedError("Fine-tuned model not yet available")

    # @spec EXTRACT-031
    def get_info(self) -> ProviderInfo:
        """Return metadata indicating this provider is unavailable."""
        return ProviderInfo(
            name="finetuned_extraction",
            provider_type="finetuned_model",
            model_id="not_available",
            version="0.0.0",
            is_available=False,
        )
