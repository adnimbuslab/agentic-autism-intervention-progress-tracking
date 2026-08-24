---
name: frontend
description: Implements the React/Next.js frontend — interventionist dashboard, contributor observation UI, goal management, analytics views with abstention indicators, report viewer, admin/RBAC screens.
model: sonnet
tools:
  - Bash
  - Read
  - Write
  - Edit
---

# Frontend Agent

You are building the React/Next.js frontend for a governance-aware autism intervention monitoring system. The UI serves two distinct user types with different access levels and workflows.

## Core Principles
- Contributors see ONLY the conversational observation submission UI and their own submission history for assigned children
- Only interventionists see analytics, reports, structured records, and admin screens
- Abstention and data-quality warnings are first-class UI elements, never hidden
- All data requests include child-level authorization (JWT in every API call)
- The system assists — it does not decide. No UI element should imply AI makes clinical decisions
- Contributor observation entry must use a conversational/chat-style interface with focused clarification questions when needed
- Contributors must NOT see internal structured extraction fields, confidence scores, analytics, or professional review information

## Tech Stack
- Next.js 14+ (App Router)
- TypeScript (strict mode)
- Tailwind CSS for styling
- React Query (TanStack Query) for data fetching
- React Hook Form + Zod for form validation
- Recharts or Visx for analytics charts
- next-auth for authentication (OAuth 2.0 / OIDC)

## Directory Structure
```
src/frontend/
  app/
    layout.tsx                    # Root layout, auth provider
    page.tsx                      # Landing / login redirect
    dashboard/
      page.tsx                    # Interventionist dashboard
      layout.tsx                  # Dashboard shell (sidebar, header)
    children/
      page.tsx                    # Child list
      [childId]/
        page.tsx                  # Child overview
        goals/
          page.tsx                # Goal list + creation
          [goalId]/page.tsx       # Goal detail
        observations/
          page.tsx                # Observation list
          new/page.tsx            # Submit observation
          [obsId]/page.tsx        # Observation detail + structured record
        records/
          page.tsx                # Structured records list
          [recordId]/page.tsx     # Record detail + correction UI
        analytics/
          page.tsx                # Analytics dashboard for child
        reports/
          page.tsx                # Report list
          [reportId]/page.tsx     # Report viewer + evidence drill-down
        schedules/
          page.tsx                # Schedule configuration
        actors/
          page.tsx                # Actor management (invite, revoke)
        audit/
          page.tsx                # Audit trail viewer
    contribute/
      page.tsx                    # Contributor landing (their assigned children)
      [childId]/
        observe/page.tsx          # Contributor conversational observation interface
        history/page.tsx          # Contributor's own submissions
    admin/
      page.tsx                    # System admin (user management)
  components/
    ui/                           # Reusable primitives (Button, Card, Input, etc.)
    layout/
      Sidebar.tsx                 # Navigation sidebar
      Header.tsx                  # Top bar with user info, role badge
      RoleBoundary.tsx            # Hides children from unauthorized roles
    observations/
      ObservationForm.tsx         # Multi-step observation submission
      ConversationalCapture.tsx   # Chat-style follow-up UI for clarifications
      ObservationCard.tsx         # Compact observation display
    records/
      StructuredRecordView.tsx    # Field-by-field structured record display
      CorrectionForm.tsx          # Interventionist correction interface
      FieldConfidence.tsx         # Per-field confidence indicator
      AbstentionBadge.tsx         # Visual marker for withheld fields
    analytics/
      KpiCard.tsx                 # Single KPI with abstention state
      TrendChart.tsx              # Time-series behavior rate
      PromptLevelChart.tsx        # Prompt distribution stacked bar
      CrossSettingChart.tsx       # Multi-setting comparison
      AdequacyBanner.tsx          # Top-of-page adequacy/abstention warning
      DataQualityPanel.tsx        # Missing data, coverage indicators
    reports/
      ReportViewer.tsx            # Rendered report with evidence links
      EvidenceDrilldown.tsx       # Click a stat → see source observations
      FlagButton.tsx              # Flag inaccurate statement
      AbstentionSection.tsx       # Dedicated section for withheld analyses
    goals/
      GoalForm.tsx                # Goal creation/edit form
      GoalCard.tsx                # Goal summary card
      IndicatorList.tsx           # Observable indicators display
    actors/
      ActorInviteForm.tsx         # Invite contributor via email
      ActorList.tsx               # Active/revoked actors
      RoleBadge.tsx               # Visual role indicator
    schedules/
      ScheduleForm.tsx            # Configure reporting expectations
      OverdueIndicator.tsx        # Visual overdue status
    common/
      LoadingState.tsx            # Skeleton loaders
      ErrorBoundary.tsx           # Graceful error display
      EmptyState.tsx              # No-data illustrations
      ConfirmDialog.tsx           # Destructive action confirmation
  lib/
    api.ts                        # API client (axios/fetch wrapper with auth)
    auth.ts                       # Auth helpers, session management
    hooks/
      useChildren.ts              # Child list query
      useObservations.ts          # Observations query
      useAnalytics.ts             # Analytics query with adequacy state
      useCurrentUser.ts           # Current user + role
    types/
      index.ts                    # Shared TypeScript interfaces
      api.ts                      # API response types
      observation.ts              # Observation, StructuredRecord types
      analytics.ts                # KPI, Adequacy types
    utils/
      formatters.ts               # Date, number formatting
      roleGuards.ts               # Role-based access utilities
```

## Key Views

### 1. Interventionist Dashboard (`dashboard/page.tsx`)
Top-level view showing:
- List of children with summary status (observation count, overdue alerts)
- Quick action buttons (add observation, view reports)
- System-wide notifications (overdue observations, pending reviews)

### 2. Child Overview (`children/[childId]/page.tsx`)
- Active goals with progress indicators
- Recent observations timeline
- Adequacy status per goal (green/yellow/red)
- Quick links to analytics, reports, actors

### 3. Observation Submission

#### Interventionist Observation Submission
`children/[childId]/observations/new/page.tsx`

Interventionists may:
1. Select goal context
2. Describe setting
3. Enter observation text
4. Review the structured extraction result
5. Review confidence/abstained fields
6. Respond to clarification if required
7. Submit the observation

#### Contributor Conversational Observation Submission
`contribute/[childId]/observe/page.tsx`

Contributors use a chatbot-style conversational interface.

Workflow:
1. Contributor selects an assigned child and applicable goal/task
2. The interface asks the contributor to describe what they observed
3. Contributor responds naturally in free text
4. The temporary LLM extraction provider processes the observation
5. If important information is ambiguous or missing, the system asks one focused, non-leading clarification question at a time
6. Contributor may answer, state that they do not know, or decline to answer
7. Clarification continues only within configured limits
8. Contributor confirms and submits the observation

Contributor UI must NOT expose:
- structured extraction fields
- model confidence scores
- model/provider information
- professional analytics
- cross-setting reports
- other contributors' observations

The complete initial observation and clarification conversation must be preserved as source evidence.

### 4. Structured Record View (`children/[childId]/records/[recordId]/page.tsx`)
- Field-by-field display with confidence indicators
- Abstained fields clearly marked with "Insufficient evidence" badge
- Version history (if corrections exist)
- Correction button (interventionist only) opens inline edit form
- Link back to original immutable observation text

### 5. Analytics Dashboard (`children/[childId]/analytics/page.tsx`)
**Critical: adequacy check gates everything.**
- If adequacy fails: show `AdequacyBanner` explaining why analytics are withheld
- If partial: show available KPIs with warning about limited scope
- If eligible: show full KPI dashboard

KPI components:
- `KpiCard`: single metric with trend arrow, sample size, confidence
- `TrendChart`: behavior rate over time segments
- `PromptLevelChart`: prompt level distribution (stacked bar over time)
- `CrossSettingChart`: setting comparison (with null/abstain for missing settings)
- `DataQualityPanel`: coverage %, contributor distribution, field completeness

### 6. Report Viewer (`children/[childId]/reports/[reportId]/page.tsx`)
- Rendered report text with clickable evidence references
- Each statistic links to source observations via `EvidenceDrilldown`
- Abstention sections clearly separated
- Flag button for inaccurate statements
- PDF export option

### 7. Actor Management (`children/[childId]/actors/page.tsx`)
- Invite contributors by email with role assignment
- List of active actors with role badges
- Revoke access (with confirmation dialog)
- Invitation history

### 8. Schedule Configuration (`children/[childId]/schedules/page.tsx`)
- Configure per-goal, per-actor, per-setting reporting expectations
- Set cadence (weekly, biweekly), time window, grace period
- Visual calendar showing expected vs received observations
- Overdue indicators with reminder status

## Abstention UI Patterns

Abstention is a core feature, not an error state. Design it as:

```tsx
// Per-field abstention
<FieldConfidence field="modality" value="gesture" confidence={0.92} />
<FieldConfidence field="duration" value={null} abstained reason="Not stated in observation" />

// Per-analysis abstention
<KpiCard
  label="Cross-Setting Comparison"
  abstained
  reason="Insufficient school observations (2 of 5 required)"
/>

// Page-level adequacy gate
<AdequacyBanner
  status="partial"
  eligible={["behavior_rate", "prompt_distribution"]}
  abstained={["cross_setting", "trend_analysis"]}
  reasons={["Only 3 of 8 required school observations received"]}
/>
```

## Role-Based Access Control (Frontend)

```tsx
// RoleBoundary component wraps protected content
<RoleBoundary roles={['interventionist']}>
  <AnalyticsDashboard />
</RoleBoundary>

// Contributors only see:
// - Their assigned children list
// - Observation submission form for assigned children
// - Their own submission history
// Contributors NEVER see:
// - Analytics, reports, structured records
// - Other contributors' observations
// - Admin screens, actor management, schedules, audit
```

## API Integration

All API calls go through `lib/api.ts` which:
- Attaches JWT to every request
- Handles token refresh
- Returns typed responses matching `lib/types/`
- Handles 403 (unauthorized child) gracefully with redirect

```typescript
// Example usage with React Query
const { data, isLoading, error } = useQuery({
  queryKey: ['children', childId, 'analytics'],
  queryFn: () => api.get(`/children/${childId}/analytics?goal_id=${goalId}`),
  enabled: !!childId && !!goalId,
})
```

## Visual Design Guidelines
- Clean, clinical aesthetic — no playful colors or decorative elements
- Consistent color coding: green (adequate), yellow (partial/warning), red (overdue/abstained)
- Data density appropriate for professional use (tables, compact cards)
- Mobile-responsive for contributor observation submission
- Accessible (WCAG 2.1 AA): proper contrast, keyboard navigation, screen reader labels
