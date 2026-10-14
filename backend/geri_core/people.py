"""Staff / department resolution (appy.py:753, 1542-1613, 1787-1815, 6148-6212)."""
import pandas as pd

from .constants import (DAILY_DEPTS_ALL, GRID_STATUS_CYCLE, GRID_STATUS_CYCLE_MANAGER,
                        GRID_STATUS_CYCLE_SENIOR, MANUAL_PLANT_ONLY_MANAGERS, MANUAL_STATUSES,
                        PNIM_DEPT, PNIM_SIDES, ROLE_ORDER, UNASSIGNED)
from .normalize import norm_dept, parse_manage_depts


def staff_row(ctx, name):
    sf = ctx.staff
    if sf.empty or 'name' not in sf.columns:
        return None
    m = sf[sf['name'].astype(str).str.strip() == str(name).strip()]
    return None if m.empty else m.iloc[0]


def staff_type(ctx, name) -> str:
    r = staff_row(ctx, name)
    return '' if r is None else str(r.get('type', '')).strip()


def get_user_email(ctx, user_name) -> str:
    try:
        sf = ctx.staff
        if sf.empty or 'email' not in sf.columns:
            return ""
        row = sf[sf['name'].astype(str).str.strip() == str(user_name).strip()]
        if row.empty:
            return ""
        return str(row.iloc[0].get('email', '') or '').strip()
    except Exception:
        return ""


def emp_dept_for_date(ctx, employee, date_str_or_obj) -> str:
    """Gantt-canonical daily_dept for (employee, year-month of date); staff.dept fallback."""
    try:
        emp_n = str(employee).strip()
        if not emp_n:
            return ""
        if hasattr(date_str_or_obj, 'strftime'):
            ym = date_str_or_obj.strftime('%Y-%m')
        else:
            ym = str(date_str_or_obj)[:7]
        dr = ctx.dept_rotation
        if not dr.empty and 'employee' in dr.columns:
            mask = ((dr['year_month'].astype(str) == ym) &
                    (dr['employee'].astype(str).str.strip() == emp_n))
            if mask.any():
                dd = str(dr[mask].iloc[0].get('daily_dept', '') or '').strip()
                if dd:
                    return dd
        sf = ctx.staff
        if not sf.empty and 'name' in sf.columns and 'dept' in sf.columns:
            srow = sf[sf['name'].astype(str).str.strip() == emp_n]
            if not srow.empty:
                return str(srow.iloc[0].get('dept', '') or '').strip()
    except Exception:
        pass
    return ""


def emp_night_dept(ctx, employee, year_month) -> str:
    """Night-shift dept ('שיקום' / 'פנימית גריאטרית'), Gantt-first with intern default."""
    try:
        emp_n = str(employee).strip()
        if not emp_n:
            return ""
        ym = str(year_month)
        dr = ctx.dept_rotation
        if not dr.empty and 'employee' in dr.columns:
            mask = ((dr['year_month'].astype(str) == ym) &
                    (dr['employee'].astype(str).str.strip() == emp_n))
            if mask.any():
                dd = str(dr[mask].iloc[0].get('daily_dept', '') or '').strip()
                if 'שיקום' in dd:
                    return 'שיקום'
                if dd == 'פנימית גריאטרית':
                    return 'פנימית גריאטרית'
        sf = ctx.staff
        if not sf.empty and 'name' in sf.columns:
            srow = sf[sf['name'].astype(str).str.strip() == emp_n]
            if not srow.empty:
                role = str(srow.iloc[0].get('type', '') or '').strip()
                if role == 'מתמחה':
                    return 'פנימית גריאטרית'
                if 'dept' in sf.columns:
                    return str(srow.iloc[0].get('dept', '') or '').strip()
    except Exception:
        pass
    return ""


def cycle_for_role(ctx, emp) -> dict:
    t = staff_type(ctx, emp)
    if t == 'מנהל מחלקה':
        return GRID_STATUS_CYCLE_MANAGER
    if t == 'רופא בכיר':
        return GRID_STATUS_CYCLE_SENIOR
    return GRID_STATUS_CYCLE


def manual_statuses_for_role(ctx, emp) -> list:
    t = staff_type(ctx, emp)
    if t == 'מנהל מחלקה':
        return ["", "עובד"]
    if t == 'רופא בכיר':
        return ["עובד", "חופש", "אחרי תורנות", "אחר"]
    return MANUAL_STATUSES


def get_dept_managers(ctx, dept_name) -> list:
    """מנהל מחלקה names whose manage_depts includes dept_name (minus manual-plant-only)."""
    try:
        sf = ctx.staff.copy()
        sf['name'] = sf['name'].astype(str).str.strip()
        sf['type'] = sf['type'].astype(str).str.strip()
        out = []
        for _, r in sf[sf['type'] == 'מנהל מחלקה'].iterrows():
            nm = str(r['name']).strip()
            if nm in MANUAL_PLANT_ONLY_MANAGERS:
                continue
            if dept_name in parse_manage_depts(r.get('manage_depts', '')):
                out.append(nm)
        return out
    except Exception:
        return []


def managed_depts(ctx, user_name) -> list:
    r = staff_row(ctx, user_name)
    return [] if r is None else parse_manage_depts(r.get('manage_depts', ''))


def manager_email_for_dept(ctx, dept) -> str:
    """First מנהל מחלקה whose manage_depts includes dept."""
    if not dept:
        return ""
    for _, sr in ctx.staff.iterrows():
        if str(sr.get('type', '')).strip() != 'מנהל מחלקה':
            continue
        if dept in parse_manage_depts(sr.get('manage_depts', '')):
            return str(sr.get('email', '')).strip()
    return ""


def sort_employees_by_role(ctx, emp_list) -> list:
    """מנהל מחלקה → רופא בכיר → מתמחה → others (stable)."""
    try:
        sf = ctx.staff
        if sf.empty or 'name' not in sf.columns:
            return list(emp_list)
        name_to_role = {str(r.get('name', '')).strip(): str(r.get('type', '')).strip()
                        for _, r in sf.iterrows()}
        return sorted(emp_list, key=lambda n: ROLE_ORDER.get(name_to_role.get(str(n).strip(), ''), 99))
    except Exception:
        return list(emp_list)


def gantt_dept_options(emp_row) -> list:
    if str(emp_row.get('type', '')).strip() == 'מנהל מחלקה':
        managed = {norm_dept(d) for d in parse_manage_depts(emp_row.get('manage_depts', ''))}
        depts = [d for d in DAILY_DEPTS_ALL if d in managed]
    else:
        depts = list(DAILY_DEPTS_ALL)
    return depts + [UNASSIGNED]


def gantt_assignment_errors(employee_rows, assignments, sides) -> list:
    errors = []
    for row in employee_rows:
        name = str(row.get('name', '')).strip()
        dept = assignments.get(name, UNASSIGNED)
        if dept not in gantt_dept_options(row):
            errors.append(f"{name}: בחר/י מחלקה מתוך המחלקות המותרות.")
        if dept == PNIM_DEPT and sides.get(name, '') not in PNIM_SIDES:
            errors.append(f"{name}: לשיוך בפנימית גריאטרית חובה לבחור צד ורוד או כחול.")
    return errors


def dept_roster(ctx, dept_name, year_month) -> list:
    """dept_rotation members of dept for the month (unsorted, as stored)."""
    dr = ctx.dept_rotation
    if dr.empty or 'employee' not in dr.columns:
        return []
    mask = ((dr['year_month'].astype(str) == year_month) &
            (dr['daily_dept'].astype(str) == dept_name))
    return dr[mask]['employee'].astype(str).str.strip().tolist()


def grid_employees(ctx, dept_name, year_month, include_user=None) -> list:
    """Managers + roster, role-sorted — the row list every סידור עבודה view uses (7973-7982, 8894)."""
    emps = dept_roster(ctx, dept_name, year_month)
    mgrs = get_dept_managers(ctx, dept_name)
    if include_user and include_user not in mgrs:
        mgrs = [include_user] + mgrs
    return sort_employees_by_role(ctx, mgrs + [e for e in emps if e not in mgrs])


def employee_dept_for_month(ctx, user_name, year_month) -> str:
    dr = ctx.dept_rotation
    if dr.empty or 'employee' not in dr.columns:
        return ""
    r = dr[(dr['employee'].astype(str).str.strip() == str(user_name).strip()) &
           (dr['year_month'].astype(str) == year_month)]
    return "" if r.empty else str(r.iloc[0].get('daily_dept', '') or '')


def is_active_quota(person) -> bool:
    try:
        return int(person.get('monthly_quota', 6)) > 0
    except Exception:
        return True


def name_set(series: pd.Series) -> set:
    return set(series.dropna().astype(str).str.strip())
