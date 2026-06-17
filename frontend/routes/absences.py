"""Absence-request (approval queue) endpoints."""
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request

from .. import db

bp = Blueprint('absences', __name__)


@bp.route('/api/absence_requests')
def api_absence_requests():
    rows = db.read_sheet('absence_requests')
    status = request.args.get('status')
    if status:
        rows = [r for r in rows if r.get('status') == status]
    return jsonify(rows)


def _update_absence_status(req_id, status, responder):
    ws = db.get_ws('absence_requests')
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
            db._invalidate('absence_requests')
            return True
    return False


@bp.route('/api/absence/approve', methods=['POST'])
def api_absence_approve():
    data = request.get_json(force=True)
    ok = _update_absence_status(data.get('id'), 'approved', data.get('responder', 'admin'))
    return jsonify({'ok': ok, 'design_mode': db.get_spreadsheet() is None})


@bp.route('/api/absence/reject', methods=['POST'])
def api_absence_reject():
    data = request.get_json(force=True)
    ok = _update_absence_status(data.get('id'), 'rejected', data.get('responder', 'admin'))
    return jsonify({'ok': ok, 'design_mode': db.get_spreadsheet() is None})


@bp.route('/api/absence/add', methods=['POST'])
def api_absence_add():
    """Admin adds a pre-approved absence (status=approved immediately)."""
    data = request.get_json(force=True)
    header = ['id', 'employee', 'start_date', 'end_date', 'type', 'status',
              'dept_at_request', 'manager_email', 'approved_by', 'notes',
              'created_at', 'responded_at']
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ok = db.append_row('absence_requests', header, {
        'id': str(uuid.uuid4()),
        'employee': db._norm(data.get('employee', '')),
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
