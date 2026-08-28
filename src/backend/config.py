from __future__ import annotations

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/autism_tracker"

    # Auth
    jwt_secret_key: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 60

    # Extraction Provider
    extraction_provider: Literal["temporary_llm", "ollama", "finetuned_model"] = "ollama"
    anthropic_api_key: str = ""

    # Ollama / OpenAI-compatible endpoint (used by the "ollama" extraction
    # provider and, when reporting_provider="ollama", by ReportingClient)
    ollama_base_url: str = "http://127.0.0.1:11434/v1"
    ollama_api_key: str = "ollama"  # Ollama ignores this; the OpenAI client requires a non-empty string
    ollama_model: str = "llama3.2:latest"

    @property
    def extraction_provider_kwargs(self) -> dict[str, str]:
        """Constructor kwargs for the currently-configured extraction provider."""
        if self.extraction_provider == "ollama":
            return {
                "base_url": self.ollama_base_url,
                "api_key": self.ollama_api_key,
                "model": self.ollama_model,
            }
        return {"api_key": self.anthropic_api_key}

    # Observation workflow
    clarification_max_turns: int = 3

    # Adequacy thresholds
    adequacy_min_observations: int = 5
    adequacy_limited_observations: int = 3
    adequacy_field_completeness_threshold: float = 0.7
    adequacy_temporal_cluster_max_ratio: float = 0.8

    # Reporting
    reporting_provider: Literal["anthropic", "ollama"] = "ollama"
    reporting_model: str = "claude-sonnet-4-20250514"
    reporting_prompt_version: str = "1.0"

    # Application
    app_env: Literal["development", "staging", "production"] = "development"
    app_debug: bool = True
    cors_origins: str = "http://localhost:3000"

    # Data Pipeline
    data_raw_dir: str = "data/raw"
    data_output_dir: str = "data/output"

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]


settings = Settings()
