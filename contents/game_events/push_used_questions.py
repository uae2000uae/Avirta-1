"""
Deprecated module: GitHub snapshot push functionality was removed.

This stub remains to avoid import errors in any older code paths. It performs no actions.
"""
from __future__ import annotations

from typing import Tuple


def push_used_questions_snapshot(*args, **kwargs) -> Tuple[bool, str]:
    """No-op stub for removed GitHub snapshot feature.

    Returns:
        (False, message): Always indicates the feature was removed.
    """
    return False, "GitHub integration was removed from Avirta; snapshot push is no longer available." 
