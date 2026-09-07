"""A ranking judge backed by a local model served through Ollama.

MARS had no judge implementation outside the unit-test stub, so the pipeline
could be reasoned about but never run. This is the smallest thing that closes
that gap while keeping every guarantee the surrounding code depends on.

Three properties matter more than the prompt wording:

  1. **Only `judge_payload()` is sent.** Aliases and normalized field values,
     nothing else. Internal ids, generator identity, generator confidence and
     multiplicity are all withheld by that method, and this class must not
     reach around it -- a judge that could see which model produced a candidate
     could prefer it for a reason other than the evidence.

  2. **The judge orders; it never authors.** It is asked for a permutation of
     the aliases it was shown and nothing else. A response carrying field
     values is not mined for the part that looks like a ranking; it is returned
     as-is and `parse_judge_response` rejects it.

  3. **A malformed answer is a rejection, not an exception.** Network failures,
     truncated output, prose instead of JSON -- all return a value that fails
     validation, so MARS abstains through its own typed reason codes rather
     than crashing the extraction.

Ranking quality is a property of the model, not of this class. A weak judge
produces a weak ordering, which fusion and the agreement gate are there to
absorb.
"""

from __future__ import annotations

import json
from typing import Any

from openai import APIError, AsyncOpenAI

from src.backend.ml.extraction.mars.blinding import JudgePresentation

JUDGE_PROMPT_VERSION = "mars-judge-v1"

SYSTEM_PROMPT = """You rank candidate structured observations extracted from a \
transcript of a child's session.

You are given the transcript and several candidates, each labelled with an \
opaque alias. Judge only how well each candidate's field values are supported \
by the transcript.

Rank every candidate from best-supported to worst-supported.

Reply with a JSON array of the alias strings in that order and nothing else. \
Include every alias exactly once. Do not include field values, explanations, \
or any other text.

Example reply format: ["kv7", "b2m", "q9x"]"""


def build_judge_user_prompt(source_text: str, presentation: JudgePresentation) -> str:
    """Render the transcript and the blinded candidate set.

    Content comes from `judge_payload()` verbatim; this function chooses layout
    only. Anything it added from the candidates themselves would be a leak.
    """
    candidates = json.dumps(presentation.judge_payload(), indent=2, sort_keys=True)
    aliases = [entry["alias"] for entry in presentation.judge_payload()]
    return (
        f"Transcript:\n{source_text}\n\n"
        f"Candidates:\n{candidates}\n\n"
        f"Rank these {len(aliases)} aliases: {aliases}\n"
        "Reply with the JSON array only."
    )


def parse_alias_array(content: str | None) -> object:
    """Pull a JSON array of aliases out of a model reply.

    Returns whatever it finds, including obviously wrong shapes -- validation
    belongs to `parse_judge_response`, which owns the rejection vocabulary.
    Returning ``None`` here means nothing array-shaped was present at all.
    """
    if not content:
        return None
    text = content.strip()
    # Models commonly wrap JSON in a fenced block or a sentence. Taking the
    # outermost bracket pair is enough to undo that without interpreting the
    # content: a reply with no brackets, or with prose inside them, still
    # fails validation downstream.
    start, end = text.find("["), text.rfind("]")
    if start == -1 or end == -1 or end < start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


class OllamaRankingJudge:
    """Ranks a blinded candidate set with a locally served model."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        temperature: float = 0.0,
        max_tokens: int = 256,
    ) -> None:
        self._client = AsyncOpenAI(base_url=base_url, api_key=api_key)
        self._model = model
        # Ordering should depend on the evidence and the seeded presentation,
        # not on sampling noise; run-to-run variation here would show up as
        # judge disagreement that no disagreement actually caused.
        self._temperature = temperature
        # A ranking is a short array. A cap this low also bounds the damage
        # when a model ignores the format and starts narrating.
        self._max_tokens = max_tokens

    @property
    def model(self) -> str:
        return self._model

    async def rank(
        self, *, source_text: str, presentation: JudgePresentation
    ) -> object:
        """Return the judge's ordering, or a value that will fail validation."""
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": build_judge_user_prompt(source_text, presentation),
                    },
                ],
            )
        except APIError:
            # An unreachable or erroring judge is a judge that did not answer.
            # Returning None routes it through the same rejection path as a
            # malformed answer, so MARS's response-count gate sees one
            # consistent notion of "unusable".
            return None
        except Exception:
            return None

        choices: list[Any] = getattr(response, "choices", None) or []
        if not choices:
            return None
        return parse_alias_array(choices[0].message.content)
