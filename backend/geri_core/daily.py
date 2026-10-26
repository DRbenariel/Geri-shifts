"""Daily work schedule (סידור עבודה): status derivation, WSD edits, grid model.

Ports appy.py:1359-1538, 1758, 1831-1993 and the data side of
_render_dept_grid / _render_pnim_sided (2046-2754).
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

import pandas as pd

from .constants import (ABSENCE_TYPE_TO_STATUS, DAILY_DEPT_TO_FRIDAY_SHIFTS, DAILY_DEPT_TO_NIGHT_DEPT,
                        FRIDAY_SHIFT_DEPTS, GRID_STATUS_LABEL_SHORT, HEB_DAY_TO_IDX, KONENUT_DEPTS,
                        PNIM_DEPT, PNIM_SIDES)
from .days import is_functional_friday, is_functional_saturday, year_for_month
from .normalize import make_initials, parse_manage_depts
from .people import cycle_for_role, manual_statuses_for_role, staff_row

WSD_COLUMNS = ['date', 'employee', 'daily_dept', 'status', 'note', 'is_manual', 'side']


# ── WSD lookups ───────────────────────────────────────────────────────────────
def wsd_get_status(ctx, date_str, employee, default="עובד"):
    return ctx.wsd_index.get((str(date_str), str(employee).strip()), {}).get('status', default)


def wsd_is_manual(ctx, date_str, employee):
    return ctx.wsd_index.get((str(date_str), str(employee).strip()), {}).get('is_manual', False)


def wsd_get_note(ctx, date_str, employee):
    return ctx.wsd_index.get((str(date_str), str(employee).strip()), {}).get('note', '')


# ── WSD mutations ─────────────────────────────────────────────────────────────
def wsd_upsert(ctx, date_str, employee, daily_dept, status, is_manual=True, note="", side="", persist=True):
    """Insert/update one (date, employee) row. `side` is sticky: '' keeps the stored side."""
    wsd = ctx.work_schedule_daily.copy()
    if wsd.empty or 'date' not in wsd.columns:
        wsd = pd.DataFrame(columns=WSD_COLUMNS)
    if 'side' not in wsd.columns:
        wsd['side'] = ''
    emp_n = str(employee).strip()
    is_manual_str = str(is_manual)
    m = (wsd['date'].astype(str) == date_str) & (wsd['employee'].astype(str).str.strip() == emp_n)
    if m.any():
        wsd.loc[m, 'status'] = status
        wsd.loc[m, 'is_manual'] = is_manual_str
        wsd.loc[m, 'daily_dept'] = daily_dept
        wsd.loc[m, 'note'] = note
        if side:
            wsd.loc[m, 'side'] = side
    else:
        wsd = pd.concat([wsd, pd.DataFrame([{
            'date': date_str, 'employee': emp_n, 'daily_dept': daily_dept,
            'status': status, 'note': note, 'is_manual': is_manual_str, 'side': side,
        }])], ignore_index=True)
    ctx.work_schedule_daily = wsd
    if persist:
        ctx.save("work_schedule_daily", wsd)


def wsd_delete(ctx, date_str, employee, persist=True):
    """Remove one row (undo a temporary transfer)."""
    wsd = ctx.work_schedule_daily.copy()
    if wsd.empty or 'date' not in wsd.columns:
        return False
    emp_n = str(employee).strip()
    m = (wsd['date'].astype(str) == date_str) & (wsd['employee'].astype(str).str.strip() == emp_n)
    if not m.any():
        return False
    wsd = wsd[~m].reset_index(drop=True)
    ctx.work_schedule_daily = wsd
    if persist:
        ctx.save("work_schedule_daily", wsd)
    return True


def cycle_cell(ctx, date_str, employee, dept_name):
    """Grid click: advance the cell to the next status in the employee's role cycle."""
    cur_status = derive_auto_status(ctx, date_str, employee, daily_dept=dept_name)
    cur_note = wsd_get_note(ctx, date_str, employee)
    new_status = cycle_for_role(ctx, employee).get(cur_status, "")
    wsd_upsert(ctx, date_str, employee, dept_name, new_status, is_manual=True, note=cur_note)
    return new_status


def set_cell(ctx, date_str, employee, dept_name, status, note):
    """Popover save: explicit status + note. Status must be allowed for the employee's role."""
    if status not in manual_statuses_for_role(ctx, employee):
        raise ValueError(f"סטטוס לא חוקי עבור {employee}: {status}")
    wsd_upsert(ctx, date_str, employee, dept_name, status, is_manual=True, note=str(note).strip())


def add_temp_transfer(ctx, date_str, employee, dept_name, side=""):
    wsd_upsert(ctx, date_str, employee, dept_name, "עובד", is_manual=True, side=side)


def incoming_transfers(ctx, dept, year_month) -> dict:
    """{employee: {'days': {day_ints}, 'side': str}} for manual rows into dept by non-members."""
    result = {}
    members = set()
    try:
        dr = ctx.dept_rotation
        if not dr.empty and 'employee' in dr.columns:
            dmask = ((dr['year_month'].astype(str) == year_month) &
                     (dr['daily_dept'].astype(str) == dept))
            members = set(dr[dmask]['employee'].astype(str).str.strip().tolist())
    except Exception:
        pass
    for (date_str, emp), entry in ctx.wsd_index.items():
        if not entry.get('is_manual'):
            continue
        if str(entry.get('daily_dept', '') or '') != dept:
            continue
        if not str(date_str).startswith(year_month):
            continue
        if emp in members:
            continue
        try:
            day_int = int(str(date_str).split('-')[2])
        except Exception:
            continue
        rec = result.setdefault(emp, {'days': set(), 'side': ''})
        rec['days'].add(day_int)
        if entry.get('side'):
            rec['side'] = entry['side']
    return result


# ── Night-shift lookups used by the day schedule ──────────────────────────────
def get_fri_shift_workers(ctx, date_str, daily_dept) -> list:
    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        if not is_functional_friday(ctx, date_obj):
            return []
        fri_shifts = DAILY_DEPT_TO_FRIDAY_SHIFTS.get(str(daily_dept), [])
        if not fri_shifts:
            return []
        sch = ctx.schedule
        if sch.empty or 'date' not in sch.columns:
            return []
        mask = (sch['date'].astype(str) == date_str) & (sch['dept'].astype(str).isin(fri_shifts))
        workers = sch[mask]['employee'].astype(str).str.strip().tolist()
        return [w for w in workers if w and w != '---']
    except Exception:
        return []


def get_night_duty(ctx, date_str, daily_dept):
    night_dept = DAILY_DEPT_TO_NIGHT_DEPT.get(str(daily_dept))
    if not night_dept:
        return None
    try:
        sch = ctx.schedule
        if sch.empty or 'date' not in sch.columns:
            return None
        mask = (sch['date'].astype(str) == date_str) & (sch['dept'].astype(str) == night_dept)
        rows = sch[mask]
        if rows.empty:
            return None
        emp = str(rows.iloc[0]['employee']).strip()
        return emp if emp and emp != '---' else None
    except Exception:
        return None


def night_shift_dept_label(ctx, prev_date_str, emp) -> str:
    try:
        sch = ctx.schedule
        if sch.empty or 'date' not in sch.columns:
            return ''
        night_sch = sch[~sch['dept'].astype(str).isin(FRIDAY_SHIFT_DEPTS)]
        mask = ((night_sch['date'].astype(str) == prev_date_str) &
                (night_sch['employee'].astype(str).str.strip() == emp))
        rows = night_sch[mask]
        if rows.empty:
            return ''
        dept = str(rows.iloc[0].get('dept', '')).strip()
        if 'פנימית' in dept:
            return 'פנג"ר'
        if 'שיקום' in dept:
            return 'שיקום'
        return dept
    except Exception:
        return ''


# ── SINGLE SOURCE OF TRUTH ────────────────────────────────────────────────────
def derive_auto_status(ctx, date_str, employee, daily_dept=None) -> str:
    """Day-schedule status for (date, employee[, dept]) — appy._derive_auto_status.

    0c manual_schedule_only / מנהל מחלקה gating → 0a Saturday → 0b Friday (שישי בוקר)
    → 1 manual WSD override (dept-aware) → 2 approved absence → 3 recurring weekday
    → 4 night shift today → 5 night shift yesterday → "עובד".
    """
    try:
        emp = str(employee).strip()
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        wd_idx = (date_obj.weekday() + 1) % 7

        try:
            sf = ctx.staff
            _erow = sf[sf['name'].astype(str).str.strip() == emp]
            if not _erow.empty:
                _er = _erow.iloc[0]
                _mso_raw = _er.get('manual_schedule_only', '')
                _manual_only = _mso_raw if isinstance(_mso_raw, bool) else str(_mso_raw).strip().lower() == 'true'
                if _manual_only:
                    _ent = ctx.wsd_index.get((date_str, emp), {})
                    if _ent.get('is_manual'):
                        return _ent.get('status', '')
                    return ""
                if str(_er.get('type', '')).strip() == 'מנהל מחלקה':
                    _ent = ctx.wsd_index.get((date_str, emp), {})
                    if _ent.get('is_manual'):
                        return _ent.get('status', '')
                    _managed = parse_manage_depts(_er.get('manage_depts', ''))
                    if daily_dept and str(daily_dept).strip() not in _managed:
                        return ""
        except Exception:
            pass

        if is_functional_saturday(ctx, date_obj):
            return "חופש"

        if is_functional_friday(ctx, date_obj) and daily_dept:
            fri_shifts = DAILY_DEPT_TO_FRIDAY_SHIFTS.get(str(daily_dept), [])
            if fri_shifts:
                try:
                    sch = ctx.schedule
                    if not sch.empty and 'date' in sch.columns:
                        fri_mask = ((sch['date'].astype(str) == date_str) &
                                    (sch['dept'].astype(str).isin(fri_shifts)))
                        fri_emps = sch[fri_mask]['employee'].astype(str).str.strip().tolist()
                        fri_emps = [e for e in fri_emps if e and e != '---']
                        return "עובד" if emp in fri_emps else "חופש"
                except Exception:
                    pass

        try:
            entry = ctx.wsd_index.get((date_str, emp), {})
            if entry.get('is_manual'):
                ent_dept = str(entry.get('daily_dept', '') or '')
                if daily_dept and ent_dept and ent_dept != str(daily_dept):
                    return ""
                return entry['status']
        except Exception:
            pass

        try:
            for sd, ed, atype in ctx.approved_map.get(emp, []):
                if sd <= date_obj <= ed:
                    atype = ABSENCE_TYPE_TO_STATUS.get(str(atype).strip(), str(atype).strip())
                    return atype if atype else "חופש"
        except Exception:
            pass

        try:
            sf = ctx.staff
            if not sf.empty and 'recurring_absent_days' in sf.columns:
                emp_row = sf[sf['name'].astype(str).str.strip() == emp]
                if not emp_row.empty:
                    rec_raw = str(emp_row.iloc[0].get('recurring_absent_days', '') or '').strip()
                    if rec_raw:
                        for tok in rec_raw.split(','):
                            if HEB_DAY_TO_IDX.get(tok.strip()) == wd_idx:
                                return "חופש"
        except Exception:
            pass

        try:
            sch = ctx.schedule
            if not sch.empty and 'date' in sch.columns:
                night_sch = sch[~sch['dept'].astype(str).isin(FRIDAY_SHIFT_DEPTS)]
                names = night_sch['employee'].astype(str).str.strip()
                dates = night_sch['date'].astype(str)
                if ((dates == date_str) & (names == emp)).any():
                    return "תורנות"
                prev = (date_obj - timedelta(days=1)).strftime("%Y-%m-%d")
                if ((dates == prev) & (names == emp)).any():
                    return "אחרי תורנות"
        except Exception:
            pass
    except Exception:
        pass
    return "עובד"


def personal_status(ctx, date_str, user_name, daily_dept=None) -> str:
    """Status rule used by the personal Excel export (appy.py:885-891)."""
    raw = wsd_get_status(ctx, date_str, user_name, default=None)
    manual = wsd_is_manual(ctx, date_str, user_name)
    if raw is None or (raw == "עובד" and not manual):
        return derive_auto_status(ctx, date_str, user_name, daily_dept=daily_dept)
    return raw


# ── Grid model (data for the UI to render; no HTML) ───────────────────────────
def konenut_day_map(ctx, dept_name, year, month) -> dict:
    out = {}
    if dept_name not in KONENUT_DEPTS:
        return out
    try:
        kdf = ctx.konenut
        if kdf.empty or 'date' not in kdf.columns:
            return out
        km = kdf[kdf['date'].str.startswith(f"{year}-{month:02d}")]
        for _, kr in km.iterrows():
            ds = str(kr['date'])
            r1 = str(kr.get('rehab_dr1', '') or '').strip()
            r2 = str(kr.get('rehab_dr2', '') or '').strip()
            if dept_name == "פנימית גריאטרית":
                out[ds] = str(kr.get('pnim_dr', '') or '').strip()
            elif dept_name == "שיקום גריאטרי א'":
                out[ds] = r1
            else:
                out[ds] = r2 if r2 else r1
    except Exception:
        pass
    return out


def pnim_side_groups(ctx, year_month, employees):
    """Split פנימית employees by dept_rotation.side; fold transfers into their side."""
    dr = ctx.dept_rotation
    side_map = {}
    if not dr.empty and 'employee' in dr.columns and 'side' in dr.columns:
        cur = dr[dr['year_month'].astype(str) == year_month]
        side_map = cur.set_index('employee')['side'].fillna('').astype(str).str.strip().to_dict()

    def _role_order(emp_name):
        r = staff_row(ctx, emp_name)
        t = '' if r is None else str(r['type']).strip()
        return 0 if t == 'רופא בכיר' else 1

    def _sorted_group(emps):
        return sorted(emps, key=lambda e: (_role_order(e), str(e)))

    emp_strs = [str(e).strip() for e in employees]
    pink = _sorted_group([e for e in emp_strs if side_map.get(e, '') == 'ורוד'])
    blue = _sorted_group([e for e in emp_strs if side_map.get(e, '') == 'כחול'])
    unassigned = _sorted_group([e for e in emp_strs if side_map.get(e, '') == ''])
    transfer_days = {}
    for emp, rec in incoming_transfers(ctx, PNIM_DEPT, year_month).items():
        if staff_row(ctx, emp) is None:          # deleted from the staff sheet
            continue
        transfer_days[emp] = rec['days']
        if (rec.get('side') or '') == 'כחול':
            if emp not in blue:
                blue.append(emp)
        else:
            if emp not in pink:
                pink.append(emp)
    return {'ורוד': pink, 'כחול': blue}, transfer_days, unassigned


def dept_grid(ctx, dept_name, year_month, month, employees, year=None) -> dict:
    """JSON-ready model of one dept × month grid (what _render_dept_grid draws).

    Each cell: {status, label, note, manual, locked, blank_weekend}. `locked` marks
    days outside a temporary transfer; `blank_weekend` marks auto weekend closures
    the UI renders as an empty tile.
    """
    if year is None:
        try:
            year = int(str(year_month).split('-')[0])
        except Exception:
            year = year_for_month(month)
    num_days = calendar.monthrange(year, month)[1]

    side_groups = None
    unassigned = []
    if dept_name == PNIM_DEPT:
        side_groups, transfer_days, unassigned = pnim_side_groups(ctx, year_month, employees)
        employees = side_groups['ורוד'] + side_groups['כחול']
    else:
        employees = list(employees)
        transfer_days = {}
        inc = {e: r for e, r in incoming_transfers(ctx, dept_name, year_month).items()
               if staff_row(ctx, e) is not None}   # deleted from the staff sheet
        if inc:
            emp_set = {str(e).strip() for e in employees}
            employees = employees + [e for e in inc if e not in emp_set]
            transfer_days = {e: rec['days'] for e, rec in inc.items()}

    rows = []
    for emp in employees:
        cells = []
        tdays = transfer_days.get(str(emp).strip())
        for d in range(1, num_days + 1):
            date_str = f"{year}-{month:02d}-{d:02d}"
            if tdays is not None and d not in tdays:
                cells.append({'day': d, 'status': None, 'label': '—', 'note': '',
                              'manual': False, 'locked': True, 'blank_weekend': False})
                continue
            status = derive_auto_status(ctx, date_str, emp, daily_dept=dept_name)
            manual = wsd_is_manual(ctx, date_str, emp)
            wd = (date(year, month, d).weekday() + 1) % 7
            is_wknd = wd in (5, 6) or is_functional_saturday(ctx, date_str)
            cells.append({
                'day': d, 'status': status,
                'label': GRID_STATUS_LABEL_SHORT.get(status, "?"),
                'note': wsd_get_note(ctx, date_str, emp),
                'manual': bool(manual), 'locked': False,
                'blank_weekend': bool(is_wknd and status == "חופש" and not manual),
            })
        r = staff_row(ctx, emp)
        rows.append({'employee': emp, 'type': '' if r is None else str(r.get('type', '')).strip(),
                     'side': next((s for s, g in (side_groups or {}).items() if emp in g), ''),
                     'transfer_days': sorted(tdays) if tdays is not None else None,
                     'allowed_statuses': manual_statuses_for_role(ctx, emp),
                     'cells': cells})

    kmap = konenut_day_map(ctx, dept_name, year, month)
    days = []
    for d in range(1, num_days + 1):
        ds = f"{year}-{month:02d}-{d:02d}"
        days.append({
            'day': d, 'date': ds, 'weekday': (date(year, month, d).weekday() + 1) % 7,
            'night_duty': get_night_duty(ctx, ds, dept_name),
            'friday_workers': get_fri_shift_workers(ctx, ds, dept_name) if is_functional_friday(ctx, ds) else None,
            'konenut': kmap.get(ds, '') if kmap else None,
        })
    return {'dept': dept_name, 'year': year, 'month': month, 'year_month': year_month,
            'side_groups': side_groups, 'unassigned_side': unassigned,
            'rows': rows, 'days': days,
            'transfers': {e: {'days': sorted(r['days']), 'side': r['side']}
                          for e, r in incoming_transfers(ctx, dept_name, year_month).items()}}


def transfer_candidates(ctx, dept_name, year_month) -> list:
    """Who may be added as a temporary transfer (everyone not on the roster; פנימית allows side moves)."""
    roster = set()
    if dept_name != PNIM_DEPT:
        dr = ctx.dept_rotation
        if not dr.empty and 'employee' in dr.columns:
            m = ((dr['year_month'].astype(str) == year_month) & (dr['daily_dept'].astype(str) == dept_name))
            roster = set(dr[m]['employee'].astype(str).str.strip().tolist())
    names = []
    if not ctx.staff.empty and 'name' in ctx.staff.columns:
        names = ctx.staff['name'].astype(str).str.strip().tolist()
    return [n for n in names if n and n not in roster]


def initials(name) -> str:
    return make_initials(name)


def side_ok(side) -> bool:
    return side in PNIM_SIDES
