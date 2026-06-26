"""
This module was intentionally removed: GitHub API integration is no longer supported in Avirta.

Stub kept to avoid import errors if any stale references remain.
"""

class GitHubIntegration:
    def __init__(self, *args, **kwargs):
        raise NotImplementedError("GitHub integration has been removed from this project.")

    def __getattr__(self, name):  # Any method access will raise
        raise NotImplementedError("GitHub integration has been removed from this project.")
