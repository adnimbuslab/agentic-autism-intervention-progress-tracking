# Answers: Technical Clarification Questions (AI / LLM and Reranking)

Each answer has two parts: **Answer** — the fact, with the repository path that
holds it — and **In plain terms** — what it means without jargon.

Recorded state: commit `6163d13`, 2026-09-19. Where a number below can change
if something is re-run, the artefact that holds it is named.

Four answers carry a correction or a caveat rather than a plain fact: **Q6**
(judge token budget had to be raised for a reasoning model), **Q12** (the
threshold is not the operative gate on a two-judge panel), **Q15** (the
four-generator MARS run has not been done), and **Q16** (the first reporting
configuration failed for a decoding reason, not a capability reason).

---

## A. Model use and inference configuration

### Q1 — Training / fine-tuning confirmation

**Answer.** No model was trained, fine-tuned, LoRA/QLoRA adapted, or updated in
any way using the annotation dataset or any other data. Every model was used as
a pretrained, instruction-tuned checkpoint driven by prompts only. Extraction is
a single forced tool call per segment; reranking is inference-time ranking by
fixed judges. The codebase contains a `FineTunedExtractionProvider` placeholder
(`src/backend/ml/extraction/finetuned_model.py`) reserved for a later phase; it
was not used and holds no trained weights. `data/training/` is empty and
reserved for the same later phase.

**In plain terms.** Nothing learned from the data. The models arrived as-is and
left as-is; we only asked them questions. The annotations were used to *grade*
the models, never to *teach* them.

### Q2 — Exact generator models

**Answer.** All served by Ollama 0.33.3. Digests are Ollama manifest IDs.

| Role | Tag | Digest | Parameters | Quantization | Context |
|---|---|---|---|---|---|
| generator | `llama3.2:latest` | `a80c4f17acd5` | 3.2B | Q4_K_M | 131072 |
| generator | `qwen2.5:3b` | `357c53fb659c` | 3.1B | Q4_K_M | 32768 |
| generator | `qwen2.5:7b` | `845dbda0ea48` | 7.6B | Q4_K_M | 32768 |
| generator (added later) | `qwen3:14b` | `bdbd181c33f2` | 14.8B | Q4_K_M | 40960 |
| judge only | `mistral:latest` | `6577803aa9a0` | 7.2B | Q4_K_M | 32768 |

**Note for the manuscript:** `llama3.2:latest` and `mistral:latest` use the
floating `latest` tag, which is not reproducible over time. The digests above
pin the exact artefacts used and should be reported instead of the tags.

**In plain terms.** Four models did the extraction, ranging from small (3B) to
large (14.8B). A fifth only acted as a referee. All are compressed ("quantized")
to about 4 bits per weight, which is how they fit on one laptop. "Latest" is a
moving label, so we give the fixed fingerprints.

### Q3 — Inference environment

**Answer.** All models ran locally on one machine: Apple M5 Pro, 15 cores,
24 GB unified memory, macOS 26.6.2 (build 25G83), Ollama 0.33.3, Python 3.12.12.
GPU is the integrated Apple GPU sharing the 24 GB unified memory; there is no
discrete VRAM. All four generators, all judges, and the reporting model ran on
this same hardware and runtime.

One operational note worth reporting: `qwen3:14b` occupies ~9.6 GB of the 24 GB,
and long runs were repeatedly terminated by memory pressure. Runs were made
resumable with checkpointing; this affected wall-clock time only, not results.

**In plain terms.** One laptop did everything, so no model had a hardware
advantage. The largest model nearly filled the machine's memory, so its runs had
to be done in chunks that could pick up where they left off.

---

## B. Extraction prompt, schema, and admission logic

### Q4 — Extraction prompt

**Answer.** Built in `src/backend/ml/extraction/prompts.py`, version
`PROMPT_VERSION = "1.0.0"`, recorded on every extraction result.

- System prompt: `build_system_prompt()` — states the task, lists exactly the
  fields to extract, enumerates the valid values of each categorical field, and
  carries four rules: use null when the text does not clearly support a field;
  never fabricate or infer beyond the text; never diagnose, recommend treatment,
  or make causal claims; prefer a low-confidence answer with a stated abstention
  reason over a confident invented one.
- User prompt: `build_user_prompt_chat_segment()` — a short CHAT-format guide
  (speaker codes, dependent tiers `%spa`/`%act`/`%gpx`, `xxx` for
  unintelligible, `0` for an action-only turn) followed by the segment text.

The exact strings should be reproduced verbatim in a supplementary file; both
functions are deterministic given the segment.

**In plain terms.** The model is told what fields to fill, what values are
allowed, how to read the transcript format, and — most importantly — that
leaving a field blank is a correct answer when the transcript does not say.

### Q5 — Extraction output schema

**Answer.** `EXTRACTION_TOOL_SCHEMA` in the same file; canonical field
definitions in `src/backend/schemas/observation_schema.py`.

| Field | Allowed values |
|---|---|
| `domain` | social_communication, language, play, behavior, motor, cognitive, adaptive, sensory |
| `behavior` | free text |
| `modality` | verbal, gestural, sign, aac, written, multimodal, unknown |
| `prompt_level` | independent, gestural, verbal, model, partial_physical, full_physical, unknown |
| `outcome` | correct, incorrect, approximation, no_response, partial, unknown |

Every categorical field accepts JSON `null` in addition to its values. Three
states are kept distinct throughout and must not be conflated:

- **`null`** — the transcript supports no value here. A substantive finding.
- **`"unknown"`** — a category meaning the thing happened but the transcript
  does not show which kind. Different from `null`.
- **field absent / model returned nothing** — an abstention, recorded as
  `missing` at scoring time.

**In plain terms.** "There is nothing here to report", "something happened but I
can't tell what", and "I didn't answer" are three different things, and the
study counts them separately. That distinction is what makes it possible to
measure a model inventing a value.

### Q6 — Generation parameters

**Answer.** Extraction (`src/backend/ml/extraction/ollama_llm.py`) sends one
request per segment, one generation per segment, via Ollama's
OpenAI-compatible `/v1/chat/completions`:

| Parameter | Value |
|---|---|
| tool choice | forced: `{"type":"function","function":{"name":"record_observation"}}` |
| temperature | not set — Ollama default |
| top_p / top_k | not set |
| max tokens | not set — server default |
| context length | model default (per Q2) |
| stop sequences | none |
| seed | none set |
| generations per segment | 1 |
| schema-constrained decoding | no — constraint is via forced tool call |

Judges (`mars/ollama_judge.py`): `temperature = 0.0`, `max_tokens = 2048`,
`extra_body={"think": false}`, one generation per judge per segment.

**Two things must be reported here, not omitted.**

1. **No seed was set and temperature was left at default for extraction.** Runs
   are therefore not bit-reproducible. The recorded generator outputs are
   preserved verbatim in the batch artefacts and are replayed rather than
   regenerated everywhere downstream, so every reported result is reproducible
   from the recorded outputs; regenerating them from the models is not
   guaranteed to reproduce them.
2. **The judge token budget was raised from 256 to 2048 during the work.** At
   256, `qwen3:14b` — a reasoning model whose chain of thought is streamed
   against the same budget — exhausted the budget before emitting an answer and
   was discarded as unparseable on 165 of 165 rerank segments, while still
   appearing on the panel. The run containing that fault was discarded and
   re-run. `run_mars` now reports a per-judge discard rate; in the reported run
   the maximum is 1.8%.

**In plain terms.** Each segment was asked once, and the model was *required* to
answer in the fixed form rather than in prose. We did not fix a random seed, so
asking again could give slightly different answers — which is why we kept the
original answers and reuse those rather than re-asking. Separately: one referee
model "thinks out loud" before answering, and its thinking used up the whole
word budget, so it was silently returning nothing while still being counted as
a referee. We found it, raised the budget, and threw away the affected run.

### Q7 — Admission logic

**Answer.** Two predicates, deliberately different.

- **`reviewable`** (MARS runtime gate, `mars/candidates.py`): provider status is
  `SUCCESS` or `PARTIAL`, the response carries at least one observation, and
  that observation has at least one of `behavior` or `domain` populated.
  Rejection reasons are recorded per candidate: `status_not_reviewable`,
  `no_observations`, `structurally_inadmissible`.
- **`judgeable`** (batch-construction policy): any response carrying at least
  one populated extracted field, regardless of the status the provider assigned.

Status itself is set by the provider from the content it produced, not by the
model's self-report of success.

The batch was built under `judgeable` because the annotation task measures how
good extracted *values* are, and a response that filled every field while
self-reporting low confidence is something an annotator can judge. Admitting
only `reviewable` responses would have retained the segments each model found
easy and reported accuracy on those.

This choice is measurable and is reported: across 496 abstentions from the three
original generators, 494 (99.6%) still carried at least one populated field.

**In plain terms.** Two different bars. The strict bar is "would the live system
pass this on?" The wider bar is "is there anything here a human could grade?"
The study used the wider bar, because models often say "I'm not confident" while
still filling in every box — and those boxes still need grading.

### Q8 — Candidate deduplication

**Answer.** `fingerprint_observation()` in `mars/candidates.py`. A SHA hash over
the normalized **extracted fields only** — the eight `LLM_EXTRACTED_FIELDS`, in
sorted order. Normalization is textual only: case folding and whitespace
trimming. Confidence, generator identity, judge data and ordering are excluded
by construction. Two candidates with the same fingerprint merge into one, whose
`multiplicity` is the number of generators that produced it.

Deliberately *not* semantic: "improved" and "improving" are different
candidates, not the same one written differently.

Empirical note: across all 330 segments, deduplication merged nothing — the
count of distinct candidates equalled the count of admitted generators at every
level. No two generators ever produced an identical extraction.

**In plain terms.** Two answers count as "the same" only if every field matches
after ignoring capitalisation and stray spaces. We do not try to judge whether
two differently-worded answers mean the same thing — that would be an opinion,
and this step has to be mechanical. In practice no two models ever agreed
exactly.

---

## C. MARS multi-judge reranking

### Q9 — MARS algorithm

**Answer.** Step by step (`mars/provider.py` orchestrates; the named modules
hold each step):

1. **Build candidates** (`candidates.py`) — admit under `reviewable`, deduplicate
   by fingerprint, record multiplicity.
2. **Classify branch** — `no_reviewable_candidate` (0 candidates, abstain);
   `single_candidate` (1, short-circuit, no judging); `rerank_required` (≥2).
3. **Select eligible judges** (`safety.py`) — see Q11.
4. **Blind the candidates** (`blinding.py`) — per-judge aliases and per-judge
   presentation order, both derived from a per-judge seed.
5. **Collect rankings** — each judge returns an ordering of aliases.
6. **Validate responses** (`fusion.py`) — a response must be a complete ordering
   of exactly the aliases presented; anything else is discarded with a reason.
7. **Fuse** — Reciprocal Rank Fusion, `score(c) = Σ_judges 1 / (RRF_K + rank_j(c))`
   with `RRF_K = 60`. Highest score is the provisional winner.
8. **Agreement gate** (`agreement.py`) — in this order: (a) provisional winner
   must be among the judges' modal first choice, else `NOT_MODAL_FIRST_CHOICE`;
   (b) if the mode is tied, `MODAL_TIE`; (c) support must be ≥ threshold, else
   `BELOW_THRESHOLD`.
9. **Integrity check** (`safety.py`) — the returned record must be one whole
   candidate, compared across `MARS_INTEGRITY_FIELDS` (identity fields plus all
   extracted fields), not a field-wise blend.
10. **Confidence composition** (`confidence.py`) — see Q14.

**Tie-breaking:** there is none by design. A tie for the modal first choice
abstains (`MODAL_TIE`). Breaking it by id, multiplicity or fused score would
manufacture agreement the judges did not express.

**In plain terms.** Several referees each rank the candidate answers. Their
rankings are combined by a fixed formula that rewards being ranked consistently
well over being ranked first once. The winner then has to clear three checks: the
referees' most common first choice has to match it, they have to agree enough,
and the answer handed back has to be one complete candidate rather than a mix of
several. If the referees split evenly, the system refuses to answer rather than
picking a side.

### Q10 — Judge prompt and blindness

**Answer.** `SYSTEM_PROMPT` and `build_judge_user_prompt()` in
`mars/ollama_judge.py`; blinding in `mars/blinding.py`.

Each judge sees exactly: the **source transcript**, and the **candidate
structured records** each labelled with an opaque alias. It returns a JSON array
of the aliases best-supported first, and nothing else.

Each judge does **not** see: which generator produced any candidate; any
generator's confidence or status; the other judges' rankings; the codebook; or
any gold annotation.

Blinding is per judge: alias assignment and presentation order derive from
separate material under the same per-judge seed, so presentation order is
independent of alias assignment. Ordering by hash rather than input position
turns each judge's position bias into noise that fusion averages out; a fixed
order shared by all judges would let their biases align and be amplified.

**In plain terms.** Referees see the transcript and the anonymous answers. They
do not know which model wrote which answer, how confident it was, or what the
other referees said. Each referee sees the answers in a different order, so if a
referee tends to favour whatever is listed first, that tendency cancels out
instead of adding up.

### Q11 — Judge eligibility

**Answer.** `eligible_judges()` in `mars/safety.py`. A judge is ineligible for a
segment if its **exact model identity** generated any candidate in that
segment's candidate set — evaluated against the union of generator identities
across every candidate, including identities merged during deduplication. Only
exact identity disqualifies; same-family overlap is permitted and recorded
rather than prohibited.

**Roster in the reported MARS run** (`mars_run_summary.json`): five models —
`llama3.2:latest`, `qwen2.5:3b`, `qwen2.5:7b`, `mistral:latest`, `qwen3:14b`.
The first three are also generators and are therefore excluded on segments where
they produced a candidate; `mistral` and `qwen3:14b` were never generators in
that run and are always eligible.

Resulting panel sizes over the 165 rerank segments: **3 eligible judges on 124
segments, 2 on 41**. Under the earlier four-model roster (without `qwen3:14b`),
41 segments had only one eligible judge and could not be gated at all.

**In plain terms.** A model is not allowed to grade its own homework. Because
three of the referees were also contestants, the panel shrinks on segments where
they competed. Adding a fifth model that never competed lifted every segment to
at least two referees.

### Q12 — Agreement threshold

**Answer.** `agreement.py`. Support is defined as

    support = (number of valid judges ranking the provisional winner first)
              / (number of valid judges)

The configured value 0.5 is the minimum support required; comparison is
`support < threshold → abstain`, so equality passes (MARS-016).

**How 0.5 behaves is panel-size dependent, and this must be reported:**

- **3 judges:** 3-0 and 2-1 pass; a 1-1-1 three-way split is a modal tie and
  abstains. The threshold therefore acts as majority rule.
- **2 judges:** support can only be 1.0 or 0.5. A 1-1 split is a **modal tie**
  and abstains at step 8(b) — *before* the threshold is consulted. So on
  two-judge panels the effective requirement is unanimity, and the 0.5 threshold
  is not the operative gate.

**Selection of 0.5 is not empirically calibrated.** It is a stated configuration
value, required as an explicit argument by the runner because a default would
settle an open question invisibly. Per-field inter-annotator kappa is the
intended empirical anchor, but human annotators judge fields against raw source
text while MARS judges rank a supplied candidate set; the two measure different
tasks and their numbers are not interchangeable. The manuscript should describe
0.5 as a configured value whose sensitivity was not swept, not as a tuned one.

**In plain terms.** "Agreement" means the share of referees whose top pick is the
winner, and 0.5 means at least half. With three referees that is majority rule.
With two it is stricter than it sounds: a 1–1 split is thrown out as a tie
before the half-way rule is even checked, so both must agree. We picked 0.5 as a
starting value and did not test alternatives.

### Q13 — MARS abstention / reason codes

**Answer.** Closed enumeration, `MarsAbstentionReason` in `mars/safety.py` —
one member per gate, separate because the remedies differ.

| Code | Triggered when |
|---|---|
| `no_reviewable_candidate` | no candidate passes `reviewable` admission (Q7) |
| `insufficient_eligible_judges` | eligible judges (Q11) fewer than `min_eligible_judges` |
| `insufficient_valid_judge_responses` | valid rankings (Q9 step 6) fewer than `min_valid_responses` |
| `judge_disagreement` | agreement gate fails — not modal first choice, modal tie, or below threshold |
| `integrity_failure` | the assembled record is not one whole candidate |

Observed in the reported 330-segment run: `no_reviewable_candidate` 42,
`judge_disagreement` 21, `insufficient_valid_judge_responses` 2; coverage 80.3%
(265 of 330 returned).

**In plain terms.** Five distinct reasons for declining to answer, kept separate
because they call for different fixes. "No usable candidates" is a generator
problem; "not enough referees" is a configuration problem you fix before the run;
"referees disagreed" is the system working as designed.

### Q14 — Confidence handling

**Answer.** `mars/confidence.py`. Two quantities are composed:

- **generator confidence** — the selected candidate's own self-reported
  confidence, combined across the generators that produced that candidate under
  a required, explicit policy (`minimum` in the reported run).
- **`mars_selection_confidence`** — `derive_selection_confidence()` returns the
  agreement gate's `first_choice_support` (Q12); it is confidence in the
  *selection*, not in the content.

Composition: `control_confidence = min(generator_confidence, mars_selection_confidence)`.
Where either input is absent, `control_confidence` is `None` and
`control_confidence_state` records why. MARS-032 forbids writing generator
confidence alone as control confidence — so single-candidate short-circuits,
which consult no judge, return `not_available_short_circuit`. Deterministic
validation gates on `control_confidence` only, never on how it was derived.

Caveat worth reporting: self-reported confidence is poorly calibrated in this
roster. One generator reported mean confidence 0.28 while populating `domain` on
97.0% of segments; another reported 0.86 alongside the sparsest output.

**In plain terms.** Two different kinds of confidence — "how sure was the model
about its answer" and "how sure are we we picked the right answer" — and the
system takes the *lower* of the two, so neither can mask the other. When there
was only one candidate, no referees were consulted, so no selection confidence
exists and the system says so rather than substituting the model's own. The
models' self-ratings are not trustworthy on their own.

### Q15 — Qwen 3 14B distinction

**Answer.** Confirmed, with one correction.

- **Confirmed:** `qwen3:14b` was run over the same 330 segments *after* the MARS
  experiment and scored against the same model-independent gold standard. It was
  **not** a candidate generator in the reported MARS run; in that run it served
  only as a judge. Its candidates are recorded in a separate artefact
  (`annotation_batch_augmented.json`); the frozen batch the annotators saw is
  unchanged.
- **Confirmed:** four-generator MARS performance has **not** been experimentally
  reported. No MARS run has been executed with `qwen3:14b` as a generator.
- **Correction to the premise:** the question states all four generators are now
  integrated into the application. All four are runnable through the same
  `ExtractionProvider` interface, and all four have been *evaluated*. Whether
  they are wired into the deployed application's default configuration is a
  separate matter and should be stated only if verified; the evaluation work
  does not establish it.

The three-generator oracle ceiling (6.1%) and the MARS results describe the
three-generator roster. Adding `qwen3:14b` raises the ceiling to 8.8%, but that
figure comes from scoring, not from a MARS run.

**In plain terms.** The big model joined late. It was graded against the same
answer key — which cost nothing extra, because the answer key was written from
the transcripts rather than from any model's output. But it never competed in
the referee experiment, so any statement about how reranking performs with four
contestants would be unsupported.

---

## D. Reporting LLM and governance validation

### Q16 — Reporting LLM configuration

**Answer.** `src/backend/ml/reporting_client.py`; evaluation harness at
`tests/eval/reporting/groundedness.py`.

| Setting | Value |
|---|---|
| model | `qwen2.5:7b` (digest `845dbda0ea48`) |
| endpoint | Ollama native `/api/chat` |
| context (`num_ctx`) | 8192 (`settings.reporting_num_ctx`) |
| temperature | not set |
| structured output | Ollama `format` = JSON Schema (`ReportingClient.REPORT_SCHEMA`) |
| system prompt | `REPORTING_SYSTEM_PROMPT` in the same file |
| output schema | object with `sections[]`, each `{heading, body, evidence_refs[], abstention_note}` |

**The replaced configuration, and why.** The original path called Ollama's
OpenAI-compatible `/v1` endpoint and requested the schema **in the prompt only**.
Under that configuration every one of 11 generations returned prose or a JSON
object of the wrong shape, and all 11 fell back to the deterministic template —
which would have been reported as a model-capability finding. It is not one:
supplying the identical schema as a *decoding constraint* produced conformant
output from the same model on all 11. The `/v1` compatibility layer silently
drops Ollama's native `format` parameter, which is why the native endpoint is
required. A fallback to `/v1` remains for non-Ollama servers, with a logged
warning that the schema cannot be enforced there.

Evidence-packet size also required the context increase: one child's packet is
~4,500 tokens against a 4,096 default, and a truncated packet produces a report
about the fragment that survived.

**In plain terms.** Asking the model nicely to answer in a fixed format did not
work — it wrote essays instead. Forcing the format during generation did work,
with the same model. The earlier result looked like "this model can't do it"
when it was really "we asked the wrong way". Also, the default working memory
was too small to hold one child's data, so it was doubled.

### Q17 — Reporting evidence packet

**Answer.** `EvidencePacket` in `src/backend/ml/schemas.py`. Fields:

| Field | Contents |
|---|---|
| `child_id`, `review_period_id`, `review_period_start/end` | period context |
| `goals` | active goal definitions |
| `structured_records` | the validated observations themselves |
| `record_ids`, `record_versions` | identifiers the report may cite, and their versions |
| `analytics` | `AnalyticsResult` — a list of `KpiResult`, each with `name`, `numerator`, `denominator`, `value`, `prerequisites_met`, `display_eligible`, `abstained`, `abstention_reason` |
| `adequacy` | `AdequacyResult` — level, per-check results, quality flags, partial abstentions |
| `quality_flags` | e.g. single-contributor or single-setting warnings |
| `contributor_summary`, `setting_summary` | counts by role and setting |
| `observation_count`, `abstained_count`, `review_count` | totals |

Withheld metrics are **present in the packet** as `KpiResult` entries with
`abstained = true` and an `abstention_reason` — they are not removed. This is
what makes failure to acknowledge them detectable.

In the reported evaluation the packets were assembled from the adjudicated gold
records grouped by child, through the production `AdequacyRouter` and
`AnalyticsEngine`. The app-known metadata those engines require — observation
date, setting, contributor role — was **derived from corpus structure**, not
taken from real intervention records. This bounds the claim: what is measured is
whether the reporting layer invents facts absent from its input, which does not
depend on the input being a real clinical record.

**In plain terms.** The reporting model receives a complete packet: the
observations, the numbers already computed for it, which numbers were
deliberately suppressed and why, and the list of record IDs it is allowed to
cite. Crucially, suppressed numbers are still *listed* as suppressed — that is
what lets us check whether the model told the reader they were withheld.

### Q18 — Governance validator

**Answer.** `validate_report()` in `reporting_client.py`, plus the groundedness
instrument in `tests/eval/reporting/groundedness.py`. Four checks:

1. **Prohibited content** — regular expressions over the joined report body for
   diagnosis, treatment/therapy recommendation, causal claims tied to the
   condition, prognostic statements, the terms normal/abnormal/delayed/deficit,
   and goal-modification language.
2. **Insufficient-evidence acknowledgement** — if adequacy level is
   `insufficient`, some section must contain "insufficient" or "limited".
3. **Withheld-metric acknowledgement** — for each `KpiResult` with
   `abstained = true` and a reason, some section must name the metric, or say
   "withheld", or say "insufficient". Failure here was the sole cause of all 11
   validation failures.
4. **Numeric grounding and reference validity** (evaluation instrument) — every
   number in the prose must match a packet value *at the precision printed*
   (magnitudes included, so a stored −0.5333 matches "decreased by 0.5333");
   record identifiers and ISO dates are excluded from the scan as identifiers
   rather than claims. Every `evidence_refs` entry must exist in `record_ids`.

The grounding rule is calibrated on the deterministic fallback, whose prose is
composed from packet values and is grounded by construction: it scores 1.0 there,
so the rule contributes no false positives at this precision.

**Reported results (11 reports):** prohibited content 0/11; ungrounded numeric
assertions 8/122 (6.6%); invalid evidence references 2/836 (0.2%); reports
passing governance validation 0/11.

**In plain terms.** Four automatic checks: don't say forbidden clinical things;
admit when evidence is thin; say so when a number was deliberately withheld; and
don't state any number that isn't in the packet. The model passed the first
completely and failed the third every single time — it quietly left out the
withheld comparisons instead of saying they had been withheld. "Failed
validation" here does **not** mean malformed output; the output was structurally
perfect.

---

## E. Learning boundary and reproducibility

### Q19 — No hidden learning in reranking

**Answer.** MARS performs no learning of any kind. It is entirely inference-time
ranking: fixed pretrained judges produce orderings, and those orderings are
combined by a deterministic formula (RRF, `K = 60`) with fixed gates. No
parameters are updated, no examples are stored between segments, no annotated
record is shown to any judge, and no gold label enters the pipeline at any point.
Each segment is processed independently.

The 330 annotated records are used **only** to score outputs after the fact. The
judges never see them.

**In plain terms.** Reranking is voting, not learning. The referees are never
shown the answer key and never change between segments. The answer key is used
only afterwards, to mark the results.

### Q20 — Reproducibility information

**Answer.**

- **Commit:** `6163d13` (`6163d1306049c401ed0b25bf8c6d2bc986f40194`), 2026-09-19.
- **Runtime:** Python 3.12.12, Ollama 0.33.3, `anthropic` 1.2.0, `openai` 3.5.0,
  `pydantic` 2.13.4. Full lock in `uv.lock`.
- **Model digests:** Q2.
- **Seeds:** annotation sheet ordering 42 (round 1) and 4242 (round 2); held-out
  sampling 20260916; held-out sheet ordering 8484; bootstrap 20260915 /
  20260916 at 10,000 replicates; MARS run seed `mars-full-330-v2`. **No
  generation seed was set** — see Q6.
- **Artefact manifest:** `docs/paper/artifact_manifest.json` — 51 artefacts, 33
  pinned by SHA-256. Human-readable listing and the full reproduction sequence:
  `docs/paper/artifacts.md`. Verify with
  `uv run python docs/paper/verify_artifacts.py`.

Key paths:

| What | Path |
|---|---|
| Extraction prompts and schema | `src/backend/ml/extraction/prompts.py` |
| Ollama extraction provider | `src/backend/ml/extraction/ollama_llm.py` |
| MARS implementation | `src/backend/ml/extraction/mars/` |
| Reporting client + validator | `src/backend/ml/reporting_client.py` |
| Frozen annotation batch | `tests/eval/extraction/results/annotation_batch.json` |
| Adjudicated gold standard | `tests/eval/extraction/results/gold_labels.json` |
| MARS run config + judge reliability | `tests/eval/extraction/results/mars_run_summary.json` |
| Consolidated metrics | `tests/eval/extraction/results/paper_metrics.json` |

**Reproducibility boundary, stated plainly.** Everything downstream of the
recorded generator outputs is deterministic and reproducible from the pinned
artefacts. Regenerating the generator outputs from the models is *not* bit-
reproducible, because no generation seed was set and temperature was left at
the server default. This is why the outputs are replayed rather than regenerated
throughout, and why the manifest pins them.

**In plain terms.** Everything from the model answers onward can be reproduced
exactly, and the files are fingerprinted so you can tell if any changed. Asking
the models again might give slightly different answers, because we did not fix
their random seed — so we saved their original answers and everything is built
from those.
