"""Tests for LangGraph observation workflow — all 5 routing paths and error handling."""

from __future__ import annotations

from datetime import date
from unittest.mock import AsyncMock, patch

import pytest

from src.backend.ml.extraction.schemas import ExtractionResult, ExtractionStatus
from src.backend.ml.schemas import RoutingDecision, ValidationResult
from src.backend.schemas.observation_schema import (
    ContributorRole,
    Domain,
    Modality,
    Outcome,
    PromptLevel,
    Setting,
    StructuredObservation,
)
from src.backend.services.observation_workflow import (
    ObservationWorkflowState,
    accept_node,
    clarify_node,
    extract_node,
    reject_node,
    retain_node,
    review_node,
    route_edge,
    route_node,
    run_observation_workflow,
    validate_node,
)


def _base_state(**overrides) -> ObservationWorkflowState:
    state: ObservationWorkflowState = {
        "observation_id": "obs-1",
        "raw_text": "The child pointed at the toy and said 'car'.",
        "child_id": "child-1",
        "session_id": "session-1",
        "source_type": "conversational",
        "setting": "home",
        "contributor_role": "interventionist",
        "observation_date": str(date.today()),
        "goal_ids": [],
        "clarification_history": [],
        "extraction_result": None,
        "validation_result": None,
        "routing_decision": None,
        "clarification_questions": [],
        "structured_record": None,
        "status": "pending",
        "error": None,
    }
    state.update(overrides)
    return state


def _mock_extraction_result():
    obs_data = StructuredObservation(
        child_id="child-1",
        session_id="session-1",
        domain=Domain.SOCIAL_COMMUNICATION,
        behavior="pointed at toy and said 'car'",
        modality=Modality.VERBAL,
        prompt_level=PromptLevel.INDEPENDENT,
        outcome=Outcome.CORRECT,
        setting=Setting.HOME,
        contributor_role=ContributorRole.INTERVENTIONIST,
        observation_date=str(date.today()),
    )
    return ExtractionResult(
        status=ExtractionStatus.SUCCESS,
        observations=[obs_data],
        provider="temporary_llm",
        model="claude-sonnet-4-20250514",
        prompt_version="1.0",
    )


class TestExtractNode:
    async def test_successful_extraction(self):
        mock_provider = AsyncMock()
        mock_result = _mock_extraction_result()
        mock_provider.extract = AsyncMock(return_value=mock_result)

        with patch(
            "src.backend.services.observation_workflow.get_extraction_provider",
            return_value=mock_provider,
        ):
            state = _base_state()
            result = await extract_node(state)

        assert result["status"] == "extracting"
        assert result["extraction_result"] is not None

    async def test_extraction_failure_sets_error(self):
        with patch(
            "src.backend.services.observation_workflow.get_extraction_provider",
            side_effect=RuntimeError("API unavailable"),
        ):
            state = _base_state()
            result = await extract_node(state)

        assert result["status"] == "failed"
        assert result["error"] is not None
        assert result["routing_decision"] == "reject"


class TestValidateNode:
    async def test_valid_extraction(self):
        extraction = _mock_extraction_result()
        state = _base_state(
            extraction_result=extraction.model_dump(mode="json"),
            status="extracting",
        )
        result = await validate_node(state)
        assert result["status"] == "validating"
        assert result["validation_result"] is not None

    async def test_skips_when_no_extraction(self):
        state = _base_state(extraction_result=None, error="extraction failed")
        result = await validate_node(state)
        assert result["validation_result"] is None

    async def test_no_observations_extracted(self):
        extraction = ExtractionResult(
            status=ExtractionStatus.FAILED,
            observations=[],
            provider="temporary_llm",
            model="claude-sonnet-4-20250514",
            prompt_version="1.0",
        )
        state = _base_state(
            extraction_result=extraction.model_dump(mode="json"),
            status="extracting",
        )
        result = await validate_node(state)
        val = result["validation_result"]
        assert val is not None
        parsed = ValidationResult.model_validate(val)
        assert parsed.is_valid is False
        assert parsed.routing == RoutingDecision.REJECT

    # @spec EXTRACT-003
    async def test_multi_observation_only_first_is_validated(self):
        """With 2+ observations, only observations[0] is passed to
        ValidationEngine.validate(); observations[1:] must not influence
        the routing decision."""
        incomplete_first = StructuredObservation(
            child_id="child-1",
            session_id="session-1",
            domain=None,
            behavior=None,
            modality=None,
            prompt_level=None,
            outcome=None,
            setting=Setting.HOME,
            contributor_role=ContributorRole.INTERVENTIONIST,
            observation_date=str(date.today()),
        )
        complete_second = _mock_extraction_result().observations[0]

        extraction = ExtractionResult(
            status=ExtractionStatus.SUCCESS,
            observations=[incomplete_first, complete_second],
            provider="temporary_llm",
            model="claude-sonnet-4-20250514",
            prompt_version="1.0",
        )
        state = _base_state(
            extraction_result=extraction.model_dump(mode="json"),
            status="extracting",
        )
        result = await validate_node(state)
        parsed = ValidationResult.model_validate(result["validation_result"])

        # observations[0] is missing both critical fields -> REJECT.
        # If observations[1] (fully populated) had been validated instead,
        # routing would be ACCEPT -- so REJECT here proves only the first
        # element was passed to the Deterministic Validation Engine.
        assert parsed.routing == RoutingDecision.REJECT


class TestRouteNode:
    async def test_routes_with_valid_state(self):
        extraction = _mock_extraction_result()
        validation = ValidationResult(
            is_valid=True,
            routing=RoutingDecision.ACCEPT,
        )
        state = _base_state(
            extraction_result=extraction.model_dump(mode="json"),
            validation_result=validation.model_dump(mode="json"),
            status="validating",
        )

        with patch(
            "src.backend.services.observation_workflow.AbstentionRouter"
        ) as MockRouter:
            MockRouter.return_value.route.return_value = RoutingDecision.ACCEPT
            result = await route_node(state)

        assert result["routing_decision"] == "accept"
        assert result["status"] == "routed"

    async def test_routes_to_reject_on_error(self):
        state = _base_state(error="something broke", extraction_result=None)
        result = await route_node(state)
        assert result["routing_decision"] == "reject"


class TestRouteEdge:
    def test_maps_accept(self):
        state = _base_state(routing_decision="accept")
        assert route_edge(state) == "accept"

    def test_maps_clarify(self):
        state = _base_state(routing_decision="clarify")
        assert route_edge(state) == "clarify"

    def test_maps_retain(self):
        state = _base_state(routing_decision="retain_with_unknown")
        assert route_edge(state) == "retain"

    def test_maps_review(self):
        state = _base_state(routing_decision="interventionist_review")
        assert route_edge(state) == "review"

    def test_maps_reject(self):
        state = _base_state(routing_decision="reject")
        assert route_edge(state) == "reject"

    # @spec ABSTAIN-020
    def test_unknown_defaults_to_reject(self):
        state = _base_state(routing_decision="unknown_value")
        assert route_edge(state) == "reject"


class TestTerminalNodes:
    async def test_accept_node_produces_record(self):
        extraction = _mock_extraction_result()
        state = _base_state(
            extraction_result=extraction.model_dump(mode="json"),
        )
        result = await accept_node(state)
        assert result["status"] == "accepted"
        assert result["structured_record"] is not None

    async def test_clarify_node_sets_clarifying(self):
        state = _base_state()
        result = await clarify_node(state)
        assert result["status"] == "clarifying"

    async def test_retain_node_produces_record(self):
        extraction = _mock_extraction_result()
        state = _base_state(
            extraction_result=extraction.model_dump(mode="json"),
        )
        result = await retain_node(state)
        assert result["status"] == "retained_with_unknown"
        assert result["structured_record"] is not None

    async def test_review_node_produces_record(self):
        extraction = _mock_extraction_result()
        state = _base_state(
            extraction_result=extraction.model_dump(mode="json"),
        )
        result = await review_node(state)
        assert result["status"] == "interventionist_review"
        assert result["structured_record"] is not None

    async def test_reject_node_no_record(self):
        state = _base_state()
        result = await reject_node(state)
        assert result["status"] == "rejected"
        assert result["structured_record"] is None


class TestEndToEndWorkflow:
    async def test_full_accept_path(self):
        mock_provider = AsyncMock()
        mock_result = _mock_extraction_result()
        mock_provider.extract = AsyncMock(return_value=mock_result)

        with (
            patch(
                "src.backend.services.observation_workflow.get_extraction_provider",
                return_value=mock_provider,
            ),
            patch(
                "src.backend.services.observation_workflow.AbstentionRouter"
            ) as MockRouter,
        ):
            MockRouter.return_value.route.return_value = RoutingDecision.ACCEPT

            state = _base_state()
            final_state = await run_observation_workflow(state)

        assert final_state["status"] == "accepted"
        assert final_state["structured_record"] is not None
        assert final_state["routing_decision"] == "accept"

    async def test_full_reject_path(self):
        mock_provider = AsyncMock()
        extraction = ExtractionResult(
            status=ExtractionStatus.FAILED,
            observations=[],
            provider="temporary_llm",
            model="claude-sonnet-4-20250514",
            prompt_version="1.0",
        )
        mock_provider.extract = AsyncMock(return_value=extraction)

        with (
            patch(
                "src.backend.services.observation_workflow.get_extraction_provider",
                return_value=mock_provider,
            ),
            patch(
                "src.backend.services.observation_workflow.AbstentionRouter"
            ) as MockRouter,
        ):
            MockRouter.return_value.route.return_value = RoutingDecision.REJECT

            state = _base_state()
            final_state = await run_observation_workflow(state)

        assert final_state["status"] == "rejected"
        assert final_state["structured_record"] is None

    async def test_full_clarify_path(self):
        mock_provider = AsyncMock()
        mock_result = _mock_extraction_result()
        mock_provider.extract = AsyncMock(return_value=mock_result)

        with (
            patch(
                "src.backend.services.observation_workflow.get_extraction_provider",
                return_value=mock_provider,
            ),
            patch(
                "src.backend.services.observation_workflow.AbstentionRouter"
            ) as MockRouter,
        ):
            router_inst = MockRouter.return_value
            router_inst.route.return_value = RoutingDecision.CLARIFY
            router_inst.generate_clarification_questions.return_value = [
                "Where did this happen?"
            ]

            state = _base_state()
            final_state = await run_observation_workflow(state)

        assert final_state["status"] == "clarifying"
        assert final_state["routing_decision"] == "clarify"

    async def test_extraction_error_reaches_reject(self):
        with patch(
            "src.backend.services.observation_workflow.get_extraction_provider",
            side_effect=RuntimeError("boom"),
        ):
            state = _base_state()
            final_state = await run_observation_workflow(state)

        assert final_state["status"] == "rejected"
        assert final_state["error"] is not None
