@echo off
setlocal enabledelayedexpansion

rem === Avirta Cloud Run Direct Deploy (Windows) ===
rem This script builds a Docker image, pushes it, and deploys to Cloud Run.
rem If Docker is not installed or not on PATH, it will fall back to source-based deploy.
rem Prerequisites:
rem  - gcloud CLI installed and initialized (gcloud init)
rem  - (Optional) Docker installed and running for image-based deploy
rem  - You are logged in to gcloud (gcloud auth login) and have a project set

rem --- Editable defaults ---
set SERVICE_NAME=avirta
set REGION=us-central1

rem Verify gcloud CLI is available
where gcloud >NUL 2>&1
if errorlevel 1 (
  echo ERROR: gcloud CLI not found. Please install Google Cloud SDK and ensure 'gcloud' is on PATH.
  echo        https://cloud.google.com/sdk/docs/install
  exit /b 1
)

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

rem Check if Docker is installed; if not, fall back to source deploy
where docker >NUL 2>&1
if errorlevel 1 (
  echo.
  echo Docker not found on PATH. Falling back to source-based deploy with gcloud.
  goto SOURCE_DEPLOY
)

:DOCKER_DEPLOY

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
echo Deploying to Cloud Run service "%SERVICE_NAME%" in region "%REGION%" (image-based)...
gcloud run deploy %SERVICE_NAME% ^
  --image %IMAGE% ^
  --region %REGION% ^
  --platform managed ^
  --allow-unauthenticated ^
  --port 8080 ^
  --set-secrets AI_Token=AI_Token:latest,GITHUB_TOKEN=GitHub_Token:latest
if errorlevel 1 (
  echo ERROR: gcloud run deploy failed.
  echo Tip: You can also deploy from source with: gcloud run deploy %SERVICE_NAME% --source . --region %REGION% --platform managed --allow-unauthenticated --set-secrets AI_Token=AI_Token:latest,GITHUB_TOKEN=GitHub_Token:latest
  exit /b 1
)

goto POST_DEPLOY

:SOURCE_DEPLOY

echo.
echo Deploying to Cloud Run service "%SERVICE_NAME%" in region "%REGION%" (source-based)...
gcloud run deploy %SERVICE_NAME% ^
  --source . ^
  --region %REGION% ^
  --platform managed ^
  --allow-unauthenticated ^
  --port 8080 ^
  --set-secrets AI_Token=AI_Token:latest,GitHub_Token=GitHub_Token:latest
if errorlevel 1 (
  echo ERROR: gcloud run deploy (source) failed.
  exit /b 1
)

:POST_DEPLOY

echo.
echo Ensuring public (unauthenticated) access to the service...
gcloud beta run services add-iam-policy-binding %SERVICE_NAME% ^
  --region=%REGION% ^
  --member=allUsers ^
  --role=roles/run.invoker >NUL 2>&1

if errorlevel 1 (
  echo Warning: failed to set IAM policy binding for public access (you may need additional permissions).
) else (
  echo Public access (roles/run.invoker) ensured.
)

echo.
echo Deployment completed successfully.
endlocal