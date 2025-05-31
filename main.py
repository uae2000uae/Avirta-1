# main.py - Entry point for Google Cloud App Engine

# Import the Flask app from the current directory
from app import app

# This is the entry point that App Engine looks for
if __name__ == '__main__':
    # App Engine uses gunicorn to serve the app, so this block
    # is primarily for local testing
    app.run(host='0.0.0.0', port=8080, debug=False)