from __future__ import annotations

import json
from typing import Any
from collections.abc import Iterator

import httpx


class OllamaProvider:
    """Local Ollama provider for Qwen generation and embeddings."""

    def __init__(self, base_url: str | None = None, model: str | None = None, embed_model: str | None = None, temperature: float | None = None):
        from ..config import get_settings
        cfg = get_settings()
        self.base_url = (base_url or cfg.topostyle_ollama_url).rstrip("/")
        self.model = model or cfg.topostyle_model
        self.embed_model = embed_model or cfg.topostyle_embed_model
        self.temperature = float(temperature if temperature is not None else cfg.topostyle_temperature)

    def _error(self, exc: Exception) -> RuntimeError:
        return RuntimeError(f"OLLAMA_UNAVAILABLE: {self.base_url} ({exc})")

    def health(self) -> dict[str, Any]:
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5)
            response.raise_for_status()
            return {"ok": True, "models": response.json().get("models", [])}
        except Exception as exc:
            raise self._error(exc) from exc

    def embed(self, texts: list[str]) -> list[list[float]]:
        try:
            values = []
            for text in texts:
                response = httpx.post(f"{self.base_url}/api/embeddings", json={"model": self.embed_model, "prompt": text}, timeout=60)
                response.raise_for_status()
                values.append(response.json()["embedding"])
            return values
        except Exception as exc:
            raise self._error(exc) from exc

    def generate(self, messages: list[dict[str, str]], *, stream: bool = False) -> str | Iterator[str]:
        payload = {"model": self.model, "messages": messages, "stream": stream, "options": {"temperature": self.temperature}}
        try:
            if not stream:
                response = httpx.post(f"{self.base_url}/api/chat", json=payload, timeout=180)
                response.raise_for_status()
                return response.json()["message"]["content"]
            response = httpx.stream("POST", f"{self.base_url}/api/chat", json=payload, timeout=180)
            response.__enter__()
            def chunks() -> Iterator[str]:
                try:
                    for line in response.iter_lines():
                        if line:
                            data = json.loads(line)
                            content = data.get("message", {}).get("content", "")
                            if content:
                                yield content
                finally:
                    response.__exit__(None, None, None)
            return chunks()
        except Exception as exc:
            raise self._error(exc) from exc

    def generate_structured(self, system_prompt: str, user_payload: dict[str, Any]) -> dict[str, Any]:
        content = self.generate([{"role": "system", "content": system_prompt}, {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)}])
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OLLAMA_INVALID_JSON_RESPONSE") from exc
