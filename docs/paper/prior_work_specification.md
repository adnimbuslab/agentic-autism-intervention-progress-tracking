# Comparison with Prior Work — specification

Not the section itself: a list of every claim in the manuscript that currently
asserts rather than cites, each with the kind of source it needs and what the
citation has to do. Written so the literature search has targets rather than a
blank heading.

Two kinds of entry, and they need different sources:

- **[EST]** — an established method the paper uses. Needs a canonical citation
  so the method is not mistaken for a contribution of this work.
- **[POS]** — a claim of novelty or of a gap. Needs the closest prior work,
  cited in order to say precisely how this study differs. These are where a
  reviewer decides whether the paper is new.

---

## Methods — established techniques the paper must not appear to claim

| # | Claim as written | Needs | Why it matters |
|---|---|---|---|
| 1 | Maximum attainable kappa under fixed marginals (`kappa_max`) separates definitional from judgement disagreement | **[EST]** Umesh, Peterson & Sauber (1989); Sim & Wright (2005) on prevalence and bias effects | The manuscript leans on this as its central diagnostic. Uncited, it reads as a novel statistic; it is not. Verify each source actually defines maximum-attainable kappa before citing. |
| 2 | Fleiss, Cohen & Everitt (1969) large-sample variance of kappa | **[EST]** the original | Named in the text and in `reliability_mathematics.md`; currently no reference. |
| 3 | Landis & Koch interpretive bands | **[EST]** Landis & Koch (1977) | Used for orientation only — cite and say so, since the bands are conventional and the authors called them arbitrary. |
| 4 | Krippendorff's 0.800 / 0.667 thresholds | **[EST]** Krippendorff | Applied to kappa by analogy; state that explicitly. |
| 5 | Cluster bootstrap for observations nested within participants | **[EST]** a standard resampling reference | Segments nest within 11 children; the paper resamples children. Needs a source for the method, not just the rationale. |
| 6 | Exact McNemar test for paired binary outcomes | **[EST]** | Used for the MARS-versus-generator comparison. |
| 7 | GRRAS reporting guideline for agreement studies | **[EST]** Kottner et al. (2011) | Reporting the reliability component against it would strengthen the submission; cite if adopted. |
| 8 | Rollins and Flusberg corpora | **[EST]** both DOIs plus TalkBank/ASDBank attribution in the form their terms require | Currently referenced only in prose. |

## Positioning — where the paper must say what is new

| # | Area | Needs | The question a reviewer will ask |
|---|---|---|---|
| 9 | **Annotation reliability and codebook development** | **[POS]** iterative codebook refinement in content analysis and in clinical/behavioural coding | Codebook revision after observing disagreement is standard practice. What is uncommon here is the *controlled* evaluation — an untreated control field carried through a blind re-annotation. Find whether that design has been used before; if it has, cite it and differentiate; if it has not, say so and let the citation gap carry the claim. |
| 10 | **Unsupported / fabricated field values in clinical NLP** | **[POS]** hallucination and faithfulness measurement in clinical information extraction | The paper operationalises this through *explicit gold-standard nulls*, which makes an unsupported assertion measurable rather than inferred. Establish whether prior work annotates absence explicitly, or only measures errors against present values. This is the paper's strongest novelty candidate. |
| 11 | **Abstention and selective prediction** | **[POS]** selective prediction / reject option, and abstention in clinical decision support | The finding is that unsupported assertion tracks willingness to answer. Prior work on abstention usually treats it as a cost to be minimised; here low abstention is the hazard. Position against that. |
| 12 | **LLM-as-judge and multi-model selection** | **[POS]** judge-based ranking, ensembling, reranking — including any negative or roster-conditional results | The MARS result is negative and roster-conditional. Cite whoever has reported similar, or note the scarcity of negative results in this area. |
| 13 | **Governance-aware clinical AI pipelines** | **[POS]** human-in-the-loop clinical AI, deterministic validation around generative components | The reporting-layer finding — structural conformance without governance conformance, and loss of upstream abstention state — needs positioning against whatever exists on constraining clinical generation. |
| 14 | **Structured / schema-constrained decoding** | **[EST]/[POS]** constrained decoding and structured output | Used as a method, and the paper reports that it changes conformance from 0/11 to 11/11. Cite the technique; note that conformance is not groundedness. |

---

## The sentence the section has to earn

The Discussion currently claims three failure modes at three pipeline stages,
none of which conventional accuracy or format metrics would surface. The
comparison section has to establish that each is either unreported or reported
differently in prior work. If any of the three turns out to be well covered
elsewhere, the honest response is to narrow the claim rather than to omit the
citation.

## What not to do

Do not cite a source for a claim without reading it. Two entries above (#1, #2)
are methods the manuscript currently describes in detail; a citation that turns
out not to define what the text says it defines is worse than the present
`[TO COMPLETE]` marker, because the marker is honest.
