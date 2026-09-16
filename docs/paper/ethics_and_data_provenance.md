# Ethics and data provenance — manuscript section

Draft for the Ethics Approval / Data Availability statements a JMIR submission
requires. Items marked **[CONFIRM]** are facts only the authors hold; they are
left as prompts rather than filled with plausible text, because a fabricated
ethics statement is worse than a missing one.

---

## Data sources

All source data is archival, publicly deposited, and was collected by third
parties. No data was collected from human participants for this work.

| Corpus | Creator | Deposited | DOI |
|---|---|---|---|
| ASDBank English Rollins Corpus | Rollins, Pamela Rosenthal | 2004-03-30 | [10.21415/T5KK53](https://doi.org/10.21415/T5KK53) |
| ASDBank English Flusberg Corpus | Tager-Flusberg, Helen | 2004-04-05 | [10.21415/T5459F](https://doi.org/10.21415/T5459F) |

Both are components of ASDBank within the TalkBank system. The Rollins corpus
records young boys with autism interviewed by a clinician; the Flusberg corpus
is a longitudinal study of language development in children with autism.
Combined: 11 children, 85 sessions, 75,003 utterances in CHAT format, from
which 2,442 behavioural segments were derived.

**[CONFIRM]** the licence each corpus is distributed under and reproduce the
attribution its terms require. TalkBank corpora carry usage conditions and a
required citation form; the manuscript must cite both corpora by DOI and
acknowledge TalkBank itself, and the submission should not assert a licence
that has not been checked against the current deposit page.

**[CONFIRM]** whether the original depositors' consent covers secondary
computational analysis of this kind. Archival reuse of a public deposit is
normally within scope, but the statement should say so explicitly rather than
leave a reviewer to assume it.

## Ethics approval

**Status: submitted, determination pending.** A request was submitted to the
Institutional Review Board at the University of Texas at Austin on
**[CONFIRM the submission date]**. As of 2026-09-16 no determination has been
returned.

The expected form is an IRB exemption or a non-human-subjects-research
determination, on the grounds that the work analyses existing, publicly
available, de-identified records and the investigators cannot readily ascertain
participant identity. That is the expected outcome, not a known one, and the
manuscript must not assert it before the determination arrives.

On receipt, replace this section with the determination as issued:

- **[CONFIRM]** the institution as named on the determination letter
- **[CONFIRM]** the determination itself (exempt / not human subjects research /
  approved), in the IRB's own wording
- **[CONFIRM]** the protocol or exemption number
- **[CONFIRM]** the date of determination

If the determination differs from the expectation above — for instance if the
IRB asserts jurisdiction rather than exempting — the Methods and Limitations
sections must be revisited, not only this paragraph.

No participants were recruited, contacted, or consented for this study. No
clinical care was delivered, influenced, or withheld on the basis of any system
output. The system was not deployed in any care setting and no interventionist
used it during the work reported here.

## De-identification

Transcripts pass through a de-identification stage before any model sees them
(`data/pipeline/deidentify.py`, applied in `load_real_segments` ahead of
segmentation). Child identifiers in this manuscript (`brett`, `carl`, `mars`, …)
are the pseudonymous labels carried by the public corpora, not real names.

**What the stage replaces.** Five patterns, each with a bracketed placeholder,
applied to utterance text *and* to every dependent tier (`%act`, `%spa`, `%gpx`):

| replaced with | what it matches |
|---|---|
| `[NAME]` | participant names harvested from the session's own `@Participants` and `@ID` headers, plus a fixed roster of the ten child pseudonyms; whole-word, case-insensitive |
| `[LOCATION]` | US-style street addresses (number + capitalised words + street suffix) |
| `[DATE]` | numeric dates (`MM/DD/YYYY`, `YYYY-MM-DD` and similar) |
| `[SSN]` | US social security numbers |
| `[PHONE]` | US telephone numbers |

Sessions are deep-copied, so the parsed originals are never mutated.

**What it does not do**, stated plainly because "de-identified" will otherwise
be read as a claim about residual risk:

- **It is roster- and header-driven, not named-entity recognition.** A person
  named in conversation who is neither a listed participant nor one of the ten
  child pseudonyms — a sibling, a teacher, a neighbour — is not detected.
- **It over-redacts common words.** Every one of the ten child pseudonyms is
  also an ordinary English word (`mark`, `jack`, `rick`, `mars`, `brett`, `sid`,
  `carl`, `stuart`, `josh`, `roger`), and matching is case-insensitive, so an
  ordinary use of "mark" is replaced with `[NAME]`. The pipeline flags these as
  ambiguous for manual review but replaces them regardless. This is visible in
  the study data: **82 `[NAME]` placeholders appear across 62 of the 330
  annotated segments (19%)**, a handful of them adjacent to function words in a
  way that suggests a redacted common noun rather than a redacted name.
  Annotators and models saw the redacted text, so wherever a redaction removed
  a content word it removed evidence both were scored on.
- **It matches only numeric dates and US-format addresses.** "last Thursday",
  "my birthday is in June", or a named school or town are not caught. In the
  330 annotated segments no `[LOCATION]`, `[DATE]`, `[SSN]` or `[PHONE]`
  placeholder occurs at all — every redaction in the study data is a `[NAME]`.
- **It operates on utterance and tier content only.** CHAT header fields are not
  scanned. Segments handed to models and annotators are assembled from
  utterances, so headers do not reach them, but the parsed `Session` objects
  retain header metadata.

The residual risk is therefore that of the public deposits themselves: these
corpora were de-identified by their depositors before publication, and this
stage is a second pass over already-public, already-pseudonymous text rather
than the primary protection.

## Third-party model processing

This is the disclosure most easily overlooked, and it must be explicit.

**Local models.** The three generators (`llama3.2`, `qwen2.5:3b`,
`qwen2.5:7b`) and the ranking judge run locally through Ollama. No transcript
content leaves the machine.

**Frontier comparator arm.** Any run that includes a `claude-*` generator
transmits transcript segments to the Anthropic API — a third party. Even
though the content is de-identified and already public, this is a data-transfer
decision, and the manuscript must:

1. state which model processed the data, at what version, and on what date;
2. confirm the transfer is permitted under the corpora's terms **[CONFIRM]**;
3. state the provider's data-retention and training posture for API traffic at
   the time of the run **[CONFIRM against current terms — do not cite from
   memory]**.

The frontier arm is **held outside the primary experiment** until items 1-3 are
documented. The primary three-generator comparison therefore carries the clean
statement that no data left local infrastructure; the Claude arm, if run, is
reported separately as a secondary benchmark with its own disclosure.

## Annotation

Two annotators each independently author gold field values for all 330
segments by reading the transcript, with no model output shown. They do not
judge model candidates.

**[CONFIRM]** who the annotators are and what qualifies them. For autism
intervention constructs (`domain`, `modality`, `prompt_level`, `outcome`) a
reviewer will expect clinically qualified raters — BCBA, SLP, or developmental
specialist — and will want:

- number of annotators, their credentials, and their independence from the
  system's development;
- the training or calibration they received before annotating;
- that they were blind to all model output (structurally: the annotation tool
  reads the transcript and never reads the candidates) and to each other's
  values (each writes a separate file);
- the adjudication procedure for disagreements, and that segments left
  unresolved on any field are excluded from the gold standard rather than
  resolved by rule.

The current identifiers `annotator_a` / `annotator_b` are placeholders and must
be replaced with a described role in the manuscript. Annotation labour was
**[CONFIRM: compensated / uncompensated / part of employed duties]**.

## AI use in preparing this work

Two uses are routinely conflated and are separated here.

**AI as the object of study.** The extraction generators (`llama3.2`,
`qwen2.5:3b`, `qwen2.5:7b`) and the MARS judge roster are the subject of the
research and are described in Methods. Their outputs are data, not authorship.

**AI as a tool in producing the code and manuscript.** Substantial portions of
the evaluation tooling in this repository — the annotation sheet export/import
chain, the reliability statistics, the adjudication tooling, the figure
generation, and the verification tests — were written with AI assistance
(Claude, Anthropic), as was drafting of the manuscript sections in
`docs/paper/`. The following are **not** AI-generated and are recorded here so
the boundary is legible:

- every gold annotation value, in both rounds, authored by the two human
  annotators from the transcripts;
- every adjudication decision, made by the two annotators jointly;
- the three codebook rules as *applied* — the rules were drafted with AI
  assistance from the observed disagreement pattern, then applied to segments
  by the human annotators;
- the research questions, corpus selection, and the decision to run a second
  annotation round.

No AI system authored, selected, or altered a gold-standard value, an
adjudication, or a reported statistic. Statistics were computed by code from
recorded artefacts, and `test_manuscript_numbers.py` and
`test_extraction_results_numbers.py` re-derive every number in the manuscript
from those artefacts so that no reported figure rests on text an author or a
tool typed by hand.

**[CONFIRM]** the exact disclosure wording required by JMIR at submission, the
model name and version to cite, and whether the journal requires this in the
Acknowledgements, a Declaration, or both.

## Data and code availability

Source corpora are publicly available from ASDBank at the DOIs above and are
**not** redistributed in this repository.

**[CONFIRM]** what will be released and where. Candidates:

- the pipeline and evaluation code (`tests/eval/extraction/`, `docs/paper/`),
  which contains no participant data;
- `annotation_batch.json`, which contains transcript excerpts from the public
  corpora together with model output — **[CONFIRM]** whether the corpora's
  terms permit redistributing excerpts in a derived artefact, or whether the
  release should ship the pipeline plus a segment-id manifest so others
  regenerate the batch from their own ASDBank access;
- the adjudicated gold labels, once they exist.

Every figure and table in `docs/paper/results_extraction.md` regenerates from
two scripts, and their commands are recorded in that file.

## Claims deliberately not made

Recorded here so they do not drift into the manuscript:

- The system does not diagnose, prescribe, or modify intervention goals.
- No claim is made about clinical utility, and none can be: no interventionist
  used the system, and no clinical outcome was measured.
- Extracted records are provisional model output, not expert gold-standard
  research labels.
- No claim is made about generalisation beyond these 11 children and two
  corpora.
