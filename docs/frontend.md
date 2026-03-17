# Frontend

The frontend is a Next.js 15 App Router application in `frontend/`.

It is a single-route UI that combines:

- chat-driven process capture
- inline editing of extracted process steps
- multi-tab results review
- a saved-session library
- profile and constraint settings

## Tech Stack

- Next.js 15
- React 19
- TypeScript
- Tailwind CSS
- React Flow
- Radix primitives and local utility components

## Route Structure

The app currently uses one route:

```text
frontend/app/layout.tsx
frontend/app/page.tsx
```

There is no multi-page route hierarchy yet. Most state lives in `page.tsx`.

## UI Structure

At a high level, the page is composed of:

```text
Header
ContextStrip (results mode only)
LeftRail
SettingsDrawer (toggleable)
LibraryPanel or Analyze view
```

The Analyze view contains:

- `ChatInterface`
- `ProcessStepsTable`
- `ProcessIntelligencePanel`

## Interaction Model

### Phase 1: Process capture

Before a completed analysis exists, the main area emphasizes:

- the empty state
- chat input
- uploaded file handling
- extracted process table editing

### Phase 2: Result review

After analysis completes and the reveal animation finishes, the layout becomes a split view:

- left column: chat and process table
- right column: results panel

This transition is controlled by `revealState` in `frontend/app/page.tsx`.

## Left Rail and Main Modes

The left rail currently switches between two app modes:

- `analyze`
- `library`

The library and analyze panes stay mounted and are hidden with CSS instead of being unmounted. That preserves chat and UI state when the user switches views.

## Main Components

### `ChatInterface`

File: `frontend/components/chat/ChatInterface.tsx`

Responsibilities:

- manage chat message history
- submit text extraction requests
- submit file extraction requests
- trigger analysis once process data is ready
- keep track of pending extracted data vs. analyzed data

Important implementation detail:
The web UI currently uses `/extract` and `/analyze`, not `/continue`.

### `ProcessStepsTable`

File: `frontend/components/process/ProcessStepsTable.tsx`

Responsibilities:

- render extracted steps
- allow inline edits
- surface `estimated_fields`
- expose an "estimate missing values" action back into chat

### `ProcessIntelligencePanel`

File: `frontend/components/results/ProcessIntelligencePanel.tsx`

Responsibilities:

- render the result tabs
- capture recommendation feedback
- expose export actions
- coordinate graph highlighting

Current tabs:

- Overview
- Issues
- Recommendations
- Flow
- Scenarios
- Data

Important correction:
Earlier docs described a smaller three-tab layout. The current result panel is broader and more dashboard-like.

### `LibraryPanel`

File: `frontend/components/library/LibraryPanel.tsx`

Shows saved analyses returned by `GET /sessions/{user_id}`.

### `SettingsDrawer`

File: `frontend/components/settings/SettingsDrawer.tsx`

Current UI fields include:

- LLM provider
- analysis mode
- investigation depth slider
- industry
- company size
- regulatory environment
- budget limit
- timeline weeks
- no layoffs
- no new hires
- reset-data action

Important correction:
The backend profile and constraint models contain more fields than the current UI exposes. For example, `annual_revenue`, `preferred_frameworks`, `previous_improvements`, `must_maintain_audit_trail`, `priority`, and `technology_restrictions` exist in backend models but are not currently editable in the web UI.

## State Model

`frontend/app/page.tsx` owns most application state.

Key state slices include:

| State | Purpose |
| --- | --- |
| `processData` | editable current process |
| `analysedProcessData` | frozen snapshot of the last analyzed process |
| `insight` | latest `AnalysisInsight` |
| `graphSchema` | latest backend graph DTO |
| `threadId` | thread/session identifier returned by analysis |
| `profile` | business profile loaded from and saved to the backend |
| `constraints` | active session constraints |
| `analysisMode` | model preset selection |
| `llmProvider` | selected provider |
| `maxCycles` | investigation depth override |
| `activeNav` | analyze vs. library |
| `settingsOpen` | settings drawer visibility |
| `demoMode` | server-driven UI restriction mode |
| `tracingEnabled` | server-driven privacy indicator |

Two-state detail worth noticing:

- `processData` can continue changing after analysis
- `analysedProcessData` is the snapshot used by the results panel so the result view stays tied to what was actually analyzed

## API Client

The frontend talks to the backend only through `frontend/lib/api.ts`.

The client currently exposes wrappers for:

- `extractText`
- `extractFile`
- `analyzeProcess`
- `continueConversation`
- `getGraphSchema`
- `healthCheck`
- `getProfile`
- `saveProfile`
- `deleteUserData`
- `getUserSessions`
- `submitFeedback`
- `exportPdf`
- `exportCsv`

Important correction:
Not all exported client helpers are currently used by the web UI. Today the UI uses:

- `extractText`
- `extractFile`
- `analyzeProcess`
- `healthCheck`
- `getProfile`
- `saveProfile`
- `deleteUserData`
- `getUserSessions`
- `submitFeedback`
- `exportPdf`

The following helpers exist but are not wired into the current UI path:

- `continueConversation`
- `getGraphSchema`
- `exportCsv`

## Type Synchronization

`frontend/lib/types.ts` is a hand-maintained mirror of Python Pydantic models and API DTOs.

There is no code generation layer.

That means schema changes require touching both:

- Python models and/or `api/schemas.py`
- `frontend/lib/types.ts`

This is a deliberate trade-off in a portfolio-sized codebase, but it does require discipline.

## Dynamic Imports

The frontend uses `next/dynamic` with `ssr: false` for browser-only components:

- `ChatInterface`
- `ProcessIntelligencePanel`
- `ProcessStepsTable`
- `ProcessGraph`

That avoids hydration problems around browser APIs such as local storage, file handling, and graph rendering.

## Graph Rendering

The UI renders a backend-provided `GraphSchema` with React Flow.

Notable details:

- backend computes graph positions and severity labels
- frontend maps those DTOs to React Flow nodes and edges
- before/after rendering is powered by `before_nodes` and `after_nodes`
- the "after" state highlights only steps affected by the top recommendation

Important implementation detail:
Low-severity issues are not given a dedicated graph severity color today; the graph distinguishes `high`, `medium`, `core_value`, `recommendation_affected`, and `normal`.

## Export UX

The result panel currently exposes:

- Markdown export
- plain-text export
- PDF export

Important correction:
The backend also supports CSV export, but the frontend does not currently expose it.

## Known Gaps

- No frontend automated tests yet
- analysis mode changes model selection, but does not itself change the cycle count
- some backend profile/constraint fields are not editable from the UI

See [docs/backend.md](backend.md) and [docs/deployment.md](deployment.md).
