"""Employee submission endpoints: night constraints/wishes + day-absence requests."""
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request, session

from .. import db, analytics
from ..config import YEAR
from ..email_util import send_notification_email

bp = Blueprint('submissions', __name__)

REQ_HEADER = ['employee', 'date', 'status']
ABS_HEADER = ['id', 'employee', 'start_date', 'end_date', 'type', 'status',
              'dept_at_request', 'manager_email', 'approved_by', 'notes',
              'created_at', 'responded_at']


@bp.route('/api/requests/submit', methods=['POST'])
def api_requests_submit():
    """Replace the logged-in user's night constraints/wishes for one month.

    Mirrors appy.py:6580-6603 — delete the user's rows for the month, then add
    אילוץ rows for blocks + בקשה rows for wishes. blocks/wishes are date strings.
    """
    data = request.get_json(force=True) or {}
    user = db._norm(session.get('user', ''))
    if not user:
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401
    month = int(data.get('month') or db.get_active_month('active_month', 6))
    prefix = f"{YEAR}-{month:02d}"
    blocks = [str(d) for d in (data.get('blocks') or [])]
    wishes = [str(d) for d in (data.get('wishes') or [])]

    if db.get_spreadsheet() is None:
        return jsonify({'ok': False, 'design_mode': True})

    existing = db.read_sheet('requests', fresh=True)
    kept = [r for r in existing
            if not (db._norm(r.get('employee', '')) == user and str(r.get('date', '')).startswith(prefix))]
    new_rows = kept \
        + [{'employee': user, 'date': d, 'status': 'אילוץ'} for d in blocks] \
        + [{'employee': user, 'date': d, 'status': 'בקשה'} for d in wishes]
    ok = db.overwrite_sheet('requests', REQ_HEADER, new_rows)
    analytics.log_event(user, session.get('role', ''), 'constraint_submit', len(blocks), len(wishes))
    return jsonify({'ok': ok, 'blocks': len(blocks), 'wishes': len(wishes)})


def _staff_row(name):
    for s in db.read_sheet('staff'):
        if db._norm(s.get('name', '')) == db._norm(name):
            return s
    return {}


def _manager_email_for_dept(dept):
    nd = db._dept_norm(dept)
    for s in db.read_sheet('staff'):
        if db._norm(s.get('type', '')) == 'מנהל מחלקה':
            managed = [db._dept_norm(x) for x in str(s.get('manage_depts', '')).split(',')]
            if nd and nd in managed:
                return str(s.get('email', ''))
    return ''


@bp.route('/api/absence/submit', methods=['POST'])
def api_absence_submit():
    """Employee self-submits a day-absence request (status=pending) + emails manager."""
    data = request.get_json(force=True) or {}
    user = db._norm(session.get('user', ''))
    if not user:
        return jsonify({'ok': False, 'error': 'unauthorized'}), 401
    start = data.get('start_date', '')
    end = data.get('end_date', '') or start
    atype = data.get('type', 'חופש')
    if not start:
        return jsonify({'ok': False, 'error': 'missing date'}), 400

    dept = str(_staff_row(user).get('dept', ''))
    manager_email = _manager_email_for_dept(dept)
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ok = db.append_row('absence_requests', ABS_HEADER, {
        'id': str(uuid.uuid4()), 'employee': user, 'start_date': start, 'end_date': end,
        'type': atype, 'status': 'pending', 'dept_at_request': dept,
        'manager_email': manager_email, 'created_at': now,
    })
    if ok and manager_email:
        send_notification_email(
            manager_email, f"בקשת היעדרות חדשה — {user}",
            f"<div dir='rtl'>העובד/ת <b>{user}</b> ({dept}) הגיש/ה בקשת <b>{atype}</b> "
            f"לתאריכים {start} עד {end}.<br>נא לאשר/לדחות במערכת.</div>")
    return jsonify({'ok': ok, 'design_mode': not ok})
