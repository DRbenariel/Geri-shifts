"""Shared constants, lifted verbatim from appy.py (no Streamlit)."""

# Daily-schedule departments (appy.py:19)
DAILY_DEPTS_ALL = ["שיקום גריאטרי א'", "שיקום גריאטרי ב'", "פנימית גריאטרית", "זה״ב", "בדיקה"]

HEB_MONTHS = ["ינואר", "פברואר", "מרץ", "אפריל", "מאי", "יוני",
              "יולי", "אוגוסט", "ספטמבר", "אוקטובר", "נובמבר", "דצמבר"]

# פנימית גריאטרית — two sub-ward constants (appy.py:26)
PNIM_DEPT = "פנימית גריאטרית"
PNIM_SIDES = ["ורוד", "כחול"]
PNIM_COLORS = {"ורוד": "#fce7f3", "כחול": "#dbeafe"}
PNIM_ICONS = {"ורוד": "🌸", "כחול": "🔵"}

UNASSIGNED = "— לא שובץ —"

# Night-shift departments and Friday-morning half shifts
NIGHT_DEPTS = ["פנימית גריאטרית", "שיקום"]
FRIDAY_SHIFT_DEPTS = {
    "שישי בוקר - שיקום (1)", "שישי בוקר - שיקום (2)",
    "שישי בוקר - פנימית (1)", "שישי בוקר - פנימית (2)",
}
ALL_SHIFT_DEPTS = ["שיקום", "פנימית גריאטרית",
                   "שישי בוקר - שיקום (1)", "שישי בוקר - שיקום (2)",
                   "שישי בוקר - פנימית (1)", "שישי בוקר - פנימית (2)"]

LIKE_FRIDAY = 'כמו שישי (ערב חג)'
LIKE_SATURDAY = 'כמו שבת (חג)'
SPECIAL_DAY_TYPES = ["לידיעה בלבד", LIKE_FRIDAY, LIKE_SATURDAY]

ROLES = ["מתמחה", "תורן חוץ", "מנהל/ת", "רופא בכיר", "מנהל מחלקה", "מנהל על"]
STAFF_DEPTS = ["שיקום", "פנימית גריאטרית", "כללי", "הנהלה", "זה״ב"]

# Inclusive display labels for role types (appy.py:1998)
TYPE_DISPLAY = {
    'מתמחה': 'מתמחה',
    'תורן חוץ': 'תורנ/ית חוץ',
    'מנהל/ת': 'מנהל/ת',
    'רופא בכיר': 'רופא/ה בכירה',
    'מנהל מחלקה': 'מנהל/ת מחלקה',
}

# Day-schedule statuses
MANUAL_STATUSES = ["עובד", "חופש", "202", "אחרי תורנות", "אחר"]

GRID_STATUS_CYCLE = {
    "": "עובד",
    "עובד": "חופש",
    "חופש": "202",
    "202": "אחרי תורנות",
    "אחרי תורנות": "אחר",
    "אחר": "",
    "תורנות": "חופש",
}
GRID_STATUS_CYCLE_MANAGER = {"": "עובד", "עובד": ""}
GRID_STATUS_CYCLE_SENIOR = {
    "": "עובד",
    "עובד": "חופש",
    "חופש": "אחרי תורנות",
    "אחרי תורנות": "אחר",
    "אחר": "",
    "תורנות": "חופש",
}
GRID_STATUS_LABEL_SHORT = {
    "": "·",
    "עובד": "ע",
    "חופש": "ח",
    "202": "202",
    "אחרי תורנות": "א",
    "אחר": "+",
    "תורנות": "ת",
}

# absence_requests.type → work_schedule_daily status (appy.py:1739)
ABSENCE_TYPE_TO_STATUS = {
    "חופש עתידי": "חופש",
    "היעדרות אחרת": "אחר",
}

HEB_DAY_TO_IDX = {"א": 0, "ב": 1, "ג": 2, "ד": 3, "ה": 4, "ו": 5, "ש": 6}

DAILY_DEPT_TO_FRIDAY_SHIFTS = {
    "פנימית גריאטרית": ["שישי בוקר - פנימית (1)", "שישי בוקר - פנימית (2)"],
    "שיקום גריאטרי א'": ["שישי בוקר - שיקום (1)"],
    "שיקום גריאטרי ב'": ["שישי בוקר - שיקום (2)"],
}
DAILY_DEPT_TO_NIGHT_DEPT = {
    "פנימית גריאטרית": "פנימית גריאטרית",
    "שיקום גריאטרי א'": "שיקום",
    "שיקום גריאטרי ב'": "שיקום",
}

# Managers kept in `staff` but never auto-listed in a dept grid (appy.py:6145)
MANUAL_PLANT_ONLY_MANAGERS = {"רון צליק", "רתם תלם"}

ROLE_ORDER = {'מנהל מחלקה': 0, 'רופא בכיר': 1, 'מתמחה': 2}

# Batched export (appy.py:968)
BATCHED_ABSENT_STATUSES = {"חופש", "202", "אחרי תורנות", "אחר"}

# Excel colour map (appy.py:744)
XL_STATUS_FILL = {
    "עובד": "DCFCE7",
    "חופש": "DBEAFE",
    "202": "FDE047",
    "אחרי תורנות": "FFEDD5",
    "תורנות": "EDE9FE",
    "אחר": "F1F5F9",
}

KONENUT_DEPTS = {"פנימית גריאטרית", "שיקום גריאטרי א'", "שיקום גריאטרי ב'"}
KONENUT_ELIGIBLE_TYPES = {'רופא בכיר', 'מנהל מחלקה', 'מנהל/ת', 'מנהל על'}

DEFAULT_PASSWORD = "1234"

# Sheet schemas (appy.py:3199 init_db + session loaders)
SHEET_COLUMNS = {
    "staff": ['name', 'type', 'dept', 'monthly_quota', 'weekend_quota',
              'password', 'only_home_dept', 'email', 'manage_depts',
              'recurring_absent_days'],
    "schedule": ['date', 'dept', 'employee', 'is_manual', 'empty_reason'],
    "requests": ['employee', 'date', 'status'],
    "special_days": ['date', 'description', 'day_type'],
    "dept_rotation": ['employee', 'year_month', 'daily_dept'],
    "absence_requests": ['id', 'employee', 'start_date', 'end_date', 'type',
                         'status', 'dept_at_request', 'manager_email',
                         'approved_by', 'notes', 'created_at', 'responded_at'],
    "work_schedule_daily": ['date', 'employee', 'daily_dept', 'status', 'note', 'is_manual', 'side'],
    "konenut": ['date', 'pnim_dr', 'rehab_dr1', 'rehab_dr2'],
    "swap_requests": ['requester', 'requester_date', 'requester_dept', 'candidate',
                      'candidate_date', 'candidate_dept', 'swap_type', 'chain_ext',
                      'chain_ext_dept', 'created_at', 'status'],
    "settings": ['key', 'value'],
}

ANALYTICS_COLUMNS = ['event_id', 'session_id', 'timestamp', 'user_name', 'user_role',
                     'event_type', 'detail_1', 'detail_2', 'device_type', 'ua_string',
                     'viewport_width', 'active_month', 'day_of_month']

# Tabs per role (ui_components.render_navbar)
def tabs_for_role(role: str) -> list:
    items = ['הגדרות']
    if role not in ("מנהל מחלקה", "רופא בכיר", "מנהל/ת"):
        items.append('סידור תורנויות')
    if role not in ("מנהל/ת", "מנהל על", "מנהל מחלקה"):
        items.append('הגשת בקשות')
    if role == "מנהל על":
        items += ['צוות', 'דוחות וניהול']
    if role in ("מנהל על", "מנהל/ת"):
        items += ['סידור כוננויות', 'גאנט חודשי']
    if role != "תורן חוץ":
        items.append('סידור עבודה')
    if role in ("מנהל על", "מנהל/ת", "מנהל מחלקה"):
        items.append('ניהול בקשות')
    return items


def default_tab_for_role(role: str) -> str:
    default = {"מנהל על": 'דוחות וניהול', "מנהל/ת": 'גאנט חודשי',
               "מנהל מחלקה": 'סידור עבודה', "רופא בכיר": 'סידור עבודה'}.get(role, 'הגשת בקשות')
    tabs = tabs_for_role(role)
    return default if default in tabs else tabs[0]
