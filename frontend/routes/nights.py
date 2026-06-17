"""Night-shift schedule, requests, special days, and reports endpoints."""
from flask import Blueprint, jsonify, request

from .. import db
from ..config import FRIDAY_DEPTS

bp = Blueprint('nights', __name__)


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
