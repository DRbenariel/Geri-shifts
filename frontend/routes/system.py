"""System + settings + analytics endpoints."""
from flask import Blueprint, jsonify, request, session

from .. import db, analytics

bp = Blueprint('system', __name__)


@bp.route('/api/log_event', methods=['POST'])
def api_log_event():
    data = request.get_json(force=True) or {}
    analytics.log_event(
        session.get('user', ''), session.get('role', ''),
        data.get('event_type', ''), data.get('detail_1', ''), data.get('detail_2', ''),
        session_id=data.get('session_id', ''), device=data.get('device', 'unknown'),
        ua=data.get('ua', ''), viewport=data.get('viewport', ''),
        active_month=db.get_active_month('active_month', 6))
    return jsonify({'ok': True})


@bp.route('/api/health')
def api_health():
    connected = db.get_spreadsheet() is not None
    return jsonify({'ok': True, 'connected': connected, 'design_mode': not connected})


@bp.route('/api/settings')
def api_settings():
    s = db.settings_map()
    return jsonify({
        'all': s,
        'active_month': db.get_active_month('active_month', 6),
        'daily_active_month': db.get_active_month('daily_active_month', 6),
        'daily_requests_open': db._is_true(s.get('daily_requests_open', 'True')),
    })


@bp.route('/api/settings', methods=['POST'])
def api_set_setting():
    data = request.get_json(force=True)
    key, value = data.get('key'), data.get('value')
    if key is None:
        return jsonify({'ok': False, 'error': 'missing key'}), 400
    ok = db.set_setting(key, value)
    # mirror the app: opening a new daily month re-opens requests
    if key == 'daily_active_month':
        db.set_setting('daily_requests_open', 'True')
    return jsonify({'ok': ok, 'design_mode': not ok})
