"""
Secret loader for Avirta

Resolves secrets from (in order):
1) Environment variables
2) Google Cloud Secret Manager (if available and permitted)

Usage:
    from contents.admin_controls.secret_loader import get_secret
    api_key = get_secret("ANTHROPIC_API_KEY")

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

# Cache the resolved project id (including a negative "" result) so we don't
# re-hit google.auth / the metadata server on every secret lookup.
_PROJECT_ID_CACHE = {"value": None, "resolved": False}


def _detect_project_id() -> Optional[str]:
    """Best-effort discovery of the GCP project id.

    Cloud Run does NOT set GOOGLE_CLOUD_PROJECT by default, so relying on env
    vars alone means the Secret Manager fallback never runs unless a secret was
    also injected as an env var via --set-secrets. This resolves the project id
    from, in order:
      1) env vars (GOOGLE_CLOUD_PROJECT / GCP_PROJECT / GCLOUD_PROJECT)
      2) Application Default Credentials (google.auth.default)
      3) the GCE/Cloud Run metadata server
    Result (including failure) is cached for the process lifetime.
    """
    if _PROJECT_ID_CACHE["resolved"]:
        return _PROJECT_ID_CACHE["value"]

    project_id = (
        os.environ.get("GOOGLE_CLOUD_PROJECT")
        or os.environ.get("GCP_PROJECT")
        or os.environ.get("GCLOUD_PROJECT")
    )

    # 2) Application Default Credentials
    if not project_id:
        try:
            import google.auth  # type: ignore
            _creds, adc_project = google.auth.default()
            if adc_project:
                project_id = adc_project
        except Exception:
            pass

    # 3) Metadata server (available on Cloud Run / GCE)
    if not project_id:
        try:
            import urllib.request
            req = urllib.request.Request(
                "http://metadata.google.internal/computeMetadata/v1/project/project-id",
                headers={"Metadata-Flavor": "Google"},
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                project_id = resp.read().decode("utf-8").strip() or None
        except Exception:
            pass

    _PROJECT_ID_CACHE["value"] = project_id or None
    _PROJECT_ID_CACHE["resolved"] = True
    return _PROJECT_ID_CACHE["value"]


def get_secret(key: str, default: Optional[str] = None) -> Optional[str]:
    """Return secret value for key from env or Google Secret Manager.

    Resolution order:
      1) Environment variable with exact name `key`
      2) Google Secret Manager: uses GOOGLE_CLOUD_PROJECT and secret name
         derived from `key`, but can be overridden by env var
         SECRET_<key>_NAME (e.g., SECRET_AI_Token_NAME)

    The returned value is stripped of whitespace and common prefixes like
    "Bearer ". If nothing can be resolved, returns `default`.
    """
    if not key:
        return default

    def _clean(val: Optional[str]) -> Optional[str]:
        if val is None:
            return None
        v = str(val).strip()
        if not v or v in essential_placeholders or v.lower() in {"none", "null"}:
            return None
        if v.lower().startswith("bearer "):
            v = v[7:].strip()
        return v

    # 1) Environment variable first
    val = _clean(os.environ.get(key))
    if val:
        return val

    # 2) Google Secret Manager (only if project id is available). Auto-detect
    #    the project id so this works on Cloud Run even when the secret was not
    #    injected as an env var via --set-secrets.
    project_id = _detect_project_id()
    if project_id:
        # Allow custom secret resource name via SECRET_<KEY>_NAME (no legacy name fallbacks)
        override_env_name = f"SECRET_{key}_NAME"
        secret_name = os.environ.get(override_env_name, key)

        # Try primary name first, with simple cache
        cache_key = (project_id, secret_name)
        if cache_key in _SECRET_CACHE:
            return _clean(_SECRET_CACHE[cache_key]) or default
        gsm_val = _clean(_gsm_access_secret(project_id, secret_name))
        if gsm_val:
            _SECRET_CACHE[cache_key] = gsm_val
            return gsm_val

    return default
