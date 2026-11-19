"""Who changed what: one append-only row per successful write, in the `edit_log` sheet.

Every save goes through the service account, so the Sheet's own version history shows only
"scheduler-bot". This log keeps the logged-in user next to each change. For edits that name one
(date, employee) cell, it also records that day's work-schedule status before and after.
Writing the log never fails the request.
"""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

from geri_core import people

EDIT_LOG = "edit_log"
EDIT_LOG_COLUMNS = ['timestamp', 'user_name', 'user_role', 'method', 'path',
                    'employee', 'date', 'before', 'after', 'details']

_SECRET_KEYS = ('password', 'current', 'new', 'confirm')
_MAX_DETAILS = 1500


def _redact(obj):
    if isinstance(obj, dict):
        return {k: ('***' if any(s in str(k).lower() for s in _SECRET_KEYS) else _redact(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [_redact(v) for v in obj]
    return obj


def parse_body(raw: bytes | None):
    if not raw:
        return {}
    try:
        return _redact(json.loads(raw))
    except ValueError:
        return {}


def _wsd_cell(df, ds, emp):
    """'status (dept) note' of one work_schedule_daily row, or '' when there is none."""
    if df is None or df.empty or not ds or not emp or 'date' not in df.columns:
        return ''
    m = (df['date'].astype(str).str.strip() == ds) & (df['employee'].astype(str).str.strip() == emp)
    if not m.any():
        return ''
    r = df[m].iloc[-1]
    parts = [str(r.get('status', '') or '').strip()]
    dept = str(r.get('daily_dept', '') or '').strip()
    if dept:
        parts.append(f"({dept})")
    note = str(r.get('note', '') or '').strip()
    if note:
        parts.append(note)
    return ' '.join(p for p in parts if p)


def _iso(ds) -> str:
    s = str(ds or '').strip()
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d.%m.%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            pass
    return s


def build_row(user_name, ctx_before, ctx_after, method, path, body) -> list:
    body = body if isinstance(body, dict) else {}
    emp = str(body.get('employee', '') or '').strip()
    ds = _iso(body.get('date', '')) if body.get('date') else ''
    if not ds and body.get('start'):
        ds = _iso(body['start']) + (f" – {_iso(body['end'])}" if body.get('end') else '')
    before = after = ''
    if emp and ds and '–' not in ds:
        before = _wsd_cell(ctx_before, ds, emp)
        after = _wsd_cell(getattr(ctx_after, 'work_schedule_daily', None), ds, emp)
    role = ''
    try:
        row = people.staff_row(ctx_after, user_name)
        role = str(row.get('type', '')) if row is not None else ''
    except Exception:
        pass
    details = json.dumps(body, ensure_ascii=False)[:_MAX_DETAILS] if body else ''
    now = datetime.now(ZoneInfo('Asia/Jerusalem')).strftime('%Y-%m-%d %H:%M:%S')
    return [now, user_name or '', role, method, path, emp, ds, before, after, details]


def record(store, user_name, wsd_before: pd.DataFrame | None, ctx_after, method, path, raw_body):
    """Append one row; never raises."""
    try:
        row = build_row(user_name, wsd_before, ctx_after, method, path, parse_body(raw_body))
        store.append_row(EDIT_LOG, row, header=EDIT_LOG_COLUMNS)
    except Exception:
        pass
