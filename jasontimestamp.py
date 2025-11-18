"""
jasontimestamp.py

Updates/creates the timestamp.json file in the project root with the current local time.
It is designed to be imported by main.py during local development so that the UI can
show a recent "Last synced" value via /timestamp.json.

Format matches app.py's fallback generator:
    {"lastSynced": "%y%m%d.%H%M"}
"""
from __future__ import annotations

import json
import os
from datetime import datetime


def update_timestamp() -> str:
    """Create or update timestamp.json with current local time.

    Returns:
        str: The path to the written timestamp.json.
    """
    current_dir = os.path.dirname(os.path.abspath(__file__))
    ts_path = os.path.join(current_dir, 'timestamp.json')

    # Use the same format used in app.py fallback
    now = datetime.now()
    timestamp_data = {"lastSynced": now.strftime("%y%m%d.%H%M")}

    # Write atomically by writing to temp then replacing (best effort on Windows)
    tmp_path = ts_path + '.tmp'
    try:
        with open(tmp_path, 'w', encoding='utf-8') as f:
            json.dump(timestamp_data, f, ensure_ascii=False)
        # Replace the original file
        if os.path.exists(ts_path):
            try:
                os.remove(ts_path)
            except OSError:
                # If removal fails, we'll try to overwrite in place
                pass
        os.replace(tmp_path, ts_path)
    except Exception:
        # Fallback: direct write
        with open(ts_path, 'w', encoding='utf-8') as f:
            json.dump(timestamp_data, f, ensure_ascii=False)
    return ts_path


# Perform the update immediately on import for convenience in local runs
try:
    update_timestamp()
except Exception:
    # Never fail the app due to timestamp issues in dev
    pass
