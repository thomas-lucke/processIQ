# Deployment

This document covers local setup, environment variables, storage expectations, and the current limitations you should understand before deploying ProcessIQ anywhere beyond a workstation or trusted demo environment.

## Current Deployment Reality

ProcessIQ can be deployed today, but the production story is still transitional.

What is solid today:

- local development
- single-instance backend deployment
- frontend deployment to Vercel or another Next.js host
- backend deployment with a writable volume for `data/` and `.chroma/`

What is not finished yet:

- authenticated multi-user deployment
- shared persistence for multiple backend replicas
- full delete/reset coverage across every persistence layer
- a fully local extraction path that does not rely on OpenAI or Anthropic

## Local Development Setup

### Backend

```bash
git clone https://github.com/thomas-lucke/processIQ.git
cd processIQ
uv sync --group dev
cp .env.example .env
uv run uvicorn api.main:app --reload
```

### Frontend

```bash
cd frontend
pnpm install
pnpm dev
```

Local URLs:

- backend: `http://localhost:8000`
- OpenAPI docs: `http://localhost:8000/docs`
- frontend: `http://localhost:3000`

## LLM Provider Requirement

Important correction:

At least one cloud API key is required for the extraction flow today.

Use one of:

- `OPENAI_API_KEY`
- `ANTHROPIC_API_KEY`

Ollama can be used for analysis experiments, but it is not yet a complete replacement for extraction.

## Environment Variables

The authoritative defaults come from `src/processiq/config.py`.

### Core provider and tracing settings

| Variable | Default | Notes |
| --- | --- | --- |
| `OPENAI_API_KEY` | empty | required for OpenAI-backed extraction or analysis |
| `ANTHROPIC_API_KEY` | empty | required for Anthropic-backed extraction or analysis |
| `LANGSMITH_API_KEY` | empty | optional |
| `LANGSMITH_TRACING` | `false` | tracing disabled unless explicitly enabled |
| `LANGSMITH_ENDPOINT` | `https://eu.api.smith.langchain.com` | note: this differs from the example value shown in `.env.example` |
| `LANGCHAIN_PROJECT` | `processiq` | LangSmith project name |

### Global LLM settings

| Variable | Default | Notes |
| --- | --- | --- |
| `LLM_PROVIDER` | `openai` | backend default; current frontend default is `anthropic` |
| `LLM_MODEL` | empty | empty means "use provider default" |
| `LLM_TEMPERATURE` | `0.0` | some OpenAI reasoning-style models are forced to provider-compatible settings |
| `LLM_EXPLANATIONS_ENABLED` | `true` | disables LLM-generated explanation text when false |

### Per-task overrides

Each of these accepts JSON that maps to `LLMTaskConfig`:

- `LLM_TASK_EXTRACTION`
- `LLM_TASK_CLARIFICATION`
- `LLM_TASK_EXPLANATION`
- `LLM_TASK_ANALYSIS`
- `LLM_TASK_INVESTIGATION`

Example:

```bash
LLM_TASK_ANALYSIS='{"provider":"anthropic","model":"claude-sonnet-4-6"}'
LLM_TASK_INVESTIGATION='{"provider":"anthropic","model":"claude-haiku-4-5-20251001"}'
```

Important detail:
`model_presets.py` defines presets for extraction, clarification, explanation, and analysis. Investigation does not currently have per-mode presets there, so it falls back to provider defaults or explicit `LLM_TASK_INVESTIGATION` config.

### Ollama

| Variable | Default | Notes |
| --- | --- | --- |
| `OLLAMA_ENABLED` | `true` | set false in cloud environments without Ollama |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | local Ollama server |
| `OLLAMA_TIMEOUT` | `120` | increase on slower machines |

### Persistence and app settings

| Variable | Default | Notes |
| --- | --- | --- |
| `PERSISTENCE_ENABLED` | `true` | disables LangGraph checkpoint persistence when false |
| `PERSISTENCE_DB_PATH` | `data/processiq.db` | SQLite path |
| `CHROMA_PERSIST_DIRECTORY` | `.chroma` | ChromaDB storage directory |
| `ALLOWED_ORIGIN` | `http://localhost:3000` | browser CORS origin |
| `LOG_LEVEL` | `INFO` | |
| `CONFIDENCE_THRESHOLD` | `0.6` | lower means fewer clarification stops |
| `AGENT_MAX_CYCLES` | `3` | max investigate-loop turns |
| `DEMO_MODE` | `false` | when `true`, disables Ollama provider selection and investigation depth slider in the UI |
| `DOCUMENT_INGESTION_ENABLED` | `true` | disables Docling-backed file ingestion when false |

## Storage Expectations

The backend expects writable local paths for:

- `data/processiq.db`
- `.chroma/`

The Dockerfile and runtime code create directories as needed, but the process still needs filesystem write access.

### What is stored where

`data/processiq.db`
- business profiles
- saved analysis sessions
- feedback
- LangGraph checkpoints

`.chroma/`
- vector embeddings and metadata for prior analyses

In-memory process state
- active graph and CSV export cache keyed by `thread_id`

## Docker

A backend-only Dockerfile exists at the repo root.

What it covers:

- Python runtime
- WeasyPrint system dependencies
- backend package installation
- FastAPI startup

What it does **not** cover:

- frontend containerization
- full-stack orchestration
- persistent volume setup

Example build:

```bash
docker build -t processiq-backend .
```

Example run:

```bash
docker run --rm -p 8000:8000 --env-file .env processiq-backend
```

For anything beyond disposable local use, mount persistent storage for both `data/` and `.chroma/`.

## Production Deployment Guidance

### Backend

Suitable current targets:

- Railway
- Fly.io
- Render
- a VPS or VM running Uvicorn behind a reverse proxy

Recommended Uvicorn command:

```bash
uv run uvicorn api.main:app --host 0.0.0.0 --port 8000
```

Minimum deployment checklist:

1. Set `ALLOWED_ORIGIN` to the exact frontend URL.
2. Provide at least one cloud LLM API key.
3. Mount persistent storage for `data/` and `.chroma/`.
4. Decide whether LangSmith tracing should be disabled in that environment.
5. Treat the service as single-tenant or trusted-internal until auth exists.

### Frontend

The frontend is a normal Next.js deployment.

Required public environment variable:

```bash
NEXT_PUBLIC_API_URL=https://your-backend.example.com
```

The local fallback in `frontend/lib/api.ts` is `http://localhost:8000`.

## Data Deletion

`DELETE /profile/{user_id}` removes all data stored for a user:

- SQLite profile record
- SQLite analysis-session records
- ChromaDB embeddings
- LangGraph checkpoint rows for all user threads

The endpoint fetches session IDs before deletion so the checkpoint IDs are available before the session records are gone.

## Current Production Limitations

### Single-instance bias

SQLite plus local-disk ChromaDB work well for one backend instance but are a poor fit for horizontally scaled deployments.

### No authentication

User identity is browser-local UUID state, not account-backed identity.

### In-memory export cache

CSV export and graph lookup depend on an in-memory cache, so they are tied to active runtime state rather than durable session history.

### Extraction provider gap

Ollama is not yet a true extraction provider.

## Likely Next Migration Path

The cleanest production upgrade path is:

- PostgreSQL for relational state
- `pgvector` for vector retrieval
- auth-backed user accounts
- a complete delete path across all stores

That would address most of the current deployment caveats without changing the high-level application design.

## Troubleshooting

### Browser shows CORS errors

Check that `ALLOWED_ORIGIN` matches the exact frontend origin, including protocol and port.

### File uploads fail for supported-looking documents

Check `DOCUMENT_INGESTION_ENABLED`. If it is false, only CSV and Excel uploads remain supported.

### Ollama analysis is slow or times out

Increase `OLLAMA_TIMEOUT` and use a smaller model. Extraction will still require OpenAI or Anthropic.

### LangSmith traces do not appear

Check:

- `LANGSMITH_TRACING=true`
- `LANGSMITH_API_KEY` is present
- the selected endpoint matches the environment

### CSV export returns 404

That usually means the thread is no longer present in the backend's in-memory session cache.
