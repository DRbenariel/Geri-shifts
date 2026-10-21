"""Day-absence workflow (appy.py:221-380, 1616-1715, 2771-3006, 8008-8222, 8413-8868, 8937-9197)."""
from __future__ import annotations

import calendar
import uuid
from datetime import date, datetime, timedelta

import pandas as pd

from .constants import ABSENCE_TYPE_TO_STATUS
from .context import daterange, now_str
from .daily import derive_auto_status, wsd_upsert
from .days import to_date
from .normalize import norm_dept, parse_manage_depts
from .people import emp_dept_for_date, manager_email_for_dept, staff_row

ABSENCE_STATUSES_FOR_GANTT = {"חופש", "202", "אחר", "אחרי תורנות"}
GANTT_ACTIVE_TYPES = ['מתמחה', 'רופא בכיר', 'מנהל מחלקה', 'מנהל/ת']


# ── conflicts ─────────────────────────────────────────────────────────────────
def absence_conflicts(ctx, employee, dept, start_date, end_date, absence_df=None, exclude_id=None) -> list:
    """Other employees' APPROVED absences overlapping the range in the same canonical dept."""
    out = []
    try:
        emp_n = str(employee).strip()
        dept_n = str(dept or '').strip()
        filter_by_dept = bool(dept_n)
        sd = to_date(start_date)
        ed = to_date(end_date)
        if ed < sd:
            sd, ed = ed, sd
        df = absence_df if absence_df is not None else ctx.absence_requests
        if df.empty or 'status' not in df.columns:
            return out
        df2 = df.copy()
        df2['_status'] = df2['status'].astype(str).str.lower()
        df2['_emp'] = df2['employee'].astype(str).str.strip()
        df2 = df2[(df2['_status'] == 'approved') & (df2['_emp'] != emp_n)]
        for _, r in df2.iterrows():
            try:
                r_sd = to_date(r['start_date'])
                r_ed = to_date(r['end_date'])
            except Exception:
                continue
            if r_ed < r_sd:
                r_sd, r_ed = r_ed, r_sd
            ov_s = max(sd, r_sd)
            ov_e = min(ed, r_ed)
            if ov_s > ov_e:
                continue
            if exclude_id is not None and str(r.get('id', '')) == str(exclude_id):
                continue
            if filter_by_dept:
                other_dept = emp_dept_for_date(ctx, r['_emp'], r_sd)
                if not other_dept:
                    raw = r.get('dept_at_request')
                    try:
                        other_dept = '' if pd.isna(raw) else str(raw).strip()
                    except TypeError:
                        other_dept = str(raw or '').strip()
                if other_dept and str(other_dept).strip() != dept_n:
                    continue
            out.append({'employee': r['_emp'], 'start': r_sd, 'end': r_ed,
                        'type': str(r.get('type', '') or ''),
                        'overlap_start': ov_s, 'overlap_end': ov_e})
    except Exception:
        pass
    return out


def format_conflict_warning(conflicts) -> str:
    if not conflicts:
        return ""
    parts = []
    for c in conflicts:
        if c['overlap_start'] == c['overlap_end']:
            rng = c['overlap_start'].strftime('%d/%m')
        else:
            rng = f"{c['overlap_start'].strftime('%d/%m')}–{c['overlap_end'].strftime('%d/%m')}"
        parts.append(f"{c['employee']} ({rng})")
    return "⚠️ חופש כבר אושר מאותה מחלקה בתאריכים אלו: " + " · ".join(parts)


def format_conflict_question(conflicts) -> str:
    if not conflicts:
        return ""
    return format_conflict_warning(conflicts) + "  \nהאם לאשר בקשת היעדרות בכל זאת?"


def conflicts_for_request(ctx, row) -> list:
    """Conflicts for one pending absence_requests row (how every approval list computes them)."""
    emp = str(row.get('employee', '')).strip()
    rs = pd.to_datetime(row.get('start_date', ''), errors='coerce')
    re_ = pd.to_datetime(row.get('end_date', ''), errors='coerce')
    return absence_conflicts(ctx, emp, emp_dept_for_date(ctx, emp, rs), rs, re_, exclude_id=row.get('id'))


# ── status changes ────────────────────────────────────────────────────────────
def _update_absence_status(ctx, req_id, new_status, responder_name) -> bool:
    df = ctx.absence_requests.copy()
    if df.empty or 'id' not in df.columns:
        return False
    mask = df['id'].astype(str) == str(req_id)
    if not mask.any():
        return False
    df.loc[mask, 'status'] = new_status
    df.loc[mask, 'approved_by'] = responder_name
    df.loc[mask, 'responded_at'] = now_str()
    ctx.absence_requests = df
    ctx.save("absence_requests", df)
    try:
        row = df[mask].iloc[0]
        emp_name = str(row.get('employee', '')).strip()
        r = staff_row(ctx, emp_name)
        emp_email = '' if r is None else str(r.get('email', '')).strip()
        if emp_email:
            verb = "אושרה" if new_status == 'approved' else "נדחתה"
            ctx.send_email(
                emp_email, f"בקשת היעדרות {verb}",
                f"<div dir='rtl'><p>שלום {emp_name},</p>"
                f"<p>בקשת ההיעדרות שלך לתאריכים "
                f"<b>{row.get('start_date','')} – {row.get('end_date','')}</b> "
                f"({row.get('type','')}) <b>{verb}</b> על ידי {responder_name}.</p></div>")
    except Exception:
        pass
    return True


def materialize_absence_to_wsd(ctx, employee, atype, start_date, end_date):
    """One manual WSD row per day of an approved absence (single save at the end)."""
    try:
        emp = str(employee).strip()
        status = ABSENCE_TYPE_TO_STATUS.get(str(atype).strip(), str(atype).strip()) or "חופש"
        sd = datetime.strptime(str(start_date)[:10], '%Y-%m-%d').date()
        ed = datetime.strptime(str(end_date)[:10], '%Y-%m-%d').date()
        if ed < sd:
            sd, ed = ed, sd
        for cur in daterange(sd, ed):
            ds = cur.strftime('%Y-%m-%d')
            wsd_upsert(ctx, ds, emp, emp_dept_for_date(ctx, emp, ds) or '', status,
                       is_manual=True, note='', persist=False)
        ctx.save("work_schedule_daily", ctx.work_schedule_daily)
    except Exception:
        pass


def approve_request(ctx, req_id, responder_name) -> bool:
    ok = _update_absence_status(ctx, req_id, 'approved', responder_name)
    if ok:
        try:
            df = ctx.absence_requests
            row = df[df['id'].astype(str) == str(req_id)].iloc[0]
            materialize_absence_to_wsd(ctx, row.get('employee', ''), row.get('type', ''),
                                       row.get('start_date', ''), row.get('end_date', ''))
        except Exception:
            pass
    return ok


def reject_request(ctx, req_id, responder_name) -> bool:
    return _update_absence_status(ctx, req_id, 'rejected', responder_name)


def delete_absence_request(ctx, req_id) -> bool:
    """Hard-delete an approved request (admin / manager power-tool)."""
    try:
        df = ctx.absence_requests
        if df.empty or 'id' not in df.columns:
            return False
        m = df['id'].astype(str) == str(req_id)
        if not m.any():
            return False
        new_df = df[~m].reset_index(drop=True)
        ctx.absence_requests = new_df
        ctx.save("absence_requests", new_df)
        return True
    except Exception:
        return False


def migrate_requests_on_dept_change(ctx, emp_name, old_dept, new_dept, year_month) -> int:
    """Gantt moved emp old→new: retarget pending/approved requests + manual חופש/202 WSD rows."""
    emp_n = str(emp_name).strip()
    ym = str(year_month)
    new_mgr_email = ""
    try:
        sf = ctx.staff
        for _, sr in sf[sf['type'].astype(str).str.strip() == 'מנהל מחלקה'].iterrows():
            if new_dept in parse_manage_depts(sr.get('manage_depts', '')):
                new_mgr_email = str(sr.get('email', '')).strip()
                break
    except Exception:
        pass

    migrated = 0
    ar = ctx.absence_requests.copy()
    if not ar.empty and 'id' in ar.columns:
        mask = ((ar['employee'].astype(str).str.strip() == emp_n) &
                (ar['start_date'].astype(str).str.startswith(ym)) &
                (ar['dept_at_request'].astype(str).str.strip() == old_dept) &
                (ar['status'].astype(str).isin(['pending', 'approved'])))
        migrated = int(mask.sum())
        if migrated:
            ar.loc[mask, 'dept_at_request'] = new_dept
            ar.loc[mask, 'manager_email'] = new_mgr_email
            ctx.absence_requests = ar
            ctx.save("absence_requests", ar)

    wsd = ctx.work_schedule_daily.copy()
    if not wsd.empty and 'date' in wsd.columns:
        wsd_mask = ((wsd['employee'].astype(str).str.strip() == emp_n) &
                    (wsd['date'].astype(str).str.startswith(ym)) &
                    (wsd['daily_dept'].astype(str).str.strip() == old_dept) &
                    (wsd['is_manual'].astype(str).str.lower() == 'true') &
                    (wsd['status'].astype(str).isin(['חופש', '202'])))
        if wsd_mask.any():
            wsd.loc[wsd_mask, 'daily_dept'] = new_dept
            ctx.work_schedule_daily = wsd
            ctx.save("work_schedule_daily", wsd)
    return migrated


# ── creating requests ─────────────────────────────────────────────────────────
def _new_row(employee, sd, ed, atype, status, dept, mgr_email='', approved_by='', notes='', responded=''):
    return {'id': str(uuid.uuid4()), 'employee': str(employee).strip(),
            'start_date': sd, 'end_date': ed, 'type': atype, 'status': status,
            'dept_at_request': dept, 'manager_email': mgr_email, 'approved_by': approved_by,
            'notes': notes, 'created_at': now_str(), 'responded_at': responded}


def add_preapproved_absence(ctx, employee, start, end, atype, note, approver) -> dict:
    """Admin / manager section 3: an approved absence written straight to the board."""
    sd, ed = to_date(start), to_date(end)
    if ed < sd:
        raise ValueError("תאריך סיום לפני תאריך התחלה.")
    row = _new_row(employee, sd.strftime('%Y-%m-%d'), ed.strftime('%Y-%m-%d'), atype, 'approved',
                   emp_dept_for_date(ctx, employee, sd), approved_by=str(approver).strip(),
                   notes=str(note or '').strip(), responded=now_str())
    df = pd.concat([ctx.absence_requests, pd.DataFrame([row])], ignore_index=True)
    ctx.absence_requests = df
    ctx.save("absence_requests", df)
    materialize_absence_to_wsd(ctx, employee, atype, row['start_date'], row['end_date'])
    return row


def submit_day_absences(ctx, user_name, role, year, month, vac_days, days_202, requests_open=True) -> list:
    """Employee ☀️ calendar save (8649-8749): replaces this month's pending rows.

    מנהל מחלקה requests are auto-approved and written to WSD; others email the
    dept manager. רופא בכיר cannot request 202.
    """
    vac_days = sorted(set(int(d) for d in vac_days))
    days_202 = sorted(set(int(d) for d in days_202))
    if role == 'רופא בכיר' and days_202:
        raise ValueError("רופא/ה בכיר/ה אינו/ה יכול/ה לבקש 202.")
    if not (requests_open or role == 'מנהל מחלקה'):
        raise PermissionError("ההגשות לחודש זה סגורות.")
    if not (vac_days or days_202):
        return []
    first_d = (vac_days + days_202)[0]
    dept_at_req = emp_dept_for_date(ctx, user_name, date(year, month, first_d))
    mgr_email = manager_email_for_dept(ctx, dept_at_req)
    is_mgr = role == 'מנהל מחלקה'
    req_st = 'approved' if is_mgr else 'pending'
    appr = str(user_name).strip() if is_mgr else ''
    resp = now_str() if is_mgr else ''

    base = ctx.absence_requests.copy()
    if not base.empty and 'employee' in base.columns:
        keep = ~((base['employee'].astype(str).str.strip() == str(user_name).strip()) &
                 (base['status'].astype(str).str.lower() == 'pending') &
                 (base['start_date'].astype(str).str.startswith(f"{year}-{month:02d}")))
        base = base[keep]
    rows = []
    for d in vac_days:
        ds = f"{year}-{month:02d}-{d:02d}"
        rows.append(_new_row(user_name, ds, ds, 'חופש', req_st, dept_at_req, mgr_email, appr, '', resp))
    for d in days_202:
        ds = f"{year}-{month:02d}-{d:02d}"
        rows.append(_new_row(user_name, ds, ds, '202', req_st, dept_at_req, mgr_email, appr, '', resp))
    final = pd.concat([base, pd.DataFrame(rows)], ignore_index=True)
    ctx.absence_requests = final
    ctx.save("absence_requests", final)

    if is_mgr:
        mgr_dept = dept_at_req
        if not mgr_dept:
            r = staff_row(ctx, user_name)
            mdl = [] if r is None else parse_manage_depts(r.get('manage_depts', ''))
            mgr_dept = mdl[0] if mdl else ''
        if mgr_dept:
            for d in vac_days:
                wsd_upsert(ctx, f"{year}-{month:02d}-{d:02d}", str(user_name).strip(), mgr_dept,
                           'חופש', is_manual=True, note='', persist=False)
            for d in days_202:
                wsd_upsert(ctx, f"{year}-{month:02d}-{d:02d}", str(user_name).strip(), mgr_dept,
                           '202', is_manual=True, note='', persist=False)
            ctx.save("work_schedule_daily", ctx.work_schedule_daily)
    elif mgr_email:
        all_dates = ([f"חופש — {d:02d}/{month:02d}" for d in vac_days] +
                     [f"202 — {d:02d}/{month:02d}" for d in days_202])
        ctx.send_email(
            mgr_email, f"בקשת היעדרות חדשה: {user_name}",
            f"<div dir='rtl'><p>שלום,</p>"
            f"<p><b>{user_name}</b> ({dept_at_req}) הגיש/ה בקשות היעדרות:</p>"
            f"<ul>{''.join(f'<li>{x}</li>' for x in all_dates)}</ul>"
            f"<p>נא להיכנס למערכת לאישור.</p></div>")
    return rows


def submit_future_absence(ctx, user_name, start, end, atype, note) -> dict:
    """'חופש עתידי' expander (8809-8868): bypasses the open/closed gate, always pending."""
    sd, ed = to_date(start), to_date(end)
    if ed < sd:
        raise ValueError("תאריך הסיום חייב להיות שווה או אחרי תאריך ההתחלה.")
    atype = ABSENCE_TYPE_TO_STATUS.get(atype, atype)
    fut_ym = sd.strftime("%Y-%m")
    fut_dept = ""
    dr = ctx.dept_rotation
    if not dr.empty and 'employee' in dr.columns:
        mine = dr[(dr['employee'].astype(str).str.strip() == str(user_name).strip()) &
                  (dr['year_month'].astype(str) == fut_ym)]
        if not mine.empty:
            fut_dept = str(mine.iloc[0].get('daily_dept', '')).strip()
    mgr_email = manager_email_for_dept(ctx, fut_dept)
    row = _new_row(user_name, sd.strftime('%Y-%m-%d'), ed.strftime('%Y-%m-%d'), atype, 'pending',
                   fut_dept, mgr_email, '', str(note or '').strip(), '')
    df = pd.concat([ctx.absence_requests, pd.DataFrame([row])], ignore_index=True)
    ctx.absence_requests = df
    ctx.save("absence_requests", df)
    if mgr_email:
        ctx.send_email(
            mgr_email, f"בקשת חופש עתידי: {user_name}",
            f"<div dir='rtl'><p>שלום,</p>"
            f"<p>עובד <b>{user_name}</b> ({fut_dept or '—'}) הגיש בקשת חופש עתידי:</p>"
            f"<ul><li>סוג: {atype}</li>"
            f"<li>תאריכים: {row['start_date']} – {row['end_date']}</li>"
            f"<li>הערה: {note or '—'}</li></ul>"
            f"<p>נא להיכנס למערכת לאישור או דחיה.</p></div>")
    row['no_dept_warning'] = not fut_dept
    return row


# ── read models ───────────────────────────────────────────────────────────────
def my_absence_calendar(ctx, user_name, year, month) -> dict:
    """Day sets for the employee ☀️ calendar (8442-8524)."""
    out = {'approved_vac': set(), 'approved_202': set(), 'approved_future': set(), 'pending': set(),
           'pending_types': {}, 'night_shift': set(), 'post_shift': set()}
    ar = ctx.absence_requests
    if not ar.empty and 'employee' in ar.columns:
        mine = ar[ar['employee'].astype(str).str.strip() == str(user_name).strip()]
        for _, r in mine.iterrows():
            try:
                sd = datetime.strptime(str(r['start_date']), '%Y-%m-%d').date()
                ed = datetime.strptime(str(r['end_date']), '%Y-%m-%d').date()
            except Exception:
                continue
            status = str(r.get('status', '')).strip().lower()
            atype = str(r.get('type', '')).strip()
            for d in daterange(sd, ed):
                if d.month != month or d.year != year:
                    continue
                if status == 'approved':
                    if atype == '202':
                        out['approved_202'].add(d.day)
                    elif atype == 'חופש עתידי':
                        out['approved_future'].add(d.day)
                    else:
                        out['approved_vac'].add(d.day)
                elif status == 'pending':
                    out['pending'].add(d.day)
                    out['pending_types'][d.day] = 2 if atype == '202' else 1
    sch = ctx.schedule
    if not sch.empty and 'employee' in sch.columns:
        s = sch.copy()
        s['employee'] = s['employee'].astype(str).str.strip()
        s = s[(s['employee'] == str(user_name).strip()) &
              (~s['dept'].astype(str).str.contains('שישי בוקר', na=False))]
        for _, sr in s.iterrows():
            try:
                sd = datetime.strptime(str(sr['date']), '%Y-%m-%d').date()
            except Exception:
                continue
            if sd.month == month and sd.year == year:
                out['night_shift'].add(sd.day)
            nd = sd + timedelta(days=1)
            if nd.month == month and nd.year == year:
                out['post_shift'].add(nd.day)
    return {k: (sorted(v) if isinstance(v, set) else v) for k, v in out.items()}


def my_absence_history(ctx, user_name) -> list:
    ar = ctx.absence_requests
    if ar.empty or 'employee' not in ar.columns:
        return []
    mine = ar[ar['employee'].astype(str).str.strip() == str(user_name).strip()]
    cols = ['id', 'start_date', 'end_date', 'type', 'status', 'approved_by', 'notes']
    return mine[[c for c in cols if c in mine.columns]].fillna('').to_dict('records')


def manager_scope(ctx, user_name):
    """(managed_depts, normalized depts, employees ever rostered in them) for מנהל מחלקה."""
    r = staff_row(ctx, user_name)
    depts = [] if r is None else parse_manage_depts(r.get('manage_depts', ''))
    norm = [norm_dept(d) for d in depts]
    emps = set()
    dr = ctx.dept_rotation
    if not dr.empty and 'daily_dept' in dr.columns:
        for md in norm:
            emask = dr['daily_dept'].apply(norm_dept) == md
            emps.update(dr[emask]['employee'].astype(str).str.strip().tolist())
    return depts, norm, emps


def pending_requests(ctx, dept_filter=None, manager=None) -> list:
    """Pending list with conflicts. Admin filters by dept_at_request; a manager sees
    requests whose dept is theirs OR whose employee was ever rostered in their depts."""
    ar = ctx.absence_requests.copy()
    if ar.empty or 'status' not in ar.columns:
        return []
    ar['status'] = ar['status'].astype(str).str.lower()
    ar['dept_at_request'] = ar['dept_at_request'].astype(str)
    pen = ar[ar['status'] == 'pending']
    if manager is not None:
        _, norm, emps = manager_scope(ctx, manager)
        dm = pen['dept_at_request'].str.strip().apply(norm_dept).isin(norm)
        em = pen['employee'].astype(str).str.strip().isin(emps)
        pen = pen[dm | em]
    elif dept_filter and dept_filter != "הכל":
        pen = pen[pen['dept_at_request'] == dept_filter]
    if 'start_date' in pen.columns:
        pen = pen.sort_values('start_date')
    out = []
    for _, row in pen.iterrows():
        c = conflicts_for_request(ctx, row)
        rec = {k: ('' if pd.isna(v) else v) for k, v in row.to_dict().items()}
        rec['dept_canonical'] = emp_dept_for_date(ctx, row.get('employee', ''), row.get('start_date', '')) or ''
        rec['conflicts'] = [{**x, 'start': str(x['start']), 'end': str(x['end']),
                             'overlap_start': str(x['overlap_start']), 'overlap_end': str(x['overlap_end'])} for x in c]
        rec['conflict_question'] = format_conflict_question(c)
        out.append(rec)
    return out


def deletable_approved(ctx, manager_depts=None) -> list:
    df = ctx.absence_requests.copy()
    if df.empty or 'status' not in df.columns:
        return []
    df = df[df['status'].astype(str).str.lower() == 'approved'].copy()
    df['dept_canonical'] = df.apply(
        lambda r: emp_dept_for_date(ctx, r.get('employee', ''), r.get('start_date', '')) or '', axis=1)
    if manager_depts is not None:
        df = df[df['dept_canonical'].isin(manager_depts)]
    out = []
    for _, r in df.iterrows():
        out.append({'id': str(r.get('id', '')),
                    'label': (f"{str(r.get('employee', '')).strip()} · {r['dept_canonical'] or '—'} · "
                              f"{str(r.get('start_date', ''))[:10]} – {str(r.get('end_date', ''))[:10]} · "
                              f"{str(r.get('type', '') or '').strip()}")})
    return out


def absence_gantt(ctx, year, month, dept_filter=None) -> dict:
    """{dept: {employee: [(day, status)]}} + overlap days (appy._render_absence_gantt data)."""
    num_days = calendar.monthrange(year, month)[1]
    month_start = date(year, month, 1)
    sf = ctx.staff
    if sf.empty or 'name' not in sf.columns:
        return {'by_dept': {}, 'conflicts': {}}
    emp_names = sorted(set(sf[sf['type'].astype(str).str.strip().isin(GANTT_ACTIVE_TYPES)]
                           ['name'].astype(str).str.strip().tolist()))
    by_dept = {}
    for emp in emp_names:
        if not emp:
            continue
        dept_canon = emp_dept_for_date(ctx, emp, month_start) or '—'
        if dept_filter and dept_canon not in dept_filter:
            continue
        for d in range(1, num_days + 1):
            if (date(year, month, d).weekday() + 1) % 7 >= 5:
                continue
            status = derive_auto_status(ctx, f"{year}-{month:02d}-{d:02d}", emp, daily_dept=None)
            if status in ABSENCE_STATUSES_FOR_GANTT:
                by_dept.setdefault(dept_canon, {}).setdefault(emp, []).append((d, status))
    conflicts = {}
    for dept_n, emps in by_dept.items():
        day_to = {}
        for emp, items in emps.items():
            for d, _t in items:
                day_to.setdefault(d, set()).add(emp)
        for d, es in day_to.items():
            if len(es) >= 2:
                conflicts[(dept_n, d)] = sorted(es)
    return {'by_dept': by_dept, 'conflicts': conflicts}


def employee_absence_history(ctx, employee) -> list:
    """All requests for one employee (צוות tab, 7182-7242)."""
    return my_absence_history(ctx, employee)
