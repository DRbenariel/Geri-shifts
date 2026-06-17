"""Export endpoints (write wide-format sheets)."""
from flask import Blueprint, jsonify, request

from .. import db, exports

bp = Blueprint('exports', __name__)


@bp.route('/api/export/schedule', methods=['POST'])
def api_export_schedule():
    data = request.get_json(force=True) or {}
    month = int(data.get('month') or db.get_active_month('active_month', 6))
    if db.get_spreadsheet() is None:
        return jsonify({'ok': False, 'design_mode': True})
    ok, err = exports.export_schedule_wide(month)
    return jsonify({'ok': ok, 'error': err})


@bp.route('/api/export/wsd', methods=['POST'])
def api_export_wsd():
    data = request.get_json(force=True) or {}
    month = int(data.get('month') or db.get_active_month('daily_active_month', 6))
    dept = data.get('dept', '')
    if not dept:
        return jsonify({'ok': False, 'error': 'missing dept'}), 400
    if db.get_spreadsheet() is None:
        return jsonify({'ok': False, 'design_mode': True})
    ok, err = exports.export_wsd_grid(dept, month)
    return jsonify({'ok': ok, 'error': err})
