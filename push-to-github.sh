#!/bin/bash

# === Avirta Push to GitHub (Unix/Linux/Cloud Run) ===
# This script commits all amended files and pushes to GitHub.
# It's a standalone command available at any time.

set -e  # Exit on error

echo ""
echo "========================================"
echo "Avirta - Push to GitHub"
echo "========================================"
echo ""

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
  echo "ERROR: Not in a git repository. Please run this script from the Avirta project root."
  exit 1
fi

# Get current branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)

echo "Current branch: $CURRENT_BRANCH"
echo ""

# Check if there are any changes to commit
if ! git status --porcelain | grep -q .; then
  echo "No changes to commit. Everything is up to date."
  exit 0
fi

echo "Detecting changes..."
echo ""

# Show what will be committed
echo "FILES TO BE COMMITTED:"
echo "----------------------"
git status --porcelain
echo ""

# Ask for confirmation (with default yes for non-interactive environments)
if [ -t 0 ]; then
  read -p "Commit and push these changes? (y/n): " CONFIRM
  if [[ ! "$CONFIRM" =~ ^[Yy]$ ]]; then
    echo "Push cancelled."
    exit 0
  fi
else
  # Non-interactive mode (e.g., Cloud Run) - proceed automatically
  echo "Running in non-interactive mode. Proceeding with push..."
fi

echo ""

# Stage all changes
echo "[1/3] Staging all amended files..."
git add -A
echo "Staged successfully."
echo ""

# Get commit message (with default for non-interactive mode)
COMMIT_MSG="Update amended files"
if [ -t 0 ]; then
  read -p "Enter commit message (or press Enter for default): " USER_MSG
  if [ -n "$USER_MSG" ]; then
    COMMIT_MSG="$USER_MSG"
  fi
fi

# Commit changes
echo "[2/3] Creating commit with message: \"$COMMIT_MSG\""
git commit -m "$COMMIT_MSG" \
  --author="Copilot <223556219+Copilot@users.noreply.github.com>" \
  -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
if [ $? -ne 0 ]; then
  echo "ERROR: Failed to create commit."
  exit 1
fi
echo "Commit created successfully."
echo ""

# Push to GitHub
echo "[3/3] Pushing to GitHub branch: $CURRENT_BRANCH"
git push origin "$CURRENT_BRANCH"
if [ $? -ne 0 ]; then
  echo "ERROR: Failed to push to GitHub."
  echo "Please check your credentials and network connection."
  exit 1
fi
echo "Push successful!"
echo ""

echo "========================================"
echo "All changes pushed to GitHub!"
echo "========================================"

exit 0
