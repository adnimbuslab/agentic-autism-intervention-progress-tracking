---
name: data-pipeline
description: Builds the CHAT transcript processing pipeline — parsing .cha files, deidentification, episode segmentation, behavioral segment selection, and provisional structured extraction using a temporary LLM. Expert gold-standard annotation and foundation-model training will be performed later.
model: sonnet
tools:
  - Bash
  - Read
  - Write
  - Edit
---

# Data Pipeline Agent

During the current application-development phase, transform raw CHAT
(Codes for Human Analysis of Transcripts) files into clean behavioral
segments and use the temporary LLM extraction provider to generate
provisional structured records.

Do NOT fine-tune the final foundation model during this phase.

LLM-generated structured records are provisional application-development
data only. They are not expert ground truth and must not be used as final
research labels.

Expert review, adjudication, gold-standard dataset preparation, and
foundation-model fine-tuning will be performed later.

## Source Data

- **Rollins Corpus**: `exp-data/Rollins/{Carl,Roger,Sid,Mars,Josh}/*.cha`
  - 5 children, 21 sessions, child-investigator interactions
  - Rich %spa (speech acts), %act (actions), %gpx (gestures) annotations
  - Age-based dating only (e.g., 2;08 = 2 years 8 months)

- **Flusberg Corpus**: `exp-data/Flusberg.zip` (auto-extracted to `exp-data/Flusberg/` by `ensure_flusberg_extracted()`)
  - 6 children (Jack, Rick, Mark, Brett, Stuart, Roger), 65 sessions
  - Child-mother interactions with exact dates
  - Longitudinal with repeated measurements

## CHAT Format Reference

```
@UTF8
@Participants: CHI Target_Child, INV Investigator
@ID: eng|Rollins|CHI|2;08.|male|||Target_Child|||
@Activities: farm
*CHI: xxx .           ← child utterance (xxx = unintelligible)
%spa: $NIA:RP:VNR     ← speech act code
%gpx: reaches upward  ← gesture/proxemic
*INV: you want the toy ?
%spa: $DCC:YQ         ← yes/no question
%act: hands him the toy  ← action description
```

Key speaker codes: CHI (child), INV (investigator), MOT (mother)
Special utterance markers: xxx (unintelligible), 0 (no speech), [+ trn] (transitional)

## Pipeline Steps to Implement

### Step 1: CHAT Parser (`data/pipeline/chat_parser.py`)
- Parse all .cha files into structured Python objects
- Extract: headers (@-lines), utterances (*-lines), dependent tiers (%-lines)
- Link each %-tier to its parent utterance
- Output: list of Session objects, each containing Utterance objects with all tiers

### Step 2: Unified Dataset (`data/pipeline/build_dataset.py`)
- Merge Rollins + Flusberg into one long-format DataFrame/CSV
- Columns: corpus, child_id, session_id, source_file, date, relative_month, speaker_code, activity_or_setting, utterance_seq, utterance_raw, spa, act, gpx, tim, mor, gra, com
- Assign analytic child IDs (disambiguate Roger in Rollins vs Flusberg)
- Compute relative_month from age fields (Rollins) and dates (Flusberg)
- Target: ~75,003 rows

### Step 3: Deidentification (`data/pipeline/deidentify.py`)
- Scan utterance text and annotation tiers for residual names/PII
- Replace with placeholder tokens: [NAME], [LOCATION], etc.
- Flag ambiguous cases for manual review
- Output deidentification report: count of replacements, flagged items

### Step 4: Episode Segmentation (`data/pipeline/segment_episodes.py`)
- Identify coherent behavioral episodes (2-8 consecutive turns)
- Episode = multi-turn sequence centered on a communicative/behavioral event
- Criteria: child-initiated or child-response, presence of behavioral annotation
- Tag episode boundaries with type (request, imitation, joint_attention, etc.)

### Step 5: Segment Selection (`data/pipeline/select_segments.py`)
- From episodes, select 1,000-3,000 meaningful behavioral segments
- Ensure diversity across: children, goal domains, modalities, settings
- Balanced representation across all 11 children
- Output: selected segments with context, ready for temporary LLM structured extraction

### Step 6: Temporary LLM Structured Extraction (`data/annotation/`)

- Generate the structured observation JSON schema matching Section 4 of the technical specification
- Send selected behavioral segments from Step 5 to the temporary LLM extraction provider
- Require schema-constrained structured output
- Generate provisional structured records from each selected CHAT segment
- Preserve the complete source segment and provenance with every structured record
- Mark every LLM-generated record as `provisional_llm`
- Store the LLM provider/model name, prompt version, schema version, configuration hash, and timestamp
- Never treat LLM-generated records as expert gold-standard annotations
- Prepare the records so domain experts can review and correct them later
- Expert-reviewed/adjudicated records will later become the gold-standard dataset used for foundation-model fine-tuning

## Output Format

Each processed segment should produce a pair:
```json
{
  "segment_id": "R03_Sid_020200_seg_042",
  "source": {
    "corpus": "Rollins",
    "child_id": "R03_Sid",
    "session_id": "020200",
    "source_file": "Rollins/Sid/020200.cha",
    "turns": [
      {"speaker": "CHI", "text": "xxx .", "spa": "$NIA:RP:VNR", "gpx": "reaches upward"},
      {"speaker": "INV", "text": "you want the toy ?", "spa": "$DCC:YQ", "act": "hands him the toy"},
      {"speaker": "CHI", "text": "0 .", "spa": "$DCC:AN:NO", "gpx": "brushes away toy"}
    ]
  },
	"provisional_extraction": {
		"status": "provisional_llm",
		"structured_record": null,
		"provider": null,
		"model": null,
		"prompt_version": null,
		"schema_version": null,
		"generated_at": null
	}
}
```

## Technical Requirements
- Python 3.11+, pandas, pydantic for data models
- All scripts runnable from project root: `python -m data.pipeline.chat_parser`
- Unit tests for parser edge cases (malformed lines, missing tiers, encoding issues)
- Never modify source .cha files — read-only access
