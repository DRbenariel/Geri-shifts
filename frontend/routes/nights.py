"""Night-shift schedule, requests, special days, and reports endpoints."""
from flask import Blueprint, jsonify, request

from .. import db
from ..config import YEAR, FRIDAY_DEPTS
from scheduling_core import run_smart_scheduling

bp = Blueprint('nights', __name__)

SCHEDULE_HEADER = ['date', 'dept', 'employee', 'is_manual', 'empty_reason']


@bp.route('/api/requests')
def api_requests():
    prefix, _ = db._month_arg()
    rows = [r for r in db.read_sheet('requests')
            if str(r.get('date', '')).startswith(prefix)]
    return jsonify(rows)


@bp.route('/api/schedule')
def api_schedule():
    prefix, _ = db._month_arg()
    rows = [r for r in db.read_sheet('schedule')
            if str(r.get('date', '')).startswith(prefix)]
    return jsonify(rows)


@bp.route('/api/smart_schedule', methods=['POST'])
def api_smart_schedule():
    """Run the greedy night-shift scheduler and write the result to `schedule`.

    Mirrors appy.py:run_smart_scheduling — staff names are NOT stripped
    (strip_names=False) so output matches the Streamlit app for parity tests.
    """
    data = request.get_json(force=True) or {}
    month = int(data.get('month') or db.get_active_month('active_month', 6))
    only_weekends = bool(data.get('only_weekends', False))

    if db.get_spreadsheet() is None:
        return jsonify({'ok': False, 'design_mode': True})

    staff_df = db.read_df('staff', fresh=True, strip_names=False)
    schedule_df = db.read_df('schedule', fresh=True, strip_names=False)
    requests_df = db.read_df('requests', fresh=True, strip_names=False)
    special_df = db.read_df('special_days', fresh=True, strip_names=False)
    if staff_df.empty:
        return jsonify({'ok': False, 'error': 'אין נתוני צוות'}), 400
    # guarantee expected columns even when a sheet is empty
    for col in SCHEDULE_HEADER:
        if col not in schedule_df.columns:
            schedule_df[col] = ''
    for col in ('employee', 'date', 'status'):
        if col not in requests_df.columns:
            requests_df[col] = ''
    for col in ('date', 'description', 'day_type'):
        if col not in special_df.columns:
            special_df[col] = ''

    rows, balancing_msg = run_smart_scheduling(
        YEAR, month, staff_df, schedule_df, requests_df, special_df, only_weekends=only_weekends)

    ok = db.overwrite_sheet('schedule', SCHEDULE_HEADER, rows)
    prefix = f"{YEAR}-{month:02d}"
    filled = sum(1 for r in rows if str(r.get('date', '')).startswith(prefix)
                 and r.get('dept') in ('פנימית גריאטרית', 'שיקום') and r.get('employee') not in ('', '---'))
    empties = sum(1 for r in rows if str(r.get('date', '')).startswith(prefix) and r.get('employee') == '---')
    return jsonify({'ok': ok, 'filled': filled, 'empty': empties, 'message': balancing_msg})


@bp.route('/api/special_days')
def api_special_days():
    return jsonify(db.read_sheet('special_days'))


@bp.route('/api/special_days', methods=['POST'])
def api_add_special_day():
    data = request.get_json(force=True)
    ok = db.append_row('special_days', ['date', 'description', 'day_type'], {
        'date': data.get('date', ''),
        'description': data.get('description', ''),
        'day_type': data.get('day_type', ''),
    })
    return jsonify({'ok': ok, 'design_mode': not ok})


@bp.route('/api/report')
def api_report():
    """Latest daily_report rows + headline (ימי שיא חסימה) counts."""
    rows = db.read_sheet('daily_report')
    critical = sum(1 for r in rows
                   if r.get('severity') == 'קריטי' and r.get('problem_type') == 'ימי שיא חסימה')
    warning = sum(1 for r in rows
                  if r.get('severity') == 'אזהרה' and r.get('problem_type') == 'ימי שיא חסימה')
    updated = max((str(r.get('generated_at', '')) for r in rows), default='')
    return jsonify({'rows': rows, 'critical': critical, 'warning': warning, 'updated': updated})


@bp.route('/api/reports/summary')
def api_reports_summary():
    """KPI cards + submission table + shift-count bars for the active month."""
    prefix, month = db._month_arg(default=db.get_active_month('active_month', 6))
    staff = db.read_sheet('staff')
    requests_rows = [r for r in db.read_sheet('requests') if str(r.get('date', '')).startswith(prefix)]
    schedule_rows = [r for r in db.read_sheet('schedule') if str(r.get('date', '')).startswith(prefix)]

    active = [s for s in staff if db._norm(s.get('type', '')) in ('מתמחה', 'תורן חוץ')]
    submitted_names = {db._norm(r.get('employee', '')) for r in requests_rows}

    block_counts = {}
    for r in requests_rows:
        if r.get('status') == 'אילוץ':
            nm = db._norm(r.get('employee', ''))
            block_counts[nm] = block_counts.get(nm, 0) + 1

    submissions = []
    pending = 0
    for s in active:
        nm = db._norm(s.get('name', ''))
        has = nm in submitted_names
        if not has:
            pending += 1
        submissions.append({
            'name': nm, 'role': db._norm(s.get('type', '')),
            'blocks': block_counts.get(nm, 0),
            'status': 'הוגש' if has else 'טרם הוגש',
        })

    shift_counts = {}
    for r in schedule_rows:
        if r.get('dept') in FRIDAY_DEPTS:
            continue
        emp = db._norm(r.get('employee', ''))
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
