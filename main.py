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

    def _update_ts():
        """Update timestamp.json safely during local runs."""
        try:
            import jasontimestamp as _jt  # updates on import
            if hasattr(_jt, 'update_timestamp'):
                _jt.update_timestamp()
        except Exception:
            # Never block local server startup due to timestamp writing issues
            pass

    # In debug with the Werkzeug reloader, avoid double-running side effects:
    # only run timestamp update in the reloader child process.
    if (not debug) or (os.environ.get('WERKZEUG_RUN_MAIN') == 'true'):
        _update_ts()

    port = int(os.environ.get('PORT', 8080))
    # Enable Flask's built-in reloader when debug is True
    app.run(host='0.0.0.0', port=port, debug=debug, use_reloader=debug)
