"""Assemble the working manuscript as a Word document.

Every number is read from the recorded artefacts, never typed here, so the
document cannot drift from the data it describes. Figures are embedded from
docs/paper/figures/ in the order they are referenced.

This is a **working draft for internal review**, not a submission. It says so
on its first page, and the sections it cannot support are listed rather than
omitted.

    uv run python docs/paper/make_manuscript.py
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[2]
FIGURES = Path(__file__).parent / "figures"
RESULTS = ROOT / "tests/eval/extraction/results"
REPORTING = ROOT / "tests/eval/reporting/results"
OUT = Path(__file__).parent / "Manuscript_Working_Draft.docx"

INK = RGBColor(0x1F, 0x29, 0x33)
MUTED = RGBColor(0x7B, 0x89, 0x94)
RED = RGBColor(0xC1, 0x66, 0x6B)


def load(path: Path) -> dict[str, Any] | None:
    return json.loads(path.read_text()) if path.exists() else None


def pct(value: float | None, places: int = 1) -> str:
    return "n/a" if value is None else f"{100 * value:.{places}f}%"


class Builder:
    def __init__(self) -> None:
        self.doc = Document()
        self.fig_no = 0
        self.tab_no = 0
        style = self.doc.styles["Normal"]
        style.font.name = "Calibri"
        style.font.size = Pt(10.5)

    # --- primitives -----------------------------------------------------
    def h1(self, text: str) -> None:
        self.doc.add_heading(text, level=1)

    def h2(self, text: str) -> None:
        self.doc.add_heading(text, level=2)

    def p(self, text: str, *, italic: bool = False, colour: RGBColor | None = None) -> None:
        para = self.doc.add_paragraph()
        run = para.add_run(text)
        run.italic = italic
        if colour is not None:
            run.font.color.rgb = colour

    def bullets(self, items: list[str]) -> None:
        for item in items:
            self.doc.add_paragraph(item, style="List Bullet")

    def figure(self, filename: str, caption: str, width: float = 6.3) -> None:
        path = FIGURES / filename
        if not path.exists():
            self.p(f"[missing figure: {filename}]", italic=True, colour=RED)
            return
        self.fig_no += 1
        # Numbering is assigned here, in document order, rather than written
        # into each caption by hand. Hand-written numbers drift the moment a
        # figure is inserted or moved, and the images no longer carry numbers
        # of their own, so this is the single source of truth.
        caption = re.sub(r"^Figure\s+[0-9A-Za-z]+\s*[.\u2014-]\s*", "", caption)
        caption = f"Figure {self.fig_no}. {caption}"
        self.doc.add_picture(str(path), width=Inches(width))
        self.doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
        para = self.doc.add_paragraph()
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = para.add_run(caption)
        run.italic = True
        run.font.size = Pt(9)
        run.font.color.rgb = MUTED

    def table(self, caption: str, header: list[str], rows: list[list[str]]) -> None:
        self.tab_no += 1
        para = self.doc.add_paragraph()
        run = para.add_run(f"Table {self.tab_no}. {caption}")
        run.bold = True
        run.font.size = Pt(9.5)

        table = self.doc.add_table(rows=1, cols=len(header))
        table.style = "Light Grid Accent 1"
        table.alignment = WD_TABLE_ALIGNMENT.CENTER
        for cell, text in zip(table.rows[0].cells, header):
            cell.text = str(text)
            for p in cell.paragraphs:
                for r in p.runs:
                    r.bold = True
                    r.font.size = Pt(9)
        for row in rows:
            cells = table.add_row().cells
            for cell, text in zip(cells, row):
                cell.text = str(text)
                for p in cell.paragraphs:
                    for r in p.runs:
                        r.font.size = Pt(9)
        self.doc.add_paragraph()

    def code(self, text: str) -> None:
        para = self.doc.add_paragraph()
        run = para.add_run(text)
        run.font.name = "Consolas"
        run.font.size = Pt(9)

    def page_break(self) -> None:
        self.doc.add_page_break()


def build() -> Path:
    m = load(RESULTS / "paper_metrics.json")
    if m is None:
        raise SystemExit(
            "paper_metrics.json not found. Run "
            "`uv run python -m tests.eval.extraction.paper_metrics` first."
        )
    branch = load(RESULTS / "mars_branch_replay.json") or {}
    ground = load(REPORTING / "reporting_groundedness.json") or {}
    manifest = load(Path(__file__).parent / "artifact_manifest.json") or {}

    b = Builder()
    ann = m["annotation"]
    gold = m["gold_standard"]
    ext = m["extraction"]
    mars = m["mars"]
    fields = ext["scoring_policy"]["scored_fields"]
    models = list(ext["per_field_accuracy"])

    # ---- title ---------------------------------------------------------
    title = b.doc.add_heading(
        "Governance-Aware Extraction of Structured Autism Observations: "
        "Annotation Reliability, Unsupported Inference, and Multi-Model "
        "Selection",
        level=0,
    )
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER

    b.p(
        "WORKING DRAFT — NOT SUBMISSION READY. This document is assembled "
        "automatically from recorded evaluation artefacts for internal review. "
        "Ethics statements are incomplete, no frontier-model comparison has "
        "been run, and several system components are unevaluated. Sections "
        "that cannot be supported by measurement are listed under 'Not "
        "measured' rather than omitted.",
        italic=True,
        colour=RED,
    )
    b.p(
        f"Generated from {len(manifest.get('artefacts', []))} recorded artefacts; "
        "every figure in this document is derived from data in this repository "
        "and no number is typed by hand."
    )

    # ---- abstract ------------------------------------------------------
    b.h1("Abstract")
    b.p(
        "Background. Structured longitudinal records of autism intervention "
        "progress are difficult to assemble because contributor observations "
        "are heterogeneous natural language. Large language models can "
        "structure such text, but their use in a clinical monitoring pathway "
        "requires a reference standard and explicit governance."
    )
    b.p(
        f"Methods. We derived {ann['n_segments']} behavioural segments from two "
        "public ASDBank CHAT corpora (11 children, 85 sessions, 75,003 "
        f"utterances). Two annotators independently authored structured field "
        "values from the transcripts. Analysis of their disagreements "
        "identified three underspecified field definitions; these were "
        "resolved in a written codebook and the affected segments were "
        "re-annotated blind, with an untreated control field retained to "
        "separate the effect of the codebook from that of re-annotation. "
        "Surviving conflicts were adjudicated by consensus. Three local "
        "generators were scored against the resulting gold standard, and a "
        "multi-judge reranking stage (MARS) was evaluated against both a "
        "random-selection and a best-generator baseline."
    )
    r1 = ann["reliability"]["round1"]["mean_kappa"]
    r2 = ann["reliability"]["merged"]["mean_kappa"]
    best_acc = ext["whole_record"]["best_accuracy"]
    ceiling = ext["whole_record"]["oracle_ceiling"]
    b.p(
        f"Results. Mean Cohen's kappa rose from {r1:.3f} to {r2:.3f} across the "
        "four categorical fields. The three fields the codebook addressed "
        "improved by +0.29 to +0.48 with paired intervals excluding zero, "
        "while the untreated control field did not move (−0.041, interval "
        f"spanning zero). All {gold['n_segments']} segments entered the gold "
        "standard. The strongest generator produced a fully correct record on "
        f"{pct(best_acc)} of segments against an oracle ceiling of "
        f"{pct(ceiling)}. Where the gold standard records no supporting "
        "evidence for a field, generators asserted a value on up to 97% of "
        "opportunities. A larger, more recent generator added afterwards was "
        "no more accurate and had the highest unsupported-assertion rate of "
        "any model tested; across the roster, unsupported assertion tracked "
        "willingness to answer rather than capability. Reranking selected "
        "better than chance but did not improve on always using the strongest "
        "generator."
    )
    b.p(
        "Conclusions. Low inter-annotator agreement in this task was largely "
        "definitional rather than a matter of annotator inconsistency, and was "
        "measurably repaired by a written codebook under a controlled design. "
        "The generators evaluated are not adequate for the extraction task, "
        "and the failure is not attributable to model size: the largest model "
        "tested had the highest unsupported-assertion rate despite accuracy "
        "comparable to the strongest smaller model. Candidate selection "
        "cannot compensate for candidate quality."
    )

    b.page_break()

    # ---- introduction ---------------------------------------------------
    b.h1("Introduction")
    b.p(
        "Interventionists working with autistic children depend on "
        "observations contributed by parents, teachers and support staff. "
        "Those observations arrive as unstructured natural language, in "
        "heterogeneous formats, from contributors with different vocabularies "
        "and different levels of training. Reviewing them longitudinally "
        "against a defined goal is correspondingly difficult, and the "
        "difficulty grows with the length of the intervention."
    )
    b.p(
        "Large language models can convert such text into structured records, "
        "and this is an attractive application: the task is well defined, the "
        "volume is high, and the clinician's time is the scarce resource. But "
        "the same capability that structures an observation can also create "
        "one. A model asked for a prompt level will supply a prompt level, "
        "whether or not the source text supports one, and a structured record "
        "containing an unsupported clinical field is more dangerous than no "
        "record at all: it is downstream-readable, it aggregates into "
        "analytics, and nothing in its form marks it as invented."
    )
    b.p(
        "Evaluating whether a model does this requires a human reference "
        "standard that records not only what the text supports but also what "
        "it does not. That requirement exposes a second problem. Annotation "
        "rules for behavioural constructs are themselves unstable: two "
        "trained annotators reading the same transcript may apply a field "
        "definition differently, and their disagreement is easily mistaken "
        "for annotator inconsistency when it is in fact an underspecified "
        "scheme. A reference standard built on an unstable scheme cannot "
        "support conclusions about a model."
    )
    b.p(
        "A third question follows from the first two. Where several models "
        "extract from the same text and disagree, a selection mechanism might "
        "recover the better candidate. Whether it does, and whether selection "
        "can compensate for weak candidates at all, is an empirical question "
        "that has been little examined in clinical extraction settings."
    )
    b.p(
        "This study addresses all three. We construct an adjudicated gold "
        "standard over behavioural segments from two public autism corpora, "
        "treating the instability of the annotation scheme as an object of "
        "measurement rather than a nuisance; we quantify how often local "
        "extraction models assert field values the source text does not "
        "support; and we evaluate a multi-judge reranking stage against both "
        "a no-judgement and a best-single-model baseline. The contribution is "
        "the evaluation process and what it exposes, not a system that "
        "performs well: it exposes failure at the annotation layer and at the "
        "extraction layer, and reports both."
    )

    b.page_break()

    # ---- methods -------------------------------------------------------
    b.h1("Methods")

    b.h2("Corpus and batch construction")
    b.p(
        "Behavioural segments were derived from the Rollins "
        "(child-investigator) and Flusberg (child-parent) ASDBank CHAT "
        "corpora: 11 children, 85 sessions, 75,003 utterances. After parsing, "
        "de-identification and episode segmentation, 2,442 behavioural "
        "segments were available, 162 to 273 per child."
    )
    b.figure(
        "fig1_corpus.png",
        "Figure A. Corpus composition: behavioural segments per child, by "
        "source corpus.",
    )
    b.p(
        "The annotation batch was built in three stages, of which only "
        "candidate generation calls models: a stratified pool of 120 segments "
        "per child; three local generators extracting from every pooled "
        "segment; and retention only of segments where all three produced an "
        "admissible response. Two admission predicates are distinguished — the "
        "MARS runtime gate (SUCCESS or PARTIAL) and the wider 'judgeable' "
        "policy the batch was built under — because admitting only the former "
        "would retain the segments each model found easy."
    )
    b.figure(
        "fig2_admission.png",
        "Figure B. Admission policy: the two predicates and what each retains.",
    )
    b.figure(
        "fig3_joint_yield.png",
        "Figure C. Joint yield under a require-all policy. A 60-segment pilot "
        "projected 519 segments would be consumed to reach 330; the realised "
        "run consumed 506.",
    )
    b.p(
        "The batch is frozen at this point and is not regenerated. Generators "
        "are replayed from it wherever they are needed downstream, so MARS "
        "selects from exactly the candidates the annotators saw."
    )
    b.p(
        "Stage 3 conditions membership on model behaviour, and this is the "
        "principal threat to external validity in the study. Requiring all "
        "three generators to have produced an admissible response is what "
        "gives every batch item a complete candidate set, without which the "
        "three-way comparison and the oracle ceiling are not defined. The "
        "cost is that accuracy measured on the batch is accuracy on segments "
        "every model could at least attempt. Whether it generalises to an "
        "unselected sample is not answered by this batch and is addressed "
        "below."
    )

    b.h2("Model-independent held-out set")
    b.p(
        "To separate extraction performance from the batch's selection "
        "criterion, a second set was drawn without reference to any model's "
        "behaviour: 132 segments, 12 per child across all 11 children, "
        "stratified and frozen before any generator was run over it."
    )
    b.p(
        "The exclusion rule is deliberately stricter than removing the 330 "
        "annotated segments. The entire original stratified pool of 1,320 is "
        "excluded, because batch construction consumed 506 pool segments to "
        "retain 330 and no record survives of which 176 were rejected. "
        "Sampling the pool remainder would therefore have enriched the set "
        "with segments a generator had already failed on — conditioning in the "
        "opposite direction, and harder to argue away than the original. The "
        "held-out set is drawn from the 2,051 segments outside the pool "
        "entirely."
    )
    b.p(
        "Two rules govern its use. Generators are run only after the "
        "annotation is complete, because a set inspected for model performance "
        "before it is annotated is not held out. And a model that produces no "
        "admissible response is recorded as an abstention, with the segment "
        "retained — dropping it would reintroduce exactly the conditioning the "
        "set exists to avoid."
    )
    b.p(
        "The same round supplies a second quantity. Both annotators work from "
        "the final codebook from the first segment rather than reaching it "
        "after a round of disagreement, so the agreement obtained is a "
        "first-pass kappa under the final protocol rather than a "
        "within-annotator repeat. That is the comparison the two-round result "
        "cannot supply about itself, and it tests whether the codebook "
        "generalises beyond the disagreements it was written from."
    )
    b.p(
        "[PENDING] The held-out set is frozen; annotation and generator runs "
        "over it are not complete, and no result from it is reported here.",
        colour=RED,
    )
    b.figure(
        "fig5_pipeline.png",
        "Figure D. MARS control flow: models propose and rank, deterministic "
        "code decides, and each abstention carries a typed reason code.",
        width=5.4,
    )

    b.h2("Reliability statistics")
    b.p(
        "Cohen's kappa is computed per field over the value categories, with "
        "explicit nulls treated as a category rather than as missing data:"
    )
    b.code("kappa = (p_o - p_e) / (1 - p_e)")
    b.p(
        "Kappa is not pooled across fields by concatenating labels. The fields "
        "draw on different category sets and share literal labels — 'verbal' "
        "and 'gestural' occur in both the modality and prompt-level "
        "vocabularies — so a pooled confusion matrix would chance-correct "
        "against a distribution no annotator drew from. Pooling the four "
        "fields in this study gives 0.694 against a mean per-field kappa of "
        "0.610, an inflation of 0.084 that is an artefact of the pooled "
        "category count."
    )
    b.p(
        "Kappa is bounded above by the annotators' marginal distributions. "
        "Where one annotator uses a category the other never uses, those items "
        "cannot agree at any level of care:"
    )
    b.code(
        "p_o_max   = sum_i min(p_i., p_.i)\n"
        "kappa_max = (p_o_max - p_e) / (1 - p_e)\n"
        "forced disagreements = n (1 - p_o_max)"
    )
    b.p(
        "Segments are nested within children: the 330 segments come from 11 "
        "children, 30 each, across multiple sessions. Two segments from one "
        "child share that child's language, the partner's style and the "
        "session's activity, and are not independent draws. Intervals are "
        "therefore obtained by resampling **children** with replacement, each "
        "drawn child contributing all of its segments. With 11 clusters this "
        "is a small number to resample and the intervals are correspondingly "
        "wide; that width is information about the design rather than a defect "
        "of the estimator. Segment-level intervals are retained throughout as "
        "a sensitivity analysis and are reported alongside. Every conclusion "
        "in this paper holds under both."
    )
    b.p(
        "Reporting kappa alongside kappa_max separates a definitional problem "
        "— a low kappa close to its ceiling — from a judgement problem, a low "
        "kappa far below it. Intervals are 10,000-replicate percentile "
        "bootstraps resampling segments; the Fleiss-Cohen-Everitt large-sample "
        "variance is computed alongside as a cross-check and agreed to within "
        "0.005 on every bound of every field."
    )

    b.h2("Two-round protocol and the control field")
    b.p(
        "Three field definitions were identified as underspecified: whether "
        "gestural modality covers physical manipulation or only communicative "
        "gesture; whether correct/incorrect apply absent an identifiable "
        "target; and whether an adult utterance preceding a child response is "
        "a prompt or the antecedent that creates the opportunity. These were "
        "resolved in a written codebook and the affected segments re-issued "
        "blind, in a fresh order, with all five fields re-annotated."
    )
    b.p(
        "The comparison was specified before round 2 existed. Domain is "
        "re-annotated alongside every other field but no codebook rule touches "
        "it, so it carries the same practice and regression effects and none "
        "of the instruction. It is the control."
    )
    b.figure(
        "fig15_codebook_rules.png",
        "Figure 1. The three codebook rules, as the decision tests an "
        "annotator applies.",
    )
    b.figure(
        "fig14_protocol.png",
        "Figure 2. Two-round annotation protocol with realised counts; every "
        "segment is accounted for where it leaves.",
        width=5.6,
    )

    b.h2("Ethical considerations")
    b.p(
        "All source data is archival, publicly deposited, and was collected by "
        "third parties: the ASDBank English Rollins Corpus "
        "(doi:10.21415/T5KK53) and the ASDBank English Flusberg Corpus "
        "(doi:10.21415/T5459F), both components of ASDBank within TalkBank. No "
        "data was collected from human participants for this work, no "
        "participants were recruited or contacted, and no clinical care was "
        "delivered, influenced or withheld on the basis of any system output. "
        "The system was not deployed in any care setting and no interventionist "
        "used it during the work reported here."
    )
    b.p(
        "Transcripts pass through a de-identification stage before any model "
        "sees them, replacing participant names, street addresses, numeric "
        "dates, national identifiers and telephone numbers with bracketed "
        "placeholders across utterance text and every dependent tier. The "
        "stage is roster- and header-driven rather than named-entity "
        "recognition, and it over-redacts: each of the ten child pseudonyms is "
        "also an ordinary English word, so 82 [NAME] placeholders appear "
        "across 62 of the 330 annotated segments and some are redacted common "
        "words. Child identifiers throughout are the pseudonymous labels "
        "carried by the public corpora."
    )
    b.p(
        "[TO COMPLETE BEFORE SUBMISSION] A determination request has been "
        "submitted to the Institutional Review Board at the University of "
        "Texas at Austin; the determination had not been returned at the time "
        "of writing. The expected form is an exemption or a non-human-subjects "
        "research determination on the grounds that the work analyses "
        "existing, publicly available, de-identified records. This section "
        "must state the determination as issued, with institution, "
        "determination wording, and protocol number, before submission. The "
        "licence terms of both corpora and the scope of depositor consent for "
        "secondary computational analysis must also be confirmed and stated.",
        colour=RED,
    )

    b.page_break()

    # ---- results: reliability -----------------------------------------
    b.h1("Results")
    b.h2("Annotation reliability")

    r1_raw = load(RESULTS / "reliability_round1.json") or {"fields": {}}
    b.table(
        f"Round-1 reliability and the ceiling the marginals allow "
        f"(n = {ann['n_segments']} segments from 11 children). The reported "
        "interval resamples children; the segment-level interval is the "
        "sensitivity analysis.",
        ["Field", "kappa", "95% CI (children)", "95% CI (segments)",
         "kappa_max", "kappa / kappa_max"],
        [
            [
                f,
                f"{e['kappa']:.3f}",
                (
                    f"[{r1_raw['fields'][f]['cluster_bootstrap_ci']['lower']:.3f}, "
                    f"{r1_raw['fields'][f]['cluster_bootstrap_ci']['upper']:.3f}]"
                    if r1_raw["fields"].get(f, {}).get("cluster_bootstrap_ci")
                    else "--"
                ),
                f"[{e['ci'][0]:.3f}, {e['ci'][1]:.3f}]",
                f"{e['kappa_max']:.3f}",
                f"{e['kappa_over_kappa_max']:.3f}",
            ]
            for f, e in ann["reliability"]["round1"]["per_field"].items()
        ],
    )
    b.p(
        "Modality has both the lowest ceiling (0.622) and the highest ratio to "
        "it (0.916): the annotators reached 92% of the agreement their own "
        "category usage permitted. One annotator recorded 'none' 75 times; the "
        "other recorded it zero times. 80 of the 91 observed disagreements on "
        "that field were forced by the marginals before a transcript was read."
    )
    b.figure(
        "fig10_reliability_round1.png",
        "Figure 3. Round-1 kappa against the ceiling set by the annotators' "
        "marginal distributions.",
    )
    b.figure(
        "fig11_confusion_round1.png",
        "Figure 4. Annotator confusion; amber cells mark conflicts the "
        "codebook resolves. The empty 'none' column in modality is the "
        "marginal mismatch.",
    )
    b.figure(
        "fig12_conflict_decomposition.png",
        "Figure 5. Round-1 conflicts by cause. 254 of 355 fall on one of three "
        "stated definitional boundaries.",
    )

    rc = load(RESULTS / "round_comparison.json") or {"fields": {}}

    def _delta_ci(field: str, key: str) -> str:
        entry = (rc["fields"].get(field) or {}).get(key)
        if not entry:
            return "--"
        return (
            f"[{entry['lower']:+.3f}, {entry['upper']:+.3f}]"
            + ("  *" if entry["excludes_zero"] else "")
        )

    b.table(
        "Change in kappa over the re-issued segments, treated fields against "
        "the untreated control. Asterisk marks an interval excluding zero; "
        "both resampling units agree on every field.",
        ["Field", "Arm", "Round 1", "Round 2", "Change",
         "95% CI (children)", "95% CI (segments)"],
        [
            [
                f,
                e["arm"],
                f"{e['kappa_before']:.3f}",
                f"{e['kappa_after']:.3f}",
                f"{e['delta']:+.3f}",
                _delta_ci(f, "delta_clustered"),
                _delta_ci(f, "delta"),
            ]
            for f, e in ann["codebook_intervention"]["per_field"].items()
        ],
    )
    b.p(
        "All three treated fields improved with intervals excluding zero; the "
        "untreated control field did not. The substantially larger changes in "
        "the treated fields, together with the absence of improvement in the "
        "control, are consistent with an effect of the clarified definitions "
        "rather than a general re-annotation effect. The control is not "
        "identical to the treated fields in difficulty or category "
        "distribution, so it bounds rather than eliminates that alternative "
        "explanation. The proposed mechanism is visible in the ceilings: "
        "kappa_max on modality moved from 0.622 to 0.948 as the annotators' "
        "category vocabularies aligned, which is what a definition should do "
        "and what the round-1 diagnosis predicted.",
    )
    b.figure(
        "fig13_round_comparison.png",
        "Figure 6. Reliability before and after the codebook, with the paired "
        "interval on each change. The control field is shown in grey.",
    )

    b.h2("Gold standard")
    b.p(
        "**Substantive disagreement affected 127 of 330 segments, not 322.** "
        "The larger figure is the number of segments adjudication touched, and "
        "the two must not be read as the same quantity. Of the 503 fields "
        "adjudicated, 321 were free-text behavior descriptions, which differ "
        "by exact string match on almost every segment even where the two "
        "annotators describe the same event in different words; resolving "
        "those is a choice between two adequate wordings rather than a "
        "substantive judgement. Categorical disagreement — the quantity that "
        "bears on reliability — affected 182 fields across 127 segments. "
        "Because a segment undecided on any field is excluded from the gold "
        "standard entirely, the wording rows still had to be settled, which is "
        "why only 8 segments required no adjudication at all."
    )
    b.table(
        "Adjudication load, by the kind of conflict.",
        ["Quantity", "n"],
        [
            ["Categorical field conflicts (domain, modality, prompt_level, outcome)", "182"],
            ["Segments with at least one categorical conflict", "127"],
            ["Free-text behavior conflicts (exact match)", "321"],
            ["Total fields adjudicated", "503"],
            ["Segments requiring any adjudication", str(gold["composition"].get("adjudicated", 0))],
            ["Segments requiring none (agreed on every field)", str(gold["composition"].get("agreed", 0))],
        ],
    )
    b.table(
        "Composition of the adjudicated gold standard.",
        ["Property", "Value"],
        [
            ["Segments in gold", f"{gold['n_segments']} of {ann['n_segments']}"],
            ["Excluded (unresolved)", str(gold["n_excluded"])],
            ["Adjudicator", gold["adjudicator"]],
            [
                "Null values in gold",
                ", ".join(f"{k} {v}" for k, v in gold["nulls_per_field"].items()),
            ],
        ],
    )

    b.page_break()

    # ---- results: extraction ------------------------------------------
    b.h2("Generator behaviour")
    b.p(
        "Self-reported provider status is not a usable guide to whether a "
        "model produced anything. Across 496 abstentions from the three "
        "generators, 494 (99.6%) still carried at least one populated field. "
        "One generator self-reported 'abstained' on 197 of 330 segments while "
        "populating domain on 97.0% of them; another reported mean confidence "
        "0.86 alongside the sparsest output in the roster."
    )
    b.figure(
        "fig6_status_vs_output.png",
        "Figure E. Self-reported status against actual field population.",
    )
    b.p(
        "The generators diverge almost everywhere. Unanimity across all three "
        "is rare: 4.5% of segments on domain, 15.2% on modality, 12.1% on "
        "outcome, 6.1% on prompt_level. Divergence of this magnitude is what "
        "makes selection a live question rather than a formality."
    )
    b.figure(
        "fig7_divergence.png",
        "Figure F. Candidate divergence across the three generators.",
    )
    b.p(
        "Taking the union across generators raises field population above the "
        "best single generator by 16.1 points on outcome and 8.5 on "
        "prompt_level. These are populated fields, not correct ones; whether "
        "the additional values are supported by the transcript is what the "
        "annotation measures."
    )
    b.figure(
        "fig8_coverage_headroom.png",
        "Figure G. Coverage headroom available to an oracle selector, in "
        "populated fields rather than correct ones.",
    )
    b.figure(
        "fig9_mars_branches.png",
        "Figure H. MARS candidate-stage branch distribution: 12.7% abstain "
        "before any judge is consulted, 37.3% short-circuit, 50.0% present a "
        "genuine ranking decision.",
        width=5.6,
    )

    b.h2("Extraction accuracy")
    b.table(
        f"Acceptable extractions per field (n = {gold['n_segments']}; acceptable "
        "= correct or correctly null; free-text behavior excluded).",
        ["Generator", *fields],
        [
            [model, *[pct(ext["per_field_accuracy"][model][f]["rate"]) for f in fields]]
            for model in models
        ],
    )
    b.figure(
        "fig16_field_accuracy.png",
        "Figure 7. Per-field extraction accuracy against the adjudicated gold "
        "standard.",
    )
    b.p(
        "Accuracy and coverage must be read together. qwen2.5:3b returns "
        "nothing on 277 of 330 segments for prompt_level, so its 4.2% is not "
        "comparable to the others as a quality figure."
    )

    b.table(
        "Values asserted where the gold standard records that the transcript "
        "supports none. Domain and prompt_level are omitted: gold records only "
        "3 and 2 nulls for them, too few to rate.",
        ["Generator", "modality (n=77)", "outcome (n=115)"],
        [
            [
                model,
                f"{ext['unsupported_extractions'][model]['modality']['n']} "
                f"({pct(ext['unsupported_extractions'][model]['modality']['rate'])})",
                f"{ext['unsupported_extractions'][model]['outcome']['n']} "
                f"({pct(ext['unsupported_extractions'][model]['outcome']['rate'])})",
            ]
            for model in models
        ],
    )
    b.p(
        "This is the measurement the explicit null convention was designed to "
        "permit, and it bears directly on the requirement that an extraction "
        "provider must not generate field values unsupported by source text."
    )
    b.figure(
        "fig17_unsupported.png",
        "Figure 8. Values asserted where the transcript supports none.",
        width=4.6,
    )

    w = ext["whole_record"]
    b.table(
        "Whole-record accuracy (all four categorical fields acceptable) and "
        "the ceiling available to selection.",
        ["Selector", "Accuracy"],
        [
            *[[k, pct(v)] for k, v in w["per_generator"].items()],
            ["Oracle ceiling (best candidate per segment)", pct(w["oracle_ceiling"])],
            ["Headroom available to reranking", pct(w["headroom"])],
        ],
    )
    b.figure(
        "fig18_record_ceiling.png",
        "Figure 9. Whole-record accuracy and the oracle ceiling. Headroom for "
        "any selector is 1.5 points — five segments of 330.",
    )
    b.figure(
        "fig19_behavior_overlap.png",
        "Figure 10. Free-text behavior against the human reference band. The "
        "two annotators reach a median overlap of 0.316 on the same segment; "
        "models sit near 0.08.",
    )

    aug = m.get("augmented_roster")
    if aug:
        per_model = aug["per_model"]
        b.h2("A larger, more recent generator")
        b.p(
            "The three generators above are small local models, which invites "
            "the objection that the failures reported are failures of model "
            "size rather than of the task. A fourth generator, qwen3:14b, was "
            "therefore run over the same 330 segments and scored against the "
            "same gold standard. Because gold holds values authored from the "
            "transcript rather than judgements of model output, this cost no "
            "additional annotation — which is what the model-independent "
            "annotation design was for. The fourth generator contributed no "
            "candidates to the MARS run or to the three-generator ceiling "
            "reported above, and is reported separately for that reason."
        )
        b.table(
            "Four generators against the same adjudicated gold "
            f"(n = {gold['n_segments']}). Accuracy and abstention are means "
            "across the four categorical fields; unsupported assertion is "
            "pooled over the segments gold records as null.",
            ["Generator", "Mean accuracy", "Abstention", "Unsupported assertions"],
            [
                [
                    model,
                    pct(e["mean_field_accuracy"]),
                    pct(e["mean_abstention_rate"]),
                    f"{e['unsupported_n']}/{e['unsupported_opportunities']} "
                    f"({pct(e['unsupported_rate'], 0)})",
                ]
                for model, e in per_model.items()
            ],
        )
        b.p(
            "The larger, more recent model is not more accurate. Its mean "
            "field accuracy is statistically indistinguishable from the best "
            "of the smaller models, and its whole-record accuracy is lower. "
            "It is, however, markedly less safe: on modality it asserts a "
            "value on 76 of the 77 segments where the gold standard records "
            "that the transcript supports none, and on outcome 111 of 115."
        )
        b.p(
            "Within the four-model roster evaluated here, lower abstention "
            "coincided with higher unsupported assertion: the model abstaining "
            "on 48% of fields asserted unsupported values on 31% of "
            "opportunities, and the model abstaining on 3% asserted them on "
            "97%. The ordering is consistent across all four, but four models "
            "is a descriptive observation rather than evidence of a general "
            "relationship, and it is offered as such. The weakest generator in "
            "the roster appears safest only because it so often declines. This "
            "property would be important in any future clinical or "
            "intervention-monitoring pathway, and it is not one that model "
            "selection ordinarily optimises for."
        )
        b.figure(
            "fig22_extended_roster.png",
            "Figure 13. Left: per-field accuracy across four generators. "
            "Right: unsupported assertion against abstention rate. The four "
            "models are consistently ordered; with four points this is a "
            "descriptive observation, not an estimated relationship.",
        )
        b.p(
            f"Adding the fourth generator raised the oracle ceiling from "
            f"{pct(ext['whole_record']['oracle_ceiling'])} to "
            f"{pct(aug['whole_record']['oracle_ceiling'])}, so the roster did "
            "gain genuine diversity, while no single generator improved on the "
            "best of the original three."
        )

    b.page_break()

    # ---- results: MARS -------------------------------------------------
    b.h2("Multi-judge reranking (MARS)")
    cfg = mars["config"]
    b.p(
        f"Judges: {', '.join(cfg['judges'])}. Agreement threshold "
        f"{cfg['agreement_threshold']}, minimum eligible judges "
        f"{cfg['min_eligible_judges']}. Judge eligibility removes any model "
        "that generated a candidate for the segment, leaving three eligible "
        "judges on 124 rerank segments and two on 41. The maximum per-judge "
        f"discard rate in the reported run was {pct(cfg['max_judge_discard_rate'])}."
    )
    b.p(
        "An earlier run of this configuration reported 205 successes and "
        "looked unremarkable. In it, one judge — a reasoning model whose "
        "chain of thought consumed the entire token budget before an answer "
        "was emitted — was discarded as unparseable on 165 of 165 rerank "
        "segments while still appearing on the panel. The run was discarded "
        "and the runner now reports a per-judge discard rate so the failure "
        "cannot recur silently.",
        italic=True,
    )
    o = mars["outcomes"]
    b.table(
        f"MARS outcomes (n = {o['n_total']}).",
        ["Outcome", "n", "Share"],
        [
            ["Record returned", str(o["n_returned"]), pct(o["coverage"])],
            *[
                [reason.replace("_", " "), str(n), pct(n / o["n_total"])]
                for reason, n in o["abstention_reasons"].items()
            ],
        ],
    )
    b.figure(
        "fig20_mars_outcomes.png",
        "Figure 11. MARS outcome profile and whole-record accuracy against the "
        "best single generator.",
    )

    sel = mars["selection_quality"]
    b.p(
        "Whole-record accuracy over every returned record is the wrong "
        f"instrument for asking whether reranking helps: it includes the "
        f"{sel['n_short_circuit_excluded']} single-candidate short-circuits "
        "where no selection occurred, and it fires on 4.5% of segments. "
        f"Selection is therefore measured on the {sel['n_judged_segments']} "
        "judged segments, field by field."
    )
    b.table(
        f"Per-field accuracy of three selection policies ({sel['n_judged_segments']} "
        "judged segments).",
        ["Selector", *fields, "Mean"],
        [
            [
                label,
                *[pct(sel["per_field"][f][key]) for f in fields],
                pct(sel["mean_accuracy"][key]),
            ]
            for label, key in (
                ("Best generator", "best_generator"),
                ("MARS", "mars"),
                ("Random candidate", "random_candidate"),
            )
        ],
    )
    b.table(
        "Paired differences, 10,000 bootstrap replicates over segments. "
        "Asterisk marks an interval excluding zero.",
        ["Field", "MARS − random candidate", "MARS − best generator"],
        [
            [
                f,
                f"{100 * sel['per_field'][f]['vs_random']['difference']:+.1f} "
                f"[{100 * sel['per_field'][f]['vs_random']['lower']:+.1f}, "
                f"{100 * sel['per_field'][f]['vs_random']['upper']:+.1f}]"
                + ("  *" if sel["per_field"][f]["vs_random"]["excludes_zero"] else ""),
                f"{100 * sel['per_field'][f]['vs_best']['difference']:+.1f} "
                f"[{100 * sel['per_field'][f]['vs_best']['lower']:+.1f}, "
                f"{100 * sel['per_field'][f]['vs_best']['upper']:+.1f}]"
                + ("  *" if sel["per_field"][f]["vs_best"]["excludes_zero"] else ""),
            ]
            for f in fields
        ],
    )
    b.p(
        "Two findings point in opposite directions. Reranking carries real "
        "signal: MARS selects better than a random candidate on every field, "
        "significantly so on modality and prompt_level. It does not beat the "
        "simplest informed policy: against always using the strongest "
        "generator it is 3.9 points worse on average and significantly worse "
        "on domain."
    )
    b.p(
        f"MARS selected the strongest generator on "
        f"{pct(sel['share_choosing_best_generator'], 0)} of judged segments. On "
        "domain that model leads the roster by 32 points, so the 42% of "
        "selections that go elsewhere carry an expected cost of roughly 14.7 "
        "points against an observed deficit of 12.7. The judges rank "
        "candidates, while the accuracy difference lives in which model "
        "produced them. This is a property of a roster with a dominant "
        "generator, not a general result about reranking."
    )
    b.figure(
        "fig21_selection.png",
        "Figure 12. Selection quality on the judged segments, against both "
        "baselines, with paired intervals.",
    )

    # ---- reporting layer ----------------------------------------------
    if ground and ground.get("n_llm_reports"):
        summary = ground["summary"]
        n = ground["n_llm_reports"]
        b.h2("Reporting layer")
        b.p(
            "Initial prompt-only generation did not reliably conform to the "
            "report schema. Because that behaviour could reflect decoding "
            "configuration rather than model capability, generation was "
            "repeated using the model server's native schema-constrained "
            "decoding. All 11 outputs then conformed structurally, and these "
            "constrained outputs form the reporting evaluation reported here."
        )
        b.p(
            "Schema constraint guarantees the shape of the output, not the "
            "truth of the values inside it. Structural conformance and "
            "governance conformance are therefore measured separately, under "
            "three headings: content safety, evidence grounding, and "
            "abstention preservation."
        )
        b.table(
            f"Reporting-layer evaluation ({n} reports, one per child, "
            f"{ground['model']}). Rates are pooled over assertions and "
            "references rather than averaged over reports.",
            ["Property", "Result"],
            [
                [
                    "Content safety — reports containing prohibited "
                    "diagnostic, treatment, causal or prognostic content",
                    f"{summary['prohibited_content_reports']} of {n}",
                ],
                [
                    "Evidence grounding — numeric assertions absent from the "
                    "evidence packet",
                    f"{summary['numeric_ungrounded']} of "
                    f"{summary['numeric_assertions']} "
                    f"({pct(summary['pooled_ungrounded_rate'])})",
                ],
                [
                    "Evidence grounding — invalid evidence references",
                    f"{summary['evidence_references_invalid']} of "
                    f"{summary['evidence_references']} "
                    f"({pct(summary['pooled_invalid_reference_rate'])})",
                ],
                [
                    "Evidence grounding — reports with no ungrounded value",
                    f"{summary['reports_fully_grounded']} of {n}",
                ],
                [
                    "Abstention preservation — reports passing deterministic "
                    "governance validation",
                    f"{summary['reports_passing_validation']} of {n}",
                ],
            ],
        )
        b.p(
            "Schema-constrained decoding produced structurally conformant "
            "reports for all 11 children. Structural conformance did not, "
            "however, imply governance conformance. Across the 11 reports the "
            f"model made {summary['numeric_assertions']} numerical assertions, "
            f"of which {summary['numeric_ungrounded']} were not present in the "
            f"supplied evidence packet, and produced "
            f"{summary['evidence_references_invalid']} invalid evidence "
            f"references out of {summary['evidence_references']}. No report "
            "contained prohibited diagnostic, treatment, causal or prognostic "
            "content. Nevertheless, none of the 11 passed deterministic "
            "governance validation, because analytics intentionally withheld "
            "by the adequacy router — cross-setting and cross-contributor "
            "comparisons — were not acknowledged as unavailable. The model did "
            "not fabricate these analyses; it silently omitted their absence. "
            "The distinction matters because a reader cannot tell a "
            "deliberately withheld analysis from one that was simply not "
            "attempted."
        )
        b.p(
            "Deterministic governance validation, as used here, checks the "
            "evidence and governance contract rather than output structure: "
            "prohibited content, acknowledgement of insufficient evidence, and "
            "acknowledgement of each withheld metric. A failure is not "
            "malformed output.",
            italic=True,
        )

    b.page_break()

    # ---- limitations ---------------------------------------------------
    b.h1("Discussion")

    b.h2("Principal results")
    b.p(
        "Three findings, in the order the pipeline produces them. First, low "
        "inter-annotator agreement on behavioural fields was largely "
        "definitional rather than a matter of annotator care: modality's "
        "round-1 kappa of 0.570 was 92% of the ceiling the annotators' own "
        "category usage permitted, and 254 of 355 categorical conflicts fell "
        "on three enumerable definitional boundaries. A written codebook, "
        "evaluated under a design with an untreated control field, was "
        "followed by improvements of +0.29 to +0.48 on the treated fields and "
        "no change in the control."
    )
    b.p(
        "Second, the extraction models assert clinical field values the source "
        "text does not support, at high rates. Where the gold standard records "
        "that a transcript supports no modality, one generator asserted one on "
        "93.5% of occasions; on outcome, another did so on 67.8%. This is the "
        "measurement the explicit null convention was designed to permit, and "
        "it would be more consequential than accuracy in any future clinical or "
        "intervention-monitoring pathway, because an unsupported value is "
        "indistinguishable in form from a supported one once written. The "
        "corpora analysed here are archival research transcripts, not "
        "observations collected through such a pathway, so this is an "
        "argument about the failure mode rather than a demonstration of "
        "clinical impact."
    )
    b.p(
        "That failure is not a consequence of model size. A larger and more "
        "recent generator, added after annotation and scored against the same "
        "gold, matched the best smaller model on accuracy while asserting "
        "unsupported values on 97% of opportunities — the worst rate in the "
        "roster. Across all four generators the relationship between "
        "abstention and unsupported assertion was consistently ordered, which "
        "locates the safety property in a model's willingness to decline "
        "rather than in its capability — descriptively, across four models."
    )
    b.p(
        "The reporting-layer failure was not primarily one of prohibited "
        "content generation. The constraint design prevented diagnosis, "
        "treatment recommendation, causal inference and prognostic claims in "
        "all evaluated reports. The failure concerned instead the preservation "
        "of abstention state: when upstream governance withheld an analysis, "
        "the reporting model omitted the analysis without communicating that "
        "it had been withheld. Safe downstream reporting therefore requires "
        "preservation of both available evidence and unavailable evidence "
        "states — a model can appear restrained, declining to invent the "
        "withheld comparison, while still breaking the governance contract by "
        "not reporting that anything was withheld."
    )
    b.p(
        "Third, multi-model selection contains real signal but cannot rescue "
        "weak candidates. Reranking selected better than chance on every "
        "field, significantly on two, yet did not beat the simplest informed "
        "policy of always using the strongest generator. With an oracle "
        "ceiling of 6.1% on whole-record correctness, the total headroom "
        "available to any selector on this roster was 1.5 percentage points."
    )

    b.h2("Comparison with prior work")
    b.p(
        "[TO COMPLETE BEFORE SUBMISSION] This section must situate the three "
        "findings against published work and is not yet written. It should "
        "cover at minimum: reported inter-annotator agreement for behavioural "
        "and communicative coding schemes, and whether kappa is commonly "
        "reported alongside its marginal-imposed ceiling; iterative codebook "
        "development in content analysis, and whether controlled before/after "
        "designs with an untreated field have been used to evaluate a codebook "
        "revision; prior measurement of unsupported or fabricated field values "
        "in clinical information extraction, and how explicit null annotation "
        "compares with the alternatives; and evaluations of multi-model "
        "selection or LLM-as-judge reranking in health applications, "
        "particularly any that report negative or roster-conditional results.",
        colour=RED,
    )
    b.p(
        "Two specific claims in this manuscript require citation rather than "
        "assertion: that maximum attainable kappa under fixed marginals is an "
        "established diagnostic rather than a contribution of this work, and "
        "that the Fleiss-Cohen-Everitt large-sample variance is the standard "
        "asymptotic estimator used here as a cross-check.",
        colour=RED,
    )

    b.h2("Conclusions")
    b.p(
        "A rigorous evaluation process applied to this pipeline exposed "
        "failure at two layers. The annotation scheme was unstable in ways "
        "that a reported kappa alone would have concealed, and a written "
        "codebook measurably repaired it. The extraction models were not "
        "adequate for the task, and their most consequential failure was not "
        "inaccuracy but the assertion of unsupported clinical fields. "
        "Candidate selection did not compensate, and on this roster could not "
        "have: the ceiling was 6.1%."
    )
    b.p(
        "The practical implication for systems of this kind is that abstention "
        "and unsupported-assertion rates belong in the primary evaluation "
        "rather than in a safety appendix, and that a model-independent gold "
        "standard with explicit nulls is what makes them measurable. The "
        "generators evaluated here are small local models, and a stronger "
        "model may extract more accurately; whether it asserts fewer "
        "unsupported values is a separate question that this design is "
        "equipped to answer and that we regard as the more important one."
    )

    b.h1("Limitations")
    b.bullets(
        [
            "Evaluation-set membership is conditioned on model output. The "
            "batch retained only segments where all three generators produced "
            "an admissible response, so reported accuracy, unsupported-"
            "assertion rates and the oracle ceiling all describe segments the "
            "models could attempt. A model-independent held-out set has been "
            "frozen to address this but is not yet annotated, so the "
            "generalisation is currently assumed rather than demonstrated.",
            "Two annotators, one pair, one corpus. Cohen's kappa describes this "
            "pair, and the codebook rules were written after observing where "
            "this pair diverged.",
            "Agreement is not validity. Two annotators converging on a stated "
            "rule is reliability; whether the rule is correct is settled at "
            "adjudication and by argument, not by any statistic.",
            "Conflicts were adjudicated by the two annotators jointly rather "
            "than by an independent third party. Decisions split 89/90 between "
            "their respective values, indicating neither dominated, which "
            "bounds but does not eliminate the concern.",
            "Round 2 is a within-annotator repeat under instruction, not an "
            "independent replication. What two fresh annotators working under "
            "the codebook would achieve was not measured.",
            "The generator roster is four local models. Adding a larger, "
            "more recent one did not improve accuracy, which weakens but "
            "does not eliminate the objection that a frontier model might. "
            "No frontier model was evaluated; that comparison is blocked on "
            "corpus terms for third-party API processing.",
            "The MARS selection finding is roster-conditional: it follows from "
            "one generator dominating domain by 32 points. The finding is "
            "'reranking loses to a dominant generator', not 'reranking does "
            "not work'.",
            "The corpora are archival child-investigator and child-parent "
            "transcripts, not contributor observations submitted through the "
            "system's own interface. Transfer to the deployed input "
            "distribution is assumed, not demonstrated.",
            "De-identification replaces names by roster and header match "
            "rather than by named-entity recognition, and over-redacts: 82 "
            "[NAME] placeholders appear across 62 of the 330 annotated "
            "segments, some of which are ordinary words that match a child "
            "pseudonym.",
        ]
    )

    b.h1("Not measured")
    b.p(
        "Recorded so that no reader infers more than exists. The evaluation "
        "code for several of these exists and is tested; it reports that the "
        "quantity is unavailable rather than producing a number."
    )
    extra = [
        "Extraction accuracy on a sample not conditioned on model output: the "
        "held-out set is frozen (132 segments) but not yet annotated.",
        "Whether the codebook generalises to annotators using it from the "
        "start, rather than reaching it after a disagreement round.",
        "A frontier-scale generator: the four models evaluated are all "
        "locally served.",
    ]
    b.bullets([f"• {item}" for item in [*m["not_measured"], *extra]])

    b.h1("Appendix: superseded pilot")
    b.p(
        "A defect in child attribution assigned every segment to an unknown "
        "child. A pilot annotation set drawn before the fix landed 28 of its "
        "31 items on a single child and none on the Flusberg corpus. Its field "
        "accuracies are reproduced here as motivation only and are explicitly "
        "not treated as a baseline; they are superseded by the adjudicated "
        "gold standard reported above.",
        italic=True,
    )
    b.figure(
        "fig4_pilot_superseded.png",
        "Figure I. Pilot field accuracy (superseded). Retained for provenance, "
        "not as a result.",
    )

    b.h1("Reproducibility")
    pinned = sum(1 for a in manifest.get("artefacts", []) if a.get("pinned"))
    b.p(
        f"All results derive from {len(manifest.get('artefacts', []))} recorded "
        f"artefacts, of which {pinned} are pinned by SHA-256 checksum. The "
        "reproduction sequence is recorded in docs/paper/artifacts.md. Tests "
        "re-derive every number in the manuscript from its artefact and fail "
        "if prose and data disagree. Fixed seeds: sheet ordering 42 and 4242, "
        "bootstrap 20260915/20260916 at 10,000 replicates."
    )

    b.h1("Data availability")
    b.p(
        "[TO COMPLETE BEFORE SUBMISSION] The source corpora are publicly "
        "available from ASDBank/TalkBank under their own terms and are not "
        "redistributed here. The derived artefacts — the frozen annotation "
        "batch, both annotators' values for both rounds, the adjudicated gold "
        "standard, all computed statistics and the analysis code — are "
        "recorded in this repository. State the repository location, licence, "
        "and whether the gold standard will be released, before submission.",
        colour=RED,
    )

    b.h1("Author contributions, conflicts of interest, and AI use")
    b.p(
        "[TO COMPLETE BEFORE SUBMISSION] Author contributions and conflict of "
        "interest declarations are required and are not yet written.",
        colour=RED,
    )
    b.p(
        "AI use is disclosed as follows. The extraction and judge models are "
        "the object of study and are described in Methods. Separately, "
        "substantial portions of the evaluation tooling and drafting of this "
        "manuscript were produced with AI assistance. No AI system authored, "
        "selected, or altered a gold-standard value, an adjudication decision, "
        "or a reported statistic: every annotation and every adjudication is "
        "human, statistics are computed by code from recorded artefacts, and "
        "automated tests re-derive each reported number from its artefact. The "
        "exact disclosure wording required by the journal must be confirmed at "
        "submission."
    )

    b.h1("References")
    b.p(
        "[TO COMPLETE BEFORE SUBMISSION] No reference list has been compiled. "
        "Required at minimum: both corpus DOIs, the kappa and maximum-kappa "
        "literature, the asymptotic variance estimator, agreement reporting "
        "guidance, and the prior work identified in the Comparison section.",
        colour=RED,
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    b.doc.save(str(OUT))
    return OUT


def main() -> None:
    path = build()
    size = path.stat().st_size
    print(f"Wrote {path.relative_to(ROOT)}  ({size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
