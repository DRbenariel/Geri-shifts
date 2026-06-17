"""
db.py — Google Sheets data layer for the Flask backend.

Lifted from the original frontend/server.py (single source of truth for all
Sheets I/O) and extended with:
  - a 429 rate-limit retry wrapper (ported from appy.py:141-155),
  - read_df() returning a normalised pandas DataFrame for the scheduling code.

Auth mirrors daily_report.py:get_client() — env GSHEETS_CREDENTIALS or the
local service-account JSON. Boots in DESIGN MODE (every read → [], every write
helper → None/False) when no credentials are present.
"""
import os
import json
import time

import gspread
import pandas as pd
from google.oauth2.service_account import Credentials
from flask import request

from .config import SCOPES, SPREADSHEET_KEY, YEAR, CACHE_TTL, ROOT

_client = None
_spreadsheet = None
_cache = {}          # name -> (timestamp, list_of_dicts)


# ---------------------------------------------------------------------------
# Connection
# ---------------------------------------------------------------------------
def _creds_dict():
    creds_json = os.environ.get('GSHEETS_CREDENTIALS')
    if creds_json:
        return json.loads(creds_json)
    key_file = os.path.join(ROOT, 'gerishifts-7ccae6b773f7.json')
    if os.path.exists(key_file):
        with open(key_file) as f:
            return json.load(f)
    return None


def get_spreadsheet():
    """Lazy-connect. Returns None in design mode (no creds)."""
    global _client, _spreadsheet
    if _spreadsheet is not None:
        return _spreadsheet
    creds_dict = _creds_dict()
    if not creds_dict:
        return None
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    _client = gspread.Client(auth=creds)
    _spreadsheet = _client.open_by_key(SPREADSHEET_KEY)
    return _spreadsheet


def _retry(fn, attempts=4):
    """Call fn(), retrying on gspread 429 rate-limits with exponential backoff."""
    for attempt in range(attempts):
        try:
            return fn()
        except gspread.exceptions.APIError as e:
            status = getattr(getattr(e, 'response', None), 'status_code', None)
            if status == 429 and attempt < attempts - 1:
                time.sleep(2 ** attempt)
                continue
            raise


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------
def read_sheet(name, fresh=False):
    """Return a sheet as a list of dict rows (cached). [] if missing/design mode."""
    if not fresh:
        hit = _cache.get(name)
        if hit and (time.time() - hit[0]) < CACHE_TTL:
            return hit[1]
    sh = get_spreadsheet()
    if sh is None:
        return []
    try:
        rows = _retry(lambda: sh.worksheet(name).get_all_records())
    except gspread.exceptions.WorksheetNotFound:
        rows = []
    _cache[name] = (time.time(), rows)
    return rows


def read_df(name, fresh=False, strip_names=True):
    """Return a sheet as a normalised pandas DataFrame (for scheduling code).

    Applies the project's two known data-quality fixes:
      - strip trailing/invisible spaces from the 'name' column (skippable),
      - parse only_home_dept string-bool with _is_true (never .astype(bool)).

    strip_names=False reproduces appy.py:run_smart_scheduling exactly (which uses
    raw staff names) — important for schedule parity tests.
    """
    df = pd.DataFrame(read_sheet(name, fresh=fresh))
    if not df.empty:
        if strip_names and 'name' in df.columns:
            df['name'] = df['name'].astype(str).str.strip()
        if 'only_home_dept' in df.columns:
            df['only_home_dept'] = df['only_home_dept'].apply(_is_true)
    return df


def _invalidate(*names):
    for n in names:
        _cache.pop(n, None)


# ---------------------------------------------------------------------------
# Writes
# ---------------------------------------------------------------------------
def get_ws(name, rows=1000, cols=26):
    """Get a worksheet, creating it if missing. None in design mode."""
    sh = get_spreadsheet()
    if sh is None:
        return None
    try:
        return sh.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        return _retry(lambda: sh.add_worksheet(name, rows=rows, cols=cols))


def append_row(name, header, row_dict):
    """Append a row, ensuring the header exists. Returns True on write."""
    ws = get_ws(name)
    if ws is None:
        return False
    existing = _retry(ws.get_all_values)
    if not existing:
        _retry(lambda: ws.append_row(header))
        existing = [header]
    cols = existing[0]
    _retry(lambda: ws.append_row([str(row_dict.get(c, '')) for c in cols]))
    _invalidate(name)
    return True


def overwrite_sheet(name, header, rows):
    """Replace a whole sheet with header + rows (list of dicts). False in design mode."""
    ws = get_ws(name)
    if ws is None:
        return False
    out = [header] + [[str(r.get(c, '')) for c in header] for r in rows]
    _retry(ws.clear)
    _retry(lambda: ws.update('A1', out))
    _invalidate(name)
    return True


def set_setting(key, value):
    """Upsert a settings row."""
    ws = get_ws('settings')
    if ws is None:
        return False
    values = _retry(ws.get_all_values)
    if not values:
        _retry(lambda: ws.append_row(['key', 'value']))
        values = [['key', 'value']]
    for i, row in enumerate(values[1:], start=2):
        if row and row[0] == key:
            _retry(lambda: ws.update_cell(i, 2, str(value)))
            _invalidate('settings')
            return True
    _retry(lambda: ws.append_row([key, str(value)]))
    _invalidate('settings')
    return True


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _is_true(v):
    return v if isinstance(v, bool) else str(v).strip().lower() == 'true'


def _norm(s):
    return str(s).strip()


def _dept_norm(s):
    """Quote/space-insensitive dept key — tolerates א' vs א׳ vs א."""
    return ''.join(ch for ch in str(s) if ch not in " '’׳\"״").strip()


def settings_map():
    return {str(r.get('key')): r.get('value') for r in read_sheet('settings')}


def get_active_month(key='active_month', default=6):
    try:
        return int(settings_map().get(key, default))
    except (ValueError, TypeError):
        return default


def _month_arg(default=None):
    """Accept ?month=2026-06 or ?m=6. Returns (prefix 'YYYY-MM', int month)."""
    m = request.args.get('month') or request.args.get('m')
    if m and '-' in str(m):
        prefix = str(m)[:7]
        return prefix, int(prefix[5:7])
    if m:
        mi = int(m)
    elif default is not None:
        mi = default
    else:
        mi = get_active_month('active_month', 6)
    return f"{YEAR}-{mi:02d}", mi
