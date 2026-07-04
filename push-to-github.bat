@echo off
setlocal enabledelayedexpansion

rem === Avirta Push to GitHub (Windows) ===
rem This script commits all amended files and pushes to GitHub.
rem It's a standalone command available at any time.

echo.
echo ========================================
echo Avirta - Push to GitHub
echo ========================================
echo.

rem Check if we're in a git repository
git rev-parse --git-dir >NUL 2>&1
if errorlevel 1 (
  echo ERROR: Not in a git repository. Please run this script from the Avirta project root.
  exit /b 1
)

rem Get current branch
for /f "delims=" %%i in ('git rev-parse --abbrev-ref HEAD 2^>NUL') do set CURRENT_BRANCH=%%i

echo Current branch: %CURRENT_BRANCH%
echo.

rem Check if there are any changes to commit
git status --porcelain | findstr /R "^" >NUL
if errorlevel 1 (
  echo No changes to commit. Everything is up to date.
  exit /b 0
)

echo Detecting changes...
echo.

rem Show what will be committed
echo FILES TO BE COMMITTED:
echo ----------------------
git status --porcelain
echo.

rem Ask for confirmation
set /p CONFIRM="Commit and push these changes? (y/n): "
if /i not "%CONFIRM%"=="y" (
  echo Push cancelled.
  exit /b 0
)

echo.

rem Stage all changes
echo [1/3] Staging all amended files...
git add -A
if errorlevel 1 (
  echo ERROR: Failed to stage changes.
  exit /b 1
)
echo Staged successfully.
echo.

rem Get commit message
set /p COMMIT_MSG="Enter commit message (or press Enter for default): "
if "!COMMIT_MSG!"=="" (
  set COMMIT_MSG=Update amended files
)

rem Commit changes
echo [2/3] Creating commit with message: "!COMMIT_MSG!"
git commit -m "!COMMIT_MSG!" ^
  --author="Copilot <223556219+Copilot@users.noreply.github.com>" ^
  -m "Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
if errorlevel 1 (
  echo ERROR: Failed to create commit.
  exit /b 1
)
echo Commit created successfully.
echo.

rem Push to GitHub
echo [3/3] Pushing to GitHub branch: %CURRENT_BRANCH%
git push origin %CURRENT_BRANCH%
if errorlevel 1 (
  echo ERROR: Failed to push to GitHub.
  echo Please check your credentials and network connection.
  exit /b 1
)
echo Push successful!
echo.

echo ========================================
echo All changes pushed to GitHub!
echo ========================================

endlocal
exit /b 0
