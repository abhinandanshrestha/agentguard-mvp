"""OpenAI-compatible LLM client.

A minimal chat-completions client that works with any OpenAI-compatible
API: OpenAI, OpenRouter, DeepSeek, Groq, Ollama, LM Studio, etc.

No SDK dependency - uses plain HTTP requests so any provider with a
compatible endpoint can be used.
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when an LLM API call fails after all retries."""


class LLMClient:
    """Client for OpenAI-compatible chat completions APIs.

    Attributes:
        api_key: API key for authentication.
        base_url: Base URL of the API (e.g., https://api.openai.com/v1).
        model: Model name to use.
        temperature: Sampling temperature.
        max_tokens: Maximum tokens in the response.
        timeout: Request timeout in seconds.
        max_retries: Maximum number of retries on transient failures.
        retry_delay: Base delay in seconds between retries (exponential backoff).
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.openai.com/v1",
        model: str = "gpt-4o-mini",
        temperature: float = 0.2,
        max_tokens: int = 8192,
        timeout: int = 120,
        max_retries: int = 3,
        retry_delay: float = 1.0,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Send a chat completion request and return the assistant message.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            temperature: Optional override for sampling temperature.
            max_tokens: Optional override for max tokens.

        Returns:
            The assistant's response text.

        Raises:
            LLMError: If the request fails after all retries, or the API
                returns an error response.
        """
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature if temperature is None else temperature,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/chat/completions"
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )

                if response.status_code == 429 or 500 <= response.status_code < 600:
                    # Transient errors - retry with backoff
                    delay = self.retry_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "LLM API returned %s (attempt %d/%d). Retrying in %.1fs",
                        response.status_code,
                        attempt,
                        self.max_retries,
                        delay,
                    )
                    last_error = LLMError(
                        f"LLM API returned status {response.status_code}: "
                        f"{response.text[:200]}"
                    )
                    time.sleep(delay)
                    continue

                if response.status_code != 200:
                    # Non-retryable client error (401, 404, etc.)
                    raise LLMError(
                        f"LLM API error {response.status_code}: {response.text[:500]}"
                    )

                data = response.json()
                return self._extract_message(data)

            except LLMError:
                raise
            except requests.RequestException as e:
                last_error = LLMError(f"LLM request failed: {e}")
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "LLM request failed (attempt %d/%d): %s. Retrying in %.1fs",
                        attempt,
                        self.max_retries,
                        e,
                        delay,
                    )
                    time.sleep(delay)

        raise LLMError(f"LLM API failed after {self.max_retries} attempts") from last_error

    def _extract_message(self, data: dict[str, Any]) -> str:
        """Extract the assistant message from an API response.

        Args:
            data: Parsed JSON response from the chat completions API.

        Returns:
            The assistant message content.

        Raises:
            LLMError: If the response format is unexpected.
        """
        choices = data.get("choices")
        if not choices:
            raise LLMError(f"LLM API returned no choices: {str(data)[:500]}")

        message = choices[0].get("message", {})
        content = message.get("content")
        if content is None:
            raise LLMError(f"LLM API returned empty content: {str(data)[:500]}")

        return content


def create_client_from_settings(settings: Any) -> LLMClient:
    """Create an LLMClient from AgentGuard Settings.

    Args:
        settings: AgentGuard Settings instance.

    Returns:
        LLMClient configured from settings.
    """
    return LLMClient(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout,
    )
