"""
analytics.py — append-only event logging, ported from appy.py:2186.

log_event() appends one row to the analytics_log sheet. Wrapped in except —
dropped events are acceptable, never crashes the request.
"""
import uuid
from datetime import datetime

from . import db

HEADER = ['event_id', 'session_id', 'timestamp', 'user_name', 'user_role',
          'event_type', 'detail_1', 'detail_2', 'device_type', 'ua_string',
          'viewport_width', 'active_month', 'day_of_month']


def log_event(user_name, user_role, event_type, detail_1='', detail_2='',
              session_id='', device='unknown', ua='', viewport='', active_month=''):
    try:
        now = datetime.now()
        row = {
            'event_id': str(uuid.uuid4()),
            'session_id': session_id,
            'timestamp': now.strftime('%Y-%m-%d %H:%M:%S'),
            'user_name': user_name,
            'user_role': user_role,
            'event_type': event_type,
            'detail_1': str(detail_1),
            'detail_2': str(detail_2),
            'device_type': device,
            'ua_string': str(ua)[:200],
            'viewport_width': str(viewport),
            'active_month': str(active_month),
            'day_of_month': now.day,
        }
        db.append_row('analytics_log', HEADER, row)
    except Exception:
        pass
