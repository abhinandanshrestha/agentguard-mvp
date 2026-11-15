"""Anthropic LLM client.

Talks to the Anthropic Messages API (POST /v1/messages) with the same
interface as the OpenAI-compatible client, so agents can use either
provider interchangeably.

API reference: https://docs.anthropic.com/en/api/messages
"""

from __future__ import annotations

import logging
import time
from typing import Any

import requests

logger = logging.getLogger(__name__)


class AnthropicError(Exception):
    """Raised when an Anthropic API call fails after all retries."""


class AnthropicClient:
    """Client for the Anthropic Messages API.

    Attributes:
        api_key: Anthropic API key (sk-ant-...).
        base_url: Base URL of the API (default https://api.anthropic.com).
        model: Model name (e.g., claude-sonnet-4-5).
        temperature: Sampling temperature.
        max_tokens: Maximum tokens in the response (required by Anthropic).
        timeout: Request timeout in seconds.
        max_retries: Maximum number of retries on transient failures.
        retry_delay: Base delay in seconds between retries (exponential backoff).
        api_version: Anthropic API version header.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://api.anthropic.com",
        model: str = "claude-sonnet-4-5",
        temperature: float = 0.2,
        max_tokens: int = 8192,
        timeout: int = 120,
        max_retries: int = 3,
        retry_delay: float = 1.0,
        api_version: str = "2023-06-01",
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.api_version = api_version

    def chat(
        self,
        messages: list[dict[str, str]],
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str:
        """Send a Messages API request and return the assistant text.

        Accepts the same OpenAI-style message list (system + user roles);
        the system message is extracted and passed via the `system` param
        as Anthropic requires.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            temperature: Optional override for sampling temperature.
            max_tokens: Optional override for max tokens.

        Returns:
            The assistant's response text.

        Raises:
            AnthropicError: If the request fails after all retries, or the
                API returns an error response.
        """
        # Split system message from conversation
        system_text = ""
        convo: list[dict[str, str]] = []
        for msg in messages:
            if msg.get("role") == "system":
                system_text = msg.get("content", "")
            else:
                convo.append({"role": msg.get("role", "user"), "content": msg.get("content", "")})

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens if max_tokens is None else max_tokens,
            "temperature": self.temperature if temperature is None else temperature,
            "messages": convo,
        }
        if system_text:
            payload["system"] = system_text

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": self.api_version,
            "Content-Type": "application/json",
        }

        url = f"{self.base_url}/v1/messages"
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout,
                )

                if response.status_code in (429, 529) or 500 <= response.status_code < 600:
                    # Transient errors (429 rate limit, 529 overloaded) - retry
                    delay = self.retry_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "Anthropic API returned %s (attempt %d/%d). Retrying in %.1fs",
                        response.status_code,
                        attempt,
                        self.max_retries,
                        delay,
                    )
                    last_error = AnthropicError(
                        f"Anthropic API returned status {response.status_code}: "
                        f"{response.text[:200]}"
                    )
                    time.sleep(delay)
                    continue

                if response.status_code != 200:
                    # Non-retryable client error (401, 404, etc.)
                    raise AnthropicError(
                        f"Anthropic API error {response.status_code}: "
                        f"{response.text[:500]}"
                    )

                data = response.json()
                return self._extract_message(data)

            except AnthropicError:
                raise
            except requests.RequestException as e:
                last_error = AnthropicError(f"Anthropic request failed: {e}")
                if attempt < self.max_retries:
                    delay = self.retry_delay * (2 ** (attempt - 1))
                    logger.warning(
                        "Anthropic request failed (attempt %d/%d): %s. Retrying in %.1fs",
                        attempt,
                        self.max_retries,
                        e,
                        delay,
                    )
                    time.sleep(delay)

        raise AnthropicError(
            f"Anthropic API failed after {self.max_retries} attempts"
        ) from last_error

    def _extract_message(self, data: dict[str, Any]) -> str:
        """Extract the assistant text from a Messages API response.

        Args:
            data: Parsed JSON response.

        Returns:
            Concatenated text blocks from the response content.

        Raises:
            AnthropicError: If the response format is unexpected.
        """
        content = data.get("content")
        if not content:
            raise AnthropicError(f"Anthropic API returned no content: {str(data)[:500]}")

        # Response content is a list of blocks: [{"type": "text", "text": "..."}]
        text_parts = [
            block.get("text", "")
            for block in content
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        result = "".join(text_parts).strip()
        if not result:
            raise AnthropicError(f"Anthropic API returned empty text: {str(data)[:500]}")

        return result


def create_anthropic_client_from_settings(settings: Any) -> AnthropicClient:
    """Create an AnthropicClient from AgentGuard Settings.

    Args:
        settings: AgentGuard Settings instance.

    Returns:
        AnthropicClient configured from settings.
    """
    return AnthropicClient(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        model=settings.llm_model,
        temperature=settings.llm_temperature,
        max_tokens=settings.llm_max_tokens,
        timeout=settings.llm_timeout,
    )
