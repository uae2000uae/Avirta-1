#!/usr/bin/env python3
"""
Test script to verify the Avirta deployment is working correctly.
This script checks various aspects of the deployment to help diagnose issues.
"""

import os
import sys
import socket
import requests
import subprocess
from pathlib import Path

def check_python_version():
    """Check if Python version is 3.8 or higher."""
    version = sys.version_info
    if version.major < 3 or (version.major == 3 and version.minor < 8):
        print(f"❌ Python version {version.major}.{version.minor} is too old. Avirta requires Python 3.8 or higher.")
        return False
    else:
        print(f"✅ Python version {version.major}.{version.minor} is compatible.")
        return True

def check_wsgi_file():
    """Check if wsgi.py exists and is properly configured."""
    wsgi_path = Path("wsgi.py")
    if not wsgi_path.exists():
        print("❌ wsgi.py file not found in the current directory.")
        return False

    with open(wsgi_path, "r") as f:
        content = f.read()

    if "from app import app" not in content:
        print("❌ wsgi.py does not import the Flask app correctly.")
        return False

    print("✅ wsgi.py exists and imports the Flask app.")
    return True

def check_gunicorn_installed():
    """Check if Gunicorn is installed."""
    try:
        import gunicorn
        print(f"✅ Gunicorn is installed (version {gunicorn.__version__}).")
        return True
    except ImportError:
        print("❌ Gunicorn is not installed. Install it with 'pip install gunicorn'.")
        return False

def check_socket_file():
    """Check if the Unix socket file exists and has correct permissions."""
    socket_path = "/tmp/avirta.sock"
    if not os.path.exists(socket_path):
        print(f"❌ Socket file {socket_path} does not exist.")
        print("   This could mean Gunicorn is not running or is not configured to use this socket.")
        return False

    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_path)
        sock.close()
        print(f"✅ Socket file {socket_path} exists and is accessible.")
        return True
    except Exception as e:
        print(f"❌ Socket file {socket_path} exists but could not connect: {e}")
        return False

def check_nginx_config():
    """Check if Nginx configuration is valid."""
    try:
        result = subprocess.run(["nginx", "-t"], capture_output=True, text=True)
        if result.returncode == 0:
            print("✅ Nginx configuration is valid.")
            return True
        else:
            print(f"❌ Nginx configuration is invalid: {result.stderr}")
            return False
    except Exception as e:
        print(f"❌ Could not check Nginx configuration: {e}")
        return False

def check_local_server():
    """Check if the application is accessible locally."""
    try:
        response = requests.get("http://localhost", timeout=5)
        if response.status_code == 200:
            print(f"✅ Application is accessible locally (status code {response.status_code}).")
            return True
        else:
            print(f"❌ Application returned status code {response.status_code}.")
            return False
    except requests.exceptions.RequestException as e:
        print(f"❌ Could not connect to the application locally: {e}")
        return False

def check_log_files():
    """Check if log files exist and are writable."""
    log_paths = [
        "/var/log/avirta/access.log",
        "/var/log/avirta/error.log",
        "/var/log/nginx/avirta_access.log",
        "/var/log/nginx/avirta_error.log"
    ]

    all_ok = True
    for log_path in log_paths:
        if not os.path.exists(log_path):
            print(f"❌ Log file {log_path} does not exist.")
            all_ok = False
            continue

        if not os.access(log_path, os.W_OK):
            print(f"❌ Log file {log_path} is not writable.")
            all_ok = False
            continue

        print(f"✅ Log file {log_path} exists and is writable.")

    return all_ok

def main():
    """Run all checks and summarize results."""
    print("=== Avirta Deployment Test ===")

    checks = [
        ("Python Version", check_python_version),
        ("WSGI File", check_wsgi_file),
        ("Gunicorn Installation", check_gunicorn_installed),
        ("Unix Socket", check_socket_file),
        ("Nginx Configuration", check_nginx_config),
        ("Local Server", check_local_server),
        ("Log Files", check_log_files)
    ]

    results = []
    for name, check_func in checks:
        print(f"\n--- Checking {name} ---")
        try:
            result = check_func()
            results.append((name, result))
        except Exception as e:
            print(f"❌ Error during check: {e}")
            results.append((name, False))

    print("\n=== Summary ===")
    passed = sum(1 for _, result in results if result)
    total = len(results)
    print(f"Passed {passed} out of {total} checks.")

    if passed == total:
        print("✅ All checks passed! The deployment should be working correctly.")
        return 0
    else:
        print("❌ Some checks failed. Review the output above for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
