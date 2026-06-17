"""
validity.py — check_assignment_validity, lifted verbatim from appy.py:2634.

Single source of truth for hard constraint checking (type, home-dept,
block/אילוץ, quota, 2-day rest gap, same-day duplicate). Pure pandas/stdlib —
no Streamlit. Used by the scheduler, swap search, and manual override.
"""
from datetime import datetime, timedelta

import pandas as pd


def check_assignment_validity(schedule_data, person_name, check_date, target_dept,
                              staff_df, requests_df,
                              ignore_quota=False, ignore_home_restrict=False, ignore_rest=False):
    """
    Checks if assigning person_name to target_dept on check_date is valid.
    schedule_data: List of dicts OR DataFrame
    ignore_quota: If True, skips the max shifts check (useful for Swaps where count doesn't increase)
    ignore_home_restrict: If True, skips "Restricted to Home Dept" check
    ignore_rest: If True, skips "Rest Violation" (nearby days) check
    Returns (bool, reason_string).
    """
    # Normalize to list of dicts if DataFrame
    if isinstance(schedule_data, pd.DataFrame):
        schedule_data = schedule_data.to_dict('records')

    if person_name in ['ADMIN', '---']:
        return False, "Invalid Person"

    p_row = staff_df[staff_df['name'] == person_name]
    if p_row.empty:
        return False, "Unknown Employee"
    person = p_row.iloc[0]

    # --- 1. Static Constraints (Critical - Must Fail First) ---
    p_type = str(person.get('type', '')).strip()
    if 'חוץ' in p_type and 'פנימית' in target_dept:
        return False, "External cannot work Internal"

    # Home Dept Check
    if not ignore_home_restrict:
        only_home = person.get('only_home_dept', False)
        if only_home:
            target_context = target_dept
            if "שישי בוקר" in target_dept:
                target_context = "שיקום" if "שיקום" in target_dept else "פנימית גריאטרית"
            if person['dept'] != 'כללי' and person['dept'] != target_context:
                return False, f"Restricted to Home Dept ({person['dept']})"

    # --- 2. Hard User Constraints ---
    req_date_str = requests_df['date'].astype(str)
    if not requests_df[(requests_df['employee'] == person_name) & (req_date_str == check_date) & (requests_df['status'] == "אילוץ")].empty:
        return False, "User Restriction (Blocked)"

    # --- 3. Quota Check ---
    try:
        max_quota = int(person.get('monthly_quota', 6))
    except Exception:
        max_quota = 6

    if max_quota == 0:
        return False, "Quota is 0 (Inactive)"

    if not ignore_quota:
        target_month_prefix = check_date[:7]  # 'YYYY-MM'
        current_shifts = len([
            s for s in schedule_data
            if s['employee'] == person_name
            and str(s['date']).startswith(target_month_prefix)
        ])
        if current_shifts >= max_quota:
            return False, f"Quota Exceeded ({current_shifts}/{max_quota})"

    # --- 4. Situational Constraints ---
    check_d_obj = datetime.strptime(check_date, '%Y-%m-%d').date()

    # Rest Check (2 days gap)
    if not ignore_rest:
        for offset in [-2, -1, 1, 2]:
            nearby_date = str(check_d_obj + timedelta(days=offset))
            if any(s for s in schedule_data if str(s['date']) == nearby_date and s['employee'] == person_name):
                return False, "Rest Violation (Worked nearby)"

    # Duplicate Check (Same Day)
    if any(s for s in schedule_data if str(s['date']) == check_date and s['employee'] == person_name):
        return False, "Already working this day"

    return True, "Valid"
