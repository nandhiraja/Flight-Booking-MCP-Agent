"""
agent/llm_client.py

Async Groq LLM client wrapper.
"""

import logging
from groq import AsyncGroq
import config

logger = logging.getLogger(__name__)

_client: AsyncGroq | None = None


def get_groq_client() -> AsyncGroq:
    """Return a shared AsyncGroq client (lazy init)."""
    global _client
    if _client is None:
        if not config.GROQ_API_KEY:
            raise RuntimeError(
                "GROQ_API_KEY is not set. "
                "Export it before running: set GROQ_API_KEY=your_key_here"
            )
        _client = AsyncGroq(api_key=config.GROQ_API_KEY)
    return _client


async def chat_completion(messages: list[dict], tools: list[dict]) -> object:
    """
    Call Groq chat completions with tool support.

    Args:
        messages: Conversation history in OpenAI format.
        tools:    List of tool schemas.

    Returns:
        The raw Groq response object.
    """
    client = get_groq_client()
    response = await client.chat.completions.create(
        model=config.GROQ_MODEL,
        messages=messages,
        tools=tools,
        tool_choice="auto",
        temperature=0.2,
        max_tokens=4096,
    )
    logger.debug(
        "Groq response: finish_reason=%s tool_calls=%d",
        response.choices[0].finish_reason,
        len(response.choices[0].message.tool_calls or []),
    )
    return response
