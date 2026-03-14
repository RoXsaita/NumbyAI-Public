"""Shared LLM client — Ollama and MiniMax providers."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

import requests

from app.config import settings
from app.logger import create_logger

logger = create_logger("llm_service")

_GENERATE_ENDPOINT = "/api/generate"
_ANSI_ESCAPE_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
_CODE_FENCE_RE = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)
_DEFAULT_PROVIDER = "ollama"
_PROVIDER_ALIASES = {
    "local": "ollama",
    "ollama": "ollama",
    "minimax": "minimax",
}
_SUPPORTED_PROVIDERS = {"ollama", "minimax"}


def _normalized_model_aliases(model_name: str) -> set[str]:
    """Return exact model identifiers accepted as equivalent."""
    normalized = (model_name or "").strip().lower()
    if not normalized:
        return set()

    aliases = {normalized}
    if ":" in normalized:
        base, tag = normalized.rsplit(":", 1)
        if tag == "latest":
            aliases.add(base)
    else:
        aliases.add(f"{normalized}:latest")

    return aliases


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", text or "")


def _extract_json_array(raw_text: str) -> List[Dict[str, Any]]:
    decoder = json.JSONDecoder()
    cleaned = _strip_ansi(raw_text).strip()
    candidates = [match.group(1).strip() for match in _CODE_FENCE_RE.finditer(cleaned)]
    candidates.append(cleaned)

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, list):
                return parsed
        except json.JSONDecodeError:
            pass

        for idx, char in enumerate(candidate):
            if char != "[":
                continue
            try:
                parsed, end_idx = decoder.raw_decode(candidate[idx:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, list) and candidate[idx + end_idx :].strip() in {"", "```"}:
                return parsed

    raise ValueError("LLM did not return a JSON array")


def normalize_llm_provider(provider: Optional[str]) -> Optional[str]:
    """Normalize an explicit provider selection to a canonical identifier."""
    configured = (provider or "").strip().lower()
    if not configured or configured == "auto":
        return None
    return _PROVIDER_ALIASES.get(configured, configured)


def get_effective_llm_provider(provider_override: Optional[str] = None) -> str:
    """Resolve the active LLM provider from override or config."""
    normalized_override = normalize_llm_provider(provider_override)
    if normalized_override:
        return normalized_override

    configured = normalize_llm_provider(settings.llm_provider)
    if not configured:
        return _DEFAULT_PROVIDER
    return configured


def get_ollama_status() -> Dict[str, Any]:
    """Check whether Ollama is reachable and the configured model is available."""
    base_url = settings.ollama_url
    model = settings.ollama_model
    try:
        resp = requests.get(f"{base_url}/api/tags", timeout=5)
        resp.raise_for_status()
        installed_models = {
            (m.get("name", "") or "").strip().lower()
            for m in resp.json().get("models", [])
            if isinstance(m, dict)
        }
        model_available = bool(_normalized_model_aliases(model) & installed_models)
        return {
            "provider": "ollama",
            "url": base_url,
            "model": model,
            "reachable": True,
            "model_available": model_available,
            "available": model_available,
        }
    except Exception as exc:
        logger.warn("Ollama not reachable", {"url": base_url, "error": str(exc)})
        return {
            "provider": "ollama",
            "url": base_url,
            "model": model,
            "reachable": False,
            "model_available": False,
            "available": False,
            "error": str(exc),
        }


def get_minimax_status() -> Dict[str, Any]:
    """Check whether the MiniMax API is reachable with the configured key."""
    api_key = settings.minimax_api_key
    model = settings.minimax_model
    base_url = settings.minimax_base_url

    if not api_key:
        return {
            "provider": "minimax",
            "url": base_url,
            "model": model,
            "reachable": False,
            "model_available": False,
            "available": False,
            "error": "MINIMAX_API_KEY is not set",
        }
    try:
        resp = requests.get(
            f"{base_url}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=10,
        )
        resp.raise_for_status()
        return {
            "provider": "minimax",
            "url": base_url,
            "model": model,
            "reachable": True,
            "model_available": True,
            "available": True,
        }
    except Exception as exc:
        logger.warn("MiniMax API not reachable", {"url": base_url, "error": str(exc)})
        return {
            "provider": "minimax",
            "url": base_url,
            "model": model,
            "reachable": False,
            "model_available": False,
            "available": False,
            "error": str(exc),
        }


def get_llm_status(provider_override: Optional[str] = None) -> Dict[str, Any]:
    """Return availability for the selected LLM provider."""
    provider = get_effective_llm_provider(provider_override)
    if provider == "ollama":
        return get_ollama_status()
    if provider == "minimax":
        return get_minimax_status()
    return {
        "provider": provider,
        "requested_provider": provider_override,
        "configured_provider": settings.llm_provider,
        "model": None,
        "reachable": False,
        "model_available": False,
        "available": False,
        "error": (
            f"Unsupported llm_provider: {provider_override}"
            if provider_override
            else f"Unsupported llm_provider: {settings.llm_provider}"
        ),
    }


def _build_ollama_options() -> Dict[str, Any]:
    """Build the Ollama options dict from settings."""
    opts: Dict[str, Any] = {"temperature": 0}
    if settings.ollama_num_ctx is not None:
        opts["num_ctx"] = settings.ollama_num_ctx
    return opts


def _call_ollama_json_array(prompt: str, response_schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    model = settings.ollama_model
    url = f"{settings.ollama_url}{_GENERATE_ENDPOINT}"
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": response_schema,
        "options": _build_ollama_options(),
    }
    if settings.ollama_think is not None:
        payload["think"] = settings.ollama_think

    logger.info("Calling Ollama", {"model": model, "prompt_length": len(prompt)})
    resp = requests.post(url, json=payload, timeout=settings.llm_timeout_seconds)
    resp.raise_for_status()
    return _extract_json_array(resp.json().get("response", "[]"))


def _call_minimax_chat(prompt: str, response_schema: Dict[str, Any]) -> str:
    """Send a chat-completion request to the MiniMax API and return raw content."""
    api_key = settings.minimax_api_key
    if not api_key:
        raise ValueError("MINIMAX_API_KEY is not set")

    model = settings.minimax_model
    url = f"{settings.minimax_base_url}/chat/completions"

    schema_hint = json.dumps(response_schema, indent=2)
    system_msg = (
        "You are a precise JSON generator. Respond ONLY with valid JSON — "
        "no markdown fences, no commentary.\n"
        f"Expected JSON schema:\n{schema_hint}"
    )

    payload: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_msg},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }

    logger.info("Calling MiniMax", {"model": model, "prompt_length": len(prompt)})
    resp = requests.post(
        url,
        json=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        timeout=settings.llm_timeout_seconds,
    )
    resp.raise_for_status()
    data = resp.json()
    return data["choices"][0]["message"]["content"]


def _call_minimax_json_array(prompt: str, response_schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    raw = _call_minimax_chat(prompt, response_schema)
    return _extract_json_array(raw)


def _call_minimax_json_object(prompt: str, response_schema: Dict[str, Any]) -> Dict[str, Any]:
    raw = _call_minimax_chat(prompt, response_schema)
    return _extract_json_object(raw)


def call_llm_json_array(
    prompt: str,
    response_schema: Dict[str, Any],
    provider_override: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Call the configured provider and parse a JSON array response."""
    provider = get_effective_llm_provider(provider_override)
    if provider == "ollama":
        return _call_ollama_json_array(prompt, response_schema)
    if provider == "minimax":
        return _call_minimax_json_array(prompt, response_schema)
    raise ValueError(
        f"Unsupported llm_provider: {provider_override}"
        if provider_override
        else f"Unsupported llm_provider: {settings.llm_provider}"
    )


def _extract_json_object(raw_text: str) -> Dict[str, Any]:
    """Extract a single JSON object from LLM output (may contain markdown fences)."""
    decoder = json.JSONDecoder()
    cleaned = _strip_ansi(raw_text).strip()
    candidates = [match.group(1).strip() for match in _CODE_FENCE_RE.finditer(cleaned)]
    candidates.append(cleaned)

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        for idx, char in enumerate(candidate):
            if char != "{":
                continue
            try:
                parsed, end_idx = decoder.raw_decode(candidate[idx:])
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                return parsed

    raise ValueError("LLM did not return a JSON object")


def _call_ollama_json_object(prompt: str, response_schema: Dict[str, Any]) -> Dict[str, Any]:
    model = settings.ollama_model
    url = f"{settings.ollama_url}{_GENERATE_ENDPOINT}"
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": response_schema,
        "options": _build_ollama_options(),
    }
    if settings.ollama_think is not None:
        payload["think"] = settings.ollama_think

    logger.info("Calling Ollama (json_object)", {"model": model, "prompt_length": len(prompt)})
    resp = requests.post(url, json=payload, timeout=settings.llm_timeout_seconds)
    resp.raise_for_status()
    return _extract_json_object(resp.json().get("response", "{}"))


def call_llm_json_object(
    prompt: str,
    response_schema: Dict[str, Any],
    provider_override: Optional[str] = None,
) -> Dict[str, Any]:
    """Call the configured provider and parse a single JSON object response."""
    provider = get_effective_llm_provider(provider_override)
    if provider == "ollama":
        return _call_ollama_json_object(prompt, response_schema)
    if provider == "minimax":
        return _call_minimax_json_object(prompt, response_schema)
    raise ValueError(
        f"Unsupported llm_provider: {provider_override}"
        if provider_override
        else f"Unsupported llm_provider: {settings.llm_provider}"
    )
