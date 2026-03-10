# Changelog

All notable design decisions and changes to ProcessIQ are documented here.

Categories: `DESIGN`, `ARCHITECTURE`, `SCOPE`, `TECH`, `DECISION`, `CODE`, `FIX`

---

## 2026-03-10

### DESIGN: Process graph replaced serpentine grid with horizontal left-to-right flow

- Python `_grid_positions` (3-col serpentine) replaced by `_horizontal_positions` — linear processes lay out as a flat chain (`y=0`, `x=step_index`).
- Frontend: node handles switched Top/Bottom → Left/Right; MiniMap added; container height is now dynamic; wrap-edge detection removed.

### CODE: Summary row added to both process steps tables

- Both `ProcessStepsTable` (below chat) and `DataTab` (Data tab) now show a summary row: total time, total resources, avg error rate (sum / step count), and total cost.

### FIX: Process steps table not updating after chat adds a new step — `useEffect` dependency changed from `processData.steps` to `processData`.

### CODE: Frontend wiring — profile pre-fill, context attribution, feedback persistence

- Profile loaded from server on mount and auto-saved (800ms debounce); settings panel reflects stored profile on return visits.
- "Context used" block renders in OverviewTab when `context_sources` is non-empty.
- Accept/Dismiss buttons call `POST /feedback/{session_id}`; accepted/rejected recommendations written to SQLite and injected into future analyses via `analyze.j2`.
- First-use detection: onboarding note appended to analysis summary for new users.

---

## 2026-03-09

### FIX: Chat edits after analysis lost process context — `currentProcessData` passed from `page.tsx` to `ChatInterface` as fallback when `pendingProcessData` is cleared post-analysis.

### ARCHITECTURE: Analysis Library view — past analyses accessible from sidebar

- `GET /sessions/{user_id}` endpoint; `AnalysisSessionSummary` schema in Python and TypeScript.
- `LibraryPanel` component: collapsible session cards with process name, date, issue/rec badges, acceptance rate bar.
- `activeNav` lifted to `page.tsx`; Library and Analyze views kept mounted to preserve chat state across tab switches.

### CODE: React Flow graph renderer — custom `processNode` type with hover tooltips, variable-size circles (time % + severity boost), wrap-edge dashes, legend.

### CODE: UX additions — regulatory environment tooltip, "New analysis" button in settings, Data tab in ProcessIntelligencePanel.

---

## 2026-03-08

### ARCHITECTURE: Persistent memory + ChromaDB RAG

- SQLite persistence layer: `db.py` (shared connection), `profile_store.py` (CRUD + rejected approaches), `analysis_store.py` (sessions, feedback, cross-session pattern detection).
- ChromaDB vector store (`vector_store.py`): provider-aware embeddings (OpenAI / Ollama / local fallback). Semantic retrieval scoped by user ID. All ops wrapped in try/except — RAG never blocks the pipeline.
- Pipeline integration: `interface.py` retrieves similar analyses and persistent rejections before analysis; persists session and embeds after.
- `analyze.j2` extended with three conditional blocks: past analyses, rejected approaches, recurring patterns.
- User identity: localStorage UUID → `X-User-Id` header. No auth required.
- API: `GET/PUT /profile/{user_id}`, `POST /feedback/{session_id}`, `context_sources` in `AnalyzeResponse`.

---

## 2026-03-06

### CODE: Investigation depth slider (1–10) in SettingsDrawer; wired to `max_cycles_override`.
### CODE: FastAPI hardening — rate limiting (slowapi), input length caps, file extension whitelist, 50 MB size limit, session TTL + LRU eviction, CORS narrowed to `ALLOWED_ORIGIN`.

---

## 2026-03-05

### ARCHITECTURE: FastAPI + Next.js replacing Streamlit

- `api/main.py`: `/analyze`, `/extract`, `/extract-file`, `/continue`, `/graph-schema` endpoints.
- Next.js 15 App Router, TypeScript, Tailwind, React Flow. Two-phase layout: full-width chat → animated reveal → 40/60 split.
- Settings panel: LLM provider, analysis mode, constraints, business profile. Python backend unchanged.

### DESIGN: Full visual redesign — dark theme, DM Sans, design tokens, left rail, header, context strip, reveal transition, empty state, chat elevation.

---

## 2026-03-04

### ARCHITECTURE: Post-analysis follow-up routes to extraction LLM with current process context — removed `followup.j2` and brittle keyword classifier.
### FIX: Ollama analysis hang — `reasoning=False` on `ChatOllama`; `OLLAMA_TIMEOUT` config added.
### FIX: Anthropic truncated analysis — `max_tokens` raised from 4096 to 8192.

---

## 2026-03-03

### ARCHITECTURE: Renderer-agnostic `GraphSchema` DTO — `GraphNode`/`GraphEdge`, Kahn's topological sort layout, severity precedence rules, before/after node sets; consumed by React Flow.

---

## 2026-02-27

### ARCHITECTURE: Genuine agentic investigation loop replacing single-pass analysis

- `initial_analysis_node` seeds investigation history; `investigate_node` binds tools via `bind_tools()`; `ToolNode` executes; loops until no tool calls or `agent_max_cycles` hit.
- Three tools: `analyze_dependency_impact`, `validate_root_cause`, `check_constraint_feasibility` (all use `InjectedState`).
- `finalize_analysis_node` extracts `ToolMessage` content into `investigation_findings`.

### CODE: Fresh `analysis_thread_id` per invocation to prevent state leakage; `agent_max_cycles` and `llm_task_investigation` added to config.
### FIX: Extraction prompt now recognizes supplementary step data as an UPDATE rather than triggering `needs_clarification`.
### DESIGN: `resources_needed` reframed as people-only count.

---

## 2026-02-18

### SCOPE: Deployment and product strategy documented in private docs. Corrected file format claims — full Docling format range deferred to Phase 2.

---

## 2026-02-17

### DESIGN: Self-improving agent via recommendation feedback — thumbs up/down per recommendation; rejection reasons injected into `analyze.j2` on re-analysis.
### ARCHITECTURE: File uploads merge with existing process data instead of replacing it — `ProcessData.merge_with()`.
### DESIGN: ROI estimates added to `Recommendation` model; calculated from process data.
### DESIGN: Step grouping — `group_id`/`group_type` (alternative/parallel) on `ProcessStep`.

---

## 2026-02-16

### CODE: 265-unit test suite; parallel post-extraction LLM calls via `ThreadPoolExecutor`; structured output for analysis replacing manual JSON parsing.

---

## 2026-02-12

### DESIGN: Progressive disclosure on recommendations — `plain_explanation` and `concrete_next_steps`; two expander layers per recommendation.
### DESIGN: `RevenueRange` enum and business context threaded into `analyze.j2` for calibrated recommendations.

---

## 2026-02-06

### CODE: LLM provider selector (OpenAI / Anthropic / Ollama) with model presets; expert mode removed; agent graph simplified from 8 → 4 nodes.

---

## 2026-02-05

### ARCHITECTURE: LLM-first analysis pipeline — algorithms calculate facts, LLM makes judgments. New `analysis/metrics.py`, `models/insight.py`, `analyze.j2`.
### CODE: Conversational edit support — process data + conversation history passed to extraction LLM.

---

## 2026-02-04

### ARCHITECTURE: Per-task LLM configuration — `LLMTaskConfig` with resolution order (preset → task env var → global); three analysis presets.
### ARCHITECTURE: LangGraph `SqliteSaver` persistence; thread ID format `{user_id}:{conversation_id}`.

---

## 2026-02-03

### DECISION: Pivot from form-based to chat-first UI. `agent/interface.py` created as clean boundary — UI never imports `graph.py`.

---

## 2026-02-02

### ARCHITECTURE: Centralized LLM factory — `llm.py` with Anthropic/OpenAI/Ollama support.

---

## 2026-02-01

### TECH: Jinja2 prompt templates replacing inline strings.
### CODE: CSV/Excel data ingestion with Instructor-based normalizer.

---

## 2026-01-31

### CODE: LangGraph agent (`state.py`, `nodes.py`, `edges.py`) and analysis algorithms (`bottleneck.py`, `roi.py`, `confidence.py`).

---

## 2026-01-30

### CODE: Pydantic domain models — `ProcessStep`, `ProcessData`, `Constraints`, `AnalysisResult`, `BusinessProfile`.

---

## 2026-01-29

### SCOPE: Phase 1 / Phase 2 boundaries defined; files in-memory only.
### TECH: `pydantic-settings` for centralized configuration.

---

## 2026-01-28

### DECISION: Multi-agent architecture rejected — LangGraph nodes already provide task separation; tasks are sequential.
### TECH: Phase 1 dependencies finalized; ChromaDB deferred to Phase 2.

---

## 2026-01-27

### DECISION: SQLite + ChromaDB dual-store for Phase 2. LangGraph Store rejected (key-value only, no SQL or vector search).
### DECISION: Spinner over streaming for Phase 1; streaming deferred to Phase 2.

---

## 2026-01-26

### DECISION: Agent justification documented — four agentic decision points requiring judgment calls.
### ARCHITECTURE: Memory-ready design — Phase 1 populates from input; Phase 2 persists.
