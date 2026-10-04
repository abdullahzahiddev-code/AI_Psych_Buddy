"""Thin, provider-agnostic wrapper around any OpenAI-compatible chat API.

Switch provider/model purely through environment variables:
LLM_API_KEY, LLM_MODEL, LLM_BASE_URL (see .env.example).
To support a non-OpenAI-style API later, only this file needs to change.
"""
import logging

from django.conf import settings

from . import prompts

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Any problem talking to the LLM. `user_message` is safe to show to the user."""

    def __init__(self, detail, user_message=prompts.LLM_UNAVAILABLE_MESSAGE):
        super().__init__(detail)
        self.user_message = user_message


def is_configured():
    return bool(settings.LLM_API_KEY)


def _build_client():
    try:
        from openai import OpenAI
    except ImportError as exc:  # pragma: no cover
        raise LLMError("openai package is not installed") from exc
    return OpenAI(
        api_key=settings.LLM_API_KEY,
        base_url=settings.LLM_BASE_URL,
        timeout=settings.LLM_TIMEOUT_SECONDS,
        max_retries=1,
    )


def generate_reply(messages, temperature=0.6, max_tokens=500):
    """Send chat `messages` ([{role, content}, ...]) and return the reply text.

    Raises LLMError (never anything else) for missing key, bad key, timeout,
    rate limit, connection problems or an empty reply.
    """
    if not is_configured():
        raise LLMError("LLM_API_KEY is not set")

    try:
        import openai
    except ImportError as exc:  # pragma: no cover
        raise LLMError("openai package is not installed") from exc

    client = _build_client()
    try:
        response = client.chat.completions.create(
            model=settings.LLM_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    except openai.AuthenticationError as exc:
        logger.error("LLM authentication failed (check LLM_API_KEY).")
        raise LLMError("invalid API key") from exc
    except openai.APITimeoutError as exc:
        logger.error("LLM request timed out.")
        raise LLMError("timeout") from exc
    except openai.RateLimitError as exc:
        logger.error("LLM rate limit / quota reached.")
        raise LLMError("rate limited") from exc
    except openai.APIConnectionError as exc:
        logger.error("Could not connect to the LLM service.")
        raise LLMError("connection error") from exc
    except openai.OpenAIError as exc:
        logger.error("LLM API error: %s", type(exc).__name__)
        raise LLMError(f"api error: {type(exc).__name__}") from exc
    except Exception as exc:  # last-resort guard so the site never crashes
        logger.exception("Unexpected error calling the LLM")
        raise LLMError("unexpected error") from exc

    try:
        text = (response.choices[0].message.content or "").strip()
    except (AttributeError, IndexError, TypeError) as exc:
        raise LLMError("malformed response") from exc
    if not text:
        logger.error("LLM returned an empty response.")
        raise LLMError("empty response")
    return text
