# Roadmap

This roadmap is intentionally practical. It reflects what the repository already does well today, where the architecture is incomplete, and which next steps would most improve production readiness.

## Current State

### Shipped

- [x] FastAPI backend and Next.js 15 frontend
- [x] LangGraph-based analysis workflow with clarification and investigation phases
- [x] Editable extracted process model before analysis
- [x] Persistent profile and analysis history in SQLite
- [x] ChromaDB-backed semantic retrieval for prior analyses
- [x] Interactive process graph in the UI
- [x] Proposal export in Markdown, plain text, and PDF
- [x] Backend and frontend CI workflows
- [x] Portfolio-grade architecture and deployment documentation

### Not Yet Production-Ready

- [ ] Authenticated multi-user deployment
- [ ] Shared persistent storage suitable for multiple backend replicas
- [ ] Complete deletion path for user data across SQLite, checkpoints, and ChromaDB
- [ ] Frontend automated tests
- [ ] Fully local extraction path without OpenAI/Anthropic dependency

## Near-Term Priorities

### 1. Persistence hardening

- Migrate from SQLite to PostgreSQL for structured records and LangGraph checkpoints.
- Replace ChromaDB-on-disk with `pgvector` or another shared vector store.
- Add an explicit deletion path for all user-scoped data, including embeddings and checkpoints.

Why it matters:
The current storage model is strong for local development and demos, but it is not the right long-term shape for multi-instance deployment.

### 2. Authentication and identity

- Replace browser-local UUID identity with authenticated users.
- Make session history available across devices.
- Tie reset/delete behavior to a real account boundary.

Why it matters:
Today, identity is convenience state, not a security boundary.

### 3. Frontend test coverage

- Add Playwright coverage for the extraction -> edit -> analyze -> feedback path.
- Add a few targeted component tests for the result tabs and settings drawer.

Why it matters:
The frontend now carries enough state and API branching that manual-only testing is no longer ideal.

### 4. Extraction provider parity

- Add a true Ollama-compatible extraction path, or make the cloud-provider dependency explicit in the product surface.

Why it matters:
The UI presents Ollama as a provider option, but extraction is still implemented through Instructor-backed OpenAI/Anthropic clients.

## Planned Product and Platform Work

### Streaming analysis

Progressively render status and partial results as the workflow advances instead of waiting for one final JSON response.

### Investigation tool expansion

Build on the existing tool loop with tools that fetch genuinely new evidence:

- `query_similar_analyses`
- `search_industry_benchmarks`
- `fetch_process_standards`

These are described in [docs/decisions/0005-investigation-loop-design.md](docs/decisions/0005-investigation-loop-design.md).

### Comparison mode

Compare a baseline process with a proposed future-state process side by side.

### Data retention controls

Add configurable retention windows and scheduled cleanup for inactive user data.

## Longer-Term Ideas

- Opt-in benchmarking against anonymized aggregate patterns.
- Team workspaces with shared process libraries.
- Background job execution for long-running analyses and exports.
