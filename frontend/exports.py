"""
exports.py — Google Sheets exports.

- export_schedule_wide: faithful port of appy.py:455 (Schedule_Export wide).
- export_wsd_grid: per-dept work_schedule_daily as a wide employees×days grid
  (rows=employees, cols=days, cells=status). Simpler than appy's batched
  3-section layout but covers the same data; written to WSD_<dept>_<year_month>.
"""
import calendar
from datetime import date

from . import db
from .config import YEAR

_WD = ["ב'", "ג'", "ד'", "ה'", "ו'", "ש'", "א'"]   # Mon..Sun (Python weekday order)

_SCHED_COLS = [
    'תאריך', 'יום', 'פנימית גריאטרית', 'שיקום',
    'שישי בוקר - פנימית (1)', 'שישי בוקר - פנימית (2)',
    'שישי בוקר - שיקום (1)', 'שישי בוקר - שיקום (2)',
]


def export_schedule_wide(view_month):
    """Wide night-shift export → Schedule_Export. Returns (ok, error)."""
    days_in_month = calendar.monthrange(YEAR, view_month)[1]
    sched = db.read_sheet('schedule', fresh=True)
    by_date = {}
    for r in sched:
        by_date.setdefault(str(r.get('date', '')), []).append(r)

    rows = []
    for d in range(1, days_in_month + 1):
        d_obj = date(YEAR, view_month, d)
        d_str = str(d_obj)
        row = {c: '' for c in _SCHED_COLS}
        row['תאריך'] = d_str
        row['יום'] = _WD[d_obj.weekday()]
        for shift in by_date.get(d_str, []):
            dept, emp = shift.get('dept'), shift.get('employee')
            if emp == '---':
                continue
            if dept in row:
                row[dept] = emp
        rows.append(row)

    ok = db.overwrite_sheet('Schedule_Export', _SCHED_COLS, rows)
    return ok, None if ok else 'design_mode'


def export_wsd_grid(dept_name, view_month):
    """Per-dept work_schedule_daily → WSD_<dept>_<year_month> (employees×days)."""
    year_month = f"{YEAR}-{view_month:02d}"
    num_days = calendar.monthrange(YEAR, view_month)[1]
    nd = db._dept_norm(dept_name)

    rows_src = [r for r in db.read_sheet('work_schedule_daily', fresh=True)
                if str(r.get('date', '')).startswith(year_month)
                and db._dept_norm(r.get('daily_dept', '')) == nd]
    if not rows_src:
        return False, 'אין נתוני סידור עבודה למחלקה זו'

    employees = sorted({db._norm(r.get('employee', '')) for r in rows_src})
    status = {(db._norm(r.get('employee', '')), str(r.get('date', ''))[:10]): r.get('status', '')
              for r in rows_src}

    header = ['עובד'] + [str(d) for d in range(1, num_days + 1)]
    out_rows = []
    for emp in employees:
        row = {'עובד': emp}
        for d in range(1, num_days + 1):
            ds = f"{year_month}-{d:02d}"
            row[str(d)] = status.get((emp, ds), '')
        out_rows.append(row)

    safe = dept_name.replace("'", "").replace('"', '').replace('/', '_')[:25]
    ok = db.overwrite_sheet(f"WSD_{safe}_{year_month}", header, out_rows)
    return ok, None if ok else 'design_mode'
