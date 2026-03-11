# Changelog

All notable design decisions and changes to ProcessIQ are documented here.

---

## 2026-03-11 (Pydantic hardening + memory synthesis node)

### CODE: Pydantic validators on all extraction and insight models

- `Issue`, `Recommendation`, `AnalysisInsight`: case-normalisation, length truncation, and empty-title filtering on all fields. Validators clamp rather than raise to avoid hard failures on LLM output.
- `ExtractedStep`: replaced hard `ge`/`le` constraints with silent clamping validators for all numeric fields.
- `ExtractionResult`: filters steps with blank `step_name`.

### ARCHITECTURE: `memory_synthesis_node` pre-compresses RAG context

- New node synthesises raw RAG blobs (past analyses, rejections, cross-session patterns) into an 8–10 line brief via LLM before analysis runs. Skips when no memory or all similarity scores < 0.5; fails gracefully with raw blobs as fallback.
- New `memory_brief: str | None` field in `AgentState`. New `memory_brief.j2` template.
- `analyze.j2` conditionally renders compressed brief or raw memory blocks.
- Graph wired: `check_context → memory_synthesis → initial_analysis`.

---

## 2026-03-11 (Chat routing fixes)

### FIX: Closed 4 chat routing gaps in extraction and post-analysis flow

- `extract_new.j2`: LLM now responds conversationally instead of extracting when input lacks ≥2 describable steps.
- `_is_conversational()`: extended to catch short confirmation signals ("looks good", "I'm done", etc.) capped at ≤60 chars.
- `extract_converse.j2`: added `has_process` conditional — shows correct framing when process data is already loaded.
- Post-analysis follow-up: `continue_conversation` now routes to `_answer_followup()` via `followup.j2` instead of re-running full analysis. Re-analysis still triggered when explicitly requested.

---

## 2026-03-11 (Test suite expansion)

### CODE: Added 162 unit tests, bringing total to ~416

New coverage: `check_context_sufficiency`, `finalize_analysis_node`, edge routing, context utilities, `LLMTaskConfig`, `ExtractedStep` validators, normaliser pipeline.

---

## 2026-03-11 (Prompt architecture overhaul)

### ARCHITECTURE: Rewrote all prompts per Anthropic best practices

**In-place rewrites:**
- `analyze.j2`: data blocks moved to top in XML tags; query at bottom; not_problems section guarded on timing data; bare negative rules replaced with positive framing.
- `system.j2`: stripped dead metric definitions that conflicted with judgment-based analysis approach.
- `investigation_system.j2`: added `<investigation_budget>` block with hard cycle limit and arithmetic exit criteria. Tool descriptions rewritten to action-based.
- `followup.j2`, `clarification.j2`, `improvement_suggestions.j2`: persona, tone, and format improvements; `business_context` added to improvement suggestions.

**Extraction routing refactor:**
- Replaced single `extraction.j2` (4-mode LLM routing) with 4 focused templates: `extract_new.j2`, `extract_update.j2`, `extract_estimate.j2`, `extract_converse.j2`. Shared fields in `_extraction_fields.j2`.
- Deterministic code router `get_extraction_prompt()` replaces LLM-based routing decision.

---

## 2026-03-10 (RAG improvements)

### CODE: Richer embeddings and prompt effectiveness

- `AnalysisMemory` gains `process_summary` and `issue_descriptions` (full LLM reasoning text). Embeddings now match on meaning rather than keyword labels.
- Similarity threshold (0.4 cosine) added — retrieved analyses below threshold are dropped before prompt injection.
- `rejection_reasons` now correctly passed into the `similar_past` dict (was missing despite template expecting it).
- `analyze.j2` past analyses and cross-session pattern blocks given concrete directives instead of vague suggestions.

---

## 2026-03-10

### SCOPE: Export, annual metrics, analysis library full text, ruled-out options

- Proposal export: `generate_proposal_markdown()` in `export/summary.py`; frontend "Export" button triggers `.md` download.
- Annual volume metrics: `annual_volume` on `ProcessData`; `ProcessMetrics` gains `hours_per_year`, `cost_per_year`. Estimation falls back to company-size defaults. Frontend hero stat leads with hours/year.
- Analysis Library: `recommendations_json` column added to `analysis_sessions`. Full recommendation objects stored and rendered with accept/reject colouring.
- Ruled-out options: `RuledOutOption` model and `ruled_out_recommendations` on `AnalysisInsight`. `analyze.j2` generates ruled-out options when constraints are active. Frontend shows collapsed accordion.
- Process graph switched to horizontal left-to-right layout with MiniMap.

---

## 2026-03-09

### ARCHITECTURE: Analysis Library view + process graph renderer

- `GET /sessions/{user_id}` endpoint. `LibraryPanel` component with collapsible session cards.
- React Flow custom `processNode`: hover tooltips, variable-size circles, wrap-edge dashes.
- FIX: `currentProcessData` passed to `ChatInterface` as fallback after `pendingProcessData` is cleared post-analysis.

---

## 2026-03-08

### ARCHITECTURE: Persistent memory + ChromaDB RAG

- SQLite persistence (`db.py`, `profile_store.py`, `analysis_store.py`). ChromaDB semantic retrieval scoped by user. Pipeline retrieves past analyses and rejections before analysis; embeds after. `analyze.j2` extended with three conditional RAG blocks. `GET/PUT /profile`, `POST /feedback`, `context_sources` in `AnalyzeResponse`.

---

## 2026-03-06

- Investigation depth slider (1–10) wired to `max_cycles_override`.
- FastAPI hardening: rate limiting, input caps, file extension whitelist, 50 MB limit, session TTL + LRU eviction, CORS narrowed.

---

## 2026-03-05

### ARCHITECTURE: FastAPI + Next.js replacing Streamlit

- `api/main.py` with `/analyze`, `/extract`, `/extract-file`, `/continue`, `/graph-schema`. Next.js 15 App Router, TypeScript, Tailwind, React Flow. Two-phase layout: full-width chat → animated 40/60 split. Settings panel: LLM provider, analysis mode, constraints, business profile. Dark theme, DM Sans, design tokens.

---

## 2026-02-27

### ARCHITECTURE: Genuine agentic investigation loop

- `initial_analysis_node` seeds history; `investigate_node` binds tools; loops until no tool calls or `agent_max_cycles` hit. Three tools: `analyze_dependency_impact`, `validate_root_cause`, `check_constraint_feasibility`. `finalize_analysis_node` extracts tool output into `investigation_findings`.
- FIX: Extraction prompt now recognises supplementary step data as UPDATE rather than `needs_clarification`.

---

## 2026-02-17

- Self-improving agent via recommendation feedback: thumbs up/down, rejection reasons injected into `analyze.j2` on re-analysis.
- File uploads merge with existing process data (`ProcessData.merge_with()`).
- ROI estimates added to `Recommendation`. Step grouping (`group_id`/`group_type`) added to `ProcessStep`.

---

## 2026-02-16

- 265-unit test suite. Parallel post-extraction LLM calls via `ThreadPoolExecutor`. Structured output for analysis replacing manual JSON parsing.

---

## 2026-02-12

- Progressive disclosure on recommendations: `plain_explanation`, `concrete_next_steps`, two expander layers.
- `RevenueRange` enum added for calibrated recommendations.

---

## 2026-02-06

- LLM provider selector (OpenAI / Anthropic / Ollama) with model presets. Expert mode removed. Agent graph simplified 8 → 4 nodes.

---

## 2026-02-05

### ARCHITECTURE: LLM-first analysis pipeline

- Algorithms calculate facts, LLM makes judgments. New `analysis/metrics.py`, `models/insight.py`, `analyze.j2`. Conversational edit support added.

---

## 2026-02-04

- Per-task LLM configuration (`LLMTaskConfig`, three analysis presets). LangGraph `SqliteSaver` persistence.

---

## 2026-02-03

### DECISION: Chat-first UI. `agent/interface.py` as clean boundary — UI never imports `graph.py`.

---

## 2026-01-28

### DECISION: Multi-agent architecture rejected — LangGraph nodes provide sufficient task separation. ChromaDB and streaming deferred to Phase 2.

---

## 2026-01-27

### DECISION: SQLite + ChromaDB dual-store chosen for Phase 2. LangGraph Store rejected (no SQL or vector search).

---

## 2026-01-26

### DECISION: Memory-ready design — Phase 1 populates from input only, Phase 2 persists cross-session.
