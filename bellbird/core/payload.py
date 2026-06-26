"""wx-free helpers for building API request payloads."""

from __future__ import annotations

from bellbird.core.config import BellbirdConfig
from bellbird.core.conversation import Conversation


def build_options(config: BellbirdConfig) -> dict[str, object]:
    """Build the sampling parameters dict with omission semantics.

    min_p is always included. seed is included only when >= 0.
    stop is included only when non-empty (copied to avoid mutation leaks).
    """
    options: dict[str, object] = {
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "top_p": config.top_p,
        "top_k": config.top_k,
        "repeat_penalty": config.repeat_penalty,
        "min_p": config.min_p,
    }
    if config.seed >= 0:
        options["seed"] = config.seed
    if config.stop:
        options["stop"] = list(config.stop)
    return options


def build_api_messages(
    config: BellbirdConfig, conversation: Conversation
) -> list[dict]:
    """Build the base messages list: optional system prompt + conversation history.

    Does NOT include the current user message — callers append it after.
    Used identically in send_message and _continue_after_tool to eliminate
    the duplication.
    """
    messages: list[dict] = []
    if config.system_prompt.strip():
        messages.append({"role": "system", "content": config.system_prompt})
    messages.extend(conversation.get_messages_for_api())
    return messages
