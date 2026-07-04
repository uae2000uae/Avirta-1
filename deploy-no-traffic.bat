@echo off
setlocal enabledelayedexpansion
rem === Avirta: deploy a new revision WITHOUT taking traffic ===
rem New revision tagged "next" gets 0%% traffic so live games keep running.
rem Test the tagged URL, then run promote-latest.bat to switch traffic.

if "%SERVICE_NAME%"=="" set SERVICE_NAME=avirta
if "%REGION%"=="" set REGION=us-central1
if "%TAG%"=="" set TAG=next

echo Deploying "%SERVICE_NAME%" to "%REGION%" with NO traffic (tag: %TAG%)...
gcloud run deploy %SERVICE_NAME% ^
  --source . ^
  --region %REGION% ^
  --platform managed ^
  --allow-unauthenticated ^
  --port 8080 ^
  --set-secrets OPENAI_API_KEY=OPENAI_API_KEY:latest,GITHUB_TOKEN=GITHUB_TOKEN:latest,ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest ^
  --no-traffic ^
  --tag %TAG%
if errorlevel 1 (
  echo ERROR: no-traffic deploy failed.
  exit /b 1
)

echo.
echo New revision deployed with 0%% traffic. Find the "%TAG%" preview URL:
gcloud run services describe %SERVICE_NAME% --region %REGION% --format="value(status.traffic.filter('tag', '%TAG%').url)"
echo.
echo When ready (ideally no active games), promote it:  promote-latest.bat
endlocal
