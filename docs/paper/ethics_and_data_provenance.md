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

**[CONFIRM]** the institutional determination. The expected form is an IRB
exemption or a non-human-subjects-research determination, on the grounds that
the work analyses existing, publicly available, de-identified records and the
investigators cannot readily ascertain participant identity. State the
institution, the determination, and the protocol or exemption number — or, if
no submission was made, say that and give the reasoning.

No participants were recruited, contacted, or consented for this study. No
clinical care was delivered, influenced, or withheld on the basis of any system
output. The system was not deployed in any care setting and no interventionist
used it during the work reported here.

## De-identification

Transcripts pass through a de-identification stage before any model sees them
(`deidentify_sessions`, applied in `load_real_segments` ahead of segmentation).
Child identifiers in this manuscript (`brett`, `carl`, `mars`, …) are the
pseudonymous labels carried by the public corpora, not real names.

**[CONFIRM]** what the de-identification stage removes and what it leaves, and
state it plainly. A reviewer will read "de-identified" as a claim about
residual risk; the honest version names the categories handled.

Note that the corpora are already distributed publicly in de-identified form.
The stage here is defence in depth, not the primary protection.

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

If the comparator arm is dropped, say that no data left local infrastructure,
which is a cleaner statement and worth preferring where the science allows.

## Annotation

**[CONFIRM]** who the annotators are and what qualifies them. For autism
intervention constructs (`domain`, `modality`, `prompt_level`, `outcome`) a
reviewer will expect clinically qualified raters — BCBA, SLP, or developmental
specialist — and will want:

- number of annotators, their credentials, and their independence from the
  system's development;
- the training or calibration they received before annotating;
- whether they were blind to which model produced each candidate (the tooling
  is blind by default) and to each other's judgements (they are: each writes a
  separate file);
- the adjudication procedure for disagreements.

The current identifiers `annotator_a` / `annotator_b` are placeholders and must
be replaced with a described role in the manuscript. Annotation labour was
**[CONFIRM: compensated / uncompensated / part of employed duties]**.

## AI use in preparing this work

**[CONFIRM]** and disclose per JMIR policy. Distinguish two uses that are
routinely conflated:

- **AI as the object of study** — the extraction and reranking models are the
  subject of the research and are described in Methods.
- **AI as a tool in producing the manuscript or code** — any assistance in
  writing code, analysis, or manuscript text must be disclosed separately.
  Substantial portions of the evaluation tooling in this repository were
  written with AI assistance.

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
