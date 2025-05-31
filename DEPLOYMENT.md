# Avirta Deployment Guide

This guide provides instructions for deploying the Avirta web application using Nginx and Gunicorn on a Linux server.

## Prerequisites

- Python 3.8 or higher
- Nginx
- Gunicorn
- Systemd (for service management)

## Installation Steps

### 1. Clone the Repository

```bash
git clone <repository-url>
cd Avirta
```

### 2. Set Up Python Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install gunicorn
```

### 3. Configure Gunicorn

The Gunicorn configuration file is located at `gunicorn_config.py`. Review and update the configuration as needed:

- Update the `bind` parameter if you want to use a different socket path or a TCP port
- Adjust the number of `workers` based on your server's resources
- Update the log paths in `accesslog` and `errorlog`

### 4. Configure Nginx

1. Copy the Nginx configuration file to the Nginx sites directory:

```bash
sudo cp nginx_avirta.conf /etc/nginx/sites-available/avirta
```

2. Update the configuration file:
   - Replace the `server_name` with your domain name
   - Update the `alias` path in the `/static` location to point to your actual static files directory

3. Enable the site:

```bash
sudo ln -s /etc/nginx/sites-available/avirta /etc/nginx/sites-enabled/
sudo nginx -t  # Test the configuration
sudo systemctl reload nginx
```

### 5. Set Up Systemd Service

1. Copy the service file to the systemd directory:

```bash
sudo cp avirta.service /etc/systemd/system/
```

2. Update the service file:
   - Replace `/path/to/Avirta` with the actual path to your Avirta installation
   - Update the user and group if needed

3. Enable and start the service:

```bash
sudo systemctl daemon-reload
sudo systemctl enable avirta
sudo systemctl start avirta
```

### 6. Create Log Directories

```bash
sudo mkdir -p /var/log/avirta
sudo chown www-data:www-data /var/log/avirta
```

### 7. Check Service Status

```bash
sudo systemctl status avirta
```

## Troubleshooting

### Deployment Test Script

A test script is provided to help diagnose deployment issues. Run it from the project root directory:

```bash
cd /var/www/Avirta
source venv/bin/activate
python test_deployment.py
```

The script will check various aspects of your deployment and provide a summary of any issues found.

### 502 Bad Gateway Error

If you encounter a 502 Bad Gateway error, check the following:

1. Verify that the Gunicorn service is running:

```bash
sudo systemctl status avirta
```

2. Check the Gunicorn error logs:

```bash
sudo tail -f /var/log/avirta/error.log
```

3. Check the Nginx error logs:

```bash
sudo tail -f /var/log/nginx/avirta_error.log
```

4. Verify socket permissions:

```bash
ls -la /tmp/avirta.sock
```

The socket should be owned by the same user that runs the Gunicorn process (www-data in the default configuration).

5. Ensure the wsgi.py file is in the correct location:

```bash
ls -la /var/www/Avirta/wsgi.py
```

6. Test Gunicorn directly to see if it can run the application:

```bash
cd /var/www/Avirta
source venv/bin/activate
gunicorn --bind 127.0.0.1:8000 wsgi:app
```

If Gunicorn starts successfully, try accessing the application at http://127.0.0.1:8000 to verify it works.

7. Check for import errors by running the wsgi.py file directly:

```bash
cd /var/www/Avirta
source venv/bin/activate
python wsgi.py
```

8. Ensure log directories exist and have proper permissions:

```bash
sudo mkdir -p /var/log/avirta
sudo chown www-data:www-data /var/log/avirta
```

9. Restart the services:

```bash
sudo systemctl restart avirta
sudo systemctl restart nginx
```

### Common Issues

1. **Socket permission issues**: Ensure that the user running Nginx has permission to access the socket.

2. **Application errors**: Check the Gunicorn error logs for application-specific errors.

3. **Timeout issues**: If your application takes a long time to process requests, you may need to increase the timeout values in both the Nginx and Gunicorn configurations.

4. **Path issues**: Ensure that all paths in the configuration files are correct and accessible.

## Updating the Application

To update the application:

1. Pull the latest changes:

```bash
cd /var/www/Avirta
git pull
```

2. Activate the virtual environment and update dependencies:

```bash
source venv/bin/activate
pip install -r requirements.txt
```

3. Check if the wsgi.py file needs to be updated:

```bash
# If you've made changes to the application structure or imports
# you might need to update the wsgi.py file
nano wsgi.py
```

4. Restart the service:

```bash
sudo systemctl restart avirta
sudo systemctl status avirta  # Verify the service started successfully
```

5. Check the logs for any errors:

```bash
sudo tail -f /var/log/avirta/error.log
```

6. Test the application to ensure it's working correctly:

```bash
curl http://localhost
```
