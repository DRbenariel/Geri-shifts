"""
daily_report.py — Scheduled agent that scans upcoming month shift submissions
and flags projected scheduling problems. Saves results to 'daily_report' Google Sheet.

Run manually:  python daily_report.py
Run via CI:    GitHub Actions (.github/workflows/daily_report.yml)
"""

import os
import json
import calendar
import gspread
import pandas as pd
from datetime import datetime, date, timedelta
from google.oauth2.service_account import Credentials

SCOPES = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
SPREADSHEET_URL = "https://docs.google.com/spreadsheets/d/1fmjfqA04VMfbBYHw2OXqoY08X7heazlx0Cr2Uaa2LkY/edit?usp=sharing"
YEAR = 2026
DEPTS = ['פנימית גריאטרית', 'שיקום']


# ---------------------------------------------------------------------------
# Google Sheets helpers
# ---------------------------------------------------------------------------

def get_client():
    """Connect using env var (GitHub Actions) or local JSON file."""
    creds_json = os.environ.get('GSHEETS_CREDENTIALS')
    if creds_json:
        creds_dict = json.loads(creds_json)
    else:
        key_file = os.path.join(os.path.dirname(__file__), 'gerishifts-7ccae6b773f7.json')
        with open(key_file) as f:
            creds_dict = json.load(f)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def load_sheet(sh, name):
    try:
        ws = sh.worksheet(name)
        data = ws.get_all_records()
        return pd.DataFrame(data)
    except gspread.exceptions.WorksheetNotFound:
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Analysis helpers
# ---------------------------------------------------------------------------

def parse_bool(v):
    if isinstance(v, bool):
        return v
    if pd.isna(v):
        return False
    return str(v).strip().lower() == 'true'


def is_eligible(emp, dept, d_str, blocked_map):
    """Returns True if this employee can in principle work dept on d_str."""
    name = emp['name']
    # Type restriction: externals can't work פנימית
    if str(emp.get('type', '')).strip() == 'תורן חוץ' and dept == 'פנימית גריאטרית':
        return False
    # Blocked constraint
    if d_str in blocked_map.get(name, set()):
        return False
    # Home dept restriction
    if parse_bool(emp.get('only_home_dept', False)):
        home = str(emp.get('dept', '')).strip()
        if home not in ('כללי', dept):
            return False
    return True


def build_blocked_map(requests_df, month_prefix):
    """Returns {employee: set_of_blocked_date_strings} for the given month."""
    blocked = {}
    if requests_df.empty:
        return blocked
    month_reqs = requests_df[
        (requests_df['date'].astype(str).str.startswith(month_prefix)) &
        (requests_df['status'] == 'אילוץ')
    ]
    for _, r in month_reqs.iterrows():
        emp = r['employee']
        if emp not in blocked:
            blocked[emp] = set()
        blocked[emp].add(str(r['date'])[:10])
    return blocked


def get_active_month(settings_df):
    if settings_df.empty:
        return 5
    row = settings_df[settings_df['key'] == 'active_month']
    if row.empty:
        return 5
    try:
        return int(row.iloc[0]['value'])
    except (ValueError, TypeError):
        return 5


# ---------------------------------------------------------------------------
# Problem detectors
# ---------------------------------------------------------------------------

def check_empty_days(year, month, active_staff, blocked_map):
    """Days/depts with 0 or 1 eligible employee."""
    problems = []
    num_days = calendar.monthrange(year, month)[1]

    for day in range(1, num_days + 1):
        d_str = f"{year}-{month:02d}-{day:02d}"
        d_obj = date(year, month, day)
        is_weekend = d_obj.weekday() in (4, 5)  # Friday / Saturday

        for dept in DEPTS:
            eligible = [
                emp['name'] for _, emp in active_staff.iterrows()
                if is_eligible(emp, dept, d_str, blocked_map)
            ]
            n = len(eligible)
            weekend_label = 'סופ"ש'
            day_label = f"{day}/{month} ({weekend_label if is_weekend else 'חול'})"

            if n == 0:
                problems.append({
                    'severity': 'קריטי',
                    'problem_type': 'יום ריק',
                    'description': f"יום {day_label} — {dept}: אף עובד זמין",
                    'day': day
                })
            elif n == 1:
                problems.append({
                    'severity': 'אזהרה',
                    'problem_type': 'כיסוי דל',
                    'description': f"יום {day_label} — {dept}: רק {eligible[0]} זמין (אין גיבוי)",
                    'day': day
                })

    return problems


def check_quota_risk(year, month, active_staff, blocked_map):
    """Employees who blocked so many days that hitting their quota is impossible or very tight."""
    problems = []
    num_days = calendar.monthrange(year, month)[1]
    month_prefix = f"{year}-{month:02d}"

    for _, emp in active_staff.iterrows():
        name = emp['name']
        try:
            quota = int(emp.get('monthly_quota', 4) or 4)
        except (ValueError, TypeError):
            quota = 4
        if quota == 0:
            continue

        emp_blocks = blocked_map.get(name, set())
        n_blocked = len([d for d in emp_blocks if d.startswith(month_prefix)])
        available = num_days - n_blocked

        if available < quota:
            problems.append({
                'severity': 'קריטי',
                'problem_type': 'מכסה בלתי אפשרית',
                'description': (
                    f"{name}: {n_blocked} ימי חסימה, {available} ימים פנויים — "
                    f"מכסה {quota}. מתמטית בלתי אפשרי להגיע למכסה!"
                ),
                'day': 0
            })
        elif available < quota * 1.5:
            problems.append({
                'severity': 'אזהרה',
                'problem_type': 'מכסה בסיכון',
                'description': (
                    f"{name}: {available} ימים פנויים למכסה של {quota} — מרווח צר מאוד"
                ),
                'day': 0
            })

        # Consecutive block streak: a long run blocks rest-gap days around it too
        sorted_blocks = sorted([d for d in emp_blocks if d.startswith(month_prefix)])
        if len(sorted_blocks) >= 4:
            max_streak = cur_streak = 1
            for i in range(1, len(sorted_blocks)):
                d1 = datetime.strptime(sorted_blocks[i - 1], '%Y-%m-%d').date()
                d2 = datetime.strptime(sorted_blocks[i], '%Y-%m-%d').date()
                if (d2 - d1).days == 1:
                    cur_streak += 1
                    max_streak = max(max_streak, cur_streak)
                else:
                    cur_streak = 1
            if max_streak >= 5:
                problems.append({
                    'severity': 'אזהרה',
                    'problem_type': 'רצף חסימות',
                    'description': (
                        f"{name}: רצף של {max_streak} ימי חסימה רצופים — "
                        f"יצור אובדן ימי מנוחה (2 ימים לפני ואחרי), מכסה תתקשה עוד יותר"
                    ),
                    'day': 0
                })

    return problems


def check_who_not_submitted(year, month, active_staff, requests_df):
    """Employees who haven't submitted any constraints or wishes yet."""
    problems = []
    month_prefix = f"{year}-{month:02d}"

    if requests_df.empty:
        submitted_names = set()
    else:
        submitted = requests_df[requests_df['date'].astype(str).str.startswith(month_prefix)]
        submitted_names = set(submitted['employee'].unique())

    not_submitted = [
        emp['name'] for _, emp in active_staff.iterrows()
        if emp['name'] not in submitted_names
    ]

    if not_submitted:
        problems.append({
            'severity': 'מידע',
            'problem_type': 'לא הגישו בקשות',
            'description': f"{len(not_submitted)} עובדים טרם הגישו בקשות: {', '.join(not_submitted)}",
            'day': 0
        })

    return problems


def check_heavily_blocked_days(year, month, active_staff, blocked_map):
    """Days where a high share of employees blocked simultaneously — the hardest to fill."""
    problems = []
    num_days = calendar.monthrange(year, month)[1]
    n_active = len(active_staff)
    if n_active == 0:
        return problems

    for day in range(1, num_days + 1):
        d_str = f"{year}-{month:02d}-{day:02d}"
        d_obj = date(year, month, day)
        is_weekend = d_obj.weekday() in (4, 5)
        weekend_label = 'סופ"ש'
        day_label = f"{day}/{month} ({weekend_label if is_weekend else 'חול'})"

        blockers = [
            emp['name'] for _, emp in active_staff.iterrows()
            if d_str in blocked_map.get(emp['name'], set())
        ]
        n_blocked = len(blockers)
        if n_blocked < 2:
            continue

        block_pct = n_blocked / n_active
        if block_pct >= 0.5:
            severity = 'קריטי'
        elif block_pct >= 0.3:
            severity = 'אזהרה'
        else:
            continue

        pct_str = f"{int(block_pct * 100)}%"
        names_preview = ', '.join(blockers[:5])
        if len(blockers) > 5:
            names_preview += f' ועוד {len(blockers) - 5}'
        problems.append({
            'severity': severity,
            'problem_type': 'ימי שיא חסימה',
            'description': (
                f"יום {day_label}: {n_blocked}/{n_active} עובדים חסמו ({pct_str}) — "
                f"יהיה קשה לאיוש. חסמו: {names_preview}"
            ),
            'day': day
        })

    return problems


def check_weekend_coverage(year, month, active_staff, blocked_map):
    """Weekends with dangerously few eligible staff (separate from empty_days for emphasis)."""
    problems = []
    num_days = calendar.monthrange(year, month)[1]

    for day in range(1, num_days + 1):
        d_obj = date(year, month, day)
        if d_obj.weekday() not in (4, 5):
            continue
        d_str = str(d_obj)
        day_name = "שישי" if d_obj.weekday() == 4 else "שבת"

        for dept in DEPTS:
            eligible = [
                emp['name'] for _, emp in active_staff.iterrows()
                if is_eligible(emp, dept, d_str, blocked_map)
            ]
            # Only warn here if > 1 (==0 and ==1 already caught by check_empty_days)
            if len(eligible) == 2:
                problems.append({
                    'severity': 'מידע',
                    'problem_type': 'כיסוי סופ"ש',
                    'description': (
                        f"{day_name} {day}/{month} — {dept}: "
                        f"רק 2 זמינים ({', '.join(eligible)}) — אין גמישות"
                    ),
                    'day': day
                })

    return problems


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def analyze_month(year, month, staff_df, requests_df):
    month_prefix = f"{year}-{month:02d}"

    # Active scheduling employees only
    active_staff = staff_df[
        staff_df['name'].notna() &
        ~staff_df['name'].isin(['---', 'ADMIN']) &
        staff_df['type'].isin(['מתמחה', 'תורן חוץ'])
    ].copy()

    blocked_map = build_blocked_map(requests_df, month_prefix)

    problems = []
    problems += check_heavily_blocked_days(year, month, active_staff, blocked_map)
    problems += check_who_not_submitted(year, month, active_staff, requests_df)
    problems += check_quota_risk(year, month, active_staff, blocked_map)
    problems += check_empty_days(year, month, active_staff, blocked_map)
    problems += check_weekend_coverage(year, month, active_staff, blocked_map)

    # Sort: critical first, then warnings, then info, then by day
    severity_order = {'קריטי': 0, 'אזהרה': 1, 'מידע': 2, 'תקין': 3}
    problems.sort(key=lambda p: (severity_order.get(p['severity'], 9), p['day']))
    return problems


def save_report(sh, problems, year, month):
    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    month_str = f"{year}-{month:02d}"

    header = [['generated_at', 'month', 'severity', 'problem_type', 'description']]
    rows = [[now_str, month_str, p['severity'], p['problem_type'], p['description']]
            for p in problems]

    try:
        ws = sh.worksheet('daily_report')
        ws.clear()
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet('daily_report', rows=500, cols=6)

    ws.update('A1', header + rows)
    print(f"[{now_str}] Report saved: {len(rows)} issues for {month_str}")
    for p in problems:
        icon = '🔴' if p['severity'] == 'קריטי' else '🟡' if p['severity'] == 'אזהרה' else 'ℹ️'
        print(f"  {icon} [{p['problem_type']}] {p['description']}")


def main():
    print("Connecting to Google Sheets...")
    gc = get_client()
    sh = gc.open_by_url(SPREADSHEET_URL)

    staff_df    = load_sheet(sh, 'staff')
    requests_df = load_sheet(sh, 'requests')
    settings_df = load_sheet(sh, 'settings')

    month = get_active_month(settings_df)
    print(f"Active month: {YEAR}-{month:02d}")

    problems = analyze_month(YEAR, month, staff_df, requests_df)

    if not problems:
        problems = [{
            'severity': 'תקין',
            'problem_type': 'ללא בעיות',
            'description': f'לא נמצאו בעיות צפויות לחודש {month}/{YEAR}',
            'day': 0
        }]

    save_report(sh, problems, YEAR, month)


if __name__ == '__main__':
    main()
