"""ProcessIQ FastAPI backend.

Thin HTTP layer in front of processiq.agent.interface.
No business logic lives here — only routing, request/response translation,
and CORS configuration.

Run locally:
    uvicorn api.main:app --reload
    # Docs: http://localhost:8000/docs
"""

import logging
import os
import time
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api.schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ContinueRequest,
    ContinueResponse,
    ExtractResponse,
    ExtractTextRequest,
)
from processiq.agent import interface
from processiq.analysis.visualization import GraphSchema, build_graph_schema
from processiq.ingestion.docling_parser import SUPPORTED_EXTENSIONS
from processiq.logging_config import setup_logging

setup_logging()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File upload limits
# ---------------------------------------------------------------------------

MAX_FILE_BYTES = 50 * 1024 * 1024  # 50 MB — matches any upstream proxy limit

# ---------------------------------------------------------------------------
# Rate limiter — keyed by client IP
# ---------------------------------------------------------------------------

limiter = Limiter(key_func=get_remote_address)

# ---------------------------------------------------------------------------
# CORS — read allowed origin from env; default to localhost for development.
# Set ALLOWED_ORIGIN to your Vercel URL in production.
# ---------------------------------------------------------------------------

_allowed_origin = os.environ.get("ALLOWED_ORIGIN", "http://localhost:3000")

# ---------------------------------------------------------------------------
# Session store: thread_id -> {process, insight, created_at}
# Bounded by MAX_SESSIONS; entries expire after SESSION_TTL_SECONDS.
# Replace with SQLite persistence when implementing Task 3.
# ---------------------------------------------------------------------------

SESSION_TTL_SECONDS = 3600  # 1 hour
MAX_SESSIONS = 1000

_session_store: dict[str, dict[str, Any]] = {}


def _evict_sessions() -> None:
    """Remove expired sessions and enforce the size cap."""
    now = time.time()
    expired = [
        k
        for k, v in _session_store.items()
        if now - v["created_at"] > SESSION_TTL_SECONDS
    ]
    for k in expired:
        del _session_store[k]

    # If still over cap after TTL eviction, drop oldest entries
    if len(_session_store) >= MAX_SESSIONS:
        sorted_keys = sorted(
            _session_store, key=lambda k: _session_store[k]["created_at"]
        )
        for k in sorted_keys[: len(_session_store) - MAX_SESSIONS + 1]:
            del _session_store[k]


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="ProcessIQ API",
    description="AI-powered process optimization advisor",
    version="0.1.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[_allowed_origin],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze", response_model=AnalyzeResponse)
@limiter.limit("5/minute")
async def analyze(request: Request, body: AnalyzeRequest) -> AnalyzeResponse:
    logger.info("POST /analyze — process=%s", body.process.name)

    # Cap free-text fields to prevent prompt-stuffing / token abuse
    if body.process.description and len(body.process.description) > 5000:
        raise HTTPException(
            status_code=422, detail="process.description exceeds 5000 characters"
        )

    result = interface.analyze_process(
        process=body.process,
        constraints=body.constraints,
        profile=body.profile,
        thread_id=body.thread_id,
        user_id=body.user_id,
        analysis_mode=body.analysis_mode,
        llm_provider=body.llm_provider,
        feedback_history=body.feedback_history,
        max_cycles_override=body.max_cycles_override,
    )

    if result.thread_id:
        _evict_sessions()
        _session_store[result.thread_id] = {
            "process": body.process,
            "insight": result.analysis_insight,
            "created_at": time.time(),
        }

    return AnalyzeResponse(
        message=result.message,
        analysis_insight=result.analysis_insight,
        thread_id=result.thread_id,
        is_error=result.is_error,
        error_code=result.error_code,
        reasoning_trace=result.reasoning_trace,
    )


@app.post("/extract", response_model=ExtractResponse)
@limiter.limit("30/minute")
async def extract_text(request: Request, body: ExtractTextRequest) -> ExtractResponse:
    logger.info("POST /extract")

    if len(body.text) > 10_000:
        raise HTTPException(status_code=422, detail="text exceeds 10 000 characters")

    result = interface.extract_from_text(
        user_message=body.text,
        analysis_mode=body.analysis_mode,
        additional_context=body.additional_context,
        current_process_data=body.current_process_data,
        ui_messages=body.ui_messages,
        constraints=body.constraints,
        profile=body.profile,
        llm_provider=body.llm_provider,
    )

    return ExtractResponse(
        message=result.message,
        process_data=result.process_data,
        needs_input=result.needs_input,
        suggested_questions=result.suggested_questions,
        improvement_suggestions=result.improvement_suggestions,
        is_error=result.is_error,
        error_code=result.error_code,
    )


@app.post("/extract-file", response_model=ExtractResponse)
@limiter.limit("5/minute")
async def extract_file(
    request: Request,
    file: Annotated[UploadFile, File()],
    analysis_mode: Annotated[str | None, Form()] = None,
    llm_provider: Annotated[str | None, Form()] = None,
) -> ExtractResponse:
    logger.info("POST /extract-file — filename=%s", file.filename)

    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    # Extension whitelist — reuses the set already defined in docling_parser.py
    ext = Path(file.filename).suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type '{ext}'. "
            f"Allowed: {', '.join(sorted(SUPPORTED_EXTENSIONS))}",
        )

    # File size check — enforced in the backend regardless of proxy limits
    if file.size is not None and file.size > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_FILE_BYTES // (1024 * 1024)} MB.",
        )

    file_bytes = await file.read()

    # Secondary size check for cases where file.size was not set by the client
    if len(file_bytes) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large. Maximum size is {MAX_FILE_BYTES // (1024 * 1024)} MB.",
        )

    result = interface.extract_from_file(
        file_bytes=file_bytes,
        filename=file.filename,
        analysis_mode=analysis_mode,
        llm_provider=llm_provider,  # type: ignore[arg-type]
    )

    return ExtractResponse(
        message=result.message,
        process_data=result.process_data,
        needs_input=result.needs_input,
        suggested_questions=result.suggested_questions,
        improvement_suggestions=result.improvement_suggestions,
        is_error=result.is_error,
        error_code=result.error_code,
    )


@app.post("/continue", response_model=ContinueResponse)
@limiter.limit("30/minute")
async def continue_conversation(
    request: Request, body: ContinueRequest
) -> ContinueResponse:
    logger.info("POST /continue — thread=%s", body.thread_id)

    if len(body.user_message) > 10_000:
        raise HTTPException(
            status_code=422, detail="user_message exceeds 10 000 characters"
        )

    result = interface.continue_conversation(
        thread_id=body.thread_id,
        user_message=body.user_message,
        analysis_mode=body.analysis_mode,
    )

    return ContinueResponse(
        message=result.message,
        process_data=result.process_data,
        analysis_insight=result.analysis_insight,
        thread_id=result.thread_id,
        needs_input=result.needs_input,
        is_error=result.is_error,
        error_code=result.error_code,
    )


@app.get("/graph-schema/{thread_id}", response_model=GraphSchema)
async def graph_schema(thread_id: str) -> GraphSchema:
    logger.info("GET /graph-schema/%s", thread_id)

    session = _session_store.get(thread_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"No analysis found for thread '{thread_id}'. "
            "Run /analyze first.",
        )

    return build_graph_schema(
        process_data=session["process"],
        analysis_insight=session.get("insight"),
    )
