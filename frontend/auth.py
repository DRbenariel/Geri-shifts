"""
auth.py — session auth, role→tabs mapping, and request guards.

Replicates the Streamlit model: SHA256-hashed passwords stored in the `staff`
sheet (appy.py:2475), role read from the `type` column. Adds Flask server-side
(signed-cookie) sessions + login/role gating on /api/*.
"""
import hashlib

from flask import session, request, jsonify

ADMIN = 'מנהל על'
MANAGER = 'מנהל/ת'
DEPT = 'מנהל מחלקה'
SENIOR = 'רופא בכיר'
INTERN = 'מתמחה'
EXTERNAL = 'תורן חוץ'


def sha256(p):
    return hashlib.sha256(str(p).encode()).hexdigest()


# ── Role → ordered list of tabs (mirrors ui_components.render_navbar:365-417) ──
def tabs_for(role):
    t = [('settings', 'הגדרות')]
    if role not in (DEPT, SENIOR, MANAGER):
        t.append(('shifts', 'סידור תורנויות'))
    if role not in (MANAGER, ADMIN, DEPT):
        t.append(('submit', 'הגשת בקשות'))
    if role == ADMIN:
        t.append(('staff', 'צוות'))
        t.append(('reports', 'דוחות וניהול'))
    if role in (ADMIN, MANAGER):
        t.append(('monthly', 'גאנט חודשי'))
    if role != EXTERNAL:
        t.append(('daily', 'סידור עבודה'))
    if role in (ADMIN, MANAGER, DEPT):
        t.append(('requests', 'ניהול בקשות'))
    return [{'key': k, 'label': lbl} for k, lbl in t]


def default_tab(role):
    return {
        ADMIN: 'reports', MANAGER: 'monthly', DEPT: 'daily', SENIOR: 'daily',
    }.get(role, 'submit')


# ── Per-endpoint role rules (writes). Reads only need a valid session. ──
ROLE_RULES = {
    ('POST', '/api/staff'): {ADMIN},
    ('POST', '/api/special_days'): {ADMIN},
    ('POST', '/api/settings'): {ADMIN, MANAGER},
    ('POST', '/api/generate_work_schedule'): {ADMIN, MANAGER},
    ('POST', '/api/work_schedule/cell'): {ADMIN, MANAGER, DEPT},
    ('POST', '/api/absence/approve'): {ADMIN, MANAGER, DEPT},
    ('POST', '/api/absence/reject'): {ADMIN, MANAGER, DEPT},
    ('POST', '/api/absence/add'): {ADMIN, MANAGER, DEPT},
    ('POST', '/api/smart_schedule'): {ADMIN},
    ('POST', '/api/export/schedule'): {ADMIN},
    ('POST', '/api/export/wsd'): {ADMIN, MANAGER},
    ('POST', '/api/daily_report/run'): {ADMIN},
}

# Endpoints reachable without a session.
PUBLIC = {'/api/health', '/api/login'}


def install_guards(app):
    """Gate every /api/* route: login required (except PUBLIC) + role rules."""
    @app.before_request
    def _guard():
        p = request.path
        if not p.startswith('/api/') or p in PUBLIC:
            return None
        if 'user' not in session:
            return jsonify({'ok': False, 'error': 'unauthorized'}), 401
        allowed = ROLE_RULES.get((request.method, p))
        if allowed and session.get('role') not in allowed:
            return jsonify({'ok': False, 'error': 'forbidden'}), 403
        return None
