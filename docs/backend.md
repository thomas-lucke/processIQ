# Backend

The backend is a FastAPI application in `api/main.py` backed by the ProcessIQ Python package under `src/processiq/`.

This document covers:

- how the HTTP layer is structured
- what each endpoint actually does
- where current docs needed to be corrected to match implementation

## Design Goals

The backend is designed as a thin HTTP facade over a richer Python application layer.

Responsibilities of `api/`:

- parse and validate HTTP requests
- enforce API-specific limits
- shape JSON or binary responses
- expose a stable contract for the frontend

Responsibilities outside `api/`:

- extraction logic
- analysis orchestration
- LangGraph execution
- storage and retrieval behavior
- process math and visualization DTO construction

## Package Layout

```text
api/main.py       FastAPI app, middleware, handlers
api/schemas.py    HTTP request/response models
```

The API layer delegates into `processiq.agent.interface`.

## Runtime Behavior

### Middleware and request policy

#### CORS

Configured from `ALLOWED_ORIGIN` and defaults to `http://localhost:3000`.

#### Rate limiting

Implemented with `slowapi`, keyed by client IP.

| Endpoint | Limit |
| --- | --- |
| `POST /analyze` | `5/minute` |
| `POST /extract` | `30/minute` |
| `POST /extract-file` | `5/minute` |
| `POST /continue` | `30/minute` |
| `PUT /profile/{user_id}` | `10/minute` |
| `DELETE /profile/{user_id}` | `5/minute` |
| `POST /feedback/{session_id}` | `30/minute` |
| `POST /export/pdf` | `10/minute` |

#### Input limits

- `POST /extract`: text capped at 10,000 characters
- `POST /continue`: `user_message` capped at 10,000 characters
- `POST /analyze`: `process.description` capped at 5,000 characters
- file upload cap: 50 MB

### In-memory session cache

`api/main.py` maintains a small in-memory cache:

```text
thread_id -> { process, insight, created_at }
```

Characteristics:

- TTL: 1 hour
- max entries: 1,000
- eviction runs on successful `/analyze` calls

This cache is separate from LangGraph checkpoint persistence.

It currently backs:

- `GET /graph-schema/{thread_id}`
- `GET /export/csv/{thread_id}`

That means those two endpoints are **not** historical-reporting endpoints. They only work while the relevant thread is still in the in-memory cache.

## Endpoint Reference

### `GET /health`

Returns a small health/config payload:

```json
{
  "status": "ok",
  "demo_mode": false,
  "tracing_enabled": false
}
```

Important correction:
The current implementation does **not** return `document_ingestion_enabled`, even though earlier docs claimed it did.

### `POST /extract`

Extracts or updates `ProcessData` from text.

Request model: `ExtractTextRequest`

Key fields:

- `text`
- `analysis_mode`
- `additional_context`
- `current_process_data`
- `ui_messages`
- `constraints`
- `profile`
- `llm_provider`

Response model: `ExtractResponse`

Behavior:

- returns extracted `process_data`, or
- asks clarifying questions with `needs_input=true`

Important implementation note:
The extraction pipeline only supports OpenAI and Anthropic extraction clients today. If `llm_provider="ollama"` is selected, extraction falls back to OpenAI-compatible extraction logic rather than using a native Ollama extractor.

### `POST /extract-file`

Uploads a file and routes it through spreadsheet parsing or Docling-based document parsing.

Accepted form fields:

- `file`
- `analysis_mode`
- `llm_provider`
- `current_process_data`

Important correction:
Earlier docs described a `context` form field. The current endpoint does not accept one.

Supported file extensions:

- always: `.csv`, `.xlsx`, `.xls`
- when document ingestion is enabled: `.pdf`, `.docx`, `.doc`, `.pptx`, `.ppt`, `.html`, `.htm`, `.png`, `.jpg`, `.jpeg`, `.tiff`, `.bmp`

### `POST /analyze`

Runs the full analysis workflow on confirmed `ProcessData`.

Request model: `AnalyzeRequest`

Important fields:

- `process`
- `constraints`
- `profile`
- `thread_id`
- `user_id`
- `analysis_mode`
- `llm_provider`
- `feedback_history`
- `max_cycles_override`

Response model: `AnalyzeResponse`

Fields returned:

- `message`
- `analysis_insight`
- `graph_schema`
- `thread_id`
- `is_error`
- `error_code`
- `reasoning_trace`
- `context_sources`

Notes:

- `graph_schema` is built inline on the backend and returned with the analysis response.
- the result is also cached in memory for graph and CSV export lookup
- successful analyses are persisted to SQLite and embedded into ChromaDB

### `POST /continue`

Continues a conversation using checkpointed LangGraph state.

Request model: `ContinueRequest`

- `thread_id`
- `user_message`
- `analysis_mode`

Response model: `ContinueResponse`

Important implementation note:
The endpoint exists and is tested, but the current web frontend does not call it. The web UI primarily uses `/extract` and `/analyze`.

### `GET /graph-schema/{thread_id}`

Returns a `GraphSchema` for an active in-memory thread.

Important correction:
The current implementation returns `404` if the thread is not in the session cache. It does **not** return `null` or an empty success response.

### `GET /profile/{user_id}`

Loads a `BusinessProfile` if one exists.

Response model:

```json
{ "profile": { ... } }
```

### `PUT /profile/{user_id}`

Upserts a `BusinessProfile`.

Response model:

```json
{ "profile": { ... } }
```

Important correction:
Earlier docs described a `{ "status": "ok" }` response. The current implementation returns the saved profile wrapper.

### `DELETE /profile/{user_id}`

Deletes all stored data for the user and returns HTTP `204 No Content`.

What is deleted:

- SQLite profile row (`business_profiles`)
- SQLite session rows (`analysis_sessions`)
- ChromaDB embeddings for the user
- LangGraph checkpoints for all of the user's thread IDs

The endpoint fetches thread IDs from `analysis_sessions` before deleting those rows, then passes them to the checkpoint deletion path.

### `GET /sessions/{user_id}`

Returns up to 50 saved session summaries for the Library view.

Response model: `SessionsResponse`

Includes:

- session metadata
- accepted/rejected recommendation history
- a lean recommendation summary list for each session

### `POST /feedback/{session_id}`

Stores recommendation feedback for a session.

Request model:

- `accepted`
- `rejected`
- `reasons`
- `user_id`

If rejected recommendations are present and `user_id` is set, the backend also updates `BusinessProfile.rejected_approaches`.

### `POST /export/pdf`

Generates a PDF report from the current `AnalysisInsight` and optional `ProcessData`.

This endpoint does not depend on the in-memory session cache because the caller supplies the full payload.

### `GET /export/csv/{thread_id}`

Exports a CSV representation of the active cached analysis.

Important constraint:
This works only for threads still present in the in-memory session cache. It is not a historical export endpoint.

## Response and Error Shape

The backend uses a mix of:

- normal HTTP errors for malformed or blocked requests
- response payload flags like `is_error` and `error_code` for application-level failures

Examples:

- `400` for disabled Ollama selection
- `404` for missing graph/export thread IDs
- `413` for oversized uploads
- `415` for unsupported file types
- `422` for schema or size validation failures

Within successful `200` responses, application-level failures are represented with:

- `is_error: true`
- `error_code`
- human-readable `message`

## Persistence-Related Notes

The backend uses three state layers:

1. SQLite for durable structured data
2. ChromaDB for semantic retrieval
3. in-memory session cache for active thread graph/CSV export access

This split is useful, but it is easy to mis-document. If you change persistence behavior, update the docs carefully.

## Known Gaps

- No authentication or tenant isolation
- No streaming API for long-running analysis
- Frontend does not currently use `/continue` or `/graph-schema`
- `GET /export/csv/{thread_id}` exists in the API but is not wired to the frontend UI — CSV ingestion (uploading a CSV file) works, but exporting analysis results as CSV is not yet surfaced

See [docs/deployment.md](deployment.md) and [SECURITY.md](../SECURITY.md).
