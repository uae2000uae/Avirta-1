"""
Centralized AI settings loader for Avirta.

This module consolidates all OpenAI-related settings from a single place and
normalizes them for use across the application. It prefers environment variables
for secrets and provides sane defaults for optional parameters.
"""
from __future__ import annotations

import os
from typing import Dict, Any, Optional
from contents.admin_controls.secret_loader import get_secret
from contents.admin_controls.openai_models import is_known_model, get_max_output_tokens, get_model_config


PLACEHOLDER_VALUES = {"SET_IN_ENV", "set_in_env", "", None}


def _coerce_bool(val: Any, default: bool = False) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        v = val.strip().lower()
        if v in {"1", "true", "yes", "on"}:
            return True
        if v in {"0", "false", "no", "off"}:
            return False
    return default


def _parse_stop(value: Any) -> Optional[list]:
    if value is None:
        return None
    if isinstance(value, list):
        return [str(x) for x in value if str(x).strip()]
    # Support comma-separated string
    s = str(value).strip()
    if not s:
        return None
    return [seg.strip() for seg in s.split(",") if seg.strip()]


def _model_max_completion_tokens(model: str) -> int:
    # Known caps (completion tokens). This does not reflect context window.
    # Prefer the admin-facing model registry so the cap always matches what's
    # shown/enforced in the Admin Controls UI.
    if is_known_model(model):
        return get_max_output_tokens(model)

    # Fallback for models saved before the registry existed / aliases.
    caps = {
        "gpt-4o": 16384,
        "gpt-4o-mini": 16384,
        "o4-mini": 16384,
        "gpt-4.1": 16384,
        "gpt-4.1-mini": 16384,
    }
    for k, v in caps.items():
        if model.startswith(k):
            return v
    return 4096


def load_ai_settings(admin_setup) -> Dict[str, Any]:
    """Return a normalized dict of OpenAI settings for the app to use.

    Resolution order for API key:
    - Environment variable AI_Token
    - admin_setup.game_settings['openai_api_key'] if not a placeholder

    Returns a dict with keys:
    - api_key, model, temperature, top_p, frequency_penalty, presence_penalty,
      max_output_tokens (clamped), seed, stop (list), response_format (dict or None),
      request_timeout (int/float), base_url, organization, user
    """
    gs = getattr(admin_setup, "game_settings", {}) or {}

    # Secrets: prefer env var and ignore placeholders from file
    # Prefer env/Secret Manager; ignore placeholders in file
    api_key = get_secret("AI_Token") or gs.get("openai_api_key")
    if api_key and str(api_key).strip() in PLACEHOLDER_VALUES:
        api_key = get_secret("AI_Token")

    model = str(gs.get("openai_model", "gpt-4o-mini")).strip() or "gpt-4o-mini"
    temperature = float(gs.get("openai_temperature", 0.55))
    top_p = float(gs.get("openai_top_p", 1.0))
    frequency_penalty = float(gs.get("openai_frequency_penalty", 0.0))
    presence_penalty = float(gs.get("openai_presence_penalty", 0.0))
    max_tokens_cfg = int(gs.get("openai_max_tokens", 16384))
    seed = int(gs.get("openai_seed", 0) or 0)

    # Reasoning-family models (e.g. GPT-5.x) use reasoning_effort/verbosity
    # instead of temperature/top_p/penalties - the generator picks the right
    # payload shape based on is_reasoning_model.
    is_reasoning_model = is_known_model(model) and get_model_config(model).get("family") == "reasoning"
    reasoning_effort = str(gs.get("openai_reasoning_effort", "medium") or "medium").strip()
    verbosity = str(gs.get("openai_verbosity", "medium") or "medium").strip()

    # Response format is controlled solely by the "Response Format Override"
    # field - "" means plain text, "json_object" forces JSON mode.
    response_format_setting = (gs.get("openai_response_format") or "").strip()
    response_format = {"type": response_format_setting} if response_format_setting else None

    stop_list = _parse_stop(gs.get("openai_stop"))

    request_timeout = gs.get("openai_request_timeout", 60)
    try:
        request_timeout = float(request_timeout) if request_timeout is not None else None
    except Exception:
        request_timeout = 60.0

    base_url = str(gs.get("openai_base_url", "https://api.openai.com/v1") or "https://api.openai.com/v1").strip()
    organization = (os.environ.get("OPENAI_ORG") or gs.get("openai_organization") or "").strip()
    user = str(gs.get("openai_user", "") or "").strip()

    # Enhanced generation flow toggles (RAG source grounding + AI validation pass).
    # Default to enabled; both degrade gracefully if they fail at runtime.
    use_source_grounding = _coerce_bool(gs.get("openai_use_source_grounding", True), default=True)
    use_validation = _coerce_bool(gs.get("openai_use_validation", True), default=True)

    # Clamp max tokens to model cap
    cap = _model_max_completion_tokens(model)
    max_tokens = max(1, min(int(max_tokens_cfg), cap))

    return {
        "api_key": api_key or "",
        "model": model,
        "temperature": temperature,
        "top_p": top_p,
        "frequency_penalty": frequency_penalty,
        "presence_penalty": presence_penalty,
        "max_output_tokens": max_tokens,
        "seed": seed,
        "is_reasoning_model": is_reasoning_model,
        "reasoning_effort": reasoning_effort,
        "verbosity": verbosity,
        "stop": stop_list,
        "response_format": response_format,
        "request_timeout": request_timeout,
        "base_url": base_url,
        "organization": organization,
        "user": user,
        "use_source_grounding": use_source_grounding,
        "use_validation": use_validation,
    }
