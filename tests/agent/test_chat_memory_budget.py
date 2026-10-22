"""Regression tests for the chat history context budget."""

from monika.application.agent.chat.constants import MAX_HISTORY_CHARS


def test_chat_history_budget_targets_8k_tokens():
    # The history loader uses ~4 characters per token for its compaction budget.
    assert MAX_HISTORY_CHARS // 4 >= 8000
