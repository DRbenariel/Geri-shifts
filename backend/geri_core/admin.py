"""Settings, special days, on-call (כוננויות) and the monthly Gantt (appy.py:3191-3257,
4948-5206, 6493-6549, 6215-6276, 7697-7955)."""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

import pandas as pd

from .absences import migrate_requests_on_dept_change
from .constants import (HEB_MONTHS, KONENUT_ELIGIBLE_TYPES, MANUAL_PLANT_ONLY_MANAGERS, PNIM_DEPT,
                        PNIM_SIDES, SHEET_COLUMNS, SPECIAL_DAY_TYPES, UNASSIGNED)
from .normalize import is_true, norm_dr
from .people import gantt_assignment_errors, gantt_dept_options


# ── settings ─────────────────────────────────────────────────────────────────
def get_setting(ctx, key, default):
    try:
        rows = ctx.settings[ctx.settings['key'] == key]
        if not rows.empty:
            return rows['value'].iloc[0]
    except Exception:
        pass
    return default


def set_setting(ctx, key, value):
    s = ctx.settings.copy()
    s['value'] = s['value'].astype(object)
    if (s['key'] == key).any():
        s.loc[s['key'] == key, 'value'] = str(value)
    else:
        s = pd.concat([s, pd.DataFrame([{'key': key, 'value': str(value)}])], ignore_index=True)
    ctx.settings = s
    ctx.save("settings", s)


def active_months(ctx) -> dict:
    try:
        am = int(get_setting(ctx, 'active_month', date.today().month))
    except Exception:
        am = date.today().month
    try:
        dam = int(get_setting(ctx, 'daily_active_month', am))
    except Exception:
        dam = am
    return {'active_month': am, 'daily_active_month': dam,
            'daily_requests_open': str(get_setting(ctx, 'daily_requests_open', 'True')).strip().lower() == 'true'}


def make_daily_month_active(ctx, month):
    """'⚡ הפוך לחודש פעיל': also re-opens day-absence submissions."""
    set_setting(ctx, 'daily_active_month', month)
    set_setting(ctx, 'daily_requests_open', 'True')


def rolling_months(now=None) -> list:
    """12-month forward window [(year, month)] (_sw_month_selector_12 / Gantt window)."""
    now = now or datetime.now()
    return [(now.year + (now.month - 1 + i) // 12, (now.month - 1 + i) % 12 + 1) for i in range(12)]


def init_db(store):
    """Additive init: create missing sheets/settings keys only, never overwrite."""
    defaults = [
        ('active_month', str((date.today().replace(day=1) + timedelta(days=32)).month)),
        ('daily_active_month', str((date.today().replace(day=1) + timedelta(days=32)).month)),
        ('daily_requests_open', 'True'),
    ]
    required = {k: SHEET_COLUMNS[k] for k in ("staff", "schedule", "requests", "special_days",
                                              "dept_rotation", "absence_requests", "work_schedule_daily")}
    existing = store.titles()
    for name, cols in required.items():
        if name not in existing:
            store.write(name, pd.DataFrame(columns=cols))
    if "settings" not in existing:
        store.write("settings", pd.DataFrame([{'key': k, 'value': v} for k, v in defaults]))
    else:
        cur = store.read("settings")
        keys = set(cur['key'].astype(str)) if not cur.empty and 'key' in cur.columns else set()
        for k, v in defaults:
            if k not in keys:
                cur = pd.concat([cur, pd.DataFrame([{'key': k, 'value': v}])], ignore_index=True)
        if set(cur['key'].astype(str)) != keys:
            store.write("settings", cur)


# ── special days ─────────────────────────────────────────────────────────────
def add_special_day(ctx, date_str, description, day_type):
    if not description:
        raise ValueError("חובה להזין תיאור.")
    if day_type not in SPECIAL_DAY_TYPES:
        raise ValueError(day_type)
    new = pd.DataFrame([{'date': str(date_str), 'description': description, 'day_type': day_type}])
    ctx.special_days = pd.concat([ctx.special_days, new], ignore_index=True)
    ctx.save("special_days", ctx.special_days)


def delete_special_day(ctx, idx):
    ctx.special_days = ctx.special_days.drop(idx).reset_index(drop=True)
    ctx.save("special_days", ctx.special_days)


# ── כוננויות ─────────────────────────────────────────────────────────────────
def konenut_doctors(ctx) -> list:
    try:
        sf = ctx.staff
        return sorted(sf[sf['type'].astype(str).str.strip().isin(KONENUT_ELIGIBLE_TYPES)]
                      ['name'].astype(str).str.strip().tolist())
    except Exception:
        return []


def konenut_month(ctx, year, month) -> list:
    k = ctx.konenut
    m = k[k['date'].str.startswith(f"{year}-{month:02d}")].set_index('date')
    out = []
    for d in range(1, calendar.monthrange(year, month)[1] + 1):
        ds = f"{year}-{month:02d}-{d:02d}"
        r = m.loc[ds] if ds in m.index else None
        out.append({'date': ds, 'pnim_dr': '' if r is None else r['pnim_dr'],
                    'rehab_dr1': '' if r is None else r['rehab_dr1'],
                    'rehab_dr2': '' if r is None else r['rehab_dr2']})
    return out


def save_konenut_day(ctx, date_str, pnim, r1, r2):
    """Mobile save: replace only this date's row."""
    row = {'date': date_str, 'pnim_dr': (pnim or '').strip(), 'rehab_dr1': (r1 or '').strip(),
           'rehab_dr2': (r2 or '').strip()}
    full = ctx.konenut
    full = full[full['date'] != date_str]
    full = pd.concat([full, pd.DataFrame([row])], ignore_index=True).sort_values('date').reset_index(drop=True)
    ctx.konenut = full
    ctx.save("konenut", full)


def save_konenut_month(ctx, year, month, days: list):
    """Desktop save: replace the whole month with `days` ([{date,pnim_dr,rehab_dr1,rehab_dr2}])."""
    ym = f"{year}-{month:02d}"
    rows = [{'date': d['date'], 'pnim_dr': (d.get('pnim_dr') or '').strip(),
             'rehab_dr1': (d.get('rehab_dr1') or '').strip(),
             'rehab_dr2': (d.get('rehab_dr2') or '').strip()} for d in days]
    full = ctx.konenut
    full = full[~full['date'].str.startswith(ym)]
    full = pd.concat([full, pd.DataFrame(rows)], ignore_index=True).sort_values('date').reset_index(drop=True)
    ctx.konenut = full
    ctx.save("konenut", full)


# ── גאנט חודשי ───────────────────────────────────────────────────────────────
def gantt_eligible(ctx) -> pd.DataFrame:
    staff = ctx.staff.copy()
    staff['name'] = staff['name'].astype(str).str.strip()
    staff['type'] = staff['type'].astype(str).str.strip()
    el = staff[staff['type'].isin(['מתמחה', 'רופא בכיר', 'מנהל מחלקה'])]
    el = el[~((el['type'] == 'מנהל מחלקה') & el['name'].isin(MANUAL_PLANT_ONLY_MANAGERS))]
    el = el[el['name'].str.len() > 0]
    return el[el['name'] != '---']


def _dr_month(ctx, year_month):
    dr = ctx.dept_rotation.copy()
    if 'employee' not in dr.columns:
        return dr, {}, {}
    dr['employee'] = dr['employee'].astype(str).str.strip()
    dr['year_month'] = dr['year_month'].astype(str)
    dr['daily_dept'] = dr['daily_dept'].astype(str)
    if 'side' not in dr.columns:
        dr['side'] = ''
    dr['side'] = dr['side'].fillna('').astype(str).str.strip()
    cur = dr[dr['year_month'] == year_month]
    return dr, cur.set_index('employee')['daily_dept'].to_dict(), cur.set_index('employee')['side'].to_dict()


def gantt_rows(ctx, year_month) -> list:
    _, existing, sides = _dr_month(ctx, year_month)
    out = []
    for _, r in gantt_eligible(ctx).iterrows():
        opts = gantt_dept_options(r)
        cur = existing.get(r['name'], UNASSIGNED)
        side = sides.get(r['name'], '')
        out.append({'name': r['name'], 'type': r['type'], 'options': opts,
                    'dept': cur if cur in opts else None,
                    'invalid_existing': cur not in opts,
                    'side': side if side in PNIM_SIDES else '',
                    'manual_schedule_only': is_true(r.get('manual_schedule_only', False))})
    return out


def save_gantt(ctx, year_month, assignments: dict, sides: dict) -> dict:
    """Validate, write dept_rotation for the month (preserving hidden rows), migrate requests."""
    el = gantt_eligible(ctx)
    errors = gantt_assignment_errors(el.to_dict('records'), assignments, sides)
    if errors:
        raise ValueError("\n".join(errors))
    dr, existing, _ = _dr_month(ctx, year_month)
    changes = [(e, existing[e], nd) for e, nd in assignments.items()
               if e in existing and existing[e] and nd != UNASSIGNED and existing[e] != nd]
    other = dr[dr['year_month'] != year_month] if not dr.empty else pd.DataFrame(
        columns=['employee', 'year_month', 'daily_dept', 'side'])
    new_rows = [{'employee': e, 'year_month': year_month, 'daily_dept': d,
                 'side': sides.get(e, '') if d == PNIM_DEPT else ''}
                for e, d in assignments.items() if d != UNASSIGNED]
    preserved = dr[(dr['year_month'] == year_month) & ~dr['employee'].isin(set(assignments))] \
        if not dr.empty else pd.DataFrame(columns=other.columns)
    new_dr = norm_dr(pd.concat([other, preserved, pd.DataFrame(new_rows)], ignore_index=True))
    ctx.dept_rotation = new_dr
    ctx.save("dept_rotation", new_dr)
    migrated = sum(migrate_requests_on_dept_change(ctx, e, o, n, year_month) for e, o, n in changes)
    return {'saved': len(new_rows), 'migrated': migrated}


def gantt_summary(ctx, year_month) -> dict:
    dr = ctx.dept_rotation
    cur = dr[dr['year_month'].astype(str) == year_month] if not dr.empty else dr
    return {'total': len(cur), 'by_dept': cur['daily_dept'].value_counts().to_dict() if len(cur) else {}}


def month_label(year, month) -> str:
    return f"{HEB_MONTHS[month - 1]} {year}"
