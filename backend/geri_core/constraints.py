"""Night-shift constraint/wish submission (appy.py:3943-3976, 7145-7175, 8349-8406)."""
from __future__ import annotations

import calendar
from datetime import date

import pandas as pd


def counters(year, month, blocked_days, wish_days) -> dict:
    """Live counter chips for the calendar (render_modern_calendar show_validation)."""
    n = calendar.monthrange(year, month)[1]
    all_d = [date(year, month, d) for d in range(1, n + 1)]
    total_thu = sum(1 for d in all_d if d.weekday() == 3)
    total_wk = sum(1 for d in all_d if d.weekday() in [4, 5])
    blocked = [date(year, month, d) for d in blocked_days]
    av_thu = total_thu - sum(1 for d in blocked if d.weekday() == 3)
    av_wk = total_wk - sum(1 for d in blocked if d.weekday() in [4, 5])
    return {'blocks': len(blocked_days), 'wishes': len(wish_days),
            'avail_thu': av_thu, 'total_thu': total_thu, 'thu_ok': av_thu >= 2,
            'avail_weekend': av_wk, 'total_weekend': total_wk, 'weekend_ok': av_wk >= 4}


def validate(year, month, blocked_days, wish_days, role) -> list:
    """Errors that stop an employee save (8354-8372). Admin roles bypass them."""
    blocked = [date(year, month, d) for d in blocked_days]
    wishes = [date(year, month, d) for d in wish_days]
    errors = []
    if len(wishes) > 2:
        errors.append("שגיאה: ניתן לבחור עד 2 בקשות חיוביות (⭐) בלבד.")
    overlap = set(blocked).intersection(set(wishes))
    if overlap:
        errors.append(f"שגיאה: בחרת באותו יום ({list(overlap)[0].strftime('%d/%m')}) גם אילוץ וגם בקשה. נא בחר רק אחד.")
    if role == 'מתמחה':
        c = counters(year, month, blocked_days, wish_days)
        if c['avail_thu'] < 2:
            errors.append("נותר רק יום חמישי אחד פנוי (או פחות). חובה להשאיר לפחות 2 ימי חמישי פנויים.")
        if c['avail_weekend'] < 4:
            errors.append(f"נותרו רק {c['avail_weekend']} ימי סוף שבוע פנויים. חובה להשאיר לפחות 4 (שישי/שבת).")
    return errors


def my_requests(ctx, employee, year, month):
    """(blocked_day_nums, wish_day_nums) for one employee × month."""
    df = ctx.requests
    if df.empty:
        return [], []
    out = {}
    for status in ("אילוץ", "בקשה"):
        u = df[(df['employee'] == employee) & (df['status'] == status)].copy()
        if u.empty:
            out[status] = []
            continue
        u['date_dt'] = pd.to_datetime(u['date'], errors='coerce')
        v = u[(u['date_dt'].dt.month == month) & (u['date_dt'].dt.year == year)]
        out[status] = v['date_dt'].dt.day.astype(int).tolist()
    return out["אילוץ"], out["בקשה"]


def save_requests(ctx, employee, year, month, blocked_days, wish_days, role=None, enforce_rules=True):
    """Replace employee's requests for the month, merging into a LIVE read (no cross-user clobber).

    Employees: full validation. Admin editing someone (צוות tab): only the overlap rule.
    """
    if enforce_rules:
        errors = validate(year, month, blocked_days, wish_days, role)
        if errors and role != 'מנהל/ת':
            raise ValueError("\n".join(errors))
    else:
        overlap = set(blocked_days) & set(wish_days)
        if overlap:
            fmt = [date(year, month, d).strftime('%d/%m') for d in sorted(overlap)]
            raise ValueError(f"שגיאה: התאריכים הבאים מסומנים גם כחסימה וגם כבקשה: {', '.join(fmt)}")
    live = ctx.fetch_live("requests")
    base = live if not live.empty else ctx.requests
    prefix = f"{year}-{month:02d}"
    keep = ~((base['employee'].astype(str).str.strip() == str(employee).strip()) &
             (base['date'].astype(str).str.startswith(prefix)))
    base = base[keep]
    rows = ([{'employee': employee, 'date': f"{prefix}-{d:02d}", 'status': "אילוץ"} for d in sorted(blocked_days)] +
            [{'employee': employee, 'date': f"{prefix}-{d:02d}", 'status': "בקשה"} for d in sorted(wish_days)])
    merged = pd.concat([base, pd.DataFrame(rows)], ignore_index=True) if rows else base
    ctx.save("requests", merged)
    ctx.requests = merged
    return merged


def special_days_in_month(ctx, year, month) -> list:
    out = []
    sd = ctx.special_days
    if sd is None or sd.empty:
        return out
    from datetime import datetime
    for _, row in sd.iterrows():
        try:
            d = datetime.strptime(row['date'], '%Y-%m-%d').date()
        except Exception:
            continue
        if d.month == month and d.year == year:
            out.append({'date': row['date'], 'description': row['description'],
                        'day_type': row.get('day_type', 'רגיל')})
    return out
