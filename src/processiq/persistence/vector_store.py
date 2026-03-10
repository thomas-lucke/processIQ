"""ChromaDB vector store for semantic retrieval of past analyses.

Provider-aware embeddings: uses OpenAI, Ollama, or a local fallback
depending on the configured LLM provider. All ChromaDB operations are
wrapped in try/except — RAG is an enhancement, never a hard dependency.
"""

import logging
from datetime import UTC, datetime
from typing import Any

from processiq.config import settings
from processiq.models.memory import AnalysisMemory, BusinessProfile, SimilarAnalysis
from processiq.models.process import ProcessData

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "analysis_sessions"
_client = None


def _get_client() -> Any:
    """Lazy-init ChromaDB client."""
    global _client
    if _client is not None:
        return _client
    try:
        import chromadb

        _client = chromadb.PersistentClient(path=settings.chroma_persist_directory)
        logger.info(
            "ChromaDB client initialized at %s", settings.chroma_persist_directory
        )
        return _client
    except Exception:
        logger.warning("ChromaDB unavailable — RAG features disabled", exc_info=True)
        return None


def _get_embedding_function() -> Any:
    """Get ChromaDB-compatible embedding function based on configured provider."""
    provider = settings.llm_provider

    try:
        if provider == "openai" and settings.openai_api_key.get_secret_value():
            from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

            return OpenAIEmbeddingFunction(
                api_key=settings.openai_api_key.get_secret_value(),
                model_name="text-embedding-3-small",
            )

        if provider == "ollama":
            from chromadb.utils.embedding_functions import OpenAIEmbeddingFunction

            return OpenAIEmbeddingFunction(
                api_key="ollama",
                api_base=f"{settings.ollama_base_url}/v1",
                model_name="nomic-embed-text",
            )
    except Exception:
        logger.warning(
            "Failed to create %s embedding function, using default",
            provider,
            exc_info=True,
        )

    # Fallback: ChromaDB default (all-MiniLM-L6-v2, local, no API key)
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    return DefaultEmbeddingFunction()


def _get_collection() -> Any:
    client = _get_client()
    if client is None:
        return None
    return client.get_or_create_collection(
        name=_COLLECTION_NAME,
        embedding_function=_get_embedding_function(),
    )


def _build_embedding_text(
    memory: AnalysisMemory, profile: BusinessProfile | None
) -> str:
    """Construct structured text for embedding.

    Ordered from most to least semantically distinctive:
    - process_summary: LLM's own characterisation (richest signal)
    - issue_descriptions: full reasoning, not just titles
    - recommendation descriptions: what was actually suggested
    - step names, bottleneck/recommendation titles: structural labels
    - industry: scoping signal

    Excludes: raw conversation, confidence notes, investigation findings
    (too noisy or too session-specific to generalise across analyses).
    """
    parts = [f"Process: {memory.process_name}"]

    if memory.process_summary:
        parts.append(f"Summary: {memory.process_summary}")

    if profile and profile.industry:
        parts.append(f"Industry: {profile.industry.value}")

    if memory.step_names:
        parts.append(f"Steps: {', '.join(memory.step_names)}")

    if memory.bottlenecks_found:
        parts.append(f"Bottlenecks: {', '.join(memory.bottlenecks_found)}")

    if memory.issue_descriptions:
        parts.append(f"Issue details: {' | '.join(memory.issue_descriptions)}")

    if memory.suggestions_offered:
        parts.append(f"Recommendations: {', '.join(memory.suggestions_offered)}")

    # Include recommendation descriptions from recommendations_full
    rec_descriptions = [
        r["description"] for r in memory.recommendations_full if r.get("description")
    ]
    if rec_descriptions:
        parts.append(f"Recommendation details: {' | '.join(rec_descriptions)}")

    return "\n".join(parts)


def embed_analysis(
    memory: AnalysisMemory, profile: BusinessProfile | None = None
) -> None:
    """Embed and store an analysis session. Called after analysis completes."""
    try:
        collection = _get_collection()
        if collection is None:
            return

        text = _build_embedding_text(memory, profile)
        metadata = {
            "user_id": memory.user_id,
            "process_name": memory.process_name,
            "timestamp": memory.timestamp.isoformat(),
            "bottlenecks": ",".join(memory.bottlenecks_found),
            "recommendations": ",".join(memory.suggestions_offered),
            "rejected_recs": ",".join(memory.suggestions_rejected),
            "rejection_reasons": ",".join(memory.rejection_reasons),
        }

        collection.upsert(
            ids=[memory.id],
            documents=[text],
            metadatas=[metadata],
        )
        logger.info(
            "Embedded analysis %s for user %s", memory.id[:8], memory.user_id[:8]
        )
    except Exception:
        logger.warning("Failed to embed analysis %s", memory.id[:8], exc_info=True)


def find_similar_analyses(
    process_data: ProcessData,
    profile: BusinessProfile | None = None,
    user_id: str | None = None,
    top_k: int = 3,
) -> list[SimilarAnalysis]:
    """Find semantically similar past analyses.

    Query is constructed from current process data, not the raw user message.
    If user_id is provided, results are scoped to that user (privacy boundary).
    """
    try:
        collection = _get_collection()
        if collection is None:
            return []

        # Build query from process data
        query_parts = [f"Process: {process_data.name}"]
        if profile and profile.industry:
            query_parts.append(f"Industry: {profile.industry.value}")
        step_names = [s.step_name for s in process_data.steps]
        if step_names:
            query_parts.append(f"Steps: {', '.join(step_names)}")
        query_text = "\n".join(query_parts)

        where_filter = {"user_id": user_id} if user_id else None

        results = collection.query(
            query_texts=[query_text],
            n_results=top_k,
            where=where_filter,
        )

        if not results or not results["ids"] or not results["ids"][0]:
            return []

        similar: list[SimilarAnalysis] = []
        ids = results["ids"][0]
        distances = (
            results["distances"][0] if results["distances"] else [0.0] * len(ids)
        )
        metadatas = results["metadatas"][0] if results["metadatas"] else [{}] * len(ids)

        for doc_id, distance, meta in zip(ids, distances, metadatas, strict=False):
            # ChromaDB returns L2 distance; convert to similarity (lower = more similar)
            similarity = max(0.0, 1.0 - distance / 2.0)
            similar.append(
                SimilarAnalysis(
                    session_id=doc_id,
                    process_name=meta.get("process_name", ""),
                    similarity_score=similarity,
                    bottlenecks=meta.get("bottlenecks", "").split(",")
                    if meta.get("bottlenecks")
                    else [],
                    recommendations=meta.get("recommendations", "").split(",")
                    if meta.get("recommendations")
                    else [],
                    rejected_recs=meta.get("rejected_recs", "").split(",")
                    if meta.get("rejected_recs")
                    else [],
                    rejection_reasons=meta.get("rejection_reasons", "").split(",")
                    if meta.get("rejection_reasons")
                    else [],
                    timestamp=datetime.fromisoformat(
                        meta.get("timestamp", datetime.now(UTC).isoformat())
                    ),
                )
            )

        logger.info(
            "Found %d similar analyses for process '%s'",
            len(similar),
            process_data.name,
        )
        return similar

    except Exception:
        logger.warning("ChromaDB query failed — continuing without RAG", exc_info=True)
        return []
