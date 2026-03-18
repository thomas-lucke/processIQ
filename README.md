# ProcessIQ

AI-powered business process analysis for teams that need actionable recommendations without enterprise process-mining infrastructure.

![Python](https://img.shields.io/badge/python-3.12-blue)
![Agent](https://img.shields.io/badge/agent-LangGraph-orange)
![License](https://img.shields.io/badge/license-MIT-green)
![Backend CI](https://github.com/thomas-lucke/processIQ/actions/workflows/backend-ci.yml/badge.svg)
![Frontend CI](https://github.com/thomas-lucke/processIQ/actions/workflows/frontend-ci.yml/badge.svg)
[![codecov](https://codecov.io/gh/thomas-lucke/processIQ/graph/badge.svg?token=4JYVKASHOK)](https://codecov.io/gh/thomas-lucke/processIQ)

## Product Tour

<img src="docs/assets/demo.gif" alt="ProcessIQ demo showing chat input, extraction review, analysis results, and the process graph" width="920" />

<p><em>Short walkthrough: configure settings -> describe the process -> review extraction -> run analysis -> inspect issues -> inspect the graph.</em></p>

<details>
<summary>Screenshots</summary>

<p><strong>01. Start / empty state</strong></p>
<img src="docs/assets/01_start_screen.png" alt="ProcessIQ landing page with the empty chat state and settings area visible" width="920" />

<p><strong>02. Extraction review table</strong></p>
<img src="docs/assets/02_extraction_table.png" alt="Editable extraction review table with structured process steps before analysis" width="920" />

<p><strong>03. Analysis results - Issues tab</strong></p>
<img src="docs/assets/03_analysis_issues_tab.png" alt="Analysis results showing issues with severity and structured findings" width="920" />

<p><strong>04. Process graph</strong></p>
<img src="docs/assets/04_analysis_flow_chart.png" alt="React Flow process graph showing the analyzed workflow and severity states" width="920" />

</details>

## What It Does

ProcessIQ turns a plain-language workflow description or uploaded process document into:

- structured process steps
- deterministic timing, cost, dependency, and confidence calculations
- LLM-generated issues, recommendations, and follow-up questions
- an interactive process graph and proposal-style exports

The target user is an operations manager, consultant, or owner-operator who understands the business process but does not have event logs, BPM tooling, or a data team.

The core design rule is:

> Algorithms calculate facts. The LLM makes judgments.

Process metrics, confidence scoring, graph data, and persistence are deterministic Python code. The LLM is used for extraction, interpretation, and recommendation generation.

## Why It Stands Out

This is not a thin chat wrapper around an LLM. The repository includes a few design choices that are worth highlighting:

- A LangGraph workflow that branches on data completeness before analysis and can run a bounded investigation loop after the first pass.
- A deliberate split between deterministic process math and LLM-generated reasoning.
- Cross-session memory using SQLite for structured records and ChromaDB for semantic retrieval.
- A typed FastAPI and Next.js boundary, with the frontend consuming explicit API DTOs instead of free-form JSON.
- A renderer-agnostic graph schema built on the backend and displayed with React Flow.

## Product Capabilities

- Chat-first extraction from natural language.
- File ingestion for CSV, Excel, PDF, Word, PowerPoint, HTML, and common image formats when document ingestion is enabled.
- Editable extracted process table before analysis.
- Constraint-aware recommendations that respect budget, staffing, and timing limits.
- Confidence scoring that asks for clarification instead of pretending missing data is known.
- Cross-session profile and feedback memory.
- Interactive process graph with before/after severity states.
- Proposal export in Markdown, plain text, and PDF from the web UI.
- CSV export endpoint in the API for active in-memory sessions.

## Important Current Limitations

- Extraction currently requires an OpenAI or Anthropic API key. Selecting `ollama` in the UI does not provide a fully local extraction path yet because the extraction pipeline uses Instructor-backed OpenAI/Anthropic clients.
- The "Reset my data" flow deletes SQLite profile and session records, ChromaDB embeddings, and LangGraph checkpoints. See [SECURITY.md](SECURITY.md).
- The web UI does not currently surface the CSV export endpoint.
- The frontend ships without automated tests today.

## Architecture At A Glance

<img src="docs/assets/architecture_diagram.svg" alt="High-level ProcessIQ architecture showing the user and browser, Next.js web app, FastAPI and LangGraph orchestration layer, and storage systems" width="920" />

<details>
<summary>Agent workflow</summary>

<img src="docs/assets/processiq_agent.svg" alt="ProcessIQ LangGraph workflow showing context checking, clarification, memory synthesis, analysis, investigation, tool calls, and finalization" width="920" />

</details>

Start with [docs/architecture.md](docs/architecture.md) for the system view, then drill into [docs/backend.md](docs/backend.md), [docs/frontend.md](docs/frontend.md), and [docs/ai-analysis-design.md](docs/ai-analysis-design.md).

## Quick Start

### Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)
- Node.js 20+
- `pnpm`
- At least one cloud LLM API key for extraction:
  - `OPENAI_API_KEY`, or
  - `ANTHROPIC_API_KEY`
- Optional: Ollama for local analysis experiments

### Backend

```bash
git clone https://github.com/thomas-lucke/processIQ.git
cd processIQ
uv sync --group dev
cp .env.example .env
```

Populate `.env` with at least one of:

```bash
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
```

Then run the API:

```bash
uv run uvicorn api.main:app --reload
```

- API: `http://localhost:8000`
- OpenAPI docs: `http://localhost:8000/docs`

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

- App: `http://localhost:3000`

### First Run

1. Open `http://localhost:3000`.
2. Describe a process in chat or upload a sample file from [docs/example_data](docs/example_data).
3. Review and edit the extracted steps.
4. Run analysis.
5. Inspect issues, recommendations, graph output, and saved session history.

## Local Development

### Backend checks

```bash
uv run pytest -m "not llm"
uv run pytest -m "not llm" --cov=src --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run bandit -r src/
```

### Frontend checks

```bash
cd frontend
pnpm lint
pnpm exec tsc --noEmit
pnpm build
```

### Pre-commit

```bash
pre-commit install
```

The current pre-commit hooks cover Ruff, mypy, and basic file hygiene. CI adds pytest, Bandit, detect-secrets, and frontend build checks.

## Repository Map

```text
api/                     FastAPI entrypoint and HTTP schemas
frontend/                Next.js app and UI components
src/processiq/agent/     LangGraph state, nodes, edges, tools
src/processiq/analysis/  Deterministic metrics, confidence, ROI, graph schema
src/processiq/ingestion/ File parsing and LLM-backed extraction
src/processiq/persistence/ SQLite, checkpoints, ChromaDB integration
src/processiq/prompts/   Jinja2 prompt templates
tests/                   Unit and integration tests
docs/                    Architecture, deployment, AI design, ADRs
```

## Deployment Notes

- A backend-only Dockerfile is included at the repo root.
- The current persistence model assumes writable local storage for `data/` and `.chroma/`.
- Production multi-instance deployment will require replacing SQLite + ChromaDB-on-disk with a shared backing store such as PostgreSQL + pgvector.

See [docs/deployment.md](docs/deployment.md) for environment variables, storage expectations, and deployment caveats.

## Documentation Index

| Document | Purpose |
| --- | --- |
| [docs/architecture.md](docs/architecture.md) | System architecture, data flow, persistence, and design decisions |
| [docs/backend.md](docs/backend.md) | FastAPI structure, endpoint contract, runtime behavior |
| [docs/frontend.md](docs/frontend.md) | Next.js UI architecture, state model, component responsibilities |
| [docs/ai-analysis-design.md](docs/ai-analysis-design.md) | Prompt system, confidence model, memory, investigation loop |
| [docs/deployment.md](docs/deployment.md) | Environment variables, storage, Docker, deployment guidance |
| [docs/decisions/README.md](docs/decisions/README.md) | Architecture Decision Records |
| [docs/responsible-ai.md](docs/responsible-ai.md) | Lightweight responsible AI review |
| [docs/system-card.md](docs/system-card.md) | Intended use, limits, and operator guidance |
| [ROADMAP.md](ROADMAP.md) | Current roadmap and next engineering milestones |

## Security, Privacy, and Data Handling

- Uploaded files are processed in memory and are not written to disk by the ingestion pipeline.
- The app stores business profile and analysis history in `data/processiq.db`.
- Semantic retrieval data is stored in `.chroma/`.
- LangSmith tracing is optional and disabled by default.
- No authentication layer is present. User identity is a UUID stored in browser local storage.

Read [SECURITY.md](SECURITY.md) before exposing this system beyond local or trusted internal use.

## Development Approach

This project was developed using AI-assisted workflows, primarily with Claude Code and Codex. I used these tools to accelerate implementation and documentation, while retaining responsibility for architecture, technical decisions, validation, and final review.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT. See [LICENSE](LICENSE).
