"""Shared LLM client supporting Cursor CLI headless mode and Ollama."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
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
    "cloud": "cursor_cli",
    "cursor": "cursor_cli",
    "cursor-cli": "cursor_cli",
    "cursor_cli": "cursor_cli",
    "local": "ollama",
    "ollama": "ollama",
}
_SUPPORTED_PROVIDERS = {"cursor_cli", "ollama"}


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


def _build_cursor_prompt(prompt: str, response_schema: Dict[str, Any]) -> str:
    return (
        f"{prompt}\n\n"
        "Return only a valid JSON array that matches this schema exactly. "
        "Do not include markdown fences, prose, or any extra text.\n"
        f"Schema:\n{json.dumps(response_schema, indent=2, sort_keys=True)}"
    )


def _cursor_base_command() -> List[str]:
    command = shlex.split(settings.cursor_agent_command)
    if not command:
        raise ValueError("CURSOR_AGENT_COMMAND must not be empty")
    return command


def _cursor_workspace() -> str:
    return settings.cursor_agent_workspace or os.getcwd()


def _parse_cursor_models(output: str) -> set[str]:
    models: set[str] = set()
    for raw_line in _strip_ansi(output).splitlines():
        line = raw_line.strip()
        if not line:
            continue
        lower = line.lower()
        if lower.startswith("loading models") or "no models available" in lower:
            continue
        token = line.lstrip("-*• ").split()[0].strip()
        if token and token[0].isalnum():
            models.add(token.lower())
    return models


def get_cursor_cli_status() -> Dict[str, Any]:
    """Check whether the Cursor CLI is installed and the configured model is available."""
    command = _cursor_base_command()
    model = settings.llm_model
    try:
        result = subprocess.run(
            command + ["models"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
            env={**os.environ, "NO_COLOR": "1", "CI": "1"},
        )
    except FileNotFoundError as exc:
        return {
            "provider": "cursor_cli",
            "command": settings.cursor_agent_command,
            "model": model,
            "reachable": False,
            "model_available": False,
            "available": False,
            "error": str(exc),
        }
    except Exception as exc:
        logger.warn("Cursor CLI status check failed", {"error": str(exc)})
        return {
            "provider": "cursor_cli",
            "command": settings.cursor_agent_command,
            "model": model,
            "reachable": False,
            "model_available": False,
            "available": False,
            "error": str(exc),
        }

    output = f"{result.stdout}\n{result.stderr}".strip()
    available_models = _parse_cursor_models(output)
    normalized_model = (model or "").strip().lower()
    model_available = normalized_model in available_models if normalized_model else False
    reachable = result.returncode == 0

    return {
        "provider": "cursor_cli",
        "command": settings.cursor_agent_command,
        "model": model,
        "reachable": reachable,
        "model_available": model_available,
        "available": reachable and model_available,
        "available_models": sorted(available_models),
        "error": None if model_available else _strip_ansi(output).strip() or None,
    }


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


def get_llm_status(provider_override: Optional[str] = None) -> Dict[str, Any]:
    """Return availability for the selected LLM provider."""
    provider = get_effective_llm_provider(provider_override)
    if provider == "cursor_cli":
        return get_cursor_cli_status()
    if provider == "ollama":
        return get_ollama_status()
    if provider not in _SUPPORTED_PROVIDERS:
        model = None
    else:
        model = settings.llm_model if provider == "cursor_cli" else settings.ollama_model
    return {
        "provider": provider,
        "requested_provider": provider_override,
        "configured_provider": settings.llm_provider,
        "model": model,
        "reachable": False,
        "model_available": False,
        "available": False,
        "error": (
            f"Unsupported llm_provider: {provider_override}"
            if provider_override
            else f"Unsupported llm_provider: {settings.llm_provider}"
        ),
    }


def _call_ollama_json_array(prompt: str, response_schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    model = settings.ollama_model or settings.llm_model
    url = f"{settings.ollama_url}{_GENERATE_ENDPOINT}"
    payload: Dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "format": response_schema,
        "options": {"temperature": 0},
    }
    if settings.ollama_think is not None:
        payload["think"] = settings.ollama_think

    logger.info("Calling Ollama", {"model": model, "prompt_length": len(prompt)})
    resp = requests.post(url, json=payload, timeout=settings.llm_timeout_seconds)
    resp.raise_for_status()
    return _extract_json_array(resp.json().get("response", "[]"))


def _call_cursor_cli_json_array(prompt: str, response_schema: Dict[str, Any]) -> List[Dict[str, Any]]:
    command = _cursor_base_command() + [
        "--print",
        "--output-format",
        "text",
        "--mode",
        "ask",
        "--sandbox",
        settings.cursor_agent_sandbox,
        "--workspace",
        _cursor_workspace(),
    ]
    if settings.llm_model:
        command.extend(["--model", settings.llm_model])
    command.append(_build_cursor_prompt(prompt, response_schema))

    logger.info("Calling Cursor CLI", {
        "command": settings.cursor_agent_command,
        "model": settings.llm_model,
        "workspace": _cursor_workspace(),
        "prompt_length": len(prompt),
    })
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=settings.llm_timeout_seconds,
        check=False,
        env={**os.environ, "NO_COLOR": "1", "CI": "1"},
    )
    if result.returncode != 0:
        error_output = _strip_ansi((result.stderr or result.stdout or "").strip())
        raise RuntimeError(error_output or "Cursor CLI call failed")
    return _extract_json_array(result.stdout)


def call_llm_json_array(
    prompt: str,
    response_schema: Dict[str, Any],
    provider_override: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Call the selected provider and parse a JSON array response."""
    provider = get_effective_llm_provider(provider_override)
    if provider == "cursor_cli":
        return _call_cursor_cli_json_array(prompt, response_schema)
    if provider == "ollama":
        return _call_ollama_json_array(prompt, response_schema)
    raise ValueError(
        f"Unsupported llm_provider: {provider_override}"
        if provider_override
        else f"Unsupported llm_provider: {settings.llm_provider}"
    )
