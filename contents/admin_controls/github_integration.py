"""
GitHub Integration for Avirta

Provides a small utility to push local question JSON files to a GitHub repository
using the GitHub Contents API. This module is designed to be used anywhere in the
application (e.g., automatic push after a game session ends or from admin commands).

- Repository owner: uae2000uae (dynamically resolved from git/env as fallback)
- Repository name: Avirta-WebApp (dynamically resolved from git/env as fallback)
- Branch: default branch of the repository (resolved dynamically)
- Token source: Google Secret Manager/env under secret/env var name: GITHUB_TOKEN

Notes
- This module performs best-effort operations and raises only when explicitly
  requested via raise_on_error flag. By default, it logs and returns (False, msg)
  rather than crashing the caller.
- Only text files are supported through the Contents API. Our use case is JSON
  files under contents/questions/.
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import subprocess
import sys
import threading
from datetime import datetime, timezone
from typing import Iterable, List, Tuple, Optional, Dict

import requests

try:
    # Prefer runtime secret via our helper if available
    from contents.admin_controls.secret_loader import get_secret as _get_secret
except Exception:  # pragma: no cover - fallback if helper path changes
    _get_secret = None

GITHUB_API = "https://api.github.com"
REPO_OWNER = "uae2000uae"
REPO_NAME = "Avirta-WebApp"


# Thread-safe upload progress state
_progress_lock = threading.Lock()
_progress_status = {
    "status": "idle",       # "idle", "running", "success", "failed"
    "total": 0,
    "current": 0,
    "current_file": "",
    "message": "",
    "errors": [],
    "start_time": "",
    "completed_time": ""
}


def get_upload_progress() -> dict:
    """Get a copy of the current upload progress status."""
    with _progress_lock:
        return _progress_status.copy()


def update_progress(status: Optional[str] = None, total: Optional[int] = None, current: Optional[int] = None, 
                    current_file: Optional[str] = None, message: Optional[str] = None, error: Optional[str] = None):
    """Update progress tracking dict in a thread-safe manner."""
    with _progress_lock:
        if status is not None:
            _progress_status["status"] = status
        if total is not None:
            _progress_status["total"] = total
        if current is not None:
            _progress_status["current"] = current
        if current_file is not None:
            _progress_status["current_file"] = current_file
        if message is not None:
            _progress_status["message"] = message
        if error is not None:
            _progress_status["errors"].append(error)


def _resolve_token() -> Optional[str]:
    """Resolve GitHub token from env or Secret Manager.

    Order:
    1) GITHUB_TOKEN, GITHUB_API_TOKEN, or GH_TOKEN env vars
    2) Secret Manager via helper get_secret('GITHUB_TOKEN') if available
    """
    for env_name in ["GITHUB_TOKEN", "GITHUB_API_TOKEN", "GH_TOKEN"]:
        token = os.environ.get(env_name)
        if token and str(token).strip():
            return str(token).strip()

    if _get_secret is not None:
        try:
            token = _get_secret("GITHUB_TOKEN")
            if token and str(token).strip() and str(token).strip().upper() != "SET_IN_ENV":
                return str(token).strip()
        except Exception:
            pass
    return None


def _resolve_repo_details() -> Tuple[str, str]:
    """Resolve GitHub repository owner and name.

    Order:
    1) GITHUB_REPOSITORY env var (format: "owner/repo")
    2) GITHUB_OWNER and GITHUB_REPO env vars
    3) Local git remote "origin" URL via subprocess or .git/config
    4) Default constants
    """
    # 1) GITHUB_REPOSITORY (standard GitHub Actions / environment variable)
    git_repo_env = os.environ.get("GITHUB_REPOSITORY")
    if git_repo_env and "/" in git_repo_env:
        parts = git_repo_env.split("/", 1)
        return parts[0].strip(), parts[1].strip()

    # 2) GITHUB_OWNER and GITHUB_REPO
    env_owner = os.environ.get("GITHUB_OWNER")
    env_repo = os.environ.get("GITHUB_REPO")
    if env_owner and env_repo:
        return env_owner.strip(), env_repo.strip()

    # 3) Local git remote "origin" URL
    try:
        # Run git remote get-url origin
        res = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5
        )
        url = res.stdout.strip()
        if url:
            if "github.com" in url:
                if url.endswith(".git"):
                    url = url[:-4]
                if "github.com:" in url:
                    parts = url.split("github.com:", 1)[1].split("/")
                else:
                    parts = url.split("github.com/", 1)[1].split("/")
                if len(parts) >= 2:
                    return parts[0].strip(), parts[1].strip()
    except Exception:
        # Fallback to parsing .git/config manually if subprocess fails
        try:
            project_root = pathlib.Path(__file__).resolve().parents[2]
            config_path = project_root / ".git" / "config"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    content = f.read()
                for line in content.splitlines():
                    if "url =" in line:
                        url = line.split("url =", 1)[1].strip()
                        if "github.com" in url:
                            if url.endswith(".git"):
                                url = url[:-4]
                            if "github.com:" in url:
                                parts = url.split("github.com:", 1)[1].split("/")
                            else:
                                parts = url.split("github.com/", 1)[1].split("/")
                            if len(parts) >= 2:
                                return parts[0].strip(), parts[1].strip()
        except Exception:
            pass

    # 4) Default constants
    return REPO_OWNER, REPO_NAME


def _get_changed_question_files() -> List[str]:
    """Return a list of question JSON files under contents/questions/ that are modified, staged, or untracked in Git."""
    import subprocess
    import pathlib
    
    project_root = pathlib.Path(__file__).resolve().parents[2]
    changed_files = set()
    
    # 1) Get modified/staged tracked files from Git
    try:
        res = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=5
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                p_norm = pathlib.Path(project_root / line)
                # Check if file is in contents/questions/ and is a JSON file
                if "contents/questions" in line.replace("\\", "/") and line.endswith(".json"):
                    if p_norm.exists() and p_norm.is_file():
                        changed_files.add(str(p_norm))
    except Exception:
        pass

    # 2) Get untracked files from Git
    try:
        res = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            capture_output=True,
            text=True,
            cwd=str(project_root),
            timeout=5
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                line = line.strip()
                if not line:
                    continue
                p_norm = pathlib.Path(project_root / line)
                if "contents/questions" in line.replace("\\", "/") and line.endswith(".json"):
                    if p_norm.exists() and p_norm.is_file():
                        changed_files.add(str(p_norm))
    except Exception:
        pass
        
    return sorted(list(changed_files))


class GitHubIntegration:
    """Minimal GitHub client focused on pushing content files."""

    def __init__(self, owner: Optional[str] = None, repo: Optional[str] = None, token: Optional[str] = None):
        resolved_owner, resolved_repo = _resolve_repo_details()
        self.owner = owner or resolved_owner
        self.repo = repo or resolved_repo
        self.token = token or _resolve_token()
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "Avirta-GitHubIntegration/1.0"
            })
        else:
            # Still set UA/Accept for unauthenticated calls (will fail on write)
            self.session.headers.update({
                "Accept": "application/vnd.github+json",
                "User-Agent": "Avirta-GitHubIntegration/1.0"
            })
        self._default_branch_cache: Optional[str] = None

    # ------------------------- Core API helpers -------------------------
    def get_default_branch(self) -> Tuple[bool, str]:
        if self._default_branch_cache:
            return True, self._default_branch_cache
        url = f"{GITHUB_API}/repos/{self.owner}/{self.repo}"
        try:
            r = self.session.get(url, timeout=20)
            if r.status_code == 200:
                data = r.json()
                branch = data.get("default_branch") or "main"
                self._default_branch_cache = branch
                return True, branch
            else:
                return False, f"Failed to get repo info ({r.status_code}): {r.text[:200]}"
        except Exception as e:
            return False, f"Error getting default branch: {e}"

    def get_file_sha(self, path_in_repo: str, branch: Optional[str] = None) -> Tuple[bool, Optional[str], str]:
        """Return (ok, sha, message). ok=False if not found or error; sha may be None when not found."""
        ok, default_branch_or_msg = self.get_default_branch() if not branch else (True, branch)
        if not ok:
            return False, None, default_branch_or_msg  # error message
        branch = str(default_branch_or_msg)
        url = f"{GITHUB_API}/repos/{self.owner}/{self.repo}/contents/{path_in_repo}"
        params = {"ref": branch}
        try:
            r = self.session.get(url, params=params, timeout=20)
            if r.status_code == 200:
                data = r.json()
                return True, data.get("sha"), "OK"
            elif r.status_code == 404:
                return False, None, "Not found"
            else:
                return False, None, f"Failed to get file ({r.status_code}): {r.text[:200]}"
        except Exception as e:
            return False, None, f"Error getting file sha: {e}"

    def put_file(self, path_in_repo: str, content_bytes: bytes, commit_message: str,
                 branch: Optional[str] = None) -> Tuple[bool, str]:
        """Create or update a file using the Contents API."""
        if not self.token:
            return False, "Missing GITHUB_TOKEN. Configure in Secret Manager/env."
        ok, branch_or_msg = self.get_default_branch() if not branch else (True, branch)
        if not ok:
            return False, branch_or_msg
        branch = str(branch_or_msg)

        # Check if file exists to include sha for update
        exists_ok, sha, _ = self.get_file_sha(path_in_repo, branch)
        if exists_ok:
            current_sha = sha
        else:
            current_sha = None  # create path

        url = f"{GITHUB_API}/repos/{self.owner}/{self.repo}/contents/{path_in_repo}"
        payload = {
            "message": commit_message,
            "content": base64.b64encode(content_bytes).decode("ascii"),
            "branch": branch,
        }
        if current_sha:
            payload["sha"] = current_sha
        try:
            r = self.session.put(url, json=payload, timeout=30)
            if r.status_code in (200, 201):
                return True, "Committed"
            else:
                return False, f"Failed to commit {path_in_repo} ({r.status_code}): {r.text[:200]}"
        except Exception as e:
            return False, f"Error committing {path_in_repo}: {e}"

    # ------------------------- High-level helpers -------------------------
    def push_files(self, local_paths: Iterable[str], repo_base_path: str = "", branch: Optional[str] = None) -> Tuple[bool, Dict[str, str]]:
        """Push a collection of files to the repository.

        Args:
            local_paths: iterable of absolute or project-relative paths.
            repo_base_path: prefix folder inside the repo where files will be placed.
            branch: optional override branch name.
        Returns:
            (overall_ok, results) where results maps repo_path -> status/message
        """
        results: Dict[str, str] = {}
        overall_ok = True
        # Determine commit message with timestamp
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        commit_msg_base = f"Avirta: Update question files ({now})"

        # Resolve project root
        project_root = pathlib.Path(__file__).resolve().parents[2]  # .../Avirta

        local_paths_list = list(local_paths)
        total_files = len(local_paths_list)
        
        # Reset progress
        update_progress(status="running", total=total_files, current=0, current_file="", message="Scanning files...")

        for idx, lp in enumerate(local_paths_list):
            try:
                p = pathlib.Path(lp)
                if not p.is_absolute():
                    p = (project_root / p).resolve()
                
                rel_name = p.name
                update_progress(current=idx, current_file=rel_name, message=f"Uploading {rel_name} ({idx+1}/{total_files})...")

                if not p.exists() or not p.is_file():
                    results[str(lp)] = "Skip: not found"
                    overall_ok = False
                    update_progress(error=f"File not found: {lp}")
                    continue
                
                # Build repo path: either keep relative from project root or place under repo_base_path
                try:
                    rel = p.relative_to(project_root).as_posix()
                except Exception:
                    rel = p.name
                repo_path = f"{repo_base_path.rstrip('/')}/{rel}" if repo_base_path else rel
                with open(p, "rb") as f:
                    content = f.read()
                
                ok, msg = self.put_file(repo_path, content, f"{commit_msg_base}: {rel}", branch=branch)
                results[repo_path] = msg
                if not ok:
                    overall_ok = False
                    update_progress(error=f"Failed to upload {rel}: {msg}")
            except Exception as e:
                results[str(lp)] = f"Error: {e}"
                overall_ok = False
                update_progress(error=f"Error in {lp}: {e}")

        return overall_ok, results

    def push_all_questions(self, questions_dir: Optional[str] = None, branch: Optional[str] = None) -> Tuple[bool, Dict[str, str]]:
        """Push all JSON files from contents/questions to the repo, preserving paths."""
        # Default directory
        project_root = pathlib.Path(__file__).resolve().parents[2]
        qdir = pathlib.Path(questions_dir) if questions_dir else project_root / "contents" / "questions"
        files: List[str] = []
        if qdir.exists():
            for p in qdir.rglob("*.json"):
                files.append(str(p))
        return self.push_files(files, branch=branch)

    def push_changed_questions(self, branch: Optional[str] = None) -> Tuple[bool, Dict[str, str]]:
        """Find and push only changed or untracked JSON files under contents/questions/."""
        changed_files = _get_changed_question_files()
        if not changed_files:
            return True, {"No changes": "No modified or untracked question files detected in git."}
        return self.push_files(changed_files, branch=branch)


# ------------------------- Convenience API -------------------------

def push_all_amended_questions_async(detach: bool = True, branch: Optional[str] = None) -> Tuple[bool, str]:
    """Convenience function to push only changed/untracked question files.

    If detach=True, it spawns a thread to avoid blocking the caller and returns immediately.
    Returns (True, 'spawned') when detached, or (ok, summary_message) when run synchronously.
    """
    with _progress_lock:
        if _progress_status["status"] == "running":
            return False, "An upload is already in progress."

    def _run() -> Tuple[bool, str]:
        try:
            gh = GitHubIntegration()
            # Check token first
            if not gh.token:
                update_progress(status="failed", message="Missing GITHUB_TOKEN. Configure in Secret Manager/env.")
                return False, "Missing GITHUB_TOKEN"
            
            # Resolve branch if not provided
            ok_b, branch_name = gh.get_default_branch() if not branch else (True, branch)
            if not ok_b:
                update_progress(status="failed", message=f"Failed to resolve default branch: {branch_name}")
                return False, f"Failed to resolve branch: {branch_name}"

            # Start time
            with _progress_lock:
                _progress_status["errors"] = []
                _progress_status["start_time"] = datetime.now(timezone.utc).isoformat()

            ok, results = gh.push_changed_questions(branch=branch_name)
            
            with _progress_lock:
                _progress_status["completed_time"] = datetime.now(timezone.utc).isoformat()

            if "No changes" in results:
                update_progress(status="success", message="No changes to upload. Repository is up-to-date.")
                return True, "No changed files detected."

            # Build a compact summary
            failures = [k for k, v in results.items() if not v.startswith("Committed")]

            if ok:
                update_progress(status="success", message=f"Pushed {len(results)} changed files successfully.")
                return True, f"Pushed {len(results)} changed files successfully."
            else:
                update_progress(status="failed", message=f"Completed with {len(failures)} failures out of {len(results)} files.")
                return False, f"Completed with {len(failures)} failures out of {len(results)} files."
        except Exception as e:
            update_progress(status="failed", message=f"Unexpected error during sync: {e}")
            return False, str(e)

    if detach:
        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return True, "spawned"
    else:
        return _run()


# ------------------------- CLI Entrypoint -------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
        description="Avirta Standalone GitHub Push tool. Pushes question JSON files to GitHub repository dynamically."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--files", nargs="+", help="Specific space-separated files to push to GitHub"
    )
    group.add_argument(
        "--all", action="store_true", help="Push all question files under contents/questions"
    )
    group.add_argument(
        "--changed", action="store_true", default=True, help="Push only changed/untracked question files (default behavior if --all or --files is not set)"
    )
    parser.add_argument(
        "--questions-dir", help="Override path to the questions directory to upload"
    )
    parser.add_argument(
        "--token", help="Override GITHUB_TOKEN"
    )
    parser.add_argument(
        "--owner", help="Override GitHub repo owner"
    )
    parser.add_argument(
        "--repo", help="Override GitHub repo name"
    )
    parser.add_argument(
        "--branch", help="Override GitHub target branch"
    )

    args = parser.parse_args()

    # Create the integration instance with optional overrides
    gh = GitHubIntegration(owner=args.owner, repo=args.repo, token=args.token)

    print("--- Avirta GitHub Standalone Push Command ---")
    print(f"Target repository: {gh.owner}/{gh.repo}")
    
    # Check token availability
    if not gh.token:
        print("ERROR: GitHub token is not configured or resolved.", file=sys.stderr)
        print("Please set the GITHUB_TOKEN environment variable, or pass it via --token.", file=sys.stderr)
        sys.exit(1)

    # Determine default branch or branch from arg
    ok_b, branch_name = gh.get_default_branch() if not args.branch else (True, args.branch)
    if not ok_b:
        print(f"ERROR resolving branch: {branch_name}", file=sys.stderr)
        sys.exit(1)
    print(f"Target branch: {branch_name}")

    if args.files:
        print(f"Uploading specific files: {args.files} ...")
        overall_ok, results = gh.push_files(args.files, branch=branch_name)
    elif args.all:
        print("Uploading all files from contents/questions ...")
        overall_ok, results = gh.push_all_questions(questions_dir=args.questions_dir, branch=branch_name)
    else:
        # Default is changed files only
        print("Uploading only changed/untracked files from contents/questions ...")
        overall_ok, results = gh.push_changed_questions(branch=branch_name)

    print("\n--- Push Results ---")
    for rpath, status in results.items():
        print(f"  {rpath} => {status}")

    if overall_ok:
        if "No changes" in results:
            print("\nSUCCESS: No modified or untracked question files were detected.")
        else:
            print("\nSUCCESS: All changed files successfully updated/skipped on GitHub.")
        sys.exit(0)
    else:
        print("\nFAILURE: One or more files failed to be pushed to GitHub.", file=sys.stderr)
        sys.exit(1)
