@echo off
echo Testing GitHub Push Function...
echo.
echo Before running this test, make sure to edit test_github_push.py with your:
echo - GitHub token
echo - GitHub username
echo - Repository name
echo.
echo Press any key to continue or Ctrl+C to cancel...
pause > nul

python test_github_push.py
echo.
pause