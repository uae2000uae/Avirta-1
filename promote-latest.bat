@echo off
setlocal
rem === Avirta: send 100%% traffic to the latest revision ===
rem NOTE: the cutover drains the current revision, ending any in-memory games.
if "%SERVICE_NAME%"=="" set SERVICE_NAME=avirta
if "%REGION%"=="" set REGION=us-central1

echo Routing 100%% traffic to the latest revision of "%SERVICE_NAME%"...
gcloud run services update-traffic %SERVICE_NAME% --region %REGION% --to-latest
if errorlevel 1 (
  echo ERROR: failed to update traffic.
  exit /b 1
)
echo Done. Latest revision is now live.
endlocal
