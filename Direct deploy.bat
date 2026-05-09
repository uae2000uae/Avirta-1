@echo off
setlocal enabledelayedexpansion

rem === Avirta Cloud Run Direct Deploy (Windows) ===
rem This script builds a Docker image, pushes it, and deploys to Cloud Run.
rem Prerequisites:
rem  - gcloud CLI installed and initialized (gcloud init)
rem  - Docker installed and running
rem  - You are logged in to gcloud (gcloud auth login) and have a project set

rem --- Editable defaults ---
set SERVICE_NAME=avirta
set REGION=us-central1

rem Use PROJECT_ID from env if set; otherwise read from gcloud config
if "%PROJECT_ID%"=="" (
  for /f "delims=" %%i in ('gcloud config get-value project 2^>NUL') do set PROJECT_ID=%%i
)

if "%PROJECT_ID%"=="" (
  echo ERROR: PROJECT_ID is not set and not found in gcloud config.
  echo        Set it with:  set PROJECT_ID=your-gcp-project-id
  echo        Or run:       gcloud config set project YOUR_PROJECT_ID
  exit /b 1
)

set IMAGE=gcr.io/%PROJECT_ID%/avirta:latest

echo.
echo Building Docker image: %IMAGE%
docker build -t %IMAGE% .
if errorlevel 1 (
  echo ERROR: Docker build failed.
  exit /b 1
)

echo.
echo Configuring Docker to use gcloud credentials (if needed)...
gcloud auth configure-docker -q


echo.
echo Pushing image: %IMAGE%
docker push %IMAGE%
if errorlevel 1 (
  echo ERROR: Docker push failed.
  exit /b 1
)

echo.
echo Deploying to Cloud Run service "%SERVICE_NAME%" in region "%REGION%"...
gcloud run deploy %SERVICE_NAME% ^
  --image %IMAGE% ^
  --region %REGION% ^
  --platform managed ^
  --allow-unauthenticated ^
  --port 8080
if errorlevel 1 (
  echo ERROR: gcloud run deploy failed.
  echo Tip: You can also deploy from source with: gcloud run deploy %SERVICE_NAME% --source . --region %REGION% --platform managed --allow-unauthenticated
  exit /b 1
)

echo.
echo Deployment completed successfully.
endlocal