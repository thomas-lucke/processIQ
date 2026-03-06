# Changelog

All notable design decisions and changes to ProcessIQ are documented here.

Categories: `DESIGN`, `ARCHITECTURE`, `SCOPE`, `TECH`, `DECISION`, `CODE`, `FIX`

---

## 2026-03-06

### CODE: Investigation depth slider (1–10) added to Next.js SettingsDrawer; wired to `max_cycles_override` in API call
### CODE: FastAPI security hardening — rate limiting (slowapi), input length caps, file extension whitelist, 50 MB size limit, session TTL + LRU eviction, CORS narrowed to `ALLOWED_ORIGIN` env var

---

## 2026-03-05

### ARCHITECTURE: FastAPI backend + Next.js/React Flow frontend replacing Streamlit

- `api/main.py`: five endpoints (`/analyze`, `/extract`, `/extract-file`, `/continue`, `/graph-schema`)
- `frontend/`: Next.js 14 App Router, TypeScript, Tailwind, shadcn/ui, React Flow
- Two-phase layout: full-width chat → animated reveal → 40/60 split on first analysis
- Settings panel: LLM provider, analysis mode, constraints, business profile
- `ProcessGraph` component consumes `GraphSchema` DTO from `/graph-schema`
- Python backend (`agent/`, `analysis/`, `models/`) unchanged

### DESIGN: Full visual redesign — dark theme, DM Sans, design tokens, left rail, header, context strip, reveal transition, empty state, chat elevation; two-phase layout with process visualization (TB grid, snake layout, variable node sizes)
### CODE: `ProcessStepsTable` — inline-editable grid after extraction; `InvestigationFindingCard` — structured display of agent tool results

---

## 2026-03-04

### ARCHITECTURE: Post-analysis follow-up now routes to extraction LLM with current process context — removed `followup.j2` and brittle keyword classifier
### FIX: Ollama analysis hang — added `reasoning=False` to `ChatOllama`; `OLLAMA_TIMEOUT` config
### FIX: RecursionError on circular dependencies in `_calculate_longest_chain` — cycle detection added
### FIX: Anthropic truncated analysis — raised `max_tokens` from 4096 to 8192

---

## 2026-03-03

### ARCHITECTURE: Renderer-agnostic `GraphSchema` DTO (`analysis/visualization.py`) — `GraphNode`/`GraphEdge`, Kahn's topological sort layout, severity precedence rules, before/after node sets; consumed by React Flow via `/graph-schema`

---

## 2026-02-27

### ARCHITECTURE: Genuine agentic investigation loop replacing single-pass analysis

- `initial_analysis_node` seeds investigation message history
- `investigate_node`: LLM with `bind_tools()` decides which tools to call and how
- `agent/tools.py`: three `@tool` functions using `InjectedState` — `analyze_dependency_impact`, `validate_root_cause`, `check_constraint_feasibility`
- `ToolNode` from `langgraph.prebuilt` executes calls; loops until no tool calls or `agent_max_cycles` hit
- `finalize_analysis_node` extracts `ToolMessage` content into `AnalysisInsight.investigation_findings`
- New routing: `route_after_initial_analysis`, `route_investigation`

### CODE: State leakage fix — fresh `analysis_thread_id` per graph invocation; user `thread_id` retained for conversation continuity only
### CODE: `agent_max_cycles`, `agent_loop_slider_enabled`, `llm_task_investigation` added to config
### FIX: Extraction prompt now recognizes supplementary step data as an UPDATE (was falling through to `needs_clarification`)
### DESIGN: `resources_needed` reframed as people-only count; UI label changed from "Resources" to "People"

---

## 2026-02-18

### SCOPE: Deployment strategy and product strategy documented in private docs
### FIX: Corrected file format claims — UI only exposes CSV/Excel in Phase 1; Docling's full format range is Phase 2
### SCOPE: `ROADMAP.md`, `LICENSE`, `CONTRIBUTING.md` added

---

## 2026-02-17

### DESIGN: Self-improving agent via recommendation feedback — thumbs up/down per recommendation; rejection reasons injected into `analyze.j2` on re-analysis
### ARCHITECTURE: File uploads merge with existing process data instead of replacing it — `ProcessData.merge_with()`
### FIX: Extraction model switched from `gpt-5-nano` to `gpt-4o-mini` for extraction/clarification tasks — reasoning models wasted tokens on simple schema-filling
### DESIGN: ROI estimates added to `Recommendation` model; calculated from process data, not invented
### DESIGN: Step grouping — `group_id`/`group_type` (alternative/parallel) on `ProcessStep`; computed step numbering in UI

---

## 2026-02-16

### CODE: 265-unit test suite across models, analysis, agent routing, ingestion, exports, prompts; `pytest-cov` added
### DESIGN: Post-analysis follow-up routes to LLM with full context — replaced regex string matching
### CODE: Graph compilation caching; parallel post-extraction LLM calls via `ThreadPoolExecutor`; structured output for analysis replacing manual JSON parsing

---

## 2026-02-12

### DESIGN: Progressive disclosure on recommendations — `plain_explanation` and `concrete_next_steps` fields; two expander layers per recommendation
### DESIGN: Business context for calibrated recommendations — `RevenueRange` enum, free-text notes, full profile threaded into `analyze.j2`
### FIX: GPT-5 series rejects `temperature!=1` and `max_tokens` — `is_restricted_openai_model()` helper added

---

## 2026-02-06

### CODE: LLM provider selector (OpenAI / Anthropic / Ollama) and model presets (`model_presets.py`) added; expert mode removed
### CODE: Agent graph simplified: 8 nodes → 4 nodes (`check_context → initial_analysis → investigate → finalize`)
### CODE: Interview improvements — targeted follow-up questions from `ConfidenceResult.data_gaps`; "Estimate Missing" button; draft analysis preview at ≥0.5 confidence

---

## 2026-02-05

### ARCHITECTURE: LLM-first analysis pipeline — algorithms calculate facts, LLM makes judgments
- New `analysis/metrics.py`, `models/insight.py` (Issue, Recommendation, NotAProblem), `analyze.j2`
- Validated: correctly identified creative work as core value, not waste

### CODE: Conversational edit support — current process data + conversation history passed to extraction LLM; `agent/context.py` added

---

## 2026-02-04

### ARCHITECTURE: Per-task LLM configuration — `LLMTaskConfig` with resolution order: preset → task env var → global settings; three presets (Cost-Optimized / Balanced / Deep Analysis)
### ARCHITECTURE: LangGraph SqliteSaver persistence — `persistence/checkpointer.py`, `user_store.py`; thread ID format `{user_id}:{conversation_id}`

---

## 2026-02-03

### DECISION: Pivot from form-based to chat-first UI — `agent/interface.py` created as clean boundary (UI never imports `graph.py`)
### CODE: Chat-first UI, state machine, advanced options sidebar, Docling integration (14 formats)

---

## 2026-02-02

### ARCHITECTURE: Centralized LLM factory — `llm.py` with Anthropic/OpenAI/Ollama support

---

## 2026-02-01

### TECH: Jinja2 prompt templates replacing inline strings; `prompts/` folder, `agent/prompts.py` deleted
### CODE: Data ingestion — `csv_loader.py`, `excel_loader.py`, `normalizer.py` (Instructor); custom exception hierarchy

---

## 2026-01-31

### CODE: LangGraph agent — `state.py`, `nodes.py`, `edges.py`; 4 agentic decision points; end-to-end test passing
### CODE: Analysis algorithms — `bottleneck.py` (weighted scoring), `roi.py` (PERT-style ranges), `confidence.py` (data completeness)

---

## 2026-01-30

### CODE: Pydantic domain models — `ProcessStep`, `ProcessData`, `Constraints`, `AnalysisResult`, `BusinessProfile`

---

## 2026-01-29

### SCOPE: Phase 1 / Phase 2 boundaries defined; files in-memory only, never written to disk
### TECH: pydantic-settings for centralized configuration

---

## 2026-01-28

### DECISION: Multi-agent architecture rejected — LangGraph nodes already provide task separation; tasks are sequential
### TECH: Phase 1 dependencies finalized; ChromaDB deferred to Phase 2
### ARCHITECTURE: Folder structure and logging standards established

---

## 2026-01-27

### DECISION: SQLite + ChromaDB dual-store for Phase 2 — LangGraph Store rejected (key-value only, no SQL or vector search)
### DECISION: Spinner over streaming for Phase 1; streaming deferred to Phase 2

---

## 2026-01-26

### DECISION: Agent justification documented — four agentic decision points requiring judgment calls
### ARCHITECTURE: Memory-ready design — Phase 1 populates from input; Phase 2 persists with profile + collection approaches
### DECISION: Utility-based agent classification; evolution path to learning agent in Phase 2
