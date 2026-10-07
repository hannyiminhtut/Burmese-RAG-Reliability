"""Minimal UTF-8-safe client for a local Ollama generation server."""

from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.request
from typing import Any, Dict, Optional


class OllamaError(RuntimeError):
    """Base class for local Ollama failures."""


class OllamaConnectionError(OllamaError):
    pass


class OllamaTimeoutError(OllamaError):
    pass


class OllamaResponseError(OllamaError):
    pass


class OllamaModelError(OllamaError):
    def __init__(self, message: str, status_code: Optional[int] = None, detail: str = "") -> None:
        super().__init__(message)
        self.status_code = status_code
        self.detail = detail


def canonical_sha256_digest(value: str) -> str:
    """Return a SHA-256 digest as 64 lowercase hex characters without a prefix.

    Surrounding whitespace and one optional case-insensitive ``sha256:`` prefix
    are accepted. Other algorithms, malformed values, and partial digests are
    rejected rather than compared loosely.
    """
    if not isinstance(value, str):
        raise ValueError("SHA-256 digest must be a string")
    normalized = value.strip()
    if ":" in normalized:
        algorithm, normalized = normalized.split(":", 1)
        if algorithm.lower() != "sha256":
            raise ValueError(f"Unknown digest algorithm prefix: {algorithm}")
    if len(normalized) != 64:
        raise ValueError("SHA-256 digest must contain exactly 64 hexadecimal characters")
    if not re.fullmatch(r"[0-9a-fA-F]{64}", normalized):
        raise ValueError("SHA-256 digest contains non-hexadecimal characters")
    return normalized.lower()


def sha256_digest_audit(installed_raw: str, frozen_raw: str) -> Dict[str, Any]:
    """Return raw and canonical SHA-256 values plus their exact match result."""
    installed = canonical_sha256_digest(installed_raw)
    frozen = canonical_sha256_digest(frozen_raw)
    return {
        "raw_api_digest": installed_raw,
        "frozen_digest": frozen_raw,
        "canonical_installed_digest": installed,
        "canonical_frozen_digest": frozen,
        "digest_match": installed == frozen,
    }


class OllamaClient:
    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "gemma3:4b-it-q4_K_M",
        timeout_seconds: float = 600.0,
        urlopen: Optional[Any] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self._urlopen = urlopen or urllib.request.urlopen

    def _request(
        self, method: str, endpoint: str, payload: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        request = urllib.request.Request(
            self.base_url + endpoint, data=data, headers=headers, method=method
        )
        try:
            response = self._urlopen(request, timeout=self.timeout_seconds)
            raw = response.read()
        except (TimeoutError, socket.timeout) as exc:
            raise OllamaTimeoutError(
                f"Ollama request timed out after {self.timeout_seconds} seconds"
            ) from exc
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8", errors="replace")
            except Exception:
                detail = str(exc)
            raise OllamaModelError(
                f"Ollama HTTP {exc.code}: {detail}", status_code=exc.code, detail=detail
            ) from exc
        except (urllib.error.URLError, ConnectionError, OSError) as exc:
            raise OllamaConnectionError(f"Could not connect to Ollama: {exc}") from exc
        try:
            document = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise OllamaResponseError("Ollama returned malformed UTF-8 JSON") from exc
        if not isinstance(document, dict):
            raise OllamaResponseError("Ollama response must be a JSON object")
        if document.get("error"):
            raise OllamaModelError(f"Ollama model error: {document['error']}")
        return document

    def version(self) -> str:
        document = self._request("GET", "/api/version")
        version = document.get("version")
        if not isinstance(version, str) or not version:
            raise OllamaResponseError("Ollama version response is missing version")
        return version

    def require_model(self) -> str:
        self.model_info()
        return self.model

    def model_info(self) -> Dict[str, Any]:
        document = self._request("GET", "/api/tags")
        models = document.get("models")
        if not isinstance(models, list):
            raise OllamaResponseError("Ollama tags response is missing models")
        match = next(
            (item for item in models if isinstance(item, dict) and item.get("name") == self.model),
            None,
        )
        if match is None:
            raise OllamaModelError(f"Required Ollama model is not installed: {self.model}")
        return match

    def generate(
        self,
        prompt: str,
        settings: Dict[str, Any],
        output_schema: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": output_schema if output_schema is not None else "json",
            "options": settings,
        }
        document = self._request("POST", "/api/generate", payload)
        if not isinstance(document.get("response"), str):
            raise OllamaResponseError("Ollama generate response is missing response text")
        return document
