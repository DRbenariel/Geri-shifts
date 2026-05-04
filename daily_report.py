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
# Scheduling Agent helpers (pure Python — no Streamlit)
# ---------------------------------------------------------------------------

def load_all_data(sh):
    """Load staff, requests, schedule, special_days, settings from Google Sheets."""
    def _load(name):
        try:
            ws = sh.worksheet(name)
            data = ws.get_all_records()
            return pd.DataFrame(data)
        except gspread.exceptions.WorksheetNotFound:
            return pd.DataFrame()

    staff_df       = _load('staff')
    requests_df    = _load('requests')
    schedule_df    = _load('schedule')
    special_days_df= _load('special_days')
    settings_df    = _load('settings')

    # Normalise only_home_dept (stored as string "True"/"False")
    if not staff_df.empty and 'only_home_dept' in staff_df.columns:
        staff_df['only_home_dept'] = staff_df['only_home_dept'].apply(
            lambda v: v if isinstance(v, bool) else str(v).strip().lower() == 'true'
        )

    active_month = get_active_month(settings_df)
    return {
        'staff_df':        staff_df,
        'requests_df':     requests_df,
        'schedule_df':     schedule_df,
        'special_days_df': special_days_df,
        'active_month':    active_month,
    }


def is_functional_weekend_standalone(date_obj, special_days_df):
    """Pure-Python replica of is_functional_weekend() — no Streamlit required."""
    if isinstance(date_obj, str):
        date_obj = datetime.strptime(date_obj, '%Y-%m-%d').date()
    if date_obj.weekday() in (4, 5):  # Friday / Saturday
        return True
    # Check special day type
    d_str = date_obj.strftime('%Y-%m-%d')
    if not special_days_df.empty and 'day_type' in special_days_df.columns:
        match = special_days_df[special_days_df['date'] == d_str]
        if not match.empty:
            day_type = match.iloc[0]['day_type']
            if day_type in ('כמו שישי (ערב חג)', 'כמו שבת (חג)'):
                return True
    # Also check tomorrow's day_type (day-before-erev-chag is treated as weekend)
    tomorrow = date_obj + timedelta(days=1)
    tom_str = tomorrow.strftime('%Y-%m-%d')
    if not special_days_df.empty and 'day_type' in special_days_df.columns:
        match2 = special_days_df[special_days_df['date'] == tom_str]
        if not match2.empty and match2.iloc[0]['day_type'] == 'כמו שישי (ערב חג)':
            return True
    return False


def count_eligible_for_slot(date_str, dept, staff_df, requests_df, schedule_df):
    """
    Count how many employees COULD work (date_str, dept) in principle.
    Only checks: type restriction, hard block (אילוץ), already assigned on that date.
    Does NOT apply quota/rest-gap (those depend on scheduling order).
    Returns (count, [name, ...]) tuple.
    """
    already_assigned = set(
        str(r['employee']).strip()
        for r in schedule_df.to_dict('records')
        if str(r.get('date', '')) == date_str and str(r.get('employee', '')).strip() not in ('', '---')
    ) if not schedule_df.empty else set()

    blocked_on_date = set()
    if not requests_df.empty:
        mask = (
            (requests_df['date'].astype(str) == date_str) &
            (requests_df['status'].astype(str) == 'אילוץ')
        )
        blocked_on_date = set(requests_df[mask]['employee'].astype(str).str.strip().tolist())

    eligible = []
    for _, emp in staff_df.iterrows():
        name = str(emp.get('name', '')).strip()
        if not name or name in ('---', 'ADMIN'):
            continue
        emp_type = str(emp.get('type', '')).strip()
        if emp_type == 'מנהל/ת':
            continue
        # Type restriction: external can't work פנימית
        if emp_type == 'תורן חוץ' and dept == 'פנימית גריאטרית':
            continue
        # Home dept restriction
        if emp.get('only_home_dept', False):
            home = str(emp.get('dept', '')).strip()
            if home not in ('כללי', dept):
                continue
        # Already assigned elsewhere this day
        if name in already_assigned:
            continue
        # Hard block
        if name in blocked_on_date:
            continue
        eligible.append(name)

    return len(eligible), eligible


def build_ordering(year, month, data, strategy):
    """
    Build a list of (date_obj, dept) tuples in the order the simulation should fill them.
    Strategies:
      'tier'             — critical (≤1 eligible) first, then weekends, then weekdays; within
                           each tier sorted by fewest eligible ascending
      'weekend_first'    — weekends first then weekdays (mirrors current app behaviour)
      'constraint_first' — all slots sorted purely by fewest eligible ascending
    """
    staff_df        = data['staff_df']
    requests_df     = data['requests_df']
    schedule_df     = data['schedule_df']
    special_days_df = data['special_days_df']

    num_days  = calendar.monthrange(year, month)[1]
    all_dates = [date(year, month, d) for d in range(1, num_days + 1)]
    depts     = ['פנימית גריאטרית', 'שיקום']

    # Build slot list with metadata
    slots = []
    for d_obj in all_dates:
        d_str = d_obj.strftime('%Y-%m-%d')
        is_we = is_functional_weekend_standalone(d_obj, special_days_df)
        for dept in depts:
            count, _ = count_eligible_for_slot(d_str, dept, staff_df, requests_df, schedule_df)
            slots.append({
                'date_obj': d_obj,
                'dept':     dept,
                'eligible': count,
                'is_we':    is_we,
                'day':      d_obj.day,
            })

    if strategy == 'tier':
        def tier(s):
            if s['eligible'] <= 1:
                return 0
            if s['is_we']:
                return 1
            return 2
        slots.sort(key=lambda s: (tier(s), s['eligible'], s['day']))

    elif strategy == 'weekend_first':
        slots.sort(key=lambda s: (0 if s['is_we'] else 1, s['day']))

    elif strategy == 'constraint_first':
        slots.sort(key=lambda s: (s['eligible'], s['day']))

    return [(s['date_obj'], s['dept']) for s in slots]


def run_scheduling_simulation(year, month, data, day_ordering):
    """
    Greedy scheduling simulation — standalone (no Streamlit).
    Returns dict: {schedule, empty_slots, fallback_slots, score}

    Improvements over run_smart_scheduling():
    - Wish priority = +1000 score bonus (not pool restriction)
    - Day ordering provided by caller
    - All state is local (no st.session_state)
    """
    staff_df        = data['staff_df']
    requests_df     = data['requests_df']
    schedule_df     = data['schedule_df']
    special_days_df = data['special_days_df']
    month_prefix    = f"{year}-{month:02d}"

    # ── Start from existing schedule (preserve manual + real assignments) ──
    sim_schedule = []
    if not schedule_df.empty:
        for r in schedule_df.to_dict('records'):
            if not str(r.get('date', '')).startswith(month_prefix):
                sim_schedule.append(r)  # keep other months
            elif str(r.get('employee', '')).strip() not in ('', '---'):
                sim_schedule.append(r)  # keep real assignments in active month

    def safe_int(v, default=0):
        try:
            if pd.isna(v) or str(v).strip() == '':
                return default
            return int(float(v))
        except (ValueError, TypeError):
            return default

    # Initialise counters
    work_load         = {}
    weekends_worked   = {}
    last_assignment   = {}
    wed_counts        = {}
    thu_counts        = {}

    for _, p in staff_df.iterrows():
        n = str(p['name']).strip()
        work_load[n]       = 0
        weekends_worked[n] = set()
        last_assignment[n] = -999
        wed_counts[n]      = 0
        thu_counts[n]      = 0

    num_days = calendar.monthrange(year, month)[1]
    for s in sim_schedule:
        emp = str(s.get('employee', '')).strip()
        if emp not in work_load or emp in ('', '---'):
            continue
        try:
            dt = datetime.strptime(str(s['date']), '%Y-%m-%d')
        except ValueError:
            continue
        if dt.weekday() == 2: wed_counts[emp] = wed_counts.get(emp, 0) + 1
        if dt.weekday() == 3: thu_counts[emp] = thu_counts.get(emp, 0) + 1
        if dt.toordinal() > last_assignment.get(emp, -999):
            last_assignment[emp] = dt.toordinal()
        if str(s['date']).startswith(month_prefix):
            work_load[emp] = work_load.get(emp, 0) + 1
            if is_functional_weekend_standalone(dt.date(), special_days_df) and 'שישי בוקר' not in str(s.get('dept', '')):
                weekends_worked[emp].add(dt.isocalendar()[1])

    # Pre-build wish set per date
    wish_map = {}  # date_str -> set of names
    if not requests_df.empty:
        for _, r in requests_df.iterrows():
            if str(r.get('status', '')) == 'בקשה':
                d = str(r.get('date', ''))[:10]
                wish_map.setdefault(d, set()).add(str(r.get('employee', '')).strip())

    # Pre-build block set per date
    block_map = {}  # date_str -> set of names
    if not requests_df.empty:
        for _, r in requests_df.iterrows():
            if str(r.get('status', '')) == 'אילוץ':
                d = str(r.get('date', ''))[:10]
                block_map.setdefault(d, set()).add(str(r.get('employee', '')).strip())

    empty_slots    = []
    fallback_slots = []

    for d_obj, dept in day_ordering:
        d_str    = d_obj.strftime('%Y-%m-%d')
        week_num = d_obj.isocalendar()[1]

        # Already filled?
        if any(s for s in sim_schedule if str(s.get('date', '')) == d_str and s.get('dept') == dept and str(s.get('employee', '')).strip() not in ('', '---')):
            continue

        candidates = []
        failure_reasons = []

        for _, person in staff_df.iterrows():
            name     = str(person['name']).strip()
            emp_type = str(person.get('type', '')).strip()

            if not name or name in ('---', 'ADMIN') or emp_type == 'מנהל/ת':
                continue
            if emp_type == 'תורן חוץ' and dept == 'פנימית גריאטרית':
                continue
            # Already assigned another dept today
            if any(s for s in sim_schedule if str(s.get('date', '')) == d_str and str(s.get('employee', '')).strip() == name):
                continue
            # Home dept restriction
            if person.get('only_home_dept', False):
                home = str(person.get('dept', '')).strip()
                if home not in ('כללי', dept):
                    continue
            # Hard quota
            monthly_quota = safe_int(person.get('monthly_quota', 0))
            if work_load.get(name, 0) >= monthly_quota:
                failure_reasons.append(f"{name}: מכסה")
                continue
            # Soft quota reservation (first half of month)
            if d_obj.day < 15 and monthly_quota > 0 and work_load.get(name, 0) >= monthly_quota * 0.5:
                failure_reasons.append(f"{name}: שמירת מכסה")
                continue
            # Weekend quota
            weekend_quota = safe_int(person.get('weekend_quota', 0))
            if is_functional_weekend_standalone(d_obj, special_days_df):
                if len(weekends_worked.get(name, set())) >= weekend_quota and week_num not in weekends_worked.get(name, set()):
                    failure_reasons.append(f"{name}: מכסת סופ\"ש")
                    continue
            # Rest gap ±2 days
            has_rest_conflict = False
            for offset in (-2, -1, 1, 2):
                check_d = (d_obj + timedelta(days=offset)).strftime('%Y-%m-%d')
                if any(s for s in sim_schedule if str(s.get('date', '')) == check_d and str(s.get('employee', '')).strip() == name):
                    has_rest_conflict = True
                    break
            if has_rest_conflict:
                failure_reasons.append(f"{name}: מנוחה")
                continue
            # Wed-Sat rule for מתמחה
            if emp_type == 'מתמחה':
                if d_obj.weekday() == 5:  # Saturday
                    wed_check = (d_obj - timedelta(days=3)).strftime('%Y-%m-%d')
                    if any(s for s in sim_schedule if str(s.get('date', '')) == wed_check and str(s.get('employee', '')).strip() == name):
                        failure_reasons.append(f"{name}: שובץ ברביעי")
                        continue
                if d_obj.weekday() == 2:  # Wednesday
                    sat_check = (d_obj + timedelta(days=3)).strftime('%Y-%m-%d')
                    if any(s for s in sim_schedule if str(s.get('date', '')) == sat_check and str(s.get('employee', '')).strip() == name):
                        failure_reasons.append(f"{name}: משובץ בשבת")
                        continue
                    fri_check = (d_obj + timedelta(days=2)).strftime('%Y-%m-%d')
                    if any(s for s in sim_schedule if str(s.get('date', '')) == fri_check and str(s.get('employee', '')).strip() == name):
                        failure_reasons.append(f"{name}: משובץ בשישי")
                        continue
            # Hard block
            if name in block_map.get(d_str, set()):
                failure_reasons.append(f"{name}: אילוץ")
                continue

            candidates.append(person)

        if candidates:
            # Score each candidate — WISH BONUS (+1000) instead of pool restriction
            wishers_today = wish_map.get(d_str, set())

            def calc_score(cand):
                n      = str(cand['name']).strip()
                quota  = safe_int(cand.get('monthly_quota', 1), 1)
                usage  = work_load.get(n, 0) / quota if quota > 0 else 1.0
                score  = -usage * 100

                last_d     = last_assignment.get(n, -999)
                days_diff  = d_obj.toordinal() - last_d
                score     += days_diff * 2

                month_prog    = d_obj.day / num_days
                expected      = quota * month_prog
                pacing        = (expected - work_load.get(n, 0)) * 500
                score        += pacing

                if dept == 'שיקום' and str(cand.get('type', '')).strip() == 'תורן חוץ':
                    if d_obj.weekday() in (3, 4, 5) or is_functional_weekend_standalone(d_obj, special_days_df):
                        score += 2000

                emp_type_c = str(cand.get('type', '')).strip()
                if emp_type_c == 'מתמחה':
                    if d_obj.weekday() == 2: score -= wed_counts.get(n, 0) * 200
                    if d_obj.weekday() == 3: score -= thu_counts.get(n, 0) * 200

                cand_dept = str(cand.get('dept', '')).strip()
                if cand_dept in (dept, 'כללי'):
                    score += 500
                else:
                    score -= 5000

                # IMPROVEMENT: wish bonus instead of pool restriction
                if n in wishers_today:
                    score += 1000

                return score

            chosen = max(candidates, key=calc_score)
            chosen_name = str(chosen['name']).strip()
            sim_schedule.append({'date': d_str, 'dept': dept, 'employee': chosen_name,
                                  'is_manual': False, 'empty_reason': ''})
            work_load[chosen_name]       = work_load.get(chosen_name, 0) + 1
            last_assignment[chosen_name] = d_obj.toordinal()
            if d_obj.weekday() == 2: wed_counts[chosen_name] = wed_counts.get(chosen_name, 0) + 1
            if d_obj.weekday() == 3: thu_counts[chosen_name] = thu_counts.get(chosen_name, 0) + 1
            if is_functional_weekend_standalone(d_obj, special_days_df):
                weekends_worked.setdefault(chosen_name, set()).add(week_num)

        else:
            # Fallback: relax rest-gap and soft quota, keep hard quota + blocks
            fallback_pool = []
            for _, cand in staff_df.iterrows():
                fn      = str(cand['name']).strip()
                ft      = str(cand.get('type', '')).strip()
                if not fn or fn in ('---', 'ADMIN') or ft == 'מנהל/ת':
                    continue
                if ft == 'תורן חוץ' and dept == 'פנימית גריאטרית':
                    continue
                if any(s for s in sim_schedule if str(s.get('date', '')) == d_str and str(s.get('employee', '')).strip() == fn):
                    continue
                if fn in block_map.get(d_str, set()):
                    continue
                fq = safe_int(cand.get('monthly_quota', 0))
                if work_load.get(fn, 0) >= fq:
                    continue
                fallback_pool.append(fn)

            if fallback_pool:
                fb_choice = min(fallback_pool, key=lambda x: work_load.get(x, 0))
                sim_schedule.append({'date': d_str, 'dept': dept, 'employee': fb_choice,
                                      'is_manual': False, 'empty_reason': 'גיבוי (הגמשת חוקים)'})
                fallback_slots.append({'date': d_str, 'dept': dept, 'employee': fb_choice})
                work_load[fb_choice] = work_load.get(fb_choice, 0) + 1
                last_assignment[fb_choice] = d_obj.toordinal()
                if is_functional_weekend_standalone(d_obj, special_days_df):
                    weekends_worked.setdefault(fb_choice, set()).add(week_num)
            else:
                sim_schedule.append({'date': d_str, 'dept': dept, 'employee': '---',
                                      'is_manual': False, 'empty_reason': 'לא נמצא עובד'})
                empty_slots.append({'date': d_str, 'dept': dept})

    score = len(empty_slots) * 100 + len(fallback_slots) * 10
    return {
        'schedule':       sim_schedule,
        'empty_slots':    empty_slots,
        'fallback_slots': fallback_slots,
        'score':          score,
    }


def check_scheduling_feasibility(year, month, data):
    """
    Run scheduling simulation (best of 3 strategies) and return:
    1. One row per employee: total shifts, weekend shifts, Friday morning shifts.
    2. One row per empty slot the algorithm could not fill.
    Nothing else.
    """
    staff_df        = data['staff_df']
    requests_df     = data['requests_df']
    schedule_df     = data['schedule_df']
    special_days_df = data['special_days_df']

    day_names_he = {0: 'שני', 1: 'שלישי', 2: 'רביעי', 3: 'חמישי', 4: 'שישי', 5: 'שבת', 6: 'ראשון'}
    num_days = calendar.monthrange(year, month)[1]

    # ── Run 3 strategies, pick best ──
    strategies = ['tier', 'weekend_first', 'constraint_first']
    results    = {}
    for strat in strategies:
        ordering     = build_ordering(year, month, data, strat)
        results[strat] = run_scheduling_simulation(year, month, data, ordering)

    best_strat  = min(results, key=lambda s: results[s]['score'])
    best_result = results[best_strat]
    sim_sched   = best_result['schedule']

    problems = []

    # ── 1. Shift counts per employee ──
    # Collect active scheduling employees (מתמחה + תורן חוץ, not admin/---).
    active_names = []
    if not staff_df.empty:
        for _, emp in staff_df.iterrows():
            n = str(emp.get('name', '')).strip()
            t = str(emp.get('type', '')).strip()
            if n and n not in ('---', 'ADMIN') and t in ('מתמחה', 'תורן חוץ'):
                active_names.append(n)

    month_prefix = f"{year}-{month:02d}"

    for emp_name in sorted(active_names):
        total_shifts    = 0
        weekend_shifts  = 0
        fri_morning     = 0

        for s in sim_sched:
            if str(s.get('employee', '')).strip() != emp_name:
                continue
            d_str = str(s.get('date', ''))
            if not d_str.startswith(month_prefix):
                continue
            dept = str(s.get('dept', ''))

            # Friday morning shifts
            if 'שישי בוקר' in dept:
                fri_morning += 1
                continue  # don't count as a regular shift

            total_shifts += 1
            try:
                d_obj = datetime.strptime(d_str, '%Y-%m-%d').date()
                if is_functional_weekend_standalone(d_obj, special_days_df):
                    weekend_shifts += 1
            except ValueError:
                pass

        desc = (
            f"{emp_name}: {total_shifts} משמרות "
            f"(מתוכן {weekend_shifts} סופ\"ש) | "
            f"שישי בוקר: {fri_morning}"
        )
        problems.append({
            'severity':     'מידע',
            'problem_type': '[שיבוץ] סיכום עובד',
            'description':  desc,
            'day':          0,
        })

    # ── 2. Empty slots ──
    for empty in sorted(best_result['empty_slots'], key=lambda s: (s['date'], s['dept'])):
        d_str = empty['date']
        dept  = empty['dept']
        try:
            d_obj  = datetime.strptime(d_str, '%Y-%m-%d').date()
            d_disp = f"{d_obj.day}/{month} ({day_names_he[d_obj.weekday()]})"
            day_n  = d_obj.day
        except ValueError:
            d_disp = d_str
            day_n  = 0

        problems.append({
            'severity':     'קריטי',
            'problem_type': '[שיבוץ] יום ריק',
            'description':  f"יום {d_disp} — {dept}: לא נמצא עובד זמין",
            'day':          day_n,
        })

    return problems


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

def analyze_month(year, month, staff_df, requests_df, schedule_df=None, special_days_df=None):
    month_prefix = f"{year}-{month:02d}"

    if schedule_df is None:
        schedule_df = pd.DataFrame()
    if special_days_df is None:
        special_days_df = pd.DataFrame()

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

    # Scheduling simulation: runs only on days 3–8 of the month
    today = date.today()
    if 3 <= today.day <= 8:
        sched_data = {
            'staff_df':        staff_df,
            'requests_df':     requests_df,
            'schedule_df':     schedule_df,
            'special_days_df': special_days_df,
        }
        try:
            problems += check_scheduling_feasibility(year, month, sched_data)
        except Exception as e:
            problems.append({
                'severity':     'מידע',
                'problem_type': '[שיבוץ] שגיאת סימולציה',
                'description':  f"הסימולציה לא הושלמה: {e}",
                'day':          0,
            })

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
        sev  = p['severity']
        icon = '[CRITICAL]' if sev == 'קריטי' else '[WARN]' if sev == 'אזהרה' else '[INFO]'
        line = f"  {icon} day={p.get('day', 0)} type={p['problem_type'][:30]}"
        try:
            print(line)
        except Exception:
            pass  # Hebrew terminal encoding issues on Windows — safe to ignore


def main():
    print("Connecting to Google Sheets...")
    gc = get_client()
    sh = gc.open_by_url(SPREADSHEET_URL)

    staff_df        = load_sheet(sh, 'staff')
    requests_df     = load_sheet(sh, 'requests')
    settings_df     = load_sheet(sh, 'settings')
    schedule_df     = load_sheet(sh, 'schedule')
    special_days_df = load_sheet(sh, 'special_days')

    month = get_active_month(settings_df)
    today = date.today()
    print(f"Active month: {YEAR}-{month:02d} | Today: {today} | Simulation: {'YES' if 3 <= today.day <= 8 else 'no'}")

    problems = analyze_month(YEAR, month, staff_df, requests_df, schedule_df, special_days_df)

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
