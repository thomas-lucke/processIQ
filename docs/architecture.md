# Architecture

ProcessIQ is a three-layer application:

1. a Next.js frontend
2. a FastAPI backend
3. an in-process Python analysis engine built around LangGraph

This document explains the runtime shape of the system, how data moves through it, where state is persisted, and which design decisions are deliberate rather than incidental.

## System Overview

<img src="assets/architecture_diagram.svg" alt="High-level ProcessIQ architecture showing the web app, API and LangGraph orchestration layer, and storage systems" width="920" />

```text
Frontend (Next.js 15, React 19)
  - chat input
  - editable process table
  - result tabs and graph
  - settings and library views
        |
        v
API layer (FastAPI)
  - request validation
  - rate limiting
  - CORS
  - thin HTTP translation
        |
        v
Agent interface (processiq.agent.interface)
  - extraction orchestration
  - analysis orchestration
  - persistence integration
        |
        v
LangGraph workflow
  check_context
    -> request_clarification
    -> memory_synthesis
    -> initial_analysis
    -> investigate <-> tools
    -> finalize
        |
        v
Persistence
  - SQLite for profiles, analysis sessions, checkpoints
  - ChromaDB for semantic retrieval
  - in-memory session cache for active graph/CSV export data
```

## Repository Boundaries

```text
api/                     FastAPI app and HTTP schemas
frontend/                Next.js application
src/processiq/agent/     Graph state, nodes, routing, tools, public interface
src/processiq/analysis/  Deterministic metrics, confidence, ROI, visualization DTOs
src/processiq/ingestion/ File parsing and extraction
src/processiq/persistence/ SQLite, checkpoints, ChromaDB integration
src/processiq/prompts/   Jinja2 prompt templates
```

The most important seam is `src/processiq/agent/interface.py`. The API layer is expected to call the interface, not graph internals.

## Runtime Flow

### 1. Extraction

The frontend sends free text to `POST /extract` or files to `POST /extract-file`.

The backend:

- validates size and shape
- passes the request into `agent.interface`
- returns either:
  - structured `ProcessData`, or
  - a clarification response with `needs_input=true`

Extraction is implemented separately from analysis. That matters because extraction uses Instructor-backed OpenAI/Anthropic clients, while analysis and follow-up use the LangChain model factory.

### 2. Analysis

Once the user confirms or edits the extracted process, the frontend calls `POST /analyze`.

The analysis path:

1. loads or merges business profile context
2. retrieves prior user-scoped context from SQLite and ChromaDB
3. builds an `AgentState`
4. invokes the compiled LangGraph workflow
5. persists successful analysis summaries
6. returns:
   - `AnalysisInsight`
   - `GraphSchema`
   - reasoning trace
   - source attribution for retrieved prior analyses

### 3. Result review and feedback

The web UI renders:

- overview metrics
- issues and recommendations
- flow graph
- saved analysis sessions
- recommendation feedback controls

Accepted and rejected recommendation signals are stored in SQLite and influence later runs.

## Frontend Architecture

The frontend is a single-route Next.js app in `frontend/app/page.tsx`.

Notable traits:

- local state in the page component, not a global store
- dynamic imports for browser-only components
- typed API client in `frontend/lib/api.ts`
- dark theme and React Flow-based process visualization
- a left rail that toggles between the analysis view and the saved-session library

The results panel is more detailed than the earlier design docs implied. It currently exposes tabs for:

- Overview
- Issues
- Recommendations
- Flow
- Scenarios
- Data

See [docs/frontend.md](frontend.md) for the UI details.

## Backend Architecture

The FastAPI application in `api/main.py` is intentionally thin.

It is responsible for:

- request and response schemas
- request-size checks and upload validation
- IP-based rate limiting
- CORS
- response shaping
- a small in-memory session cache for active `thread_id` exports and graph lookups

It is not responsible for:

- process math
- prompt construction
- graph execution
- persistence decisions beyond delegating to the interface layer

See [docs/backend.md](backend.md).

## LangGraph Workflow

<img src="assets/processiq_agent.svg" alt="ProcessIQ LangGraph workflow showing context checking, clarification, memory synthesis, analysis, investigation, tool calls, and finalization" width="920" />

The compiled workflow is defined in `src/processiq/agent/graph.py`.

### Node sequence

```text
check_context
  -> request_clarification   if confidence is too low
  -> memory_synthesis        otherwise
memory_synthesis
  -> initial_analysis
initial_analysis
  -> investigate            if issues were found and investigation is enabled
  -> finalize               otherwise
investigate
  -> tools                  if the model requested tool calls and cycle limit allows
  -> finalize               otherwise
tools
  -> investigate
finalize
  -> END
```

### What each node does

`check_context`
- Computes deterministic confidence from process data, constraints, and profile context.

`request_clarification`
- Produces targeted follow-up questions when the workflow should not continue yet.

`memory_synthesis`
- Compresses retrieved prior-context signals into a short brief when there is enough signal to be worth injecting.

`initial_analysis`
- Computes deterministic process metrics.
- Calls the analysis model to produce `AnalysisInsight`.

`investigate`
- Runs an optional bounded tool-calling loop.
- Skips tool use entirely when the selected provider is `ollama`.

`tools`
- Executes deterministic Python tools through LangGraph `ToolNode`.

`finalize`
- Parses the investigation summary, adjusts confidence narrowly, and carries investigation findings into the final insight payload.

## Deterministic vs. LLM Responsibilities

This split is core to the architecture.

Deterministic code handles:

- process metrics
- confidence scoring
- ROI scaffolding
- graph schema construction
- storage and retrieval
- tool execution

LLM calls handle:

- extraction from unstructured input
- clarification language
- issue identification
- root-cause hypotheses
- recommendation generation
- post-analysis investigation decisions

## Persistence Model

### SQLite

`data/processiq.db` is used for:

- business profiles
- analysis sessions and feedback
- LangGraph checkpoints

### ChromaDB

`.chroma/` stores embeddings and metadata for retrieved prior analyses.

### In-memory session cache

`api/main.py` also keeps a bounded in-memory cache keyed by `thread_id`.

That cache powers:

- `GET /graph-schema/{thread_id}`
- `GET /export/csv/{thread_id}`

This means those endpoints only work for active cached analyses, not arbitrary historical sessions loaded from SQLite.

## Data Flow Details

### Analysis request

```text
User edits process data
  -> frontend/lib/api.ts -> POST /analyze
  -> api/main.py validates and delegates
  -> agent.interface.analyze_process()
  -> create AgentState + load profile/memory context
  -> compile/invoke LangGraph
  -> persist session summary + embeddings
  -> build graph schema
  -> return JSON to frontend
```

### Retrieval flow

```text
Successful analysis
  -> save SQLite session record
  -> embed analysis into ChromaDB
Later analysis for same user
  -> retrieve similar prior analyses from ChromaDB
  -> retrieve rejection and pattern history from SQLite
  -> optionally synthesize memory brief
  -> inject context into analysis prompt
```

## Current Design Constraints

These are intentional or currently real:

- The current web UI does not use `POST /continue` or `GET /graph-schema/{thread_id}` even though the API exposes them.
- `GraphSchema` is returned inline from `/analyze`; the graph endpoint is mostly useful for future clients or manual integrations.
- Extraction is not fully provider-neutral today. Ollama is not a complete replacement for cloud extraction.
- The investigation depth slider is always rendered; `DEMO_MODE=true` disables it.

## Why The Architecture Is Structured This Way

### Thin API boundary

FastAPI stays simple because analysis behavior changes more frequently than HTTP behavior.

### Hand-maintained DTO mirror

The frontend uses hand-maintained TypeScript mirrors of Python schemas rather than generated clients. That increases maintenance burden slightly, but it keeps contracts explicit and readable in a codebase of this size.

### Dual persistence strategy

SQLite is a good fit for transactional and queryable state. ChromaDB is used only where semantic retrieval is needed. The architecture keeps those concerns separated instead of forcing a single storage abstraction too early.

### Tool loop as an extension point

The investigation loop is intentionally narrow today, but it provides a place to add stronger evidence-gathering tools without changing the top-level workflow shape.

## Known Gaps and Future Direction

- Replace local-disk persistence with shared production storage.
- Add authenticated user identity.
- Add frontend test coverage.
- Add issue-scoped investigation tools and streaming UX.

See [ROADMAP.md](../ROADMAP.md) and [docs/decisions/0005-investigation-loop-design.md](decisions/0005-investigation-loop-design.md).
