"""Tests for processiq.agent.context."""

from unittest.mock import MagicMock

from processiq.agent.context import (
    MAX_MESSAGE_CHARS,
    MAX_TABLE_ROWS,
    MIN_SUBSTANTIVE_LENGTH,
    build_conversation_context,
    filter_substantive_messages,
    serialize_process_data,
)
from processiq.models import ProcessData, ProcessStep

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_msg(
    role: str = "user", content: str = "hello world", msg_type: str | None = None
):
    """Create a mock UI message."""
    msg = MagicMock()
    msg.role = role
    msg.content = content
    msg.type = msg_type
    return msg


def _make_enum_msg(
    role_value: str = "user",
    content: str = "hello world",
    type_value: str | None = None,
):
    """Create a mock UI message with enum-style role/type attributes."""
    msg = MagicMock()
    role_enum = MagicMock()
    role_enum.value = role_value
    msg.role = role_enum
    msg.content = content
    if type_value is not None:
        type_enum = MagicMock()
        type_enum.value = type_value
        msg.type = type_enum
    else:
        msg.type = None
    return msg


# ---------------------------------------------------------------------------
# serialize_process_data
# ---------------------------------------------------------------------------


class TestSerializeProcessData:
    def test_none_returns_empty_string(self):
        assert serialize_process_data(None) == ""

    def test_includes_process_name(self, simple_process):
        result = serialize_process_data(simple_process)
        assert "Simple Process" in result

    def test_includes_step_names(self, simple_process):
        result = serialize_process_data(simple_process)
        assert "Step A" in result
        assert "Step B" in result
        assert "Step C" in result

    def test_includes_time_values(self, simple_process):
        result = serialize_process_data(simple_process)
        assert "1.0" in result
        assert "2.0" in result

    def test_includes_cost_values(self, simple_process):
        result = serialize_process_data(simple_process)
        assert "50.00" in result

    def test_includes_totals(self, simple_process):
        result = serialize_process_data(simple_process)
        assert "Total time" in result
        assert "Total cost" in result

    def test_table_format_has_headers(self, simple_process):
        result = serialize_process_data(simple_process)
        assert "Step" in result
        assert "Time (hrs)" in result

    def test_no_cost_shows_dash(self):
        """Steps with no cost_per_instance (0 / falsy) show a dash."""
        data = ProcessData(
            name="P",
            steps=[
                ProcessStep(step_name="S", average_time_hours=1.0, resources_needed=1)
            ],
        )
        result = serialize_process_data(data)
        # cost_per_instance=0.0 is falsy → dash in cost column
        assert "| - |" in result or " - " in result

    def test_truncates_at_max_rows(self):
        steps = [
            ProcessStep(
                step_name=f"Step {i}", average_time_hours=1.0, resources_needed=1
            )
            for i in range(MAX_TABLE_ROWS + 5)
        ]
        data = ProcessData(name="Big", steps=steps)
        result = serialize_process_data(data)
        assert "more steps" in result

    def test_exactly_max_rows_no_truncation(self):
        steps = [
            ProcessStep(
                step_name=f"Step {i}", average_time_hours=1.0, resources_needed=1
            )
            for i in range(MAX_TABLE_ROWS)
        ]
        data = ProcessData(name="Exact", steps=steps)
        result = serialize_process_data(data)
        assert "more steps" not in result

    def test_dependencies_shown(self, simple_process):
        result = serialize_process_data(simple_process)
        # Step B depends on Step A
        assert "Step A" in result

    def test_group_shown_when_set(self):
        steps = [
            ProcessStep(
                step_name="Phone Order",
                average_time_hours=0.5,
                resources_needed=1,
                group_id="receive_order",
                group_type="alternative",
            ),
        ]
        data = ProcessData(name="Grouped", steps=steps)
        result = serialize_process_data(data)
        assert "receive_order" in result


# ---------------------------------------------------------------------------
# filter_substantive_messages
# ---------------------------------------------------------------------------


class TestFilterSubstantiveMessages:
    def test_empty_list_returns_empty(self):
        assert filter_substantive_messages([]) == []

    def test_non_user_messages_filtered(self):
        msgs = [_make_msg(role="agent", content="Here is my analysis")]
        assert filter_substantive_messages(msgs) == []

    def test_user_messages_kept(self):
        msg = _make_msg(role="user", content="This is a detailed user message")
        result = filter_substantive_messages([msg])
        assert len(result) == 1

    def test_file_type_messages_filtered(self):
        msg = _make_msg(role="user", content="Uploaded process.csv", msg_type="file")
        assert filter_substantive_messages([msg]) == []

    def test_status_type_messages_filtered(self):
        msg = _make_msg(
            role="user", content="Analyzing your process...", msg_type="status"
        )
        assert filter_substantive_messages([msg]) == []

    def test_short_messages_filtered(self):
        # Below MIN_SUBSTANTIVE_LENGTH
        msg = _make_msg(role="user", content="ok")
        assert filter_substantive_messages([msg]) == []

    def test_exactly_min_length_passes(self):
        content = "x" * MIN_SUBSTANTIVE_LENGTH
        msg = _make_msg(role="user", content=content)
        result = filter_substantive_messages([msg])
        assert len(result) == 1

    def test_enum_role_handled(self):
        msg = _make_enum_msg(
            role_value="user", content="This is a substantive message here"
        )
        result = filter_substantive_messages([msg])
        assert len(result) == 1

    def test_enum_role_agent_filtered(self):
        msg = _make_enum_msg(
            role_value="agent", content="Here is my detailed analysis output"
        )
        assert filter_substantive_messages([msg]) == []

    def test_enum_type_file_filtered(self):
        msg = _make_enum_msg(
            role_value="user",
            content="Uploaded my process file here",
            type_value="file",
        )
        assert filter_substantive_messages([msg]) == []

    def test_missing_role_filtered(self):
        msg = MagicMock()
        del msg.role  # Simulate missing attribute
        msg.role = None
        msg.content = "Some content here but role is missing"
        assert filter_substantive_messages([msg]) == []

    def test_mixed_messages(self):
        msgs = [
            _make_msg(
                role="user", content="This is a substantive message about the process"
            ),
            _make_msg(role="agent", content="Here is the analysis"),
            _make_msg(role="user", content="ok"),  # too short
            _make_msg(
                role="user", content="Another substantive message about workflow steps"
            ),
        ]
        result = filter_substantive_messages(msgs)
        assert len(result) == 2


# ---------------------------------------------------------------------------
# build_conversation_context
# ---------------------------------------------------------------------------


class TestBuildConversationContext:
    def test_no_data_no_messages_returns_empty(self):
        assert build_conversation_context(None, []) == ""

    def test_includes_process_data(self, simple_process):
        result = build_conversation_context(simple_process, [])
        assert "Simple Process" in result
        assert "Current Process Data" in result

    def test_includes_recent_messages(self, simple_process):
        msgs = [
            _make_msg(content="This is first message about process mapping workflow"),
            _make_msg(content="Then I want to optimize the approval step here"),
            _make_msg(content="Current message right here"),
        ]
        result = build_conversation_context(simple_process, msgs)
        # Should include the penultimate message, not the last one (current input)
        assert "Recent Conversation" in result

    def test_excludes_last_message_as_current_input(self, simple_process):
        msgs = [
            _make_msg(content="Earlier context message about the process flow"),
            _make_msg(content="THIS IS THE CURRENT INPUT MESSAGE DO NOT INCLUDE"),
        ]
        result = build_conversation_context(simple_process, msgs)
        assert "THIS IS THE CURRENT INPUT MESSAGE" not in result

    def test_no_process_data_only_messages(self):
        msgs = [
            _make_msg(content="Earlier substantive message about the workflow process"),
            _make_msg(content="Current message that should not be included"),
        ]
        result = build_conversation_context(None, msgs)
        # Process data section absent, messages might be included
        assert "Current Process Data" not in result

    def test_limits_message_history(self, simple_process):
        # Create many messages
        msgs = [
            _make_msg(
                content=f"Substantive message number {i} about the workflow steps"
            )
            for i in range(20)
        ]
        result = build_conversation_context(simple_process, msgs, max_messages=2)
        # Should only show up to max_messages in the context
        assert result.count("User:") <= 2

    def test_truncates_very_long_messages(self, simple_process):
        long_content = "x" * (MAX_MESSAGE_CHARS + 100)
        # Need 3 msgs so the long one (index 1) appears in "recent" (not the last/current)
        msgs = [
            _make_msg(content="x" * MIN_SUBSTANTIVE_LENGTH),  # padding
            _make_msg(content=long_content),
            _make_msg(content="current message"),  # last = excluded as current input
        ]
        result = build_conversation_context(simple_process, msgs)
        assert "..." in result

    def test_none_process_omits_data_section(self):
        result = build_conversation_context(None, [])
        assert "Current Process Data" not in result
