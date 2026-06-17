"""Staff endpoints."""
from flask import Blueprint, jsonify, request

from .. import db

bp = Blueprint('staff', __name__)


@bp.route('/api/staff')
def api_staff():
    rows = db.read_sheet('staff')
    for r in rows:
        r['only_home_dept'] = db._is_true(r.get('only_home_dept', False))
    return jsonify(rows)


@bp.route('/api/staff', methods=['POST'])
def api_staff_save():
    """Add a new staff member or update an existing one (matched by name)."""
    data = request.get_json(force=True)
    name = db._norm(data.get('name', ''))
    if not name:
        return jsonify({'ok': False, 'error': 'missing name'}), 400
    ws = db.get_ws('staff')
    if ws is None:
        return jsonify({'ok': False, 'design_mode': True})
    values = ws.get_all_values()
    header = values[0] if values else list(data.keys())
    if not values:
        ws.append_row(header)
    name_col = header.index('name') if 'name' in header else 0
    for i, row in enumerate(values[1:], start=2):
        if len(row) > name_col and db._norm(row[name_col]) == name:
            new_row = [str(data.get(c, row[j] if j < len(row) else '')) for j, c in enumerate(header)]
            ws.update(f'A{i}', [new_row])
            db._invalidate('staff')
            return jsonify({'ok': True, 'updated': True})
    ws.append_row([str(data.get(c, '')) for c in header])
    db._invalidate('staff')
    return jsonify({'ok': True, 'created': True})
