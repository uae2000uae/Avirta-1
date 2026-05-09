"""
Secret loader for Avirta

Resolves secrets from (in order):
1) Environment variables
2) Google Cloud Secret Manager (if available and permitted)

Usage:
    from contents.admin_controls.secret_loader import get_secret
    api_key = get_secret("OPENAI_API_KEY")

Notes:
- To override the secret name in GSM, set an env var named
  SECRET_<SECRETNAME>_NAME. Example: SECRET_OPENAI_API_KEY_NAME=MyOpenAIKey
- Requires google-cloud-secret-manager at runtime on GCP. Falls back gracefully
  if not installed or if permissions are missing.
"""
from __future__ import annotations

import os
from typing import Optional

# Try to import Google Secret Manager client lazily
try:
    from google.cloud import secretmanager  # type: ignore
    _GSM_AVAILABLE = True
except Exception:
    secretmanager = None  # type: ignore
    _GSM_AVAILABLE = False

# Simple in-process cache to avoid repeated GSM lookups
_SECRET_CACHE = {}


def _gsm_access_secret(project_id: str, secret_name: str) -> Optional[str]:
    if not _GSM_AVAILABLE:
        return None
    try:
        client = secretmanager.SecretManagerServiceClient()
        # Always read latest version
        name = f"projects/{project_id}/secrets/{secret_name}/versions/latest"
        response = client.access_secret_version(request={"name": name})
        payload = response.payload.data.decode("UTF-8").strip()
        return payload
    except Exception:
        # Any error (not found, permission, network) → return None to fall back
        return None


essential_placeholders = {"", None, "SET_IN_ENV"}


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Return secret value for key from env or Google Secret Manager.

    Resolution order:
      1) Environment variable with exact name `key`
      2) Google Secret Manager: uses GOOGLE_CLOUD_PROJECT and secret name
         derived from `key`, but can be overridden by env var
         SECRET_<key>_NAME (e.g., SECRET_OPENAI_API_KEY_NAME)

    If nothing can be resolved, returns `default`.
    """
    if not key:
        return default

    # 1) Environment variable first
    val = os.environ.get(key)
    if val and val not in essential_placeholders:
        return val

    # 2) Google Secret Manager (only if project id is available)
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCP_PROJECT")
    if project_id:
        # Allow custom secret resource name via SECRET_<KEY>_NAME
        override_env_name = f"SECRET_{key}_NAME"
        secret_name = os.environ.get(override_env_name, key)
        cache_key = (project_id, secret_name)
        if cache_key in _SECRET_CACHE:
            return _SECRET_CACHE[cache_key]
        gsm_val = _gsm_access_secret(project_id, secret_name)
        if gsm_val and gsm_val not in essential_placeholders:
            _SECRET_CACHE[cache_key] = gsm_val
            return gsm_val

    return default
