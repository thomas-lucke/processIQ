# Changelog

All notable design decisions and changes to ProcessIQ are documented here.

---

## 2026-03-10 (RAG improvements)

### RAG embedding quality + prompt effectiveness

- `AnalysisMemory` gains `process_summary` (LLM's 1-2 sentence characterisation) and `issue_descriptions` (full reasoning text, not just titles). Both populated in `_persist_analysis()` from `AnalysisInsight`.
- `_build_embedding_text()` now includes: process summary, issue descriptions, recommendation descriptions from `recommendations_full`. Previous version was title-only keyword labels; now embeds the LLM's actual reasoning, making semantic retrieval match on meaning rather than names.
- Similarity threshold added: retrieved past analyses below 0.4 cosine similarity are dropped before prompt injection. Prevents unrelated sessions from being injected as noise.
- `rejection_reasons` now included in `similar_past` dict passed to the prompt (was missing despite template expecting it).
- `analyze.j2` past analyses block: vague "give more calibrated recommendations" replaced with concrete directives — if same bottleneck type recurs, note whether same root cause applies; if recommendation was previously rejected, do not repeat unless approach is fundamentally different.
- `analyze.j2` cross-session patterns block: elevated from a soft suggestion to a mandatory instruction — LLM must surface recurring organizational patterns explicitly in summary/patterns fields, not just note them privately.

---

## 2026-03-10

### Export proposal download
- `generate_proposal_markdown()` added to `export/summary.py` (Executive Summary → Current Process → Key Findings → Recommendations → Next Steps → Appendix). Client-side `buildProposalMarkdown()` mirrors this in the frontend; "Export" button in the results tab bar triggers a `.md` download.

### Annual volume metrics
- `annual_volume` added to `ProcessData`. `ProcessMetrics` gains `hours_per_year`, `cost_per_year`, `annual_volume_used`, `volume_is_estimated`. Estimation falls back to company-size defaults (startup 120, small 250, mid 500, enterprise 2000) when not provided. Frontend hero stat block now leads with hours/year as the primary number.

### Analysis Library — full recommendation text
- `recommendations_json` column migrated into `analysis_sessions` (idempotent `ALTER TABLE`). Full recommendation objects (title, description, expected_benefit, estimated_roi) now stored and served via `GET /sessions`. Library panel renders expandable recommendation cards with accepted/rejected colouring; falls back to title-only list for older sessions.

### Constraint reasoning — "What I ruled out"
- `RuledOutOption` model and `ruled_out_recommendations` field added to `AnalysisInsight`. `analyze.j2` generates ruled-out options when constraints are active. Frontend shows a collapsed accordion below the recommendations list.

### Hero stat block + Investigation timeline
- Overview tab now opens with a 2–4 column stat row (hours/year, time per run, cost, issues, recommendations) computed client-side.
- `InvestigationTimeline` component renders `investigation_findings` as labelled, individually-expandable steps instead of a raw text dump.

---

## 2026-03-10 (earlier)

### Process graph layout — horizontal left-to-right flow
- Replaced serpentine 3-column grid with flat horizontal layout. React Flow handles switched Top/Bottom → Left/Right; MiniMap added; container height dynamic.

### Frontend wiring — profile, context attribution, feedback persistence
- Profile loaded on mount and auto-saved (800ms debounce). "Context used" block in OverviewTab when `context_sources` is non-empty. Accept/Dismiss buttons call `POST /feedback/{session_id}`; results injected into future analyses.

### Steps table summary row
- Both process tables now show totals: time, resources, avg error rate, cost.

---

## 2026-03-09

### Analysis Library view
- `GET /sessions/{user_id}` endpoint; `AnalysisSessionSummary` schema. `LibraryPanel` component: collapsible session cards with issue/rec badges and acceptance rate bar. Library and Analyze views kept mounted to preserve chat state across nav switches.

### Process graph renderer
- React Flow custom `processNode`: hover tooltips, variable-size circles (time % + severity boost), wrap-edge dashes, legend.

### FIX: Chat edits after analysis lost process context
- `currentProcessData` passed to `ChatInterface` as fallback when `pendingProcessData` is cleared post-analysis.

---

## 2026-03-08

### Persistent memory + ChromaDB RAG
- SQLite persistence (`db.py`, `profile_store.py`, `analysis_store.py`). ChromaDB semantic retrieval scoped by user. Pipeline retrieves past analyses and rejections before analysis; embeds after. `analyze.j2` extended with three conditional RAG blocks. `GET/PUT /profile`, `POST /feedback`, `context_sources` in `AnalyzeResponse`.

---

## 2026-03-06

- Investigation depth slider (1–10) wired to `max_cycles_override`.
- FastAPI hardening: rate limiting, input caps, file extension whitelist, 50 MB limit, session TTL + LRU eviction, CORS narrowed.

---

## 2026-03-05

### FastAPI + Next.js replacing Streamlit
- `api/main.py` with `/analyze`, `/extract`, `/extract-file`, `/continue`, `/graph-schema`. Next.js 15 App Router, TypeScript, Tailwind, React Flow. Two-phase layout: full-width chat → animated 40/60 split. Settings panel: LLM provider, analysis mode, constraints, business profile.

### Full visual redesign
- Dark theme, DM Sans, design tokens, left rail, header, reveal transition, empty state.

---

## 2026-02-27

### Genuine agentic investigation loop
- `initial_analysis_node` seeds history; `investigate_node` binds tools; loops until no tool calls or `agent_max_cycles` hit. Three tools: `analyze_dependency_impact`, `validate_root_cause`, `check_constraint_feasibility`. `finalize_analysis_node` extracts tool output into `investigation_findings`.

### FIX: Extraction prompt now recognises supplementary step data as UPDATE rather than `needs_clarification`.

---

## 2026-02-17

- Self-improving agent via recommendation feedback: thumbs up/down, rejection reasons injected into `analyze.j2` on re-analysis.
- File uploads merge with existing process data (`ProcessData.merge_with()`).
- ROI estimates added to `Recommendation` model.
- Step grouping: `group_id`/`group_type` (alternative/parallel) on `ProcessStep`.

---

## 2026-02-16

- 265-unit test suite. Parallel post-extraction LLM calls via `ThreadPoolExecutor`. Structured output for analysis replacing manual JSON parsing.

---

## 2026-02-12

- Progressive disclosure on recommendations: `plain_explanation`, `concrete_next_steps`, two expander layers.
- `RevenueRange` enum threaded into `analyze.j2` for calibrated recommendations.

---

## 2026-02-06

- LLM provider selector (OpenAI / Anthropic / Ollama) with model presets. Expert mode removed. Agent graph simplified 8 → 4 nodes.

---

## 2026-02-05

### LLM-first analysis pipeline
- Algorithms calculate facts, LLM makes judgments. New `analysis/metrics.py`, `models/insight.py`, `analyze.j2`. Conversational edit support added.

---

## 2026-02-04

- Per-task LLM configuration (`LLMTaskConfig`, three analysis presets). LangGraph `SqliteSaver` persistence; thread ID format `{user_id}:{conversation_id}`.

---

## 2026-02-03

### DECISION: Chat-first UI. `agent/interface.py` as clean boundary — UI never imports `graph.py`.

---

## 2026-02-02

- Centralised LLM factory (`llm.py`) with Anthropic/OpenAI/Ollama support.

---

## 2026-02-01

- Jinja2 prompt templates. CSV/Excel ingestion with Instructor-based normaliser.

---

## 2026-01-31

- LangGraph agent (`state.py`, `nodes.py`, `edges.py`) and analysis algorithms.

---

## 2026-01-30

- Pydantic domain models: `ProcessStep`, `ProcessData`, `Constraints`, `AnalysisResult`, `BusinessProfile`.

---

## 2026-01-29

- Phase 1/2 boundaries defined. `pydantic-settings` for configuration.

---

## 2026-01-28

- Multi-agent architecture rejected — LangGraph nodes already provide task separation. ChromaDB deferred to Phase 2.

---

## 2026-01-27

- SQLite + ChromaDB dual-store chosen for Phase 2. LangGraph Store rejected (no SQL or vector search). Streaming deferred to Phase 2.

---

## 2026-01-26

- Agent justification documented. Memory-ready design: Phase 1 populates from input, Phase 2 persists.
