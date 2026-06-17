"""Swap endpoints: search (employee), request, approve/reject (admin)."""
import uuid
from datetime import datetime

from flask import Blueprint, jsonify, request, session

from .. import db
from ..config import YEAR
from scheduling_core import find_swap_candidates

bp = Blueprint('swaps', __name__)

SWAP_HEADER = ['id', 'requester', 'requester_date', 'requester_dept',
               'candidate', 'candidate_date', 'candidate_dept', 'swap_type',
               'chain_ext', 'chain_ext_dept', 'created_at', 'status']
SCHEDULE_HEADER = ['date', 'dept', 'employee', 'is_manual', 'empty_reason']


@bp.route('/api/swaps/search')
def api_swaps_search():
    user = db._norm(session.get('user', ''))
    swap_date = request.args.get('date', '')
    swap_dept = request.args.get('dept', '')
    if not swap_date or not swap_dept:
        return jsonify({'full': [], 'partial': [], 'chain': []})
    staff_df = db.read_df('staff', fresh=True, strip_names=False)
    schedule_df = db.read_df('schedule', fresh=True, strip_names=False)
    requests_df = db.read_df('requests', fresh=True, strip_names=False)
    for col in ('employee', 'date', 'status'):
        if col not in requests_df.columns:
            requests_df[col] = ''
    for col in SCHEDULE_HEADER:
        if col not in schedule_df.columns:
            schedule_df[col] = ''
    if staff_df.empty:
        return jsonify({'full': [], 'partial': [], 'chain': []})
    month = int(str(swap_date)[5:7]) if len(str(swap_date)) >= 7 else db.get_active_month('active_month', 6)
    res = find_swap_candidates(schedule_df, requests_df, staff_df, user, swap_date, swap_dept, month, year=YEAR)
    return jsonify(res)


@bp.route('/api/swaps/request', methods=['POST'])
def api_swaps_request():
    data = request.get_json(force=True) or {}
    user = db._norm(session.get('user', ''))
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    ok = db.append_row('swap_requests', SWAP_HEADER, {
        'id': str(uuid.uuid4()),
        'requester': user,
        'requester_date': data.get('requester_date', ''),
        'requester_dept': data.get('requester_dept', ''),
        'candidate': data.get('candidate', ''),
        'candidate_date': data.get('candidate_date', ''),
        'candidate_dept': data.get('candidate_dept', ''),
        'swap_type': data.get('swap_type', 'partial'),
        'chain_ext': data.get('chain_ext', ''),
        'chain_ext_dept': data.get('chain_ext_dept', ''),
        'created_at': now, 'status': 'pending',
    })
    return jsonify({'ok': ok, 'design_mode': not ok})


@bp.route('/api/swaps')
def api_swaps_list():
    rows = db.read_sheet('swap_requests')
    status = request.args.get('status')
    if status:
        rows = [r for r in rows if r.get('status') == status]
    return jsonify(rows)


def _apply_swap(req):
    """Mutate the schedule sheet to execute an approved swap. Returns True on write."""
    rows = db.read_sheet('schedule', fresh=True)
    for col in SCHEDULE_HEADER:
        for r in rows:
            r.setdefault(col, '')

    def find(date_s, dept, emp):
        for r in rows:
            if str(r.get('date', '')) == date_s and r.get('dept') == dept and db._norm(r.get('employee', '')) == db._norm(emp):
                return r
        return None

    st = req.get('swap_type', 'partial')
    rq, rqd, rqdept = req.get('requester'), req.get('requester_date'), req.get('requester_dept')
    cand, cd, cdept = req.get('candidate'), req.get('candidate_date'), req.get('candidate_dept')

    if st == 'full':
        a = find(rqd, rqdept, rq)
        b = find(cd, cdept, cand)
        if a:
            a['employee'] = cand; a['is_manual'] = 'True'
        if b:
            b['employee'] = rq; b['is_manual'] = 'True'
    elif st == 'partial':
        a = find(rqd, rqdept, rq)
        if a:
            a['employee'] = cand; a['is_manual'] = 'True'
    elif st == 'chain':
        ext, extdept = req.get('chain_ext'), req.get('chain_ext_dept') or 'שיקום'
        a = find(rqd, 'פנימית גריאטרית', rq)     # requester leaves פנימית
        b = find(rqd, 'שיקום', cand)              # מתמחה moves שיקום→פנימית
        if a:
            a['employee'] = cand; a['is_manual'] = 'True'
        if b:
            b['employee'] = ext; b['is_manual'] = 'True'
    return db.overwrite_sheet('schedule', SCHEDULE_HEADER, rows)


def _set_swap_status(req_id, status, apply=False):
    ws = db.get_ws('swap_requests')
    if ws is None:
        return False, None
    values = ws.get_all_values()
    if not values:
        return False, None
    header = values[0]
    try:
        id_i = header.index('id')
        st_i = header.index('status')
    except ValueError:
        return False, None
    for i, row in enumerate(values[1:], start=2):
        if len(row) > id_i and row[id_i] == req_id:
            req = dict(zip(header, row))
            ws.update_cell(i, st_i + 1, status)
            db._invalidate('swap_requests')
            if apply:
                _apply_swap(req)
            return True, req
    return False, None


@bp.route('/api/swaps/approve', methods=['POST'])
def api_swaps_approve():
    data = request.get_json(force=True) or {}
    ok, _ = _set_swap_status(data.get('id'), 'approved', apply=True)
    return jsonify({'ok': ok, 'design_mode': db.get_spreadsheet() is None})


@bp.route('/api/swaps/reject', methods=['POST'])
def api_swaps_reject():
    data = request.get_json(force=True) or {}
    ok, _ = _set_swap_status(data.get('id'), 'rejected', apply=False)
    return jsonify({'ok': ok, 'design_mode': db.get_spreadsheet() is None})
