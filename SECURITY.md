# Security Policy

## Reporting a Vulnerability

Please do not open public GitHub issues for security vulnerabilities.

Report security concerns privately to the maintainers.

Include:

- a description of the issue
- steps to reproduce
- impact assessment
- any suggested mitigation, if available

TODO: publish a dedicated security contact address so reporters have a stable private channel.

## Supported Deployment Posture

The current repository is best treated as:

- a local development project
- an internal demo or portfolio deployment
- a trusted-environment single-tenant app

It is not yet a production-ready multi-tenant SaaS baseline because it does not include authentication, encrypted-at-rest persistence, or full user-data purge behavior.

## What The System Stores

### SQLite: `data/processiq.db`

The backend stores:

- business profiles
- analysis session summaries and feedback
- LangGraph checkpoints

### ChromaDB: `.chroma/`

The backend stores:

- vector embeddings and metadata for prior analyses used in semantic retrieval

### Browser local storage

The frontend stores:

- a generated UUID used as the current user identifier

## What The System Does Not Store

- raw uploaded files from the ingestion flow
- frontend-visible API keys
- user authentication secrets, because no auth system exists

Uploaded files are parsed in memory and passed through extraction; the ingestion path does not intentionally persist the raw file bytes to disk.

## Data Deletion

`DELETE /profile/{user_id}` deletes all stored data for a user:

- SQLite profile rows
- SQLite analysis-session rows
- ChromaDB embeddings for that user
- LangGraph checkpoint rows for all of that user's threads

## Runtime Security Assumptions

### No authentication

There is no login or token-based access control layer. Anyone who can reach the API can call it.

### UUID identity is not a security boundary

User state is keyed to a UUID in browser local storage. That is a convenience mechanism, not an authorization model.

### Local disk persistence

SQLite and ChromaDB data are stored on local disk. The repository does not implement encryption at rest.

### CORS is not access control

`ALLOWED_ORIGIN` limits browser cross-origin requests, but it does not prevent direct API access by other clients.

## Input Validation and Abuse Controls

The FastAPI layer currently enforces:

- `POST /analyze`: max 5 requests/minute per IP
- `POST /extract`: max 30 requests/minute per IP
- `POST /extract-file`: max 5 requests/minute per IP
- `POST /continue`: max 30 requests/minute per IP
- `POST /feedback/{session_id}`: max 30 requests/minute per IP
- `POST /export/pdf`: max 10 requests/minute per IP
- `PUT /profile/{user_id}`: max 10 requests/minute per IP
- `DELETE /profile/{user_id}`: max 5 requests/minute per IP

Other request validation includes:

- `/extract` text capped at 10,000 characters
- `/continue` text capped at 10,000 characters
- `/analyze` `process.description` capped at 5,000 characters
- file upload cap of 50 MB
- explicit upload extension whitelist

When document ingestion is enabled, supported upload types include:

- `.csv`
- `.xlsx`
- `.xls`
- `.pdf`
- `.docx`
- `.doc`
- `.pptx`
- `.ppt`
- `.html`
- `.htm`
- `.png`
- `.jpg`
- `.jpeg`
- `.tiff`
- `.bmp`

## LLM and Observability Exposure

### LLM providers

Process descriptions, extracted text, constraints, and prior-context summaries may be sent to OpenAI or Anthropic depending on configuration.

### Ollama

Ollama is supported for analysis calls, but extraction is not yet fully local. If a user selects `ollama` during extraction, the extraction pipeline currently falls back to OpenAI-compatible extraction logic.

### LangSmith

If tracing is enabled, prompts, model inputs, and outputs may be sent to LangSmith.

Review:

- `LANGSMITH_TRACING`
- `LANGSMITH_API_KEY`
- `LANGSMITH_ENDPOINT`

before enabling tracing in environments that handle sensitive business data.

## Recommended Hardening Before Public Exposure

- Add authentication and authorization.
- Add encrypted-at-rest storage or encrypted volumes for SQLite and ChromaDB.
- Move persistence to managed shared infrastructure for multi-instance deploys.
- Review provider retention settings for any hosted LLM or tracing service.

## Related Documents

- [README.md](README.md)
- [docs/deployment.md](docs/deployment.md)
- [docs/responsible-ai.md](docs/responsible-ai.md)
- [docs/system-card.md](docs/system-card.md)
