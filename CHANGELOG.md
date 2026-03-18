# Changelog

All notable design decisions and changes to ProcessIQ are documented here.

---

## 2026-03-18

### DOCS: Reworked product and interaction docs to match the current implementation

- Rewrote `docs/PROJECT_BRIEF.md` as a current-state product and architecture brief.
- Rewrote `docs/PRODUCT_STRATEGY.md` to focus on grounded product strategy and current product priorities.
- Rewrote `docs/CONVERSATION_FLOW.md` to match the actual Next.js chat, review, analysis, and re-analysis flow.
- Standardized tone and positioning across these documents so they read as maintainable product and engineering documentation.

### DOCS: Split architecture visualization into two Mermaid diagrams

- `docs/architecture_diagram.mmd` is now a high-level system view focused on the product surface, API, analysis engine, storage, and outputs.
- Added `docs/agent_flow.mmd` as a separate workflow diagram for the LangGraph analysis flow.
- Simplified labels and structure so each diagram is easier to scan and more useful to human readers.
- Refined the high-level architecture diagram further to emphasize the primary request path and reduce diagram clutter.

### DOCS: Added product media and architecture visuals to the README and docs

- Added a short product demo GIF and four UI screenshots to `README.md`.
- Embedded the exported high-level architecture SVG in `README.md` and `docs/architecture.md`.
- Embedded the exported LangGraph workflow SVG in `README.md`, `docs/architecture.md`, and `docs/ai-analysis-design.md`.
- Replaced the older text-only architecture snapshot in `README.md` with visual documentation.

## 2026-03-17

### FIX: Improvement suggestions message now opens with a blocked-analysis notice when confidence < 60%

### ARCHITECTURE: Investigation loop findings now feed back into analysis output

- Haiku emits a structured `<investigation_verdict>` block at the end of its summary (CONFIDENCE: HIGHER/UNCHANGED/LOWER, REASON, SEVERITY_CHANGES)
- `finalize_analysis_node` parses this verdict and adjusts `confidence_score` (+/-5-8%) and appends the reason to `confidence_notes`
- Issue severity can be promoted or demoted if tool findings warrant it
- No additional LLM call - verdict is extracted from the summary message haiku already writes

### FIX: Annual volume extraction - volume mentioned in user input was discarded as a warning log instead of being stored, causing ROI estimates to be off by ~10x when actual volume was provided. Added `annual_volume` field to `ExtractionResult` and wired it through to `ProcessData`.

### FIX: LangSmith tracing flag exposed via `/health` endpoint and reflected in the settings drawer Data & Privacy section. `tracing_enabled` is only true when both the flag is set and an API key is present.

### FIX: Empty state example prompts made non-interactive - chips were submitting to the chat on click; now purely visual.

## 2026-03-16

### CODE: Test coverage - `agent/interface.py` - 33 new unit tests covering `extract_from_text`, `analyze_process`, `continue_conversation`, and `AgentResponse` properties. Overall `src/` coverage moved from 64% to 72%.

## 2026-03-13

### CODE: Export dropdown - `.md`, `.txt`, and PDF

- Replaced single Export button with a three-option dropdown
- `.txt` strips markdown syntax client-side before download
- PDF rendered server-side via WeasyPrint (`POST /export/pdf`); produces vector PDF with selectable text; `weasyprint>=62.0` added
- `GET /export/csv/{thread_id}` wired to existing `csv_export.py` (API only, not in UI)

### FIX: Constraints field name mismatch between Python and TypeScript - renamed `cannot_hire`/`max_implementation_weeks` to `no_new_hires`/`no_layoffs`/`timeline_weeks`; kept old names as computed properties for internal compatibility.

### DESIGN: UI theme overhaul - light gray surfaces (`#f0f2f5`) with neutral gray accent (`#5a6272`). All badges, graph, minimap, and status colors updated for both passes.

## 2026-03-13

### FIX: Removed dead draft analysis code - `_generate_draft_analysis` and `_generate_post_extraction_extras` deleted from `interface.py`; result was never sent to the frontend. Extracted latency reduced by ~60s.
### FIX: Anthropic model IDs updated - `claude-sonnet-4-5-20250929` to `claude-sonnet-4-6` in `model_presets.py`.
### CODE: Added entry log to `_run_llm_analysis` to close the 2-minute silent window during structured-output calls.

---

## 2026-03-12

### ARCHITECTURE: CI/CD - GitHub Actions backend (ruff -> mypy -> pytest -> bandit -> detect-secrets) and frontend (ESLint -> tsc -> build) pipelines; `bandit` and `detect-secrets` added as dev deps; pre-commit pins updated.
### ARCHITECTURE: Removed Streamlit UI - `src/processiq/ui/` and `app.py` deleted.
### FIX: Cross-session feedback loop fully wired - rejected recommendations now persist to `business_profiles.rejected_approaches` and feed future analyses. Added FastAPI lifespan handler for SQLite shutdown.

---

## 2026-03-11

### DESIGN: Added `docs/responsible-ai.md` and `docs/system-card.md`; prompt injection section, security threat model, "not for personnel evaluation" disclaimer.
### ARCHITECTURE: Four ADRs created in `docs/decisions/` - LangGraph, ChromaDB, LLM factory, FastAPI + Next.js.
### CODE: Pydantic validators added to all extraction and insight models - clamping rather than raising on bad LLM output.
### ARCHITECTURE: `memory_synthesis_node` pre-compresses RAG context into an 8-10 line brief before analysis; skips below 0.5 cosine similarity; `check_context -> memory_synthesis -> initial_analysis`.
### FIX: Four chat routing gaps fixed - conversational detection, `extract_converse.j2` `has_process` guard, post-analysis follow-up routed via `followup.j2` instead of re-running full analysis.

---

## 2026-03-11

### CODE: +162 unit tests (total ~416) - `check_context_sufficiency`, `finalize_analysis_node`, edge routing, `LLMTaskConfig`, `ExtractedStep` validators.
### ARCHITECTURE: Prompt overhaul per Anthropic best practices - XML data blocks in `analyze.j2`, `<investigation_budget>` in `investigation_system.j2`, extraction routing replaced with 4 focused templates and deterministic code router.

---

## 2026-03-10 (RAG improvements)

### CODE: Richer embeddings and prompt effectiveness

- `AnalysisMemory` gains `process_summary` and `issue_descriptions` (full LLM reasoning text). Embeddings now match on meaning rather than keyword labels.
- Similarity threshold (0.4 cosine) added - retrieved analyses below threshold are dropped before prompt injection.
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

- Investigation depth slider (1-10) wired to `max_cycles_override`.
- FastAPI hardening: rate limiting, input caps, file extension whitelist, 50 MB limit, session TTL + LRU eviction, CORS narrowed.

---

## 2026-03-05

### ARCHITECTURE: FastAPI + Next.js replacing Streamlit

- `api/main.py` with `/analyze`, `/extract`, `/extract-file`, `/continue`, `/graph-schema`. Next.js 15 App Router, TypeScript, Tailwind, React Flow. Two-phase layout: full-width chat -> animated 40/60 split. Settings panel: LLM provider, analysis mode, constraints, business profile. Dark theme, DM Sans, design tokens.

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

- LLM provider selector (OpenAI / Anthropic / Ollama) with model presets. Expert mode removed. Agent graph simplified 8 -> 4 nodes.

---

## 2026-02-05

### ARCHITECTURE: LLM-first analysis pipeline

- Algorithms calculate facts, LLM makes judgments. New `analysis/metrics.py`, `models/insight.py`, `analyze.j2`. Conversational edit support added.

---

## 2026-02-04

- Per-task LLM configuration (`LLMTaskConfig`, three analysis presets). LangGraph `SqliteSaver` persistence.

---

## 2026-02-03

### DECISION: Chat-first UI. `agent/interface.py` as clean boundary - UI never imports `graph.py`.

---

## 2026-01-28

### DECISION: Multi-agent architecture rejected - LangGraph nodes provide sufficient task separation. ChromaDB and streaming deferred to Phase 2.

---

## 2026-01-27

### DECISION: SQLite + ChromaDB dual-store chosen for Phase 2. LangGraph Store rejected (no SQL or vector search).

---

## 2026-01-26

### DECISION: Memory-ready design - Phase 1 populates from input only, Phase 2 persists cross-session.
