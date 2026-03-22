"""User identification without login.

Provides UUID-based user identification for conversation continuity.
User IDs are stored in the browser's localStorage via the Next.js frontend.

Thread IDs combine user ID and conversation ID for unique identification:
    thread_id = f"{user_id}:{conversation_id}"

This allows:
- Multiple conversations per user
- Resume conversations after browser refresh
- No login required (privacy-friendly)
"""

import logging
import uuid
from collections.abc import Callable
from datetime import UTC, datetime

logger = logging.getLogger(__name__)


def generate_user_id() -> str:
    """Generate a new unique user ID.

    Returns:
        UUID string for user identification.
    """
    user_id = str(uuid.uuid4())
    logger.debug("Generated new user ID: %s", user_id[:8])
    return user_id


def generate_conversation_id() -> str:
    """Generate a new unique conversation ID.

    Returns:
        UUID string for conversation identification.
    """
    return str(uuid.uuid4())


def get_thread_id(user_id: str, conversation_id: str | None = None) -> str:
    """Create a thread ID from user ID and conversation ID.

    Thread IDs uniquely identify a conversation thread for checkpointing.
    Format: "{user_id}:{conversation_id}"

    Args:
        user_id: The user's unique identifier.
        conversation_id: Optional conversation ID. If None, generates a new one.

    Returns:
        Combined thread ID string.
    """
    if conversation_id is None:
        conversation_id = generate_conversation_id()
    return f"{user_id}:{conversation_id}"


def parse_thread_id(thread_id: str) -> tuple[str, str]:
    """Parse a thread ID into user ID and conversation ID.

    Args:
        thread_id: Combined thread ID string.

    Returns:
        Tuple of (user_id, conversation_id).

    Raises:
        ValueError: If thread_id format is invalid.
    """
    parts = thread_id.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid thread_id format: {thread_id}")
    return parts[0], parts[1]


def get_user_id(session_state_getter: Callable[[], str | None]) -> str:
    """Get or create user ID from session state.

    This function should be called with a getter function that
    retrieves the user_id from session state (e.g., from the frontend or API layer).

    Args:
        session_state_getter: Function that returns user_id or None.

    Returns:
        User ID string (existing or newly generated).
    """
    existing_id = session_state_getter()
    if existing_id:
        return existing_id
    return generate_user_id()


def create_thread_metadata(
    user_id: str,
    conversation_id: str,
    process_name: str | None = None,
) -> dict[str, str | None]:
    """Create metadata for a conversation thread.

    This metadata can be stored alongside the thread for
    displaying conversation history to the user.

    Args:
        user_id: The user's unique identifier.
        conversation_id: The conversation's unique identifier.
        process_name: Optional name of the process being analyzed.

    Returns:
        Dict with thread metadata.
    """
    return {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "thread_id": f"{user_id}:{conversation_id}",
        "process_name": process_name,
        "created_at": datetime.now(UTC).isoformat(),
    }
