@echo off
echo ===================================================================
echo Deploying to Google Cloud App Engine with debug logging...
echo ===================================================================
echo.
echo Changes made to fix Nginx bad gateway error:
echo 1. Updated entrypoint to use gunicorn_config.py
echo 2. Increased timeout settings to 300 seconds
echo 3. Increased buffer sizes for larger responses
echo 4. Increased number of workers to 4
echo.
echo Press any key to start deployment...
pause
echo.
gcloud app deploy --verbosity=debug
echo.
echo ===================================================================
echo Deployment completed. Check the logs for any errors.
echo ===================================================================
pause
