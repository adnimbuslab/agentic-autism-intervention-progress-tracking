"""LangGraph observation pipeline — stateful graph for extraction, validation,
routing, and terminal disposition.  Nodes are pure state transformers; DB
persistence is handled by observation_service.py which consumes the result."""

from __future__ import annotations

from datetime import date
from typing import TypedDict

from langgraph.graph import END, StateGraph

from src.backend.config import settings
from src.backend.ml.abstention_router import AbstentionRouter
from src.backend.ml.extraction import get_extraction_provider
from src.backend.ml.extraction.schemas import ExtractionRequest, ExtractionResult, SourceType
from src.backend.ml.schemas import RoutingDecision, ValidationResult
from src.backend.ml.validation_engine import ValidationEngine
from src.backend.schemas.observation_schema import ContributorRole, Setting


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------


class ObservationWorkflowState(TypedDict):
    # Input
    observation_id: str
    raw_text: str
    child_id: str
    session_id: str
    source_type: str
    setting: str
    contributor_role: str
    observation_date: str
    goal_ids: list[str]
    clarification_history: list[dict]

    # Pipeline outputs
    extraction_result: dict | None
    validation_result: dict | None
    routing_decision: str | None
    clarification_questions: list[str]
    structured_record: dict | None

    # Status
    status: str
    error: str | None


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


async def extract_node(state: ObservationWorkflowState) -> dict:
    try:
        provider = get_extraction_provider(
            settings.extraction_provider,
            **settings.extraction_provider_kwargs,
        )
        request = ExtractionRequest(
            source_type=SourceType(state["source_type"]),
            text=state["raw_text"],
            child_id=state["child_id"],
            session_id=state["session_id"],
            contributor_role=ContributorRole(state["contributor_role"]),
            observation_date=date.fromisoformat(state["observation_date"]),
            setting=Setting(state["setting"]),
            goal_ids=state.get("goal_ids", []),
            clarification_history=state.get("clarification_history", []),
        )
        result = await provider.extract(request)
        return {
            "extraction_result": result.model_dump(mode="json"),
            "status": "extracting",
        }
    except Exception as exc:
        return {
            "extraction_result": None,
            "status": "failed",
            "error": str(exc),
            "routing_decision": RoutingDecision.REJECT.value,
        }


# @spec EXTRACT-003
async def validate_node(state: ObservationWorkflowState) -> dict:
    if state.get("error") or state.get("extraction_result") is None:
        return {
            "validation_result": None,
            "status": state.get("status", "failed"),
        }

    extraction = ExtractionResult.model_validate(state["extraction_result"])
    engine = ValidationEngine()

    if extraction.observations:
        validation = engine.validate(
            extraction.observations[0],
            goal_ids=state.get("goal_ids"),
        )
    else:
        validation = ValidationResult(
            is_valid=False,
            routing=RoutingDecision.REJECT,
            messages=["No observations extracted"],
        )

    return {
        "validation_result": validation.model_dump(mode="json"),
        "status": "validating",
    }


async def route_node(state: ObservationWorkflowState) -> dict:
    if state.get("error") or state.get("extraction_result") is None:
        return {
            "routing_decision": RoutingDecision.REJECT.value,
            "clarification_questions": [],
            "status": "routed",
        }

    extraction = ExtractionResult.model_validate(state["extraction_result"])
    validation = ValidationResult.model_validate(state["validation_result"])

    router = AbstentionRouter()
    decision = router.route(extraction, validation)

    questions: list[str] = []
    if decision == RoutingDecision.CLARIFY and extraction.observations:
        questions = router.generate_clarification_questions(
            extraction.observations[0], validation
        )

    return {
        "routing_decision": decision.value,
        "clarification_questions": questions,
        "status": "routed",
    }


async def accept_node(state: ObservationWorkflowState) -> dict:
    extraction = ExtractionResult.model_validate(state["extraction_result"])
    record = None
    if extraction.observations:
        record = extraction.observations[0].model_dump(mode="json")
    return {
        "structured_record": record,
        "status": "accepted",
    }


async def clarify_node(state: ObservationWorkflowState) -> dict:
    return {"status": "clarifying"}


async def retain_node(state: ObservationWorkflowState) -> dict:
    extraction = ExtractionResult.model_validate(state["extraction_result"])
    record = None
    if extraction.observations:
        record = extraction.observations[0].model_dump(mode="json")
    return {
        "structured_record": record,
        "status": "retained_with_unknown",
    }


async def review_node(state: ObservationWorkflowState) -> dict:
    extraction = ExtractionResult.model_validate(state["extraction_result"])
    record = None
    if extraction.observations:
        record = extraction.observations[0].model_dump(mode="json")
    return {
        "structured_record": record,
        "status": "interventionist_review",
    }


async def reject_node(state: ObservationWorkflowState) -> dict:
    return {
        "structured_record": None,
        "status": "rejected",
    }


# ---------------------------------------------------------------------------
# Conditional edge
# ---------------------------------------------------------------------------


# @spec ABSTAIN-020
def route_edge(state: ObservationWorkflowState) -> str:
    decision = state.get("routing_decision")
    mapping = {
        RoutingDecision.ACCEPT.value: "accept",
        RoutingDecision.CLARIFY.value: "clarify",
        RoutingDecision.RETAIN_WITH_UNKNOWN.value: "retain",
        RoutingDecision.INTERVENTIONIST_REVIEW.value: "review",
        RoutingDecision.REJECT.value: "reject",
    }
    return mapping.get(decision, "reject")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

_graph = StateGraph(ObservationWorkflowState)

_graph.add_node("extract", extract_node)
_graph.add_node("validate", validate_node)
_graph.add_node("route", route_node)
_graph.add_node("accept", accept_node)
_graph.add_node("clarify", clarify_node)
_graph.add_node("retain", retain_node)
_graph.add_node("review", review_node)
_graph.add_node("reject", reject_node)

_graph.set_entry_point("extract")
_graph.add_edge("extract", "validate")
_graph.add_edge("validate", "route")
_graph.add_conditional_edges("route", route_edge, {
    "accept": "accept",
    "clarify": "clarify",
    "retain": "retain",
    "review": "review",
    "reject": "reject",
})
_graph.add_edge("accept", END)
_graph.add_edge("clarify", END)
_graph.add_edge("retain", END)
_graph.add_edge("review", END)
_graph.add_edge("reject", END)

observation_workflow = _graph.compile()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def run_observation_workflow(
    state: ObservationWorkflowState,
) -> ObservationWorkflowState:
    return await observation_workflow.ainvoke(state)  # type: ignore[return-value]
