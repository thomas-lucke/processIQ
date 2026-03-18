# Contributing to ProcessIQ

Thanks for contributing. This project is small enough to move quickly, but it already has a few architectural constraints that are worth understanding before you change behavior.

Start with:

- [README.md](README.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/ai-analysis-design.md](docs/ai-analysis-design.md)
- [CHANGELOG.md](CHANGELOG.md)

## Development Setup

### Prerequisites

- Python 3.12+
- [`uv`](https://docs.astral.sh/uv/)
- Node.js 20+
- `pnpm`
- At least one of:
  - `OPENAI_API_KEY`
  - `ANTHROPIC_API_KEY`

Ollama is useful for local analysis experiments, but it is not sufficient on its own for end-to-end development because the extraction pipeline currently depends on OpenAI or Anthropic clients.

### Install

```bash
git clone https://github.com/thomas-lucke/processIQ.git
cd processIQ
uv sync --group dev
cp .env.example .env
pre-commit install
```

Frontend dependencies:

```bash
cd frontend
pnpm install
```

### Run Locally

Backend:

```bash
uv run uvicorn api.main:app --reload
```

Frontend:

```bash
cd frontend
pnpm dev
```

## Quality Gates

### Backend

```bash
uv run pytest -m "not llm"
uv run pytest -m "not llm" --cov=src --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
uv run bandit -r src/
```

### Frontend

```bash
cd frontend
pnpm lint
pnpm exec tsc --noEmit
pnpm build
```

### Live LLM tests

```bash
uv run pytest
```

Tests marked `@pytest.mark.llm` call real providers and are intentionally excluded from CI.

## What CI Actually Enforces

Backend CI currently runs:

- Ruff lint
- Ruff format check
- mypy on `src/`
- pytest without `llm` tests
- Bandit
- detect-secrets
- coverage upload

Frontend CI currently runs:

- ESLint
- `tsc --noEmit`
- production build

Pre-commit is helpful, but it is not the full CI gate. Today it covers Ruff, mypy, and basic file hygiene only.

## Project Rules

### 1. Keep the API layer thin

`api/main.py` is an HTTP boundary, not a business-logic home. Route handlers should translate requests and responses, enforce API-level validation, and delegate into `processiq.agent.interface`.

Do not couple the API directly to graph internals unless there is a strong reason.

### 2. Preserve the deterministic/LLM split

The core architecture is:

- deterministic code computes metrics, confidence, graph data, and storage behavior
- the LLM interprets those facts and produces recommendations

Do not move process math into prompts or LLM nodes when the logic can be implemented deterministically in `src/processiq/analysis/`.

### 3. Keep prompts in template files

Prompts live in `src/processiq/prompts/*.j2`.

- Do not add large inline prompt strings to Python modules.
- If behavior changes because of instruction wording, make the change in the template and add or update tests where practical.
- If you add a new prompt, keep the name aligned with the task and update any relevant docs.

### 4. Keep Python and TypeScript schemas aligned

There is no generated client or generated type layer.

- Python request/response shapes live in `api/schemas.py` and `src/processiq/models/`.
- Frontend mirrors live in `frontend/lib/types.ts`.

If you change a field in one side, update the other side in the same PR.

### 5. Be explicit about persistence behavior

The current persistence stack is a mix of:

- SQLite records
- LangGraph checkpoints
- ChromaDB embeddings
- an in-memory session cache for graph/CSV export

When changing storage behavior, document exactly what is durable, what is cached, and what deletion paths actually remove.

## Repository Conventions

- Use `logger = logging.getLogger(__name__)` in Python modules that need logging.
- Prefer specific exceptions from `src/processiq/exceptions.py` over bare `Exception`.
- Keep prompt/template, backend, and frontend terminology consistent.
- Delete dead code rather than commenting it out.
- Update docs when behavior changes in setup, APIs, persistence, deployment, or AI behavior.

## Documentation Expectations

For user-visible or architecture-significant changes, update the relevant docs in the same PR:

- `README.md` for setup, scope, and top-level behavior
- `docs/backend.md` for API contract changes
- `docs/frontend.md` for UI architecture changes
- `docs/ai-analysis-design.md` for prompt, memory, confidence, or orchestration changes
- `docs/deployment.md` for environment variable or runtime changes
- `docs/decisions/README.md` and a new ADR when the change is architectural
- `CHANGELOG.md` for notable user-facing or architecture-level changes

## Adding or Changing Investigation Tools

The extension point for deeper post-analysis reasoning is `src/processiq/agent/tools.py`.

If you add a tool:

1. Add the tool function and its docstring.
2. Register it in `INVESTIGATION_TOOLS`.
3. Update `investigation_system.j2` so the model knows when to use it.
4. Add tests under `tests/unit/test_agent/`.
5. Update [docs/decisions/0005-investigation-loop-design.md](docs/decisions/0005-investigation-loop-design.md) if the tool changes the role of the loop.

## Pull Requests

Please keep PRs focused and reviewable.

Recommended checklist:

1. Explain the problem being solved, not just the implementation.
2. Include relevant screenshots or short recordings for UI changes.
3. Run the checks that match your change surface.
4. Update docs and changelog entries when behavior changes.
5. Call out any follow-up work or known limitations explicitly.

## Code of Conduct

By participating in this project, you agree to follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

By contributing, you agree that your contributions will be licensed under the MIT License.
