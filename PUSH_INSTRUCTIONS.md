# Push to GitHub Instructions

This document explains how to use the standalone "push to github" commands to commit and push all amended files to the GitHub repository.

## Quick Start

### Windows / Local Development
```bash
.\push-to-github.bat
```

### Cloud Run / Linux / Mac
```bash
bash push-to-github.sh
```

Or make it executable first:
```bash
chmod +x push-to-github.sh
./push-to-github.sh
```

## What the Scripts Do

1. **Verify Repository**: Checks that you're in a valid git repository
2. **Detect Changes**: Shows all modified, deleted, and untracked files
3. **Confirm Action**: Prompts for confirmation before proceeding (auto-confirms in non-interactive mode on Cloud Run)
4. **Stage Changes**: Adds all changes to the git staging area
5. **Create Commit**: Creates a commit with an optional custom message (defaults to "Update amended files")
6. **Push to GitHub**: Pushes the commit to the current branch

## Important Notes

### Cloud Run Compatibility
- The shell script (`push-to-github.sh`) is designed to work on **Cloud Run** and other Unix/Linux environments
- It runs in **non-interactive mode** when called from Cloud Run (automatically proceeds without prompting)
- The batch script (`push-to-github.bat`) works on **Windows** locally

### Authentication
- Requires valid Git credentials (SSH key or personal access token)
- Ensure `GITHUB_TOKEN` secret is available on Cloud Run (already configured in `cloudbuild.yaml`)

### What Gets Committed
- All modified files
- New untracked files
- Deleted files
- The scripts exclude files listed in `.gitignore` (including Python cache, `.env`, IDE configs, etc.)

### Git Commit Attribution
- Commits are attributed to: `Copilot <223556219+Copilot@users.noreply.github.com>`
- Includes standard co-author footer

## Examples

### Example 1: Using on Cloud Run (non-interactive)
```bash
cd /workspace
bash push-to-github.sh
# Output:
# ========================================
# Avirta - Push to GitHub
# ========================================
#
# Current branch: Avirta-1
# ...
# [1/3] Staging all amended files...
# [2/3] Creating commit with message: "Update amended files"
# [3/3] Pushing to GitHub branch: Avirta-1
# Push successful!
```

### Example 2: Using Locally with Custom Message
```cmd
C:\Avirta> .\push-to-github.bat
# Output:
# ========================================
# Avirta - Push to GitHub
# ========================================
#
# Current branch: Avirta-1
# 
# FILES TO BE COMMITTED:
# ----------------------
# M app.py
# M contents/questions/cars.json
# 
# Commit and push these changes? (y/n): y
# Enter commit message (or press Enter for default): Fixed bug in game logic
# [1/3] Staging all amended files...
# [2/3] Creating commit with message: "Fixed bug in game logic"
# [3/3] Pushing to GitHub branch: Avirta-1
# Push successful!
```

### Example 3: Canceling the Push
```cmd
C:\Avirta> .\push-to-github.bat
# ... shows files ...
# Commit and push these changes? (y/n): n
# Push cancelled.
```

## Troubleshooting

### "Not in a git repository" Error
- Make sure you're running the script from the Avirta project root directory
- Verify `.git` folder exists in the current directory

### "Failed to push to GitHub" Error
- Check your Git credentials (SSH key or personal access token)
- Verify your GitHub account has push access to the repository
- Check network connection

### No Changes to Commit
- If everything is already committed and pushed, the script will report: "No changes to commit. Everything is up to date."

### On Cloud Run: Permission Denied
- Make sure the shell script has execute permissions:
  ```bash
  chmod +x push-to-github.sh
  ```

## Integration with Deployment

The push scripts integrate seamlessly with:
- **Direct deploy.bat**: Local direct deployment to Cloud Run
- **cloudbuild.yaml**: Automated Cloud Build pipeline
- **Cloud Run**: The deployed service can trigger pushes via API endpoints (when integrated with Flask)

## Version Information
- Created: 2026-07-04
- Supports: Windows (batch), Linux/Mac/Cloud Run (shell)
- Git Branches: Works with any branch (current branch is auto-detected)
