"""Prompt loader utilities."""
from __future__ import annotations

from pathlib import Path
from typing import Dict

_PROMPT_ROOT = Path(__file__).resolve().parent
_PROMPT_CACHE: Dict[str, str] = {}


def load_prompt(relative_path: str) -> str:
    """Load a prompt template from the prompts directory."""
    if relative_path in _PROMPT_CACHE:
        return _PROMPT_CACHE[relative_path]
    prompt_path = _PROMPT_ROOT / relative_path
    content = prompt_path.read_text(encoding="utf-8")
    _PROMPT_CACHE[relative_path] = content
    return content


def render_prompt(template: str, **kwargs: str) -> str:
    """Render a prompt template by replacing {{key}} placeholders."""
    rendered = template
    for key, value in kwargs.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered
