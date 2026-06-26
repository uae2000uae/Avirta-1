"""
Simplified and Efficient GitHub Integration for Avirta using MD5 Hash Tracking.

Only uploads changed files by tracking local file hashes in file_hashes.json.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import threading
from datetime import datetime, timezone
from typing import List, Tuple, Optional, Dict

import requests

try:
    from contents.admin_controls.secret_loader import get_secret as _get_secret
except Exception:
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
    "errors": []
}


def get_upload_progress() -> dict:
    """Get a copy of the current upload progress status."""
    with _progress_lock:
        return _progress_status.copy()


def update_progress(status: Optional[str] = None, total: Optional[int] = None, current: Optional[int] = None, 
                    current_file: Optional[str] = None, message: Optional[str] = None, error: Optional[str] = None):
    """Update progress tracking dict in a thread-safe manner."""
    with _progress_lock:
        if status is not None: _progress_status["status"] = status
        if total is not None: _progress_status["total"] = total
        if current is not None: _progress_status["current"] = current
        if current_file is not None: _progress_status["current_file"] = current_file
        if message is not None: _progress_status["message"] = message
        if error is not None: _progress_status["errors"].append(error)


def _get_file_hash(path: pathlib.Path) -> str:
    """Compute MD5 hash of a file."""
    try:
        with open(path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()
    except Exception:
        return ""


def _load_hashes() -> Dict[str, str]:
    """Load cached file hashes from local JSON registry."""
    path = pathlib.Path(__file__).resolve().parent / "file_hashes.json"
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_hashes(hashes: Dict[str, str]):
    """Save file hashes registry locally."""
    path = pathlib.Path(__file__).resolve().parent / "file_hashes.json"
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(hashes, f, indent=4)
    except Exception:
        pass


def _resolve_token() -> Optional[str]:
    """Resolve GITHUB_TOKEN from env or Secret Manager."""
    for name in ["GITHUB_TOKEN", "GITHUB_API_TOKEN", "GH_TOKEN"]:
        t = os.environ.get(name)
        if t and t.strip():
            return t.strip()
    if _get_secret:
        try:
            t = _get_secret("GITHUB_TOKEN")
            if t and t.strip() and t.strip().upper() != "SET_IN_ENV":
                return t.strip()
        except Exception:
            pass
    return None


def _resolve_repo_details() -> Tuple[str, str]:
    """Resolve GitHub repository owner and name from env or git."""
    repo_env = os.environ.get("GITHUB_REPOSITORY")
    if repo_env and "/" in repo_env:
        parts = repo_env.split("/", 1)
        return parts[0].strip(), parts[1].strip()
    
    owner = os.environ.get("GITHUB_OWNER")
    repo = os.environ.get("GITHUB_REPO")
    if owner and repo:
        return owner.strip(), repo.strip()
        
    try:
        res = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, check=True, timeout=3
        )
        url = res.stdout.strip()
        if "github.com" in url:
            if url.endswith(".git"): url = url[:-4]
            parts = url.split("github.com:", 1)[1].split("/") if "github.com:" in url else url.split("github.com/", 1)[1].split("/")
            return parts[0].strip(), parts[1].strip()
    except Exception:
        pass
        
    return REPO_OWNER, REPO_NAME


class GitHubIntegration:
    """Minimal GitHub client focused on pushing content files."""

    def __init__(self, owner: Optional[str] = None, repo: Optional[str] = None, token: Optional[str] = None):
        res_owner, res_repo = _resolve_repo_details()
        self.owner = owner or res_owner
        self.repo = repo or res_repo
        self.token = token or _resolve_token()
        self.session = requests.Session()
        if self.token:
            self.session.headers.update({
                "Authorization": f"token {self.token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "Avirta-GitHubIntegration/1.0"
            })
        self._default_branch_cache: Optional[str] = None

    def get_default_branch(self) -> Tuple[bool, str]:
        if self._default_branch_cache:
            return True, self._default_branch_cache
        url = f"{GITHUB_API}/repos/{self.owner}/{self.repo}"
        try:
            r = self.session.get(url, timeout=15)
            if r.status_code == 200:
                branch = r.json().get("default_branch") or "main"
                self._default_branch_cache = branch
                return True, branch
            return False, f"HTTP {r.status_code}"
        except Exception as e:
            return False, str(e)

    def get_file_sha(self, path: str, branch: str) -> Optional[str]:
        """Get file SHA if it exists on GitHub."""
        url = f"{GITHUB_API}/repos/{self.owner}/{self.repo}/contents/{path}"
        try:
            r = self.session.get(url, params={"ref": branch}, timeout=15)
            if r.status_code == 200:
                return r.json().get("sha")
        except Exception:
            pass
        return None

    def put_file(self, repo_path: str, content: bytes, message: str, branch: str) -> bool:
        """Create or update a file on GitHub."""
        url = f"{GITHUB_API}/repos/{self.owner}/{self.repo}/contents/{repo_path}"
        sha = self.get_file_sha(repo_path, branch)
        payload = {
            "message": message,
            "content": base64.b64encode(content).decode("ascii"),
            "branch": branch
        }
        if sha:
            payload["sha"] = sha
        try:
            r = self.session.put(url, json=payload, timeout=25)
            return r.status_code in (200, 201)
        except Exception:
            return False

    def push_files(self, files: List[str], branch: str) -> Tuple[bool, Dict[str, str]]:
        """Commit a list of files to the repository."""
        project_root = pathlib.Path(__file__).resolve().parents[2]
        results = {}
        ok = True
        
        total = len(files)
        update_progress(status="running", total=total, current=0, current_file="", message="Uploading changes...")
        
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        commit_msg = f"Avirta: Update questions ({now})"

        for idx, file_path in enumerate(files):
            p = pathlib.Path(file_path)
            rel = p.relative_to(project_root).as_posix()
            
            update_progress(current=idx, current_file=p.name, message=f"Uploading {p.name} ({idx+1}/{total})...")
            
            try:
                with open(p, "rb") as f:
                    content = f.read()
                if self.put_file(rel, content, f"{commit_msg}: {p.name}", branch):
                    results[rel] = "Committed"
                else:
                    results[rel] = "Failed"
                    ok = False
                    update_progress(error=f"Upload failed for {p.name}")
            except Exception as e:
                results[rel] = f"Error: {e}"
                ok = False
                update_progress(error=f"Error reading {p.name}: {e}")
                
        return ok, results

    def push_all_questions(self, questions_dir: Optional[str] = None, branch: Optional[str] = None) -> Tuple[bool, Dict[str, str]]:
        """Force-push all local questions to the repository."""
        project_root = pathlib.Path(__file__).resolve().parents[2]
        qdir = pathlib.Path(questions_dir) if questions_dir else project_root / "contents" / "questions"
        files = [str(p) for p in qdir.rglob("*.json")] if qdir.exists() else []
        
        ok_b, b_name = self.get_default_branch() if not branch else (True, branch)
        if not ok_b:
            return False, {"Error": f"Branch resolution failed: {b_name}"}
            
        ok, results = self.push_files(files, b_name)
        if ok:
            hashes = {}
            for f in files:
                p = pathlib.Path(f)
                rel = p.relative_to(project_root).as_posix()
                hashes[rel] = _get_file_hash(p)
            _save_hashes(hashes)
            
        return ok, results

    def push_changed_questions(self, branch: Optional[str] = None) -> Tuple[bool, Dict[str, str]]:
        """Upload only changed or untracked JSON files using MD5 hashes comparison."""
        project_root = pathlib.Path(__file__).resolve().parents[2]
        qdir = project_root / "contents" / "questions"
        
        ok_b, b_name = self.get_default_branch() if not branch else (True, branch)
        if not ok_b:
            return False, {"Error": f"Branch resolution failed: {b_name}"}

        saved_hashes = _load_hashes()
        
        # On first run, register current files' hashes as a baseline to prevent uploading all files
        if not saved_hashes:
            hashes = {}
            if qdir.exists():
                for p in qdir.rglob("*.json"):
                    rel = p.relative_to(project_root).as_posix()
                    hashes[rel] = _get_file_hash(p)
            _save_hashes(hashes)
            return True, {"No changes": "First-run hash registry baselined. Repository considered up-to-date."}

        changed_files = []
        new_hashes = saved_hashes.copy()
        
        if qdir.exists():
            for p in qdir.rglob("*.json"):
                rel = p.relative_to(project_root).as_posix()
                h = _get_file_hash(p)
                if h and saved_hashes.get(rel) != h:
                    changed_files.append(str(p))
                    new_hashes[rel] = h

        if not changed_files:
            return True, {"No changes": "All question files are up-to-date."}

        ok, results = self.push_files(changed_files, b_name)
        if ok:
            _save_hashes(new_hashes)
        return ok, results


# ------------------------- Convenience API -------------------------

def push_all_amended_questions_async(detach: bool = True, branch: Optional[str] = None) -> Tuple[bool, str]:
    """Asynchronously push only changed files."""
    with _progress_lock:
        if _progress_status["status"] == "running":
            return False, "An upload is already in progress."

    def _run():
        gh = GitHubIntegration()
        if not gh.token:
            update_progress(status="failed", message="Missing GITHUB_TOKEN.")
            return
        
        update_progress(status="running", message="Detecting changed files...")
        ok, results = gh.push_changed_questions(branch=branch)
        
        if "No changes" in results:
            update_progress(status="success", message=list(results.values())[0])
            return
            
        if ok:
            update_progress(status="success", message=f"Pushed {len(results)} changed files successfully.")
        else:
            update_progress(status="failed", message="Some files failed to upload.")

    if detach:
        threading.Thread(target=_run, daemon=True).start()
        return True, "spawned"
    else:
        _run()
        return _progress_status["status"] == "success", _progress_status["message"]


# ------------------------- CLI Entrypoint -------------------------

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Avirta Standalone GitHub Push tool.")
    parser.add_argument("--all", action="store_true", help="Push all question files")
    args = parser.parse_args()

    gh = GitHubIntegration()
    if not gh.token:
        print("ERROR: GitHub token not found.", file=sys.stderr)
        sys.exit(1)

    print(f"Target repository: {gh.owner}/{gh.repo}")
    if args.all:
        print("Uploading all questions...")
        ok, res = gh.push_all_questions()
    else:
        print("Uploading changed questions only...")
        ok, res = gh.push_changed_questions()

    print("\nResults:")
    for path, status in res.items():
        print(f"  {path} => {status}")
        
    sys.exit(0 if ok else 1)
