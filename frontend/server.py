"""
server.py — Flask backend for the new admin frontend (frontend/admin/index.html).

Bridges the static HTML UI to the same Google Sheets "database" the Streamlit
app uses. The service-account credentials stay server-side; the browser only
ever talks to this JSON API.

Run locally:
    pip install -r requirements.txt
    # creds via env (recommended) or the local service-account JSON file:
    export GSHEETS_CREDENTIALS="$(cat gerishifts-7ccae6b773f7.json)"
    python frontend/server.py
    # → http://127.0.0.1:5000

Auth pattern mirrors daily_report.py:get_client() exactly.

If no credentials are found the server still boots in DESIGN MODE — every read
returns [] and every write returns {"ok": false, "design_mode": true} so the
UI can be previewed without a database connection.
"""

import os
import json
import time
import uuid
import calendar
from datetime import datetime, timedelta

import gspread
from google.oauth2.service_account import Credentials
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SCOPES = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive',
]
SPREADSHEET_KEY = "1fmjfqA04VMfbBYHw2OXqoY08X7heazlx0Cr2Uaa2LkY"
YEAR = 2026
MAIN_DEPTS = ['פנימית גריאטרית', 'שיקום']
DAILY_DEPTS = ['שיקום גריאטרי א׳', 'שיקום גריאטרי ב׳', 'פנימית גריאטרית']
FRIDAY_DEPTS = [
    'שישי בוקר - שיקום (1)', 'שישי בוקר - שיקום (2)',
    'שישי בוקר - פנימית (1)', 'שישי בוקר - פנימית (2)',
]
CACHE_TTL = 15  # seconds — reads are cached briefly; writes invalidate

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

app = Flask(__name__, static_folder=None)
CORS(app)


# ---------------------------------------------------------------------------
# Google Sheets layer
# ---------------------------------------------------------------------------
_client = None
_spreadsheet = None
_cache = {}          # name -> (timestamp, list_of_dicts)


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
        rows = sh.worksheet(name).get_all_records()
    except gspread.exceptions.WorksheetNotFound:
        rows = []
    _cache[name] = (time.time(), rows)
    return rows


def _invalidate(*names):
    for n in names:
        _cache.pop(n, None)


def get_ws(name, rows=1000, cols=26):
    """Get a worksheet, creating it if missing. None in design mode."""
    sh = get_spreadsheet()
    if sh is None:
        return None
    try:
        return sh.worksheet(name)
    except gspread.exceptions.WorksheetNotFound:
        return sh.add_worksheet(name, rows=rows, cols=cols)


def append_row(name, header, row_dict):
    """Append a row, ensuring the header exists. Returns True on write."""
    ws = get_ws(name)
    if ws is None:
        return False
    existing = ws.get_all_values()
    if not existing:
        ws.append_row(header)
        existing = [header]
    cols = existing[0]
    ws.append_row([str(row_dict.get(c, '')) for c in cols])
    _invalidate(name)
    return True


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _is_true(v):
    return v if isinstance(v, bool) else str(v).strip().lower() == 'true'


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


def settings_map():
    return {str(r.get('key')): r.get('value') for r in read_sheet('settings')}


def get_active_month(key='active_month', default=6):
    try:
        return int(settings_map().get(key, default))
    except (ValueError, TypeError):
        return default


def set_setting(key, value):
    """Upsert a settings row."""
    ws = get_ws('settings')
    if ws is None:
        return False
    values = ws.get_all_values()
    if not values:
        ws.append_row(['key', 'value'])
        values = [['key', 'value']]
    for i, row in enumerate(values[1:], start=2):
        if row and row[0] == key:
            ws.update_cell(i, 2, str(value))
            _invalidate('settings')
            return True
    ws.append_row([key, str(value)])
    _invalidate('settings')
    return True


def _norm(s):
    return str(s).strip()


def _dept_norm(s):
    """Quote/space-insensitive dept key — tolerates א' vs א׳ vs א."""
    return ''.join(ch for ch in str(s) if ch not in " '’׳\"״").strip()


# ---------------------------------------------------------------------------
# Static file serving — frontend/ is the web root
# ---------------------------------------------------------------------------
@app.route('/')
def index():
    return send_from_directory(os.path.join(HERE, 'admin'), 'index.html')


@app.route('/<path:path>')
def static_proxy(path):
    return send_from_directory(HERE, path)


# ---------------------------------------------------------------------------
# API — system / settings
# ---------------------------------------------------------------------------
@app.route('/api/health')
def api_health():
    return jsonify({'ok': True, 'connected': get_spreadsheet() is not None,
                    'design_mode': get_spreadsheet() is None})


@app.route('/api/settings')
def api_settings():
    s = settings_map()
    return jsonify({
        'all': s,
        'active_month': get_active_month('active_month', 6),
        'daily_active_month': get_active_month('daily_active_month', 6),
        'daily_requests_open': _is_true(s.get('daily_requests_open', 'True')),
    })


@app.route('/api/settings', methods=['POST'])
def api_set_setting():
    data = request.get_json(force=True)
    key, value = data.get('key'), data.get('value')
    if key is None:
        return jsonify({'ok': False, 'error': 'missing key'}), 400
    ok = set_setting(key, value)
    # mirror the app: opening a new daily month re-opens requests
    if key == 'daily_active_month':
        set_setting('daily_requests_open', 'True')
    return jsonify({'ok': ok, 'design_mode': not ok})


# ---------------------------------------------------------------------------
# API — staff
# ---------------------------------------------------------------------------
@app.route('/api/staff')
def api_staff():
    rows = read_sheet('staff')
    for r in rows:
        r['only_home_dept'] = _is_true(r.get('only_home_dept', False))
    return jsonify(rows)


@app.route('/api/staff', methods=['POST'])
def api_staff_save():
    """Add a new staff member or update an existing one (matched by name)."""
    data = request.get_json(force=True)
    name = _norm(data.get('name', ''))
    if not name:
        return jsonify({'ok': False, 'error': 'missing name'}), 400
    ws = get_ws('staff')
    if ws is None:
        return jsonify({'ok': False, 'design_mode': True})
    values = ws.get_all_values()
    header = values[0] if values else list(data.keys())
    if not values:
        ws.append_row(header)
    # find existing row by name (column 'name')
    name_col = header.index('name') if 'name' in header else 0
    for i, row in enumerate(values[1:], start=2):
        if len(row) > name_col and _norm(row[name_col]) == name:
            new_row = [str(data.get(c, row[j] if j < len(row) else '')) for j, c in enumerate(header)]
            ws.update(f'A{i}', [new_row])
            _invalidate('staff')
            return jsonify({'ok': True, 'updated': True})
    ws.append_row([str(data.get(c, '')) for c in header])
    _invalidate('staff')
    return jsonify({'ok': True, 'created': True})


# ---------------------------------------------------------------------------
# API — night-shift schedule + requests + reports
# ---------------------------------------------------------------------------
@app.route('/api/requests')
def api_requests():
    prefix, _ = _month_arg()
    rows = [r for r in read_sheet('requests')
            if str(r.get('date', '')).startswith(prefix)]
    return jsonify(rows)


@app.route('/api/schedule')
def api_schedule():
    prefix, _ = _month_arg()
    rows = [r for r in read_sheet('schedule')
            if str(r.get('date', '')).startswith(prefix)]
    return jsonify(rows)


@app.route('/api/special_days')
def api_special_days():
    return jsonify(read_sheet('special_days'))


@app.route('/api/special_days', methods=['POST'])
def api_add_special_day():
    data = request.get_json(force=True)
    ok = append_row('special_days', ['date', 'description', 'day_type'], {
        'date': data.get('date', ''),
        'description': data.get('description', ''),
        'day_type': data.get('day_type', ''),
    })
    return jsonify({'ok': ok, 'design_mode': not ok})


@app.route('/api/report')
def api_report():
    """Latest daily_report rows + headline (ימי שיא חסימה) counts."""
    rows = read_sheet('daily_report')
    critical = sum(1 for r in rows
                   if r.get('severity') == 'קריטי' and r.get('problem_type') == 'ימי שיא חסימה')
    warning = sum(1 for r in rows
                  if r.get('severity') == 'אזהרה' and r.get('problem_type') == 'ימי שיא חסימה')
    updated = max((str(r.get('generated_at', '')) for r in rows), default='')
    return jsonify({'rows': rows, 'critical': critical, 'warning': warning, 'updated': updated})


@app.route('/api/reports/summary')
def api_reports_summary():
    """KPI cards + submission table + shift-count bars for the active month."""
    prefix, month = _month_arg(default=get_active_month('active_month', 6))
    staff = read_sheet('staff')
    requests_rows = [r for r in read_sheet('requests') if str(r.get('date', '')).startswith(prefix)]
    schedule_rows = [r for r in read_sheet('schedule') if str(r.get('date', '')).startswith(prefix)]

    # active = those who submit night constraints (מתמחה / תורן חוץ)
    active = [s for s in staff if _norm(s.get('type', '')) in ('מתמחה', 'תורן חוץ')]
    submitted_names = {_norm(r.get('employee', '')) for r in requests_rows}

    # blocks per employee + submission status
    block_counts = {}
    for r in requests_rows:
        if r.get('status') == 'אילוץ':
            block_counts[_norm(r.get('employee', ''))] = block_counts.get(_norm(r.get('employee', '')), 0) + 1

    submissions = []
    pending = 0
    for s in active:
        nm = _norm(s.get('name', ''))
        has = nm in submitted_names
        if not has:
            pending += 1
        submissions.append({
            'name': nm, 'role': _norm(s.get('type', '')),
            'blocks': block_counts.get(nm, 0),
            'status': 'הוגש' if has else 'טרם הוגש',
        })

    # shift counts per employee (night shifts, exclude Friday-morning)
    shift_counts = {}
    for r in schedule_rows:
        if r.get('dept') in FRIDAY_DEPTS:
            continue
        emp = _norm(r.get('employee', ''))
        if emp:
            shift_counts[emp] = shift_counts.get(emp, 0) + 1
    bars = sorted(({'name': k, 'count': v} for k, v in shift_counts.items()),
                  key=lambda x: -x['count'])

    return jsonify({
        'month': month,
        'total_staff': len(active),
        'submitted': len(active) - pending,
        'pending': pending,
        'submissions': submissions,
        'bars': bars,
    })


# ---------------------------------------------------------------------------
# API — dept rotation (gantt) + daily work schedule
# ---------------------------------------------------------------------------
@app.route('/api/dept_rotation')
def api_dept_rotation():
    prefix, _ = _month_arg()
    rows = [r for r in read_sheet('dept_rotation')
            if str(r.get('year_month', '')).startswith(prefix)]
    return jsonify(rows)


@app.route('/api/work_schedule')
def api_work_schedule():
    prefix, _ = _month_arg()
    dept = request.args.get('dept')
    rows = [r for r in read_sheet('work_schedule_daily')
            if str(r.get('date', '')).startswith(prefix)]
    if dept:
        nd = _dept_norm(dept)
        rows = [r for r in rows if _dept_norm(r.get('daily_dept', '')) == nd]
    return jsonify(rows)


@app.route('/api/work_schedule/cell', methods=['POST'])
def api_work_cell():
    """Upsert one work_schedule_daily cell (manual edit → is_manual=True)."""
    data = request.get_json(force=True)
    date_s = data.get('date', '')
    emp = _norm(data.get('employee', ''))
    ws = get_ws('work_schedule_daily')
    if ws is None:
        return jsonify({'ok': False, 'design_mode': True})
    values = ws.get_all_values()
    header = ['date', 'employee', 'daily_dept', 'status', 'note', 'is_manual']
    if not values:
        ws.append_row(header)
        values = [header]
    header = values[0]
    di, ei = header.index('date'), header.index('employee')
    for i, row in enumerate(values[1:], start=2):
        if len(row) > ei and row[di] == date_s and _norm(row[ei]) == emp:
            new_row = list(row) + [''] * (len(header) - len(row))
            new_row[header.index('status')] = data.get('status', '')
            new_row[header.index('is_manual')] = 'True'
            if 'daily_dept' in header and data.get('daily_dept'):
                new_row[header.index('daily_dept')] = data.get('daily_dept')
            ws.update(f'A{i}', [new_row])
            _invalidate('work_schedule_daily')
            return jsonify({'ok': True, 'updated': True})
    ws.append_row([
        date_s, emp, data.get('daily_dept', ''),
        data.get('status', ''), data.get('note', ''), 'True',
    ])
    _invalidate('work_schedule_daily')
    return jsonify({'ok': True, 'created': True})


@app.route('/api/generate_work_schedule', methods=['POST'])
def api_generate_work_schedule():
    """Pure-Python port of _generate_work_schedule. Preserves is_manual rows."""
    data = request.get_json(force=True) or {}
    month = int(data.get('month') or get_active_month('daily_active_month', 6))
    prefix = f"{YEAR}-{month:02d}"
    ws = get_ws('work_schedule_daily')
    if ws is None:
        return jsonify({'ok': False, 'design_mode': True})

    rotation = [r for r in read_sheet('dept_rotation', fresh=True)
                if str(r.get('year_month', '')).startswith(prefix)]
    if not rotation:
        return jsonify({'ok': False, 'error': 'אין נתוני dept_rotation עבור החודש'}), 400

    # approved absences: {employee: [(start,end,type)]}
    absences = {}
    for a in read_sheet('absence_requests', fresh=True):
        if a.get('status') != 'approved':
            continue
        emp = _norm(a.get('employee', ''))
        absences.setdefault(emp, []).append(
            (str(a.get('start_date', ''))[:10], str(a.get('end_date', ''))[:10], a.get('type', '')))

    # night shifts → next day is "אחרי תורנות"
    after_duty = set()  # (employee, date_str)
    for s in read_sheet('schedule', fresh=True):
        if s.get('dept') in FRIDAY_DEPTS:
            continue
        try:
            d = datetime.strptime(str(s.get('date'))[:10], '%Y-%m-%d').date()
        except ValueError:
            continue
        after_duty.add((_norm(s.get('employee', '')), (d + timedelta(days=1)).strftime('%Y-%m-%d')))

    # preserve manual rows; rebuild the rest
    existing = read_sheet('work_schedule_daily', fresh=True)
    manual = {(str(r.get('date'))[:10], _norm(r.get('employee', '')))
              for r in existing if _is_true(r.get('is_manual', False))}
    kept = [r for r in existing
            if not (str(r.get('date', '')).startswith(prefix)
                    and not _is_true(r.get('is_manual', False)))]

    ndays = calendar.monthrange(YEAR, month)[1]
    generated = []
    for emp_row in rotation:
        emp = _norm(emp_row.get('employee', ''))
        dept = emp_row.get('daily_dept', '')
        for day in range(1, ndays + 1):
            ds = f"{prefix}-{day:02d}"
            if (ds, emp) in manual:
                continue
            status = 'עובד'
            for (start, end, atype) in absences.get(emp, []):
                if start <= ds <= end:
                    status = atype
                    break
            else:
                if (emp, ds) in after_duty:
                    status = 'אחרי תורנות'
            generated.append({'date': ds, 'employee': emp, 'daily_dept': dept,
                              'status': status, 'note': '', 'is_manual': 'False'})

    header = ['date', 'employee', 'daily_dept', 'status', 'note', 'is_manual']
    out = [header]
    for r in kept + generated:
        out.append([str(r.get(c, '')) for c in header])
    ws.clear()
    ws.update('A1', out)
    _invalidate('work_schedule_daily')
    return jsonify({'ok': True, 'generated': len(generated), 'preserved_manual': len(manual)})


# ---------------------------------------------------------------------------
# API — absence requests (approval queue)
# ---------------------------------------------------------------------------
@app.route('/api/absence_requests')
def api_absence_requests():
    rows = read_sheet('absence_requests')
    status = request.args.get('status')
    if status:
        rows = [r for r in rows if r.get('status') == status]
    return jsonify(rows)


def _update_absence_status(req_id, status, responder):
    ws = get_ws('absence_requests')
    if ws is None:
        return False
    values = ws.get_all_values()
    if not values:
        return False
    header = values[0]
    try:
        id_i = header.index('id')
    except ValueError:
        return False
    for i, row in enumerate(values[1:], start=2):
        if len(row) > id_i and row[id_i] == req_id:
            def col(name, val):
                if name in header:
                    ws.update_cell(i, header.index(name) + 1, val)
            col('status', status)
            col('approved_by', responder)
            col('responded_at', datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
            _invalidate('absence_requests')
            return True
    return False


@app.route('/api/absence/approve', methods=['POST'])
def api_absence_approve():
    data = request.get_json(force=True)
    ok = _update_absence_status(data.get('id'), 'approved', data.get('responder', 'admin'))
    return jsonify({'ok': ok, 'design_mode': get_spreadsheet() is None})


@app.route('/api/absence/reject', methods=['POST'])
def api_absence_reject():
    data = request.get_json(force=True)
    ok = _update_absence_status(data.get('id'), 'rejected', data.get('responder', 'admin'))
    return jsonify({'ok': ok, 'design_mode': get_spreadsheet() is None})


@app.route('/api/absence/add', methods=['POST'])
def api_absence_add():
    """Admin adds a pre-approved absence (status=approved immediately)."""
    data = request.get_json(force=True)
    header = ['id', 'employee', 'start_date', 'end_date', 'type', 'status',
              'dept_at_request', 'manager_email', 'approved_by', 'notes',
              'created_at', 'responded_at']
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ok = append_row('absence_requests', header, {
        'id': str(uuid.uuid4()),
        'employee': _norm(data.get('employee', '')),
        'start_date': data.get('start_date', ''),
        'end_date': data.get('end_date', '') or data.get('start_date', ''),
        'type': data.get('type', 'חופש'),
        'status': 'approved',
        'dept_at_request': data.get('dept', ''),
        'approved_by': data.get('responder', 'admin'),
        'notes': data.get('notes', ''),
        'created_at': now,
        'responded_at': now,
    })
    return jsonify({'ok': ok, 'design_mode': not ok})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    connected = get_spreadsheet() is not None
    print(f"[server] {'CONNECTED to Google Sheets' if connected else 'DESIGN MODE (no creds)'} — http://127.0.0.1:{port}")
    app.run(host='0.0.0.0', port=port, debug=True)
