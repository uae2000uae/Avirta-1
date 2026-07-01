"""
Registry of ChatGPT/OpenAI models offered in the Admin Controls "API Settings"
panel, and the tunable parameters shown for each one.

This is the single source of truth for:
- which models appear in the "AI Model" dropdown
- each model's default parameter values (used when nothing has been saved yet)
- each model's max output token ceiling
- the help text / min / max shown in the info tooltip for each parameter

To add a new model, add an entry to MODELS below - the admin UI and the
per-model settings persistence in AdminSetup will pick it up automatically.
"""
from __future__ import annotations

from typing import Any, Dict, List

# Parameters shown in the per-model panel, in display order - varies by model
# "family" since reasoning models (e.g. GPT-5.x) don't use traditional sampling
# knobs at all. Everything else (base URL, timeout, organization, seed, etc.)
# lives in the "Advanced" section since it applies uniformly regardless of
# which model is selected.
PARAM_ORDER_BY_FAMILY = {
    'standard': [
        'openai_temperature',
        'openai_top_p',
        'openai_frequency_penalty',
        'openai_presence_penalty',
        'openai_max_tokens',
    ],
    'reasoning': [
        'openai_reasoning_effort',
        'openai_verbosity',
        'openai_max_tokens',
    ],
}

# Static, model-agnostic guidance for each parameter. `max` for
# openai_max_tokens is intentionally omitted here - it is filled in per-model
# from MODELS[model]['max_output_tokens_cap'].
PARAM_INFO: Dict[str, Dict[str, Any]] = {
    'openai_temperature': {
        'label': 'Temperature',
        'type': 'number',
        'min': 0.0,
        'max': 2.0,
        'step': 0.01,
        'help': 'Controls randomness of the output. Lower (e.g. 0.2) is more focused and repeatable; higher (e.g. 1.5) is more varied and creative. Maximum allowed: 2.0.',
    },
    'openai_top_p': {
        'label': 'Top P',
        'type': 'number',
        'min': 0.0,
        'max': 1.0,
        'step': 0.01,
        'help': 'Nucleus sampling: only considers tokens making up the top P probability mass. OpenAI recommends adjusting either this or Temperature, not both. Maximum allowed: 1.0.',
    },
    'openai_frequency_penalty': {
        'label': 'Frequency Penalty',
        'type': 'number',
        'min': -2.0,
        'max': 2.0,
        'step': 0.01,
        'help': 'Penalizes tokens based on how often they already appear in the output, reducing word/phrase repetition. Range: -2.0 to 2.0.',
    },
    'openai_presence_penalty': {
        'label': 'Presence Penalty',
        'type': 'number',
        'min': -2.0,
        'max': 2.0,
        'step': 0.01,
        'help': 'Penalizes tokens that have appeared at all so far, encouraging the model to bring up new topics/wording. Range: -2.0 to 2.0.',
    },
    'openai_max_tokens': {
        'label': 'Max Output Tokens',
        'type': 'number',
        'min': 1,
        'max': None,  # filled per-model from max_output_tokens_cap
        'step': 1,
        'help': 'Maximum number of tokens the model may generate in one reply. Higher values allow longer responses but cost more and take longer. Capped by the selected model’s output limit.',
    },
    'openai_reasoning_effort': {
        'label': 'Reasoning Effort',
        'type': 'select',
        'options': ['none', 'low', 'medium', 'high', 'xhigh'],
        'help': 'How much internal reasoning the model performs before answering. Higher effort can improve quality on complex prompts but costs more and is slower. "none" disables extended reasoning.',
    },
    'openai_verbosity': {
        'label': 'Verbosity',
        'type': 'select',
        'options': ['low', 'medium', 'high'],
        'help': 'Controls how expansive the model\'s replies are, independent of reasoning effort. Lower is more concise.',
    },
}

DEFAULT_MODEL = 'gpt-4o-mini'

MODELS: Dict[str, Dict[str, Any]] = {
    'gpt-4o-mini': {
        'display_name': 'GPT-4o mini',
        'description': 'Fast and low-cost. Recommended default for high-volume question generation.',
        'max_output_tokens_cap': 16384,
        'family': 'standard',
        'defaults': {
            'openai_temperature': 0.55,
            'openai_top_p': 1.0,
            'openai_frequency_penalty': 0.3,
            'openai_presence_penalty': 0.2,
            'openai_max_tokens': 4096,
        },
    },
    'gpt-4o': {
        'display_name': 'GPT-4o',
        'description': 'Flagship multimodal model. Higher quality than the mini variant, at higher cost/latency.',
        'max_output_tokens_cap': 16384,
        'family': 'standard',
        'defaults': {
            'openai_temperature': 0.6,
            'openai_top_p': 1.0,
            'openai_frequency_penalty': 0.3,
            'openai_presence_penalty': 0.2,
            'openai_max_tokens': 4096,
        },
    },
    'gpt-4.1': {
        'display_name': 'GPT-4.1',
        'description': 'Improved reasoning and instruction-following over GPT-4o for complex question sets.',
        'max_output_tokens_cap': 16384,
        'family': 'standard',
        'defaults': {
            'openai_temperature': 0.6,
            'openai_top_p': 1.0,
            'openai_frequency_penalty': 0.3,
            'openai_presence_penalty': 0.2,
            'openai_max_tokens': 4096,
        },
    },
    'gpt-4.1-mini': {
        'display_name': 'GPT-4.1 mini',
        'description': 'Balanced cost/quality option between GPT-4.1 and GPT-4.1 nano.',
        'max_output_tokens_cap': 16384,
        'family': 'standard',
        'defaults': {
            'openai_temperature': 0.55,
            'openai_top_p': 1.0,
            'openai_frequency_penalty': 0.3,
            'openai_presence_penalty': 0.2,
            'openai_max_tokens': 4096,
        },
    },
    'gpt-4.1-nano': {
        'display_name': 'GPT-4.1 nano',
        'description': 'Cheapest and fastest 4.1-family model. Best for simple/short question batches.',
        'max_output_tokens_cap': 16384,
        'family': 'standard',
        'defaults': {
            'openai_temperature': 0.5,
            'openai_top_p': 1.0,
            'openai_frequency_penalty': 0.3,
            'openai_presence_penalty': 0.2,
            'openai_max_tokens': 4096,
        },
    },
    'gpt-3.5-turbo': {
        'display_name': 'GPT-3.5 Turbo',
        'description': 'Legacy low-cost model, kept for compatibility. Lower quality than the GPT-4 family.',
        'max_output_tokens_cap': 4096,
        'family': 'standard',
        'defaults': {
            'openai_temperature': 0.7,
            'openai_top_p': 1.0,
            'openai_frequency_penalty': 0.3,
            'openai_presence_penalty': 0.2,
            'openai_max_tokens': 2048,
        },
    },
    # Reasoning-family models (GPT-5.x): no temperature/top_p/penalties - see
    # PARAM_ORDER_BY_FAMILY['reasoning']. These use max_completion_tokens
    # instead of max_tokens under the hood (handled in the generator/validator).
    'gpt-5.4-mini': {
        'display_name': 'GPT-5.4 mini',
        'description': 'Smaller, faster reasoning model. Good balance of reasoning quality and cost.',
        'max_output_tokens_cap': 128000,
        'family': 'reasoning',
        'defaults': {
            'openai_reasoning_effort': 'medium',
            'openai_verbosity': 'medium',
            'openai_max_tokens': 8192,
        },
    },
    'gpt-5.4': {
        'display_name': 'GPT-5.4',
        'description': 'Reasoning-optimized flagship model. Higher quality on complex prompts than the mini variant.',
        'max_output_tokens_cap': 128000,
        'family': 'reasoning',
        'defaults': {
            'openai_reasoning_effort': 'medium',
            'openai_verbosity': 'medium',
            'openai_max_tokens': 8192,
        },
    },
    'gpt-5.5': {
        'display_name': 'GPT-5.5',
        'description': 'Latest, most capable reasoning model. Best quality, highest cost/latency.',
        'max_output_tokens_cap': 128000,
        'family': 'reasoning',
        'defaults': {
            'openai_reasoning_effort': 'medium',
            'openai_verbosity': 'medium',
            'openai_max_tokens': 8192,
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
    """Return the max completion-token ceiling for a model (fallback: 4096)."""
    return get_model_config(model_id).get('max_output_tokens_cap', 4096)


def get_model_params(model_id: str) -> List[Dict[str, Any]]:
    """Return the ordered param definitions (with per-model max/default filled in) for a model.

    The param set itself depends on the model's family - 'standard' models get
    temperature/top_p/penalties, 'reasoning' models (e.g. GPT-5.x) get
    reasoning_effort/verbosity instead.
    """
    cfg = get_model_config(model_id)
    defaults = cfg['defaults']
    family = cfg.get('family', 'standard')
    param_order = PARAM_ORDER_BY_FAMILY.get(family, PARAM_ORDER_BY_FAMILY['standard'])
    params = []
    for key in param_order:
        info = dict(PARAM_INFO[key])
        info['key'] = key
        if key == 'openai_max_tokens':
            info['max'] = cfg.get('max_output_tokens_cap', 4096)
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
