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
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from api.schemas import (
    AnalysisSessionSummary,
    AnalyzeRequest,
    AnalyzeResponse,
    ContinueRequest,
    ContinueResponse,
    ExportPdfRequest,
    ExtractResponse,
    ExtractTextRequest,
    FeedbackRequest,
    FeedbackResponse,
    ProfileResponse,
    RecommendationSummary,
    SessionsResponse,
)
from processiq.agent import interface
from processiq.agent.interface import SUPPORTED_EXTENSIONS
from processiq.analysis.visualization import GraphSchema, build_graph_schema
from processiq.config import settings
from processiq.export.csv_export import export_insight_csv
from processiq.export.pdf_export import render_proposal_pdf
from processiq.logging_config import setup_logging
from processiq.models import BusinessProfile
from processiq.persistence.analysis_store import (
    delete_user_sessions,
    get_user_sessions,
    update_session_feedback,
)
from processiq.persistence.db import close_connection
from processiq.persistence.profile_store import (
    delete_profile,
    load_profile,
    save_profile,
    update_rejected_approaches,
)

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


@asynccontextmanager
async def lifespan(app: FastAPI):  # type: ignore[type-arg]
    yield
    close_connection()


app = FastAPI(
    title="ProcessIQ API",
    description="AI-powered process optimization advisor",
    version="0.1.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[_allowed_origin],
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type", "X-User-Id"],
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

    if body.llm_provider == "ollama" and not settings.ollama_enabled:
        raise HTTPException(
            status_code=400,
            detail="Ollama is not available in this environment. Please select a different provider.",
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

    context_sources = (
        result.analysis_insight.context_sources if result.analysis_insight else []
    )

    # Build graph schema inline so the frontend gets it in one round-trip.
    # Only built when we have a successful analysis with process data.
    graph_schema = None
    if result.process_data and not result.is_error:
        try:
            graph_schema = build_graph_schema(
                process_data=result.process_data,
                analysis_insight=result.analysis_insight,
            )
        except Exception:
            logger.exception("Failed to build graph schema for /analyze response")

    return AnalyzeResponse(
        message=result.message,
        analysis_insight=result.analysis_insight,
        graph_schema=graph_schema,
        thread_id=result.thread_id,
        is_error=result.is_error,
        error_code=result.error_code,
        reasoning_trace=result.reasoning_trace,
        context_sources=context_sources,
    )


@app.post("/extract", response_model=ExtractResponse)
@limiter.limit("30/minute")
async def extract_text(request: Request, body: ExtractTextRequest) -> ExtractResponse:
    logger.info("POST /extract")

    if len(body.text) > 10_000:
        raise HTTPException(status_code=422, detail="text exceeds 10 000 characters")

    if body.llm_provider == "ollama" and not settings.ollama_enabled:
        raise HTTPException(
            status_code=400,
            detail="Ollama is not available in this environment. Please select a different provider.",
        )

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

    if llm_provider == "ollama" and not settings.ollama_enabled:
        raise HTTPException(
            status_code=400,
            detail="Ollama is not available in this environment. Please select a different provider.",
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
            detail=f"No analysis found for thread '{thread_id}'. Run /analyze first.",
        )

    return build_graph_schema(
        process_data=session["process"],
        analysis_insight=session.get("insight"),
    )


# ---------------------------------------------------------------------------
# Profile endpoints
# ---------------------------------------------------------------------------


@app.get("/profile/{user_id}", response_model=ProfileResponse)
async def get_profile(user_id: str) -> ProfileResponse:
    logger.info("GET /profile/%s", user_id[:8])
    profile = load_profile(user_id)
    return ProfileResponse(profile=profile)


@app.put("/profile/{user_id}", response_model=ProfileResponse)
@limiter.limit("10/minute")
async def put_profile(
    request: Request, user_id: str, body: BusinessProfile
) -> ProfileResponse:
    logger.info("PUT /profile/%s", user_id[:8])
    save_profile(user_id, body)
    return ProfileResponse(profile=body)


@app.delete("/profile/{user_id}", status_code=204)
@limiter.limit("5/minute")
async def delete_user_data(request: Request, user_id: str) -> None:
    """Delete all stored data for a user — profile and analysis history.

    Called when the user chooses to reset their data from the settings panel.
    The frontend clears the localStorage UUID immediately after this returns.
    """
    logger.info("DELETE /profile/%s — resetting all user data", user_id[:8])
    delete_user_sessions(user_id)
    delete_profile(user_id)


# ---------------------------------------------------------------------------
# Sessions endpoint (Library view)
# ---------------------------------------------------------------------------


@app.get("/sessions/{user_id}", response_model=SessionsResponse)
async def get_sessions(user_id: str) -> SessionsResponse:
    """Return all past analysis sessions for a user, newest first."""
    logger.info("GET /sessions/%s", user_id[:8])
    memories = get_user_sessions(user_id, limit=50)
    summaries = [
        AnalysisSessionSummary(
            session_id=m.id,
            process_name=m.process_name,
            process_description=m.process_description,
            industry=m.industry,
            timestamp=m.timestamp.isoformat(),
            step_names=m.step_names,
            bottlenecks_found=m.bottlenecks_found,
            suggestions_offered=m.suggestions_offered,
            suggestions_accepted=m.suggestions_accepted,
            suggestions_rejected=m.suggestions_rejected,
            recommendations_full=[
                RecommendationSummary(**r) for r in m.recommendations_full
            ],
        )
        for m in memories
    ]
    return SessionsResponse(sessions=summaries)


# ---------------------------------------------------------------------------
# Feedback endpoint
# ---------------------------------------------------------------------------


@app.post("/feedback/{session_id}", response_model=FeedbackResponse)
@limiter.limit("30/minute")
async def post_feedback(
    request: Request, session_id: str, body: FeedbackRequest
) -> FeedbackResponse:
    logger.info(
        "POST /feedback/%s — accepted=%d, rejected=%d",
        session_id[:8],
        len(body.accepted),
        len(body.rejected),
    )
    update_session_feedback(
        session_id=session_id,
        accepted=body.accepted,
        rejected=body.rejected,
        reasons=body.reasons,
    )
    if body.rejected and body.user_id:
        update_rejected_approaches(body.user_id, body.rejected)
    return FeedbackResponse()


# ---------------------------------------------------------------------------
# Export endpoints
# ---------------------------------------------------------------------------


@app.post("/export/pdf")
@limiter.limit("10/minute")
async def export_pdf(request: Request, body: ExportPdfRequest) -> Response:
    """Render the improvement proposal as a PDF and return the bytes."""
    logger.info(
        "POST /export/pdf — process=%s",
        body.process_data.name if body.process_data else "unknown",
    )
    pdf_bytes = render_proposal_pdf(
        insight=body.insight,
        process_data=body.process_data,
    )
    slug = ""
    if body.process_data:
        import re

        slug = re.sub(
            r"[^a-z0-9-]", "", body.process_data.name.lower().replace(" ", "-")
        )
    filename = (
        f"{slug}-improvement-proposal.pdf" if slug else "improvement-proposal.pdf"
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/export/csv/{thread_id}")
async def export_csv(thread_id: str) -> Response:
    """Export the analysis for a session as CSV."""
    logger.info("GET /export/csv/%s", thread_id[:8])
    session = _session_store.get(thread_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail=f"No analysis found for thread '{thread_id}'. Run /analyze first.",
        )
    insight = session.get("insight")
    if insight is None:
        raise HTTPException(status_code=404, detail="No analysis insight in session.")

    process = session.get("process")
    slug = ""
    if process:
        import re

        slug = re.sub(r"[^a-z0-9-]", "", process.name.lower().replace(" ", "-"))
    filename = f"{slug}-analysis.csv" if slug else "analysis.csv"

    csv_bytes = export_insight_csv(insight)
    return Response(
        content=csv_bytes,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
