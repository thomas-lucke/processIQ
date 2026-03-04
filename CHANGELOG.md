# Changelog

All notable design decisions and changes to ProcessIQ are documented here.

Categories: `DESIGN`, `ARCHITECTURE`, `SCOPE`, `TECH`, `DECISION`, `CODE`, `FIX`

---

## 2026-03-04

### ARCHITECTURE: Post-analysis follow-up routing replaced with extraction LLM

Removed `_handle_followup_question`, `_is_process_update`, `get_followup_prompt`, and `followup.j2`. After analysis, all user messages now route to `_process_text_input`, which calls the extraction LLM with the current process data as context. The extraction prompt already distinguishes process changes from questions, eliminating the brittle keyword classifier and a redundant LLM call.

### FIX: Ollama analysis hang and improved error handling

- Added `reasoning=False` to `ChatOllama` to disable thinking mode on qwen3 and similar models — required for reliable structured output
- Timeout configurable via `OLLAMA_TIMEOUT` in `.env` (default 120s); no longer retries on timeout
- User-facing error message now explains the cause and suggests alternatives

### FIX: Several smaller fixes

- RecursionError crash when LLM produced a circular dependency (A → B → A) in `_calculate_longest_chain` — added cycle detection
- Visualization node severity colors not applying — `_assign_severity` was exact-string only; switched to case-insensitive substring match
- Anthropic structured output truncated mid-response for complex analyses — raised `max_tokens` from 4096 to 8192

---

## 2026-03-03 (Phase 2 Task 2: process visualization)

### ARCHITECTURE: Two-layer visualization system (`analysis/visualization.py`)

New module implementing a renderer-agnostic data layer on top of which a temporary Plotly renderer sits:

- **Layer 1 (permanent):** `GraphSchema` Pydantic model with `GraphNode`, `GraphEdge`. `build_graph_schema()` computes a layered DAG layout (Sugiyama-style topological sort — not networkx) and assigns severity per node using precedence rules: high issue > medium issue > recommendation-affected > core value > normal. Before and after node sets share positions but differ in severity, supporting the Before/After toggle without re-layout.
- **Layer 2 (temporary):** `build_process_figure()` converts `GraphSchema` to a Plotly figure with `updatemenus` Before/After toggle. This layer will be deleted when React Flow replaces Streamlit (Task 2.5). The data layer and `GraphSchema` contract stay unchanged.

Layout algorithm: Kahn's topological sort → longest-path level assignment → y-centering within each level. Falls back to linear sequence on cycles or missing dependency data. ~40 lines, no new dependency.

### CODE: New `ui/components/process_visualization.py`

Thin Streamlit wrapper: calls `build_graph_schema()` then `build_process_figure()`, renders with `st.plotly_chart()`. Handles graceful degradation: < 2 steps → skip silently; no dependency data → linear sequence; no `AnalysisInsight` → all-gray nodes. Exception-safe — a rendering failure does not break the rest of the results display.

### CODE: Process flowchart integrated into results display

`results_display.py` now renders the process visualization between the summary and the main opportunities sections. Order: What I Found → Process Flow → Main Opportunities → Core Value Work → expandable details.

---

## 2026-02-27 (Phase 2 Task 1: agentic investigation loop + UX fixes)

### ARCHITECTURE: Replaced single-pass analysis node with genuine agentic loop

The analysis pipeline now supports iterative LLM-driven investigation via native function calling (LangGraph `ToolNode` + `InjectedState`). Key changes:

- `analyze_with_llm_node` renamed to `initial_analysis_node`. Produces `AnalysisInsight` as before, but also caches `ProcessMetrics` in state and seeds the investigation message history.
- New `investigate_node`: binds the LLM to `INVESTIGATION_TOOLS` via `model.bind_tools()`. The LLM decides which tools to call and what arguments to pass — not an enum selection.
- New `agent/tools.py`: three `@tool` functions using `InjectedState` — `analyze_dependency_impact`, `validate_root_cause`, `check_constraint_feasibility`. Tools read `process_metrics` from state to avoid redundant recomputation.
- `ToolNode` from `langgraph.prebuilt` executes tool calls; results loop back to `investigate_node` until no tool calls remain or `agent_max_cycles` is reached.
- `finalize_analysis_node` now extracts `ToolMessage` content into `AnalysisInsight.investigation_findings` (new dedicated field — not `confidence_notes`).
- Two new routing functions in `edges.py`: `route_after_initial_analysis` (skips investigation when no issues found or max_cycles=0) and `route_investigation` (tools vs finalize based on tool calls and cycle count).

### CODE: State leakage fix in interface.py

`analyze_process()` now uses a fresh `analysis_thread_id = str(uuid.uuid4())` for every graph invocation. The user-facing `thread_id` is retained for conversation continuity but is no longer passed to the graph, preventing `add_messages` reducer accumulation across runs.

### CODE: New config settings for investigation loop

Added `TASK_INVESTIGATION`, `agent_max_cycles` (default: 3), `agent_loop_slider_enabled` (default: False), and `llm_task_investigation: LLMTaskConfig` to `Settings`. Full per-task override support follows existing pattern.

### CODE: UI additions for investigation loop

- `investigation_findings` rendered as collapsible "Investigation Details" section in results.
- Investigation depth slider added to Advanced Options (gated behind `agent_loop_slider_enabled` env var).
- `max_cycles_override` flows from UI slider → session state → `analyze_process()` → `create_initial_state()`.

### FIX: Extraction prompt now recognizes supplementary step data as an update

When existing process data was present and the user provided natural-language information about a named step (e.g., "fulfill order takes 1-5 hours and costs €40/hr"), the LLM was falling through to `needs_clarification` because the UPDATE rule only matched imperative edit-verb language. Added an explicit rule and example for the "supplementary info about an existing step" case.

### CODE: Time display formatted as `Xh Ym` in summary metrics

Added `format_hours(hours)` to `ui/styles.py`. Applied to "Total Time" metric in the chat table and data review components. The editable data_editor column retains numeric input with `"%.2f h"` format.

### DESIGN: `resources_needed` reframed as people-only count

Changed field description from "number of people/systems involved" to "number of people involved (0 = fully automated)". Rationale: people and systems aren't comparable units — the old label invited confusion. Systems are implicitly captured by cost. UI column label changed from "Resources" to "People" across chat table and data review. Internal field name and CSV schema unchanged for backwards compatibility.

---

## 2026-02-18 (deployment strategy)

### SCOPE: Added deployment strategy to PRODUCT_STRATEGY.md

- Hosting path documented: Streamlit Community Cloud (Phase 1) → HuggingFace Spaces (Phase 2, ChromaDB headroom) → Railway (if always-on reliability needed before paying users)
- Instrumentation stack defined: Sentry (error tracking), PostHog (event analytics with specific events for ProcessIQ), `st.feedback()` + Tally.so (in-app qualitative feedback)
- Launch sequence documented: BetaList pre-launch → Reddit target communities → Show HN → Indie Hackers → Product Hunt (later, for social proof not acquisition)
- Target communities listed with rationale: r/operations, r/lean, r/businessanalysis, Process Excellence Network, LinkedIn Lean Six Sigma Group, iSixSigma
- Async-first feedback approach: written follow-up pattern, three specific diagnostic questions, instrumentation for behavioral data without user interviews

---

## 2026-02-18 (product strategy)

### SCOPE: Expanded roadmap and added product strategy document

- `ROADMAP.md` restructured: Phase 2 expanded with four new items (process visualization moved up from Phase 3, PDF/HTML report export, Docling UI exposure, outcome tracking hook in 2A); Phase 3 adds process templates and formal outcome tracking; sequencing table updated with rationale
- `docs/PRODUCT_STRATEGY.md` created: detailed reasoning behind Phase 2 and Phase 3 priorities — covers the SMB market opportunity, time-to-value analysis, why shareable output drives organic growth, the difference between preference feedback and outcome feedback, and why specific features were ruled out
- ROADMAP.md links to PRODUCT_STRATEGY.md for the "why" behind each decision

---

## 2026-02-18

### FIX: Corrected file format claims across docs

- `render_file_uploader` defaults to `["csv", "xlsx", "xls"]` — the UI only exposes spreadsheets, not Docling's full 14-format range
- Removed "14 formats" and Docling format claims from Phase 1 sections in README, ROADMAP, and PROJECT_BRIEF
- Phase 1 vs Phase 2 scope table in PROJECT_BRIEF updated: PDF/DOCX/image upload now correctly marked as Phase 2
- Docling parser is implemented and wired up in `agent/interface.py` but not exposed in the UI uploader

### SCOPE: Added ROADMAP.md, LICENSE, CONTRIBUTING.md

- `LICENSE` — MIT license file added at repo root (was referenced in README badge and pyproject.toml but did not exist)
- `ROADMAP.md` — full roadmap with sequenced priorities and rationale extracted from PROJECT_BRIEF; replaces the 5-bullet stub in README
- `CONTRIBUTING.md` — setup, workflow, and design principles for contributors
- README roadmap section updated to link to ROADMAP.md

### DECISION: Updated CONVERSATION_FLOW.md and architecture_diagram.mmd to match current implementation

- `CONVERSATION_FLOW.md`: corrected `MessageRole.AGENT` value, fixed `ChatMessage` field types, removed stale "Edit Data" button and "Guided vs Expert Mode" section, updated session state table
- `architecture_diagram.mmd`: rewrote Agent subgraph to reflect actual 4-node LangGraph implementation; removed 9 fabricated nodes that were never built; updated ingestion and output subgraphs

---

## 2026-02-17

### DESIGN: Self-Improving Agent via Recommendation Feedback

- Added thumbs up/down feedback buttons on each recommendation in the results display. Thumbs down shows an optional text input for rejection reason.
- Feedback stored in session state, persists across re-analyses within the same session (cleared on full reset).
- On re-analysis, feedback history is formatted and injected into `analyze.j2` as a new `feedback_history` section. The LLM is instructed to avoid repeating rejected recommendations and lean toward accepted patterns.
- Pipeline: `ui/state.py` (storage) -> `handlers.py` (passes to analysis) -> `agent/state.py` -> `nodes.py` (formats text) -> `analyze.j2` (prompt injection).

### ARCHITECTURE: File Upload Merging

- File uploads now merge with existing process data instead of replacing it. Matching steps (by name, case-insensitive) have their values updated; new steps are appended; existing-only steps are preserved.
- Added `ProcessData.merge_with()` method. Fields overwritten by file data are removed from `estimated_fields` (no longer marked as AI-estimated).
- Enables the workflow: describe process in text -> upload spreadsheet with costs -> merged table ready for analysis.

### FIX: Extraction Model Selection for OpenAI

- Switched extraction and clarification tasks from `gpt-5-nano` (reasoning model) to `gpt-4o-mini` across all analysis modes. Reasoning models burned 12k+ tokens on internal chain-of-thought for simple schema-filling tasks, causing slow responses and occasional empty outputs when the reasoning budget was exhausted.
- Analysis and explanation tasks still use reasoning models where deeper thinking adds value.

### FIX: Multiple Bug Fixes

- **Asterisk on user-edited values**: Table edits now remove fields from `estimated_fields` when the user changes a value, preventing false AI-estimated markers.
- **Duplicate logging**: Replaced module-level `_logging_configured` flag with `app_logger.handlers` check. The flag reset on every Streamlit rerun, causing handler accumulation (2-4x log messages).
- **OpenAI zeros vs blanks**: Strengthened extraction prompt to explicitly require every "not provided" zero to be listed in `estimated_fields`. Anthropic inferred this; OpenAI needed it spelled out.
- **File stays in uploader**: Increment file upload key counter after processing to clear the widget.
- **Follow-up answers hidden**: In CONTINUING state, analysis results now collapse into an expander so follow-up conversation stays visible.

### DESIGN: ROI Estimates on Recommendations

- Added `estimated_roi` field to `Recommendation` model for rough dollar-range estimates.
- Analysis prompt instructs LLM to calculate ROI from actual process data (time x cost, error reduction) rather than inventing figures.
- Displayed with styled callout and "(rough estimate)" label below each recommendation.

### DESIGN: Step Numbering with Alternative/Parallel Group Support

- Added `group_id` and `group_type` fields to `ProcessStep` and `ExtractedStep` models. `group_type` is either `"alternative"` (either/or, e.g., phone OR email) or `"parallel"` (simultaneous, e.g., invoice paid AND tax entry).
- New "Step #" column in the data table with computed numbering: sequential steps show "1", "2", "3"; alternatives show "1a (OR)", "1b (OR)"; parallel steps show "5a (AND)", "5b (AND)".
- Updated extraction prompt with grouping detection instructions and examples.

---

## 2026-02-16

### CODE: Comprehensive test suite (265 tests)

- Created 19 test files covering models, analysis algorithms, agent routing, ingestion loaders, exports, prompts, exceptions, and LLM utilities.
- Coverage: models 100%, analysis 90–100%, agent/edges 100%, ingestion 81–94%, exports 81–100%, exceptions 100%.
- Added `pytest-cov` dev dependency and `@pytest.mark.llm` marker for LLM-dependent tests.

### DESIGN: Post-Analysis Follow-Up Conversation

- Follow-up questions after analysis were previously handled by regex string matching with a canned response. Now routes all follow-up questions to the LLM with full analysis context, chat history, business profile, and constraints.
- New prompt template `followup.j2` for follow-up conversation context.
- Analysis results panel no longer disappears when a follow-up message is sent.

### CODE: Efficiency and Workflow Optimizations

- **Graph compilation caching**: Module-level cache prevents recompiling the LangGraph on every analysis call.
- **Parallel post-extraction LLM calls**: Improvement suggestions and draft analysis run concurrently via `ThreadPoolExecutor`.
- **Structured output for analysis**: Replaced manual JSON parsing with `with_structured_output(AnalysisInsight)`, removing ~50 lines of brittle parsing code.
- **Instructor client caching**: Clients cached at module level instead of recreated per call.
- **Transitive closure fix** (`metrics.py`): Fixed shared visited set causing exponential blowup on reconvergent DAGs.
- **Dead code removal**: Removed 15 unused form-based session state functions, 7 unused `_STATE_DEFAULTS` keys, and a renderer that never ran.

---

## 2026-02-12

### DESIGN: Progressive Disclosure on Recommendations

- Added `plain_explanation` and `concrete_next_steps` fields to `Recommendation` model.
- Updated results display with two new expander sections per recommendation: "What this means in practice" and "How to get started."
- Both compact (issue-linked) and standalone recommendation renderers updated.

### DESIGN: Business Context for Calibrated Recommendations

- **Problem**: Recommendations like "automate this for $15–50k/year" are meaningless without business scale context. A 3-store bakery and a 1000-person enterprise get the same generic suggestions.
- **Solution**: Added revenue range, free-text business notes, and full business profile threading into the analysis prompt.
- Added `RevenueRange` enum to `BusinessProfile` (8 tiers from "Under $100K" to "Over $100M" plus "Prefer not to say").
- Surfaced revenue dropdown and "About Your Business" text area in sidebar.
- Built `_format_business_context_for_llm()` in `nodes.py` to serialize full profile into LLM-readable format.
- Updated `analyze.j2` to receive `business_context` (replaces bare `industry` string) with explicit instruction to calibrate costs to business scale.

### FIX: GPT-5 Series and Cross-Provider Model Resolution

- GPT-5 and o-series models reject `temperature!=1` and `max_tokens`. Added `is_restricted_openai_model()` helper; applied in both LangChain and Instructor code paths.
- Fixed cross-provider model bug where selecting "anthropic" in UI but having `LLM_PROVIDER=openai` in `.env` caused the wrong model to be used.
- All call sites in `graph.py` and `interface.py` now thread `provider` and `analysis_mode` through correctly.

---

## 2026-02-06

### CODE: UI and Analysis Pipeline (Rework Phase 4)

- **LLM Provider Selector**: New sidebar radio (OpenAI / Anthropic / Ollama).
- **Model Presets**: New `model_presets.py` with per-provider/mode/task model config (GPT-5 series, Claude 4.5 Haiku/Sonnet, qwen3:8b).
- **Analysis Mode Wiring**: `analysis_mode` + `llm_provider` threaded from UI through `AgentState` → `_run_llm_analysis()` → `get_chat_model()`.
- **Expert Mode Removed**: Removed toggle, two-column layout, and related session state functions. Inline editable table is always available.

### CODE: Agent Graph Cleanup (Rework Phase 4)

- Rewired graph: old flow (8 nodes) → new flow (4 nodes: `check_context → analyze → finalize`).
- Removed old algorithm-first nodes from `nodes.py` (bottleneck detection, generic suggestions, constraint validation, ROI calculation).
- Simplified `edges.py` and `state.py`.
- `nodes.py`: 829→339 lines (−59%), `graph.py`: 288→207 lines (−28%).

### CODE: Interview Improvements (Rework Phase 3)

- Targeted follow-up questions based on `ConfidenceResult.data_gaps` (replaces generic "Does this look correct?").
- "Estimate Missing" button for step-level gaps.
- Draft analysis preview shown immediately after extraction (when confidence ≥ 0.5).

### CODE: Summary-First Results Display (Rework Phase 2)

- New layout: "What I Found" → "Main Opportunities" with severity badges → "Core Value Work" → expandable details.
- Issues linked to specific recommendations.

### DOCS: Documentation Overhaul

- Rewrote `PROJECT_BRIEF.md`, `CONVERSATION_FLOW.md`, and `README.md` to reflect the LLM-first analysis pipeline.

---

## 2026-02-05

### ARCHITECTURE: LLM-Based Analysis Pipeline (Rework Phase 1)

- **Problem:** Old architecture used algorithms that just found `max(time)` and called it a "bottleneck."
- **Solution:** Algorithms calculate FACTS (percentages, dependencies), LLM makes JUDGMENTS (waste vs value).
- New modules: `analysis/metrics.py` (process metrics), `models/insight.py` (Issue, Recommendation, NotAProblem).
- New prompt: `analyze.j2` (pattern detection, waste vs value distinction, trade-off analysis).
- Validated on creative agency example: correctly identified creative work as core value, not waste.

### CODE: Conversational Edit Support

- LLM calls now include current process data and recent conversation history as context.
- New `agent/context.py` module for serializing process data and filtering messages.
- Updated extraction prompt with UPDATE decision path for edit requests.

---

## 2026-02-04

### ARCHITECTURE: Per-Task LLM Configuration

- Different tasks can use different models (e.g., fast model for extraction, strong model for analysis).
- `LLMTaskConfig` with resolution order: analysis mode preset → task-specific env var → global settings.
- Three user-facing presets: Cost-Optimized, Balanced (default), Deep Analysis.

### ARCHITECTURE: LangGraph SqliteSaver Persistence

- `persistence/checkpointer.py`: SqliteSaver wrapper with singleton pattern.
- `persistence/user_store.py`: UUID-based user identification without login.
- Thread ID format: `{user_id}:{conversation_id}` for per-user conversation history.

---

## 2026-02-03

### DECISION: UI Paradigm Shift — Forms to Chat-First

- **Problem:** Form-based UI too clunky for non-technical users (bakery owner example).
- **Solution:** Pivot to chat-first interface with file drop; forms become "edit mode" for reviewing extracted data.
- Created `agent/interface.py` as clean API between UI and LangGraph (UI never imports `graph.py` directly).

### CODE: Chat-First UI Implementation

- Chat component with message types: TEXT, FILE, DATA_CARD, ANALYSIS, CLARIFICATION, STATUS, ERROR.
- Advanced options sidebar: constraints, business context, analysis mode (collapsed by default).
- State machine: WELCOME → GATHERING → CONFIRMING → ANALYZING → RESULTS.

### CODE: Docling Integration for Document Parsing

- `ingestion/docling_parser.py`: Semantic chunking preserves document structure (tables, headings, lists).
- Supports 14 formats: PDF, DOCX, PPTX, Excel, HTML, PNG, JPG, TIFF, BMP.

---

## 2026-02-02

### ARCHITECTURE: Centralized LLM Factory

- `llm.py` with `get_chat_model()` supporting Anthropic, OpenAI, and Ollama providers.
- Algorithms provide facts, LLM explains reasoning.
- Expanded system prompt with definitions, terminology glossary, and anti-hallucination rules.

---

## 2026-02-01

### TECH: Jinja2 Prompt Templating

- Migrated all inline prompt strings to `.j2` templates in `prompts/` folder.
- Deleted old `agent/prompts.py` (inline strings).

### CODE: Data Ingestion Module

- `ingestion/csv_loader.py`, `excel_loader.py`: Auto-detect delimiters, column name mapping, messy value cleaning.
- `ingestion/normalizer.py`: LLM-powered extraction with Instructor, automatic retries on validation failure.
- Custom exception hierarchy: `ProcessIQError`, `InsufficientDataError`, `ExtractionError`.

---

## 2026-01-31

### CODE: LangGraph Agent Implemented

- `agent/state.py`: AgentState TypedDict with analysis fields and control flow.
- `agent/nodes.py`: Node functions implementing 4 agentic decision points (context sufficiency, bottleneck prioritization, constraint conflict resolution, confidence-driven output).
- `agent/edges.py`: Conditional routing with clarification loop.
- End-to-end test: 3 bottlenecks, 3 suggestions, 88% confidence, $130K/year ROI.

### CODE: Analysis Algorithms (Pure Logic, No LLM)

- `analysis/bottleneck.py`: Weighted scoring based on time, error rate, cost, and cascade impact via dependency graph.
- `analysis/roi.py`: PERT-style ROI with pessimistic/likely/optimistic ranges.
- `analysis/confidence.py`: Data completeness scoring (process 60%, constraints 25%, profile 15%).

---

## 2026-01-30

### CODE: Pydantic Models Created

- `models/process.py`: ProcessStep, ProcessData.
- `models/constraints.py`: Constraints, Priority enum.
- `models/analysis.py`: AnalysisResult, severity/type enums.
- `models/memory.py`: BusinessProfile, AnalysisMemory (Phase 2 ready).

---

## 2026-01-29

### SCOPE: Phase 1 Scope Defined

- Phase 1: Conversational input + file upload → LLM extracts → user reviews → analysis.
- Phase 2: Full conversational interview, persistent memory, RAG.
- Files: in-memory BytesIO, never written to disk.

### TECH: pydantic-settings for Configuration

- Centralized Settings class with type validation and `.env` file loading.

---

## 2026-01-28

### DECISION: Multi-Agent Architecture Rejected

- LangGraph nodes already provide task separation; multi-agent adds unnecessary complexity.
- Tasks are sequential (ingest → analyze → suggest → validate), not parallel.

### TECH: Phase 1 Dependencies Finalized

- Added: instructor, langsmith, pydantic-settings, langchain-core/community/anthropic.
- Removed from Phase 1: chromadb (no RAG until Phase 2).

### ARCHITECTURE: Folder Structure and Standards

- Root-level modules: config.py, constants.py, exceptions.py, logging_config.py.
- Python standard logging from day one, every module, every node.

---

## 2026-01-27

### DECISION: SQLite + ChromaDB Dual-Store for Phase 2

- SQLite for structured data (profiles, history, preferences).
- ChromaDB for vector search and semantic similarity.
- LangGraph Store rejected — limited to key-value lookups.

### DECISION: Spinner over Streaming for Phase 1

- Spinner showing current analysis step; streaming deferred to Phase 2.

---

## 2026-01-26

### DECISION: Agent Justification Documented

- Four agentic decision points: context sufficiency, multi-bottleneck prioritization, constraint conflict resolution, confidence-driven branching.
- Litmus test: system must make judgment calls, not just execute steps.

### ARCHITECTURE: Memory-Ready Design

- Phase 1: populate from input, don't persist.
- Phase 2: add persistence with profile approach (single doc) and collection approach (discrete items).

### TECH: Data Models and Frontend Strategy

- Pydantic BaseModel for domain models, TypedDict for LangGraph state.

### SCOPE: Phase 1 (MVP) vs Phase 2 Boundaries

- Phase 1: Chat + file upload, core agent, Streamlit UI.
- Phase 2: Persistent memory, full RAG.

### DESIGN: Agent Architecture Classification

- Utility-based agent: competing objectives (cost vs time vs quality vs constraints).
- Evolution path to learning agent in Phase 2 (user feedback, pattern learning).
