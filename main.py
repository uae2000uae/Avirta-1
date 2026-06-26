# main.py - Entry point for Google Cloud App Engine

# Import the Flask app from the current directory
from app import app

# This is the entry point that App Engine looks for
if __name__ == '__main__':
    # App Engine uses gunicorn to serve the app, so this block
    # is primarily for local testing
    import os

    # Determine debug/reloader from environment (default ON for local dev)
    debug = os.environ.get('FLASK_DEBUG', '1') == '1'

    port = int(os.environ.get('PORT', 8080))
    # Enable Flask's built-in reloader when debug is True
    app.run(host='0.0.0.0', port=port, debug=debug, use_reloader=debug)
