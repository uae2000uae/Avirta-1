@echo off
setlocal enabledelayedexpansion
rem === Avirta: stop question-data pushes from triggering a Cloud Run deploy ===
rem Adds contents/questions/** to the Cloud Build trigger's ignoredFiles.
rem Usage:  configure-deploy-trigger.bat <TRIGGER_NAME> [comma,separated,globs]

if "%REGION%"=="" set REGION=us-central1
set TRIGGER=%1
set PATTERNS=%2
if "%PATTERNS%"=="" set PATTERNS=contents/questions/**,questionmanagement/reported_questions/**

if "%TRIGGER%"=="" (
  echo Usage: configure-deploy-trigger.bat ^<TRIGGER_NAME^> [comma,separated,globs]
  echo.
  echo Triggers in region %REGION%:
  gcloud builds triggers list --region=%REGION% --format="table(name, github.name, filename)"
  exit /b 1
)

set TMP=%TEMP%\avirta_trigger.yaml
echo Exporting trigger "%TRIGGER%"...
gcloud builds triggers export %TRIGGER% --region=%REGION% --destination="%TMP%"
if errorlevel 1 exit /b 1

python "%~dp0_deploy_trigger_ignore.py" "%TMP%" "%PATTERNS%"
if errorlevel 1 exit /b 1

echo Importing updated trigger...
gcloud builds triggers import --region=%REGION% --source="%TMP%"
if errorlevel 1 exit /b 1
del "%TMP%" >NUL 2>&1

echo.
echo Done. Pushes that only touch [%PATTERNS%] will no longer trigger a deploy.
endlocal
