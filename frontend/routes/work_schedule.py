"""Daily work schedule + dept rotation endpoints."""
import calendar
from datetime import datetime, timedelta

from flask import Blueprint, jsonify, request

from .. import db
from ..config import YEAR, FRIDAY_DEPTS

bp = Blueprint('work_schedule', __name__)


@bp.route('/api/dept_rotation')
def api_dept_rotation():
    prefix, _ = db._month_arg()
    rows = [r for r in db.read_sheet('dept_rotation')
            if str(r.get('year_month', '')).startswith(prefix)]
    return jsonify(rows)


@bp.route('/api/work_schedule')
def api_work_schedule():
    prefix, _ = db._month_arg()
    dept = request.args.get('dept')
    rows = [r for r in db.read_sheet('work_schedule_daily')
            if str(r.get('date', '')).startswith(prefix)]
    if dept:
        nd = db._dept_norm(dept)
        rows = [r for r in rows if db._dept_norm(r.get('daily_dept', '')) == nd]
    return jsonify(rows)


@bp.route('/api/work_schedule/cell', methods=['POST'])
def api_work_cell():
    """Upsert one work_schedule_daily cell (manual edit → is_manual=True)."""
    data = request.get_json(force=True)
    date_s = data.get('date', '')
    emp = db._norm(data.get('employee', ''))
    ws = db.get_ws('work_schedule_daily')
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
        if len(row) > ei and row[di] == date_s and db._norm(row[ei]) == emp:
            new_row = list(row) + [''] * (len(header) - len(row))
            new_row[header.index('status')] = data.get('status', '')
            new_row[header.index('is_manual')] = 'True'
            if 'daily_dept' in header and data.get('daily_dept'):
                new_row[header.index('daily_dept')] = data.get('daily_dept')
            ws.update(f'A{i}', [new_row])
            db._invalidate('work_schedule_daily')
            return jsonify({'ok': True, 'updated': True})
    ws.append_row([
        date_s, emp, data.get('daily_dept', ''),
        data.get('status', ''), data.get('note', ''), 'True',
    ])
    db._invalidate('work_schedule_daily')
    return jsonify({'ok': True, 'created': True})


@bp.route('/api/generate_work_schedule', methods=['POST'])
def api_generate_work_schedule():
    """Pure-Python port of _generate_work_schedule. Preserves is_manual rows."""
    data = request.get_json(force=True) or {}
    month = int(data.get('month') or db.get_active_month('daily_active_month', 6))
    prefix = f"{YEAR}-{month:02d}"
    ws = db.get_ws('work_schedule_daily')
    if ws is None:
        return jsonify({'ok': False, 'design_mode': True})

    rotation = [r for r in db.read_sheet('dept_rotation', fresh=True)
                if str(r.get('year_month', '')).startswith(prefix)]
    if not rotation:
        return jsonify({'ok': False, 'error': 'אין נתוני dept_rotation עבור החודש'}), 400

    absences = {}
    for a in db.read_sheet('absence_requests', fresh=True):
        if a.get('status') != 'approved':
            continue
        emp = db._norm(a.get('employee', ''))
        absences.setdefault(emp, []).append(
            (str(a.get('start_date', ''))[:10], str(a.get('end_date', ''))[:10], a.get('type', '')))

    after_duty = set()  # (employee, date_str)
    for s in db.read_sheet('schedule', fresh=True):
        if s.get('dept') in FRIDAY_DEPTS:
            continue
        try:
            d = datetime.strptime(str(s.get('date'))[:10], '%Y-%m-%d').date()
        except ValueError:
            continue
        after_duty.add((db._norm(s.get('employee', '')), (d + timedelta(days=1)).strftime('%Y-%m-%d')))

    existing = db.read_sheet('work_schedule_daily', fresh=True)
    manual = {(str(r.get('date'))[:10], db._norm(r.get('employee', '')))
              for r in existing if db._is_true(r.get('is_manual', False))}
    kept = [r for r in existing
            if not (str(r.get('date', '')).startswith(prefix)
                    and not db._is_true(r.get('is_manual', False)))]

    ndays = calendar.monthrange(YEAR, month)[1]
    generated = []
    for emp_row in rotation:
        emp = db._norm(emp_row.get('employee', ''))
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
    db._invalidate('work_schedule_daily')
    return jsonify({'ok': True, 'generated': len(generated), 'preserved_manual': len(manual)})
