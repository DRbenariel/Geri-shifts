"""
server.py — dev entrypoint for the Flask backend.

Bridges the HTML UI (frontend/admin/index.html) to the same Google Sheets DB
the Streamlit app uses. The real app lives in the `frontend` package:
  - config.py   constants/paths
  - db.py       Google Sheets data layer (auth, cache, 429 retry)
  - routes/     API blueprints
  - app.py      create_app() factory

Run locally:
    pip install -r requirements.txt
    export GSHEETS_CREDENTIALS="$(cat gerishifts-7ccae6b773f7.json)"   # or place the JSON at repo root
    python frontend/server.py            # → http://127.0.0.1:5000

Production (Render):
    gunicorn 'frontend.app:create_app()' --bind 0.0.0.0:$PORT

If no credentials are found the server boots in DESIGN MODE — every read
returns [] and every write returns {"ok": false, "design_mode": true}.
"""
import os
import sys

# Allow `python frontend/server.py` to resolve the `frontend` package by
# putting the repo root on sys.path (gunicorn runs from root already).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from frontend.app import create_app   # noqa: E402
from frontend import db               # noqa: E402

app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    connected = db.get_spreadsheet() is not None
    mode = 'CONNECTED to Google Sheets' if connected else 'DESIGN MODE (no creds)'
    print(f"[server] {mode} — http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)
