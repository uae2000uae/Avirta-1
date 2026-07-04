"""
Git Push Helper for Avirta - Commits and pushes all amended files to GitHub.

This module provides web-accessible functions to stage, commit, and push all
amended files to the GitHub repository using the native git command (not the
GitHub API). This is designed to work with Cloud Run and local environments.
"""

import subprocess
import threading
from datetime import datetime, timezone
from typing import Tuple, Optional, Dict
import os

# Thread-safe push progress state
_progress_lock = threading.Lock()
_progress_status = {
    "status": "idle",       # "idle", "running", "success", "failed"
    "message": "",
    "errors": [],
    "files_count": 0,
    "current_branch": "main"
}


def get_push_progress() -> dict:
    """Get a copy of the current push progress status."""
    with _progress_lock:
        return _progress_status.copy()


def update_progress(status: Optional[str] = None, message: Optional[str] = None, 
                    files_count: Optional[int] = None, error: Optional[str] = None,
                    branch: Optional[str] = None):
    """Update progress tracking dict in a thread-safe manner."""
    with _progress_lock:
        if status is not None: 
            _progress_status["status"] = status
        if message is not None: 
            _progress_status["message"] = message
        if files_count is not None: 
            _progress_status["files_count"] = files_count
        if error is not None: 
            _progress_status["errors"].append(error)
        if branch is not None:
            _progress_status["current_branch"] = branch


def _run_git_command(args: list, cwd: Optional[str] = None) -> Tuple[bool, str]:
    """
    Run a git command and return (success, output_or_error).
    
    Args:
        args: List of git command arguments (e.g., ['add', '-A'])
        cwd: Working directory (defaults to repo root)
    
    Returns:
        Tuple of (success: bool, output: str)
    """
    if not cwd:
        cwd = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    try:
        result = subprocess.run(
            ['git'] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            return False, result.stderr.strip()
    except subprocess.TimeoutExpired:
        return False, "Git command timed out"
    except Exception as e:
        return False, str(e)


def get_current_branch(repo_root: Optional[str] = None) -> Tuple[bool, str]:
    """
    Get the current git branch name.
    
    Returns:
        Tuple of (success: bool, branch_name: str)
    """
    success, output = _run_git_command(['rev-parse', '--abbrev-ref', 'HEAD'], cwd=repo_root)
    return success, output if success else "main"


def get_status(repo_root: Optional[str] = None) -> Tuple[int, str]:
    """
    Get git status summary.
    
    Returns:
        Tuple of (file_count: int, status_output: str)
    """
    success, output = _run_git_command(['status', '--porcelain'], cwd=repo_root)
    if success:
        lines = [line.strip() for line in output.split('\n') if line.strip()]
        return len(lines), '\n'.join(lines)
    return 0, ""


def push_all_amended_files_async(repo_root: Optional[str] = None, commit_message: Optional[str] = None,
                                  detach: bool = True) -> Tuple[bool, str]:
    """
    Asynchronously stage, commit, and push all amended files to GitHub.
    
    Args:
        repo_root: Path to repository root (auto-detected if None)
        commit_message: Custom commit message (defaults to "Update amended files")
        detach: If True, run in background thread; if False, run synchronously
    
    Returns:
        Tuple of (success: bool, message: str)
    """
    with _progress_lock:
        if _progress_status["status"] == "running":
            return False, "A push is already in progress."

    def _run():
        try:
            # Detect repo root if not provided
            if not repo_root:
                repo_root_local = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            else:
                repo_root_local = repo_root
            
            update_progress(status="running", message="Initializing git push...")
            
            # Get current branch
            success, branch = get_current_branch(repo_root_local)
            if not success:
                branch = "main"
            update_progress(branch=branch)
            
            # Get status
            file_count, status_output = get_status(repo_root_local)
            if file_count == 0:
                update_progress(status="success", message="No changes to commit. Everything is up to date.", files_count=0)
                return
            
            update_progress(message=f"Detected {file_count} changed files", files_count=file_count)
            
            # Stage all changes
            update_progress(message="[1/3] Staging all amended files...")
            success, output = _run_git_command(['add', '-A'], cwd=repo_root_local)
            if not success:
                update_progress(status="failed", message="Failed to stage files", error=output)
                return
            
            # Create commit
            if not commit_message:
                commit_message = "Update amended files"
            
            update_progress(message=f"[2/3] Creating commit: '{commit_message}'")
            success, output = _run_git_command([
                'commit',
                '-m', commit_message,
                '--author=Copilot <223556219+Copilot@users.noreply.github.com>',
                '-m', 'Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>'
            ], cwd=repo_root_local)
            
            if not success:
                if "nothing to commit" in output.lower():
                    update_progress(status="success", message="No changes to commit.", files_count=file_count)
                    return
                update_progress(status="failed", message="Failed to create commit", error=output)
                return
            
            # Push to GitHub
            update_progress(message=f"[3/3] Pushing to GitHub branch: {branch}")
            success, output = _run_git_command(['push', 'origin', branch], cwd=repo_root_local)
            
            if not success:
                update_progress(status="failed", message="Failed to push to GitHub", error=output)
                return
            
            update_progress(
                status="success",
                message=f"Successfully pushed {file_count} changed files to GitHub ({branch})",
                files_count=file_count
            )
            
        except Exception as e:
            update_progress(status="failed", message=f"Unexpected error during push: {str(e)}", error=str(e))

    if detach:
        threading.Thread(target=_run, daemon=True).start()
        return True, "push_started"
    else:
        _run()
        progress = get_push_progress()
        return progress["status"] == "success", progress["message"]


# CLI entrypoint for direct execution
if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Avirta Git Push Helper - Push all amended files to GitHub")
    parser.add_argument('--message', type=str, default=None, help='Custom commit message')
    parser.add_argument('--repo', type=str, default=None, help='Repository root path')
    args = parser.parse_args()
    
    print("Avirta - Git Push Helper")
    print("========================\n")
    
    # Check current branch
    success, branch = get_current_branch(args.repo)
    print(f"Current branch: {branch}")
    
    # Get status
    file_count, status_output = get_status(args.repo)
    if file_count == 0:
        print("\nNo changes to commit. Everything is up to date.")
        sys.exit(0)
    
    print(f"\nDetected {file_count} changed files:")
    print(status_output)
    print()
    
    # Confirm
    response = input("Commit and push these changes? (y/n): ").strip().lower()
    if response != 'y':
        print("Push cancelled.")
        sys.exit(0)
    
    # Get commit message
    if not args.message:
        user_input = input("Enter commit message (or press Enter for default): ").strip()
        args.message = user_input if user_input else "Update amended files"
    
    print(f"\nCommitting with message: '{args.message}'\n")
    
    # Push synchronously
    success, message = push_all_amended_files_async(
        repo_root=args.repo,
        commit_message=args.message,
        detach=False
    )
    
    print(f"\nResult: {message}\n")
    sys.exit(0 if success else 1)
