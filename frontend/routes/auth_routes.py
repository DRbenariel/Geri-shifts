"""Authentication endpoints: login / logout / me / change_password."""
from flask import Blueprint, jsonify, request, session

from .. import db
from ..auth import sha256, tabs_for, default_tab

bp = Blueprint('auth', __name__)


@bp.route('/api/login', methods=['POST'])
def api_login():
    data = request.get_json(force=True) or {}
    username = str(data.get('username', '')).strip()
    password = str(data.get('password', ''))

    staff = db.read_sheet('staff', fresh=True)   # always fresh, like appy.py _fetch_live
    if not staff:
        return jsonify({'ok': False, 'error': 'לא ניתן לטעון את רשימת הצוות'}), 503
    if 'name' not in staff[0]:
        return jsonify({'ok': False, 'error': 'לא ניתן לטעון את רשימת הצוות'}), 503

    h = sha256(password)
    matches = [s for s in staff if str(s.get('name', '')).strip() == username]
    if not matches:
        return jsonify({'ok': False, 'error': 'שם המשתמש לא נמצא במערכת'}), 401
    user = next((s for s in matches if str(s.get('password', '')) == h), None)
    if user is None:
        return jsonify({'ok': False, 'error': 'סיסמה שגויה'}), 401

    role = str(user.get('type', '')).strip()
    session['user'] = username
    session['role'] = role
    session.permanent = True
    return jsonify({'ok': True, 'name': username, 'role': role,
                    'tabs': tabs_for(role), 'default_tab': default_tab(role)})


@bp.route('/api/logout', methods=['POST'])
def api_logout():
    session.clear()
    return jsonify({'ok': True})


@bp.route('/api/me')
def api_me():
    role = session.get('role', '')
    return jsonify({'name': session.get('user', ''), 'role': role,
                    'tabs': tabs_for(role), 'default_tab': default_tab(role)})


@bp.route('/api/change_password', methods=['POST'])
def api_change_password():
    data = request.get_json(force=True) or {}
    current = str(data.get('current', ''))
    new = str(data.get('new', ''))
    if len(new) < 3:
        return jsonify({'ok': False, 'error': 'סיסמה חדשה קצרה מדי'}), 400

    name = session.get('user', '')
    ws = db.get_ws('staff')
    if ws is None:
        return jsonify({'ok': False, 'design_mode': True})
    values = ws.get_all_values()
    if not values:
        return jsonify({'ok': False, 'error': 'no staff'}), 500
    header = values[0]
    try:
        ni, pi = header.index('name'), header.index('password')
    except ValueError:
        return jsonify({'ok': False, 'error': 'staff sheet missing columns'}), 500

    for i, row in enumerate(values[1:], start=2):
        if len(row) > ni and str(row[ni]).strip() == name:
            if len(row) <= pi or str(row[pi]) != sha256(current):
                return jsonify({'ok': False, 'error': 'הסיסמה הנוכחית שגויה'}), 403
            ws.update_cell(i, pi + 1, sha256(new))
            db._invalidate('staff')
            return jsonify({'ok': True})
    return jsonify({'ok': False, 'error': 'user not found'}), 404
