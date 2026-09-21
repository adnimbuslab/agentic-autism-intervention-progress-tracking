# User and Demo Manual

## Interventionist AI System — Autism Intervention Progress Tracking

---

## Table of Contents

1. [What This Application Does](#1-what-this-application-does)
2. [User Roles](#2-user-roles)
3. [How to Start the Application](#3-how-to-start-the-application)
4. [Demo Accounts](#4-demo-accounts)
5. [Interventionist Walkthrough](#5-interventionist-walkthrough)
6. [Goals Workflow](#6-goals-workflow)
7. [Observation Workflow](#7-observation-workflow)
8. [Records / Correction / Versioning](#8-records--correction--versioning)
9. [Analytics Workflow](#9-analytics-workflow)
10. [Reports Workflow](#10-reports-workflow)
11. [Contributor Walkthrough](#11-contributor-walkthrough)
12. [Clarification Workflow](#12-clarification-workflow)
13. [Contributor Privacy / RBAC](#13-contributor-privacy--rbac)
14. [Schedules](#14-schedules)
15. [Contributors / Actors](#15-contributors--actors)
16. [Audit](#16-audit)
17. [Demo Script](#17-demo-script)
18. [Troubleshooting](#18-troubleshooting)
19. [Security / Secret Handling](#19-security--secret-handling)
20. [Known Limitations](#20-known-limitations)

---

## 1. What This Application Does

This application collects natural-language observations about a child's intervention-related behavior from authorized contributors such as parents or teachers. It is designed for use in longitudinal autism intervention research.

**What the system can do:**

- **Preserve original observations** — Every observation submitted by a contributor is stored exactly as written and can never be altered or deleted.
- **Extract candidate structured information** — The system attempts to identify structured fields (such as the type of behavior observed, the communication modality used, whether the child was prompted, and the outcome) from the natural-language text.
- **Ask clarifying questions** — When the system needs additional information to understand the observation, it can ask the contributor focused, non-leading follow-up questions.
- **Validate structured data** — All extracted information passes through a deterministic validation step that checks for consistency and completeness. This validation is performed by code, not by AI.
- **Retain provenance** — Every piece of structured data records which extraction provider, model, and prompt version produced it. Every correction records who made it and why.
- **Allow interventionist correction and versioning** — An interventionist can review AI-extracted records and submit corrections. Corrections create new versions; original versions are never overwritten.
- **Compute deterministic analytics** — Evidence adequacy and key performance indicators (KPIs) are computed entirely by code, never by AI.
- **Generate evidence-grounded progress reports** — Reports are generated from pre-computed analytics and structured evidence. Reports must pass a safety validation check before being displayed.
- **Preserve auditability** — All significant actions (creating children, submitting observations, correcting records, generating reports) are logged in an audit trail.

**What the system does NOT do:**

- **It does not diagnose** autism or any other condition.
- **It does not prescribe treatment** — no therapy, medication, or intervention recommendations.
- **It does not make autonomous intervention decisions** — the interventionist always remains the highest authority.
- **It does not replace professional judgment** — all AI outputs are drafts requiring human review.
- **It does not make causal claims** — it will not say "improvement was caused by" any intervention.

This is a **controlled research prototype**, not production clinical software.

---

## 2. User Roles

### Interventionist

The interventionist is the primary professional user. They have full access to all features within their assigned children's workspaces.

An interventionist can:
- Create and manage child profiles
- Set intervention goals
- Invite contributors (parents, teachers) and assign them to children
- View all observations submitted by any contributor for their children
- See the AI-extracted structured data alongside original observations
- Correct AI-extracted records (creating new versions)
- Run analytics on defined review periods
- Generate and review progress reports
- Flag reports for review
- View the full audit trail
- Manage observation schedules

### Contributor

A contributor is typically a parent, teacher, therapist, or other person who regularly observes the child. Contributors have limited access designed to protect their privacy and the child's data.

A contributor can:
- See only the children they have been assigned to by an interventionist
- Submit observations in natural language (describing what they saw in their own words)
- Answer clarification questions from the system
- View their own observation history for assigned children

A contributor **cannot**:
- See other children
- See the interventionist's dashboard
- View AI-extracted structured fields or model confidence scores
- Access professional analytics or cross-setting reports
- Correct structured records
- View the audit trail
- Manage goals, schedules, or other contributors

---

## 3. How to Start the Application

### Prerequisites

- Docker and Docker Compose must be installed on your computer
- No other application should be using ports 3000, 5433, or 8000

### Starting the Application

Open a terminal at the root of the repository and run:

```
docker compose -f docker/docker-compose.yml up --build -d
```

**What this does:**
- Builds and starts three containers:
  - **db** — PostgreSQL 16 database
  - **backend** — Python/FastAPI API server (port 8000)
  - **frontend** — Next.js web application (port 3000)
- The `-d` flag runs containers in the background
- The `--build` flag ensures the latest code is included

### Checking Status

To verify all containers are running and healthy:

```
docker compose -f docker/docker-compose.yml ps
```

You should see three services listed. The `db` and `backend` services should show as "healthy" after about 30 seconds.

### Running Database Migrations

After the containers start, run the database migrations:

```
docker compose -f docker/docker-compose.yml exec backend alembic upgrade head
```

This creates all the necessary database tables.

### Loading Demo Data

To populate the application with synthetic demonstration data:

```
docker compose -f docker/docker-compose.yml exec backend python -m scripts.seed_demo
```

This creates:
- Three demo user accounts (interventionist, parent, teacher)
- Two demo children (Alex and Sam)
- Goals, observations, structured records, schedules, and audit events
- Alex has 8 observations across home and school settings (ADEQUATE evidence)
- Sam has 2 observations from one setting (LIMITED evidence)

The seed script is idempotent — running it again will not create duplicate data.

### Opening the Application

Open a web browser and navigate to:

```
http://localhost:3000
```

You should see the login page with the title "Intervention Tracker".

### Stopping the Application

```
docker compose -f docker/docker-compose.yml down
```

To also remove the database data:

```
docker compose -f docker/docker-compose.yml down -v
```

---

## 4. Demo Accounts

The following accounts are created by the seed script. These are **synthetic demo accounts only** — they do not represent real people.

| Role | Email | Password |
|---|---|---|
| **Interventionist** | demo-interventionist@example.com | DemoPass123! |
| **Parent** (Contributor) | demo-parent@example.com | DemoPass123! |
| **Teacher** (Contributor) | demo-teacher@example.com | DemoPass123! |

### Demo Children

| Name | Evidence Level | Observations | Contributors | Settings |
|---|---|---|---|---|
| **Demo Child Alex** | ADEQUATE | 8 observations | Parent + Teacher | Home + School |
| **Demo Child Sam** | LIMITED | 2 observations | Parent only | Home only |

---

## 5. Interventionist Walkthrough

### Step 1 — Login

1. Open your browser and go to `http://localhost:3000`.
2. You will see the login page with the title "Intervention Tracker".
3. In the **Email** field, type: `demo-interventionist@example.com`
4. In the **Password** field, type: `DemoPass123!`
5. Click **Sign In**.

**Expected result:** You are redirected to the Dashboard.

### Step 2 — Dashboard

After logging in, you see the Dashboard. This is the interventionist's home page.

**What you should see:**
- A heading that says "Dashboard" or shows a welcome message
- Two child cards:
  - **Demo Child Alex** — with an "Active" badge
  - **Demo Child Sam** — with an "Active" badge
- A left-side navigation panel (or top navigation) with links

The dashboard shows all children that this interventionist has created. Each child card is clickable.

### Step 3 — Open a Child Workspace

Click on **Demo Child Alex**.

**Expected result:** You enter Alex's workspace. This is the central hub for everything related to this child.

You should see navigation links or tabs for:
- **Overview** — summary of the child's workspace
- **Goals** — intervention goals for this child
- **Observations** — all submitted observations
- **Records** — AI-extracted structured records
- **Analytics** — deterministic analytics and KPIs
- **Reports** — generated progress reports
- **Schedules** — expected observation frequency
- **Contributors** — people assigned to observe this child
- **Audit** — action log for this child's data

Each tab is explained in the sections below.

### Step 4 — Overview

The Overview tab shows a summary of the child's workspace, including:
- Child's display name
- Date of birth (if provided)
- Quick links to other tabs
- Summary statistics

### Step 5 — Goals

Click the **Goals** tab.

This shows the intervention goals that the interventionist has defined for this child. For Demo Child Alex, you should see:
- **Functional requesting** — Domain: social_communication, Type: long_term
- **Cooperative play** — Domain: play, Type: short_term

Goals define what the intervention team is working on. Observations are understood in the context of these goals.

### Step 6 — Observations

Click the **Observations** tab.

This shows all observations submitted by any contributor for this child. For Demo Child Alex, there are 8 observations from both the parent and teacher, spanning home and school settings.

Each observation row shows:
- Date submitted
- Setting (home/school)
- Status (FINALIZED for completed observations)
- Who submitted it

**Click on any observation** to see its full detail.

### Step 7 — Observation Detail

When you open an observation, you see several sections:

**Source Evidence — Original Observation**
This is the exact text the contributor wrote. It is never modified. For example:
> "Demo observation: Alex pointed to the cookie jar and said 'want cookie' without any prompting."

**Source Evidence — Clarification Conversation** (if present)
If the system asked the contributor a follow-up question, the question and answer appear here. For Alex's last observation, you will see:
> Question: "Could you describe the type of prompt used — was it a gesture, verbal cue, or physical guidance?"
> Answer: "It was a gestural prompt — I pointed toward the crackers."

**AI-Derived Structured Information** (interventionist view only)
This shows the structured fields extracted from the observation:
- Domain (e.g., social_communication)
- Behavior (e.g., "pointed and said 'want cookie'")
- Modality (e.g., gestural, verbal)
- Prompt Level (e.g., independent)
- Outcome (e.g., correct)
- Confidence score
- Provider/model/prompt version (provenance)
- Validation status

**Why are these separate?** The original text is the ground truth — it is what the contributor actually saw and reported. The structured information is the system's interpretation of that text. The structured record is a candidate that must be reviewed by the interventionist. Keeping them separate preserves the evidence chain.

### Step 8 — Records

Click the **Records** tab.

This shows all structured records for the child, including version history. You can see:
- The record's current version number
- Its status (VALIDATED or CORRECTED)
- Provider and model information
- The structured field values

### Step 9 — Analytics

See [Section 9 — Analytics Workflow](#9-analytics-workflow) below.

### Step 10 — Reports

See [Section 10 — Reports Workflow](#10-reports-workflow) below.

### Step 11 — Schedules

See [Section 14 — Schedules](#14-schedules) below.

### Step 12 — Contributors

See [Section 15 — Contributors / Actors](#15-contributors--actors) below.

### Step 13 — Audit

See [Section 16 — Audit](#16-audit) below.

---

## 6. Goals Workflow

Goals define the intervention objectives for a child. They are managed by the interventionist.

### Viewing Goals

1. Open a child's workspace (e.g., Demo Child Alex).
2. Click the **Goals** tab.
3. You will see the list of active goals.

Each goal shows:
- **Title** — a short description (e.g., "Functional requesting")
- **Domain** — the area of development (e.g., social_communication, play, language, daily_living)
- **Type** — long_term or short_term
- **Description** — a detailed description of the goal
- **Status** — whether the goal is Active

### Adding a Goal

If the interface supports goal creation (an "Add Goal" or "New Goal" button is present):
1. Click the button.
2. Fill in the title, domain, type, and description.
3. Click Save.

Only interventionists can create or modify goals. Contributors cannot.

### Why Goals Matter

Goals provide context for observations. When analytics are computed, structured records are organized by goal domain. This helps the interventionist understand whether observations are covering the intended intervention areas.

---

## 7. Observation Workflow

### Viewing the Observation List

1. Open a child's workspace.
2. Click the **Observations** tab.
3. All observations for this child are listed, newest first.

Each observation shows: date, setting, contributor, status.

### Observation Detail Screen

Click any observation to view its detail. The detail page has three key sections:

#### Source Evidence — Original Observation

This is the raw text exactly as the contributor typed it. It is immutable — it can never be changed or deleted. This is the foundation of the evidence chain.

#### Source Evidence — Clarification Conversation

If the system needed more information, it may have asked the contributor a follow-up question. The complete question-and-answer exchange is preserved here. This is part of the source evidence.

The contributor does not see structured extraction fields during this conversation. The questions are designed to be non-leading — they ask about observable facts, not about clinical interpretations.

#### AI-Derived Structured Information

This section is visible only to the interventionist. It shows:

- **Domain** — which area of development the behavior relates to
- **Behavior** — a structured description of the observed behavior
- **Modality** — how the child communicated (verbal, gestural, multimodal, AAC)
- **Prompt Level** — how much support the child needed (independent, verbal prompt, gestural prompt, model, physical)
- **Outcome** — what happened (correct, approximation, partial, no_response)
- **Confidence** — how confident the extraction system was
- **Validation Status** — whether the structured data passed deterministic validation
- **Provenance** — which extraction provider, model, and prompt version produced this record

**Important:** The structured information is the system's candidate interpretation. It may contain errors. The interventionist should review it against the original observation text before relying on it.

---

## 8. Records / Correction / Versioning

### What Are Structured Records?

A structured record is the system's interpretation of an observation, organized into defined fields (domain, behavior, modality, prompt level, outcome, etc.). Each observation can have one or more record versions.

### Viewing Records

1. Open a child's workspace.
2. Click the **Records** tab.
3. Records are listed with their version number and status.

### Record Statuses

- **VALIDATED** — The record passed deterministic validation. Nobody has read it yet, and it is **excluded from longitudinal analytics** until someone does.
- **VERIFIED** — An interventionist read the record and accepted it as written. Analytics-eligible.
- **CORRECTED** — An interventionist submitted a correction, creating a new version. Analytics-eligible.
- **PENDING** — The record is awaiting interventionist review (used for records routed to INTERVENTIONIST_REVIEW).
- **REJECTED** / **ABSTAINED** — Excluded from analytics.

### The Verification Gate

Deterministic validation establishes that a record is schema-conformant. It cannot establish that the record read the observation correctly — a wrong value drawn from the right list of choices looks exactly like a right one. So longitudinal analytics reads only the two states that represent a human decision: **VERIFIED** and **CORRECTED**.

To verify a record:

1. Open the record detail. An unreviewed record shows a **Review required** panel.
2. Click **Verify as written** if the record is correct, or **Correct** to change it.

Notes:

- Verification changes review state, not content, so it does not create a new version. Who verified and when are recorded, and the action is written to the audit trail.
- A **PENDING** record cannot be verified as written. It was routed for review because the evidence was inadequate, so accepting it unchanged would undo that routing — correct it or leave it out.
- Only interventionists assigned to the child can verify.

### Correcting a Record

If the interventionist finds an error in a structured record:

1. Open the record detail.
2. Click the correction button (e.g., "Correct" or "Submit Correction").
3. Modify the field values as needed.
4. Enter a **Correction Reason** explaining what was changed and why.
5. Submit the correction.

**What happens:**
- A new version (v2) is created with the corrected data and the status CORRECTED.
- The original version (v1) is **preserved unchanged**. It is never overwritten.
- The correction reason is stored alongside the new version.
- The new version links back to the original via `previous_version_id`.

### Version History

To see the full version history of a record:
1. Open the record detail.
2. Look for a "Version History" section or link.
3. You will see all versions listed in order (v1, v2, etc.) with their status, data, and who made each correction.

### Why Versioning Matters

Versioning is critical for research integrity:
- The original AI-extracted record is always available for comparison.
- Every correction is attributed to a specific person with a documented reason.
- Analytics and reports use the latest version, so corrections improve downstream accuracy.
- The version chain provides a complete audit trail of how structured data evolved.

### Using the Seeded Corrected Record

In the demo data, Alex's first observation has a corrected record:
- **v1** (original): prompt_level = "independent"
- **v2** (corrected): prompt_level = "gestural"
- **Correction reason:** "Corrected prompt level: parent clarified gestural prompt was used (demo)"

This demonstrates the versioning workflow.

---

## 9. Analytics Workflow

### What Are Analytics?

Analytics are numerical summaries computed entirely by code (never by AI) from the structured records within a defined review period. They tell the interventionist about patterns, rates, and trends in the observation data.

### Review Periods

A **review period** is a defined time window (e.g., June 1 to June 30, 2026) used to scope the analytics computation. You must select or create a review period before viewing analytics.

### How to View Analytics

1. Open a child's workspace (e.g., Demo Child Alex).
2. Click the **Analytics** tab.
3. **Select or create a review period:**
   - If existing review periods are listed, click one to select it.
   - If you need a new period, look for a "Create Review Period" option and set the start and end dates.
4. Once a review period is selected, the analytics computation runs and KPI cards appear.

### Evidence Adequacy

Before showing analytics, the system assesses whether there is sufficient evidence. The thresholds behind these levels are **configurable prototype defaults, not validated clinical cutoffs** — they make withholding deterministic and auditable, but no expert procedure established the numbers themselves. The adequacy levels are:

| Level | Meaning |
|---|---|
| **ADEQUATE** | Enough observations from multiple contributors and settings. Full analytics are shown. |
| **LIMITED** | Some observations exist but coverage is narrow (e.g., single contributor or single setting). Analytics are shown with quality flags. |
| **INSUFFICIENT** | Too few observations to compute meaningful analytics. Most analytics are withheld. |

The adequacy assessment is displayed alongside the KPI cards. Quality flags explain specific limitations (e.g., "Only 2 observations received" or "Single contributor").

### Understanding KPI Cards

Each KPI card shows:
- **Name** — what is being measured
- **Value** — the computed result (displayed as a percentage if between 0 and 1, otherwise as a plain number)
- **Numerator / Denominator** — the raw counts behind the value
- **Abstention note** — if the KPI was withheld due to insufficient data, the reason is shown

### Current KPIs

| KPI | What It Currently Means | Known Limitation |
|---|---|---|
| **observation_count** | Total number of structured records in the review period | None |
| **independence_rate** | Fraction of observations where the child responded independently (without prompting) | None — correctly computed as rate with numerator/denominator |
| **positive_outcome_rate** | Fraction of observations with a positive outcome (correct or approximation) | None — correctly computed as rate |
| **domain_distribution** | Number of distinct goal domains observed | Currently shows only the count of distinct domains (e.g., "2"), not which domains or how many observations each. The full breakdown is not yet stored. |
| **modality_distribution** | Number of distinct communication modalities observed | Same limitation — shows count of distinct modalities only |
| **prompt_level_distribution** | Number of distinct prompt levels observed | Same limitation |
| **outcome_distribution** | Number of distinct outcome types observed | Same limitation |
| **contributor_distribution** | Number of distinct contributor roles submitting observations | Same limitation |
| **setting_distribution** | Number of distinct settings where observations occurred | Same limitation |
| **missing_data_rate** | Fraction of key data fields that are missing or unknown | None — correctly computed as rate |
| **prompt_support_trend** | Change in independence rate between the first and second halves of the review period | Positive value means improvement. Coarse comparison (two halves only). |
| **outcome_trend** | Change in positive outcome rate between the first and second halves | Same approach as prompt_support_trend |
| **cross_setting_comparison** | Number of distinct settings represented | Currently only counts settings, does not compare rates across settings |
| **cross_contributor_comparison** | Number of distinct contributor roles represented | Currently only counts roles, does not compare rates across roles |

---

## 10. Reports Workflow

### What Are Reports?

Reports are narrative summaries of the analytics and evidence for a review period. They translate numerical KPIs into readable prose for interventionist review.

### How to Generate a Report

1. Open a child's workspace.
2. Click the **Reports** tab.
3. Click **Generate Report**.
4. **Select a review period** by clicking on one of the listed periods (shown with human-readable date ranges and Active/Inactive badges).
5. Click **Generate**.
6. Wait for the report to appear (this may take a few seconds).

### Two Report-Generation Paths

The system has two paths for generating reports. Only the first is operational.

#### A. Deterministic Reporting (default)

The system renders the report entirely from pre-computed analytics, in code, without calling any model. This is the operational path and the default in every environment, selected by `reporting_mode = "deterministic"`.

- Provider: `deterministic`
- Model: `deterministic_reporter_v1`
- Banner: blue — "Deterministic Evidence Summary — This report was rendered in code from structured evidence and pre-computed analytics, with no language model involved. Interventionist review is still required."

A deterministic report uses only the information the analytics engine already computed. It cannot invent or infer anything beyond the evidence packet, and it names every indicator the adequacy router withheld together with the reason.

#### B. Generative Reporting (experimental, opt-in)

Setting `reporting_mode = "generative_experimental"` sends the evidence packet to the configured reporting model, which writes the prose. The model is constrained by a system prompt that prohibits diagnosis, treatment recommendations, causal claims, and other prohibited content, and the output is scanned by the same deterministic validator before display.

- Provider: `anthropic` or `ollama`
- Model: e.g., `claude-sonnet-4-20250514`
- Banner: amber — "Experimental AI Draft — ... not an operational report."

This path is experimental because it failed the system's governance check in evaluation: across 11 reports it produced no prohibited content, but it never stated that an analysis had been withheld, so none of the 11 passed validation. If the model call fails, the system falls back to the deterministic reporter and the report is labelled deterministic, because that is what produced it.

### Report Sections

A deterministic report contains up to 7 sections:

1. **Review Period Summary** — Dates, observation count, evidence level, active goals
2. **Evidence Coverage** — Contributor and setting breakdowns, missing data rate, abstained/review counts
3. **Key Indicators** — Independence rate and positive outcome rate with exact numerator/denominator counts
4. **Observed Patterns** — Distribution of goal domains, modalities, prompt levels, outcomes
5. **Progress Indicators** — Trends in independence and positive outcome rates (first half vs. second half)
6. **Cross-Setting and Cross-Contributor Observations** — Number of distinct settings and contributor roles represented
7. **Evidence Limitations** — Quality flags, withheld KPIs with reasons, missing data, evidence level

### Report Provenance

At the bottom of every report, the **Report Provenance** section shows:
- **Provider** — which system generated the report (`deterministic`, or the model provider when the experimental path is enabled)
- **Model** — which model was used
- **Prompt Version** — which prompt version was used (N/A for deterministic reports)
- **Report Version** — version number of this report
- **Validation** — whether the report passed the prohibited-content safety check (Passed/Failed)

### Evidence Packet

The report is generated from an **Evidence Packet** that contains:
- All structured records for the review period
- All computed KPIs
- Adequacy assessment
- Active goals
- Record IDs (for traceability)

Each report section can include **evidence references** — the specific record IDs that support the statements in that section.

### Flagging a Report

If the interventionist finds an issue with a generated report:
- Look for a "Flag Report" option
- Enter a reason for flagging
- The report will be marked with a "Flagged" badge and the reason will be displayed

---

## 11. Contributor Walkthrough

### Step 1 — Login as Parent

1. Open your browser and go to `http://localhost:3000`.
2. In the **Email** field, type: `demo-parent@example.com`
3. In the **Password** field, type: `DemoPass123!`
4. Click **Sign In**.

**Expected result:** You are redirected to the Contributor page (`/contribute`), NOT the interventionist dashboard.

### Step 2 — Login as Teacher

The same steps apply, but use: `demo-teacher@example.com` with the same password.

### Step 3 — View Assigned Children

After logging in as a contributor, you see only the children assigned to you:
- The **Parent** account can see Demo Child Alex and Demo Child Sam
- The **Teacher** account can see Demo Child Alex only

Each child shows a link to submit a new observation and view history.

### Step 4 — Submit a New Observation

1. Click **New Observation** (or similar link) next to a child's name.
2. You are taken to the observation submission page.
3. In the **"What did you observe?"** text area, describe what you saw in your own words.

**Example observation** (this is a synthetic example for demonstration):
> "During breakfast, Alex wanted juice. After one verbal prompt, he pointed to the juice carton and said 'juice please'."

4. Select the **Setting** where the observation took place (Home, School, Clinic, Community, or Other).
5. Click **Submit Observation**.

### What Happens Next

After you submit, the system attempts to extract structured information from your text. Depending on the result:

- **If the extraction succeeds clearly:** You see "Submitted — Your observation has been recorded. Thank you!" You can submit another observation.
- **If the system needs more information:** You are shown a clarification question (see [Section 12](#12-clarification-workflow)).
- **If the extraction fails:** You see "Observation processing failed." with a "Try Again" button. This typically means the extraction service is unavailable (see the limitation note below).

### Current Limitation: Live Extraction Requires an API Key

**Important:** Live extraction requires a valid `ANTHROPIC_API_KEY` to be configured in the Docker environment. Without this key:
- Your observation text is still **saved permanently** in the database
- The extraction step **will fail**
- No structured record will be created from your observation
- You will see "Observation processing failed."

The seeded demo observations and their structured records were inserted directly into the database. They demonstrate the downstream system (analytics, reporting, versioning) but they were **not** produced by the live extraction pipeline.

### Step 5 — View Observation History

1. Click the **History** link for a child.
2. You see a list of your past observations for that child.
3. Each entry shows the date, setting, and status.

Contributors see only their own observations — not those submitted by other contributors.

---

## 12. Clarification Workflow

Sometimes the system's extraction cannot confidently fill in all structured fields from the observation text alone. When this happens, the system may ask a follow-up question.

### How It Works

1. You submit an observation.
2. Instead of showing "Submitted", the system shows a **"Quick Question"** card.
3. The card displays a specific, focused question. For example:
   > "Could you describe the type of prompt used — was it a gesture, verbal cue, or physical guidance?"
4. You have three options:
   - **Type an answer** in the text area and click **Send**
   - Click **"I don't know"** if you cannot answer
   - Click **"Skip"** to skip the question

### What Happens After You Answer

- If your answer provides enough information, the system finalizes the observation and shows "Submitted."
- If more information is still needed, another question may appear (up to a system-defined maximum number of turns).
- If you skip or say "I don't know," the system finalizes with whatever information it has, marking uncertain fields as unknown.

### What Is Preserved

- Your original observation text is never changed
- Every question and answer is saved as part of the evidence chain
- The interventionist can see the full clarification conversation alongside the observation and structured record

### Design Principles

The clarification questions are designed to be:
- **Focused** — asking about one specific piece of information
- **Non-leading** — not suggesting what the answer should be
- **Observable** — asking about what happened, not about clinical interpretation

You (the contributor) **never** see the structured extraction fields, model confidence scores, or any AI internals. You only see the question.

---

## 13. Contributor Privacy / RBAC

### What Contributors Cannot Access

Contributors are restricted from accessing information that is intended only for professional use. Specifically, contributors **cannot**:

- See children they are not assigned to
- Open the interventionist dashboard
- View professional analytics or KPI cards
- Generate or view progress reports
- See AI-extracted structured fields, confidence scores, or validation results
- Access model/provider/prompt version details
- Correct structured records
- View the audit trail
- See other contributors' observations or personal information
- Manage goals, schedules, or contributor assignments

### How This Is Enforced

- The **backend API** checks the user's role on every request. Contributor requests to interventionist-only endpoints receive a 403 (Forbidden) response.
- The **frontend** routes contributors to `/contribute` instead of `/dashboard` and does not render interventionist-only navigation items.
- **Child-level authorization** ensures contributors can only access data for children they are assigned to. Attempting to access another child's data returns 403.

---

## 14. Schedules

### What Are Schedules?

Schedules define how often observations are expected for a child. They help the interventionist track whether contributors are submitting observations at the expected frequency.

### Viewing Schedules

1. Open a child's workspace (as an interventionist).
2. Click the **Schedules** tab.
3. You will see the expected observation schedules.

For Demo Child Alex, the seed data creates two schedules:
- Weekly home observation (every 7 days, linked to the "Functional requesting" goal)
- Biweekly school observation (every 14 days, linked to the "Cooperative play" goal)

### Why Schedules Matter

When expected observations are missing, the evidence adequacy assessment may flag the gap. For example, if a weekly home observation has not been submitted for two weeks, this contributes to quality flags in the adequacy check and may result in a LIMITED or INSUFFICIENT evidence level.

Only interventionists can create or modify schedules.

---

## 15. Contributors / Actors

### What Are Actor Assignments?

An **actor assignment** connects a user (parent, teacher, or other contributor) to a specific child. This is how the system knows which contributors are authorized to observe which children.

### Viewing Contributor Assignments

1. Open a child's workspace (as an interventionist).
2. Click the **Contributors** tab.
3. You will see a list of users assigned to this child, with their role (parent, teacher, etc.).

For Demo Child Alex, the seed data creates:
- Parent (demo-parent@example.com)
- Teacher (demo-teacher@example.com)

### Managing Contributors

An interventionist can:
- **Invite** a new contributor by providing their email and role
- **Revoke** an existing contributor's access

Contributors cannot manage other contributors.

---

## 16. Audit

### What Is the Audit Trail?

The audit trail is a log of significant actions performed within a child's workspace. It provides accountability and traceability.

### Viewing the Audit Trail

1. Open a child's workspace (as an interventionist).
2. Click the **Audit** tab.
3. You will see a list of audit events.

Each event records:
- **Action** — what was done (e.g., create_child, submit_observation, submit_clarification, correct_record, generate_report)
- **Resource** — what was affected (e.g., observation, record, report)
- **User** — who performed the action
- **Timestamp** — when it happened

### Why Audit Matters

Auditability is a core governance requirement. It ensures that:
- Every change to the data can be traced to a specific person
- The history of actions is preserved and tamper-evident
- Research integrity can be verified by reviewing the audit trail

Only interventionists can view the audit trail. Contributors cannot.

---

## 17. Demo Script

This is a suggested 10–15 minute demonstration sequence suitable for presenting to a research collaborator, technical reviewer, or interventionist.

### Part 1 — Interventionist View (8 minutes)

**Step 1: Login**
- Open `http://localhost:3000`
- Login as `demo-interventionist@example.com` / `DemoPass123!`
- Show: dashboard with two children

**Step 2: Open Demo Child Alex**
- Click the Alex card
- Show: child workspace with navigation tabs

**Step 3: Goals**
- Click Goals tab
- Show: two goals — "Functional requesting" (social_communication) and "Cooperative play" (play)
- Explain: goals define intervention objectives

**Step 4: Observation with Clarification**
- Click Observations tab
- Open Alex's last observation (the one with a clarification turn)
- Show: original observation text under "Source Evidence"
- Show: clarification Q&A — system asked about prompt type, contributor answered
- Explain: original text is preserved; clarification enriches the evidence without modifying the original

**Step 5: Structured Record and Provenance**
- In the same observation detail, show the "AI-Derived Structured Information" section
- Show: domain, behavior, modality, prompt_level, outcome
- Show: provider=demo_seed, model=demo_seed_v1 (because these are seeded records)
- Explain: structured data is a candidate interpretation, not ground truth

**Step 6: Corrected Record and Version History**
- Navigate to the Records tab
- Find the record with version history (v1 and v2)
- Show: v1 (original, VALIDATED), v2 (CORRECTED)
- Show: correction reason
- Explain: corrections create new versions; originals are never overwritten

**Step 7: Analytics**
- Click Analytics tab
- Select the existing review period
- Show: adequacy level (ADEQUATE for Alex)
- Show: KPI cards — independence_rate, positive_outcome_rate, trend indicators
- Explain: all analytics are computed by code, never by AI

**Step 8: Report**
- Click Reports tab
- Click Generate Report
- Select the review period
- Click Generate
- Show: deterministic report with 7 sections
- Show: blue banner — "Deterministic Evidence Summary"
- Show: Report Provenance — provider=deterministic
- Explain: this report was rendered entirely from pre-computed analytics, with no LLM involved — the operational path

### Part 2 — Contributor View (4 minutes)

**Step 9: Logout**
- Log out of the interventionist account

**Step 10: Contributor Login**
- Login as `demo-parent@example.com` / `DemoPass123!`
- Show: redirected to /contribute (not /dashboard)

**Step 11: Contributor Isolation**
- Show: only assigned children visible (Alex and Sam)
- Show: no analytics, reports, records, or audit tabs
- Explain: contributors see only what they need — natural-language submission and history

**Step 12: Observation Submission Interface**
- Click "New Observation" for Alex
- Show: the simple submission form — text area and setting selector
- Explain: contributors describe what they saw in their own words
- **Note:** Submitting a new observation requires a valid `ANTHROPIC_API_KEY`. Without it, the observation text will be saved but extraction will fail. If demonstrating without an API key, show the form without submitting, or explain the expected behavior.

**Step 13: Navigate to Interventionist Routes**
- Try navigating to `/dashboard` in the browser URL bar
- Show: redirected back to /contribute
- Explain: RBAC prevents contributors from accessing interventionist functionality

### Part 3 — Wrap-up (1 minute)

Summarize the key governance properties demonstrated:
1. Raw observations are immutable
2. Structured records are versioned, not overwritten
3. Analytics are deterministic, not AI-generated
4. Reports trace back to evidence
5. Role boundaries are enforced at both UI and API levels
6. The interventionist always remains the highest authority

---

## 18. Troubleshooting

### localhost:3000 Not Opening

- **Check Docker is running:** Run `docker compose -f docker/docker-compose.yml ps` to verify containers are up.
- **Check port conflicts:** Ensure nothing else is using port 3000 (frontend) or 8000 (backend).
- **Wait for startup:** The frontend depends on the backend being healthy, which may take up to 30 seconds.

### Docker Not Running

- Make sure Docker Desktop (or Docker Engine) is installed and running.
- On Windows, Docker Desktop should show a green "Running" status.

### Backend Unhealthy

- Check backend logs: `docker compose -f docker/docker-compose.yml logs backend`
- Common issues:
  - Database not ready yet (backend retries automatically)
  - Missing migration (run `alembic upgrade head`)
  - Python dependency issue

### Database Port Mapping

The database is mapped to host port **5433** (not the default 5432) to avoid conflicts with any local PostgreSQL installation. If you need to connect directly:
- Host: `localhost`
- Port: `5433`
- User: `postgres`
- Password: `postgres`
- Database: `autism_tracker`

### Login Failure

- Make sure you ran the seed script: `docker compose -f docker/docker-compose.yml exec backend python -m scripts.seed_demo`
- Check that you are using the exact email and password from Section 4.
- Credentials are case-sensitive.

### No Seeded Data

If the dashboard is empty after login:
1. Run `docker compose -f docker/docker-compose.yml exec backend alembic upgrade head`
2. Run `docker compose -f docker/docker-compose.yml exec backend python -m scripts.seed_demo`
3. Refresh the page.

### Migration Issue

If you see database errors:
1. Check that all migration files exist in `alembic/versions/`:
   - `001_initial_schema.py`
   - `002_add_report_prompt_version_and_version.py`
   - `003_add_missing_foreign_keys.py`
   - `004_add_verified_record_status.py`
2. Run `docker compose -f docker/docker-compose.yml exec backend alembic upgrade head`

### Reports Are Deterministic

This is **expected behavior**, and not a missing-API-key symptom: deterministic reporting is the operational default (`reporting_mode = "deterministic"`). The report uses pre-computed analytics and deterministic logic instead of an LLM. The blue banner confirms it.

### Live Observation Extraction Failure (Missing API Key)

When a contributor submits a new observation without a valid API key:
- The observation text is saved to the database
- The extraction step fails
- The UI shows "Observation processing failed."
- This is expected. To enable live extraction, set `ANTHROPIC_API_KEY` in the Docker environment (see Section 19).

### Inspecting Docker Status and Logs

```
# Check container status
docker compose -f docker/docker-compose.yml ps

# View backend logs
docker compose -f docker/docker-compose.yml logs backend

# View frontend logs
docker compose -f docker/docker-compose.yml logs frontend

# View database logs
docker compose -f docker/docker-compose.yml logs db

# Follow logs in real time
docker compose -f docker/docker-compose.yml logs -f backend
```

---

## 19. Security / Secret Handling

### Never Do the Following

- **Never commit `ANTHROPIC_API_KEY`** to the Git repository
- **Never paste API keys** into source code files
- **Never add API keys** to `.env.example` or any tracked file
- **Never commit production credentials** of any kind

### Safe Local Configuration

To use the Anthropic API for live extraction and LLM-powered reporting, set the environment variable in your local shell before starting Docker:

**On Linux/macOS:**
```
export ANTHROPIC_API_KEY=your-key-here
docker compose -f docker/docker-compose.yml up --build -d
```

**On Windows (PowerShell):**
```
$env:ANTHROPIC_API_KEY = "your-key-here"
docker compose -f docker/docker-compose.yml up --build -d
```

The `docker-compose.yml` file references this variable as `${ANTHROPIC_API_KEY:-}`, which passes it to the backend container if set, or defaults to an empty string if not.

**Never share your API key** with others through the repository, chat, or other unencrypted channels.

---

## 20. Known Limitations

### Research Prototype Status

This application is a **controlled research prototype**. It is:

- **NOT** production clinical software
- **NOT** a clinical decision support system
- **NOT** clinically validated or regulatory-approved
- **NOT** intended for autonomous clinical use

### Extraction Model

- The current extraction uses a **temporary general-purpose LLM** (Claude via Anthropic API), not a final fine-tuned model purpose-built for this domain.
- The fine-tuned extraction provider is planned for future development. When available, it will replace the temporary provider without requiring changes to the rest of the system.
- Extraction accuracy, precision/recall, F1 score, and hallucination rate have **not been formally evaluated** as part of this prototype.

### CHAT Transcript Processing

- CHAT transcript parsing, deidentification, and episode segmentation are implemented.
- Structured extraction from CHAT segments is **provisional** — produced by the temporary LLM, not expert gold-standard annotation.
- Expert adjudication and gold-standard dataset finalization are **deferred to a later phase**.

### Seeded Demo Data

- The seeded demo records (provider=`demo_seed`) bypass the live extraction pipeline entirely.
- They demonstrate downstream features (analytics, reporting, versioning) but do **not** prove that live extraction from natural-language observations works end-to-end.
- To verify live extraction, a valid `ANTHROPIC_API_KEY` must be configured and a new observation must be submitted through the UI.

### Live Extraction Dependency

- Without a valid `ANTHROPIC_API_KEY`, observation submission will preserve the raw text but fail to produce a structured record.
- There is no mock or demo extraction provider that simulates extraction without an API key.

### Analytics Distribution and Comparison KPIs

- Six "distribution" KPIs and two "cross-comparison" KPIs currently return only the count of distinct categories, not the full breakdown of how observations are distributed among those categories.
- For example, `domain_distribution = 2.0` means "2 distinct domains were observed" but does not show which domains or how many observations each had.
- This is an identified improvement area. The computation is deterministically correct for its current scope, but the level of detail is limited.

### Model Scientific Evaluation

The following are all **future work** and have not been performed:
- Expert-adjudicated gold-standard dataset finalization
- Foundation-model fine-tuning (LoRA/QLoRA)
- Fine-tuned vs. baseline model comparison
- Held-out research-model evaluation
- Model calibration analysis
- Inter-rater reliability assessment
- Extraction accuracy benchmarking

---

*Manual last updated: 2026-08-26.*
