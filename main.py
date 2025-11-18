# main.py - Entry point for Google Cloud App Engine

# Import the Flask app from the current directory
from app import app

# This is the entry point that App Engine looks for
if __name__ == '__main__':
    # App Engine uses gunicorn to serve the app, so this block
    # is primarily for local testing
    import os

    # In local development, update timestamp.json so the UI shows a fresh "Last synced".
    # This import is safe/no-op in production since this block doesn't run under gunicorn.
    try:
        import jasontimestamp as _jt  # updates on import
        # Ensure update runs even if import side-effect is changed later
        if hasattr(_jt, 'update_timestamp'):
            _jt.update_timestamp()
    except Exception:
        # Never block local server startup due to timestamp writing issues
        pass

    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
