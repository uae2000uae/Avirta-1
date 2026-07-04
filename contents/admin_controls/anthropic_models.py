"""
Registry of Anthropic (Claude) models offered in the Admin Controls "API
Settings" panel, and the tunable parameters shown for each one.

This mirrors ``openai_models.py`` but for the Anthropic Messages API. It is the
single source of truth for:
- which Claude models appear in the "Claude Model" dropdown
- each model's default parameter values (used when nothing has been saved yet)
- each model's max output token ceiling
- the help text / min / max shown in the info tooltip for each parameter

To add a new model, add an entry to MODELS below - the admin UI and the
per-model settings persistence in AdminSetup will pick it up automatically.

Notes on Anthropic vs OpenAI parameters:
- Anthropic's ``temperature`` and ``top_p`` are both in the range 0.0-1.0
  (OpenAI allows temperature up to 2.0).
- There are no frequency/presence penalties; the Messages API exposes
  ``temperature``, ``top_p`` and ``top_k`` only.
- ``max_tokens`` is REQUIRED on every request (unlike OpenAI where it is
  optional), so a sensible per-model default matters.
"""
from __future__ import annotations

from typing import Any, Dict, List

# Parameters shown in the per-model panel, in display order. Claude models all
# share the same simple sampling knobs, so there is a single order (no
# "reasoning vs standard" split like the OpenAI registry needs).
PARAM_ORDER = [
    'anthropic_temperature',
    'anthropic_top_p',
    'anthropic_max_tokens',
]

# Static, model-agnostic guidance for each parameter. `max` for
# anthropic_max_tokens is intentionally omitted here - it is filled in per-model
# from MODELS[model]['max_output_tokens_cap'].
PARAM_INFO: Dict[str, Dict[str, Any]] = {
    'anthropic_temperature': {
        'label': 'Temperature',
        'type': 'number',
        'min': 0.0,
        'max': 1.0,
        'step': 0.01,
        'help': 'Controls randomness of the output. Lower (e.g. 0.2) is more focused and repeatable; higher (e.g. 0.9) is more varied. For Claude the maximum allowed is 1.0.',
    },
    'anthropic_top_p': {
        'label': 'Top P',
        'type': 'number',
        'min': 0.0,
        'max': 1.0,
        'step': 0.01,
        'help': 'Nucleus sampling: only considers tokens making up the top P probability mass. Anthropic recommends adjusting either this or Temperature, not both. Maximum allowed: 1.0.',
    },
    'anthropic_max_tokens': {
        'label': 'Max Output Tokens',
        'type': 'number',
        'min': 1,
        'max': None,  # filled per-model from max_output_tokens_cap
        'step': 1,
        'help': 'Maximum number of tokens Claude may generate in one reply. This is required by the Messages API. Higher values allow longer batches but cost more and take longer. Capped by the selected model’s output limit.',
    },
}

# Best model first - used as the default when nothing has been chosen yet.
DEFAULT_MODEL = 'claude-opus-4-8'

MODELS: Dict[str, Dict[str, Any]] = {
    'claude-opus-4-8': {
        'display_name': 'Claude Opus 4.8',
        'description': 'Most capable Claude model. Best quality and reasoning for high-stakes question generation. Highest cost/latency. Recommended default.',
        'max_output_tokens_cap': 32000,
        'defaults': {
            'anthropic_temperature': 0.7,
            'anthropic_top_p': 1.0,
            'anthropic_max_tokens': 8192,
        },
    },
    'claude-sonnet-5': {
        'display_name': 'Claude Sonnet 5',
        'description': 'Balanced flagship model. Excellent quality at lower cost/latency than Opus. Great everyday choice for large batches.',
        'max_output_tokens_cap': 32000,
        'defaults': {
            'anthropic_temperature': 0.7,
            'anthropic_top_p': 1.0,
            'anthropic_max_tokens': 8192,
        },
    },
    'claude-haiku-4-5-20251001': {
        'display_name': 'Claude Haiku 4.5',
        'description': 'Fastest and lowest-cost Claude model. Best for simple/short question batches or high-volume generation on a budget.',
        'max_output_tokens_cap': 16000,
        'defaults': {
            'anthropic_temperature': 0.7,
            'anthropic_top_p': 1.0,
            'anthropic_max_tokens': 4096,
        },
    },
}


def get_model_ids() -> List[str]:
    """Ordered list of model ids offered in the dropdown."""
    return list(MODELS.keys())


def is_known_model(model_id: str) -> bool:
    return model_id in MODELS


def get_model_config(model_id: str) -> Dict[str, Any]:
    """Return the registry entry for a model, falling back to the default model."""
    return MODELS.get(model_id) or MODELS[DEFAULT_MODEL]


def get_model_defaults(model_id: str) -> Dict[str, Any]:
    """Return a copy of the default parameter values for a model."""
    return dict(get_model_config(model_id)['defaults'])


def get_max_output_tokens(model_id: str) -> int:
    """Return the max output-token ceiling for a model (fallback: 8192)."""
    return get_model_config(model_id).get('max_output_tokens_cap', 8192)


def get_model_params(model_id: str) -> List[Dict[str, Any]]:
    """Return the ordered param definitions (with per-model max/default filled in)."""
    cfg = get_model_config(model_id)
    defaults = cfg['defaults']
    params = []
    for key in PARAM_ORDER:
        info = dict(PARAM_INFO[key])
        info['key'] = key
        if key == 'anthropic_max_tokens':
            info['max'] = cfg.get('max_output_tokens_cap', 8192)
        info['default'] = defaults.get(key)
        params.append(info)
    return params


def get_registry_for_frontend() -> Dict[str, Any]:
    """Serializable registry (models + per-model params) for embedding in the admin page."""
    return {
        'default_model': DEFAULT_MODEL,
        'models': {
            model_id: {
                'display_name': cfg['display_name'],
                'description': cfg['description'],
                'max_output_tokens_cap': cfg['max_output_tokens_cap'],
                'defaults': cfg['defaults'],
                'params': get_model_params(model_id),
            }
            for model_id, cfg in MODELS.items()
        },
    }
