"""
Ollama API Client - Kommunikation mit dem lokalen LLM.
Mit Retry-Logik, Circuit Breaker und Streaming-Support.
"""

import json
import logging
from typing import AsyncGenerator, Optional

import aiohttp

from .config import settings
from .resilience import CircuitBreaker, retry_async

logger = logging.getLogger(__name__)


class OllamaClient:
    """Asynchroner Client fuer die Ollama REST API."""

    def __init__(self):
        self.base_url = settings.ollama_url
        self._cb = CircuitBreaker(name="ollama", failure_threshold=3, recovery_timeout=30.0)

    async def chat(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        tools: Optional[list] = None,
        temperature: float = 0.7,
        max_tokens: int = 256,
    ) -> dict:
        """
        Sendet eine Chat-Anfrage an Ollama (mit Retry).

        Returns:
            Ollama API Response dict oder {"error": "..."}
        """
        model = model or settings.model_smart
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if tools:
            payload["tools"] = tools

        async def _do_request():
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status == 404:
                        error = await resp.text()
                        logger.error("Ollama Modell nicht gefunden: %s", error)
                        return {"error": f"Modell '{model}' nicht gefunden"}
                    if resp.status == 503:
                        raise ConnectionError("Ollama ueberlastet (503)")
                    if resp.status != 200:
                        error = await resp.text()
                        raise aiohttp.ClientError(f"Ollama {resp.status}: {error}")
                    return await resp.json()

        try:
            return await retry_async(
                _do_request,
                max_retries=3,
                base_delay=1.0,
                max_delay=8.0,
                exceptions=(aiohttp.ClientError, ConnectionError, TimeoutError),
                circuit_breaker=self._cb,
            )
        except ConnectionError as e:
            logger.error("Ollama nicht verfuegbar: %s", e)
            return {"error": str(e)}
        except Exception as e:
            logger.error("Ollama Fehler nach Retries: %s", e)
            return {"error": str(e)}

    async def chat_stream(
        self,
        messages: list[dict],
        model: Optional[str] = None,
        tools: Optional[list] = None,
        temperature: float = 0.7,
        max_tokens: int = 256,
    ) -> AsyncGenerator[dict, None]:
        """
        Streaming Chat - gibt Text-Chunks zurueck.

        Yields:
            {"type": "text", "content": "..."} fuer jeden Chunk
            {"type": "done", "content": "...", "tool_calls": [...]} am Ende
        """
        model = model or settings.model_smart
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }
        if tools:
            payload["tools"] = tools

        full_content = ""

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120),
                ) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        yield {"type": "error", "content": error}
                        return

                    async for line in resp.content:
                        if not line:
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        msg = chunk.get("message", {})
                        text = msg.get("content", "")

                        if text:
                            full_content += text
                            yield {"type": "text", "content": text}

                        if chunk.get("done"):
                            tool_calls = msg.get("tool_calls", [])
                            yield {
                                "type": "done",
                                "content": full_content,
                                "tool_calls": tool_calls,
                            }
                            self._cb.record_success()
                            return

        except Exception as e:
            self._cb.record_failure()
            logger.error("Ollama Streaming Fehler: %s", e)
            yield {"type": "error", "content": str(e)}

    async def is_available(self) -> bool:
        """Prueft ob Ollama erreichbar ist."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"{self.base_url}/api/tags",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    available = resp.status == 200
                    if available:
                        self._cb.record_success()
                    return available
        except aiohttp.ClientError:
            return False

    async def list_models(self) -> list[str]:
        """Listet alle verfuegbaren Modelle."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.base_url}/api/tags") as resp:
                    data = await resp.json()
                    return [m["name"] for m in data.get("models", [])]
        except aiohttp.ClientError:
            return []
