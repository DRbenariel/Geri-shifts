"""Night shifts (תורנויות): validity, swaps, manual edits, availability.

Ports appy.py:3460-3701 (validity, employee swap search), 5215-5258
(admin availability), 5507-5818 (admin swap finder), 5833-5980 (swap
execution), 6563-6656 (manual tool + cleanup), 6670-6749 (suggestion
actions), 6408-6490 (swap request rows) and 6801-6847 (swap approval).
"""
from __future__ import annotations

import calendar
from datetime import date, datetime, timedelta

import pandas as pd

from .context import now_str
from .people import emp_night_dept


# ── validity (single source of truth for constraint checks) ───────────────────
def check_assignment_validity(ctx, schedule_data, person_name, check_date, target_dept, staff_df, requests_df,
                              ignore_quota=False, ignore_home_restrict=False, ignore_rest=False):
    if isinstance(schedule_data, pd.DataFrame):
        schedule_data = schedule_data.to_dict('records')
    if person_name in ['ADMIN', '---']:
        return False, "Invalid Person"
    p_row = staff_df[staff_df['name'] == person_name]
    if p_row.empty:
        return False, "Unknown Employee"
    person = p_row.iloc[0]

    p_type = str(person.get('type', '')).strip()
    if 'חוץ' in p_type and 'פנימית' in target_dept:
        return False, "External cannot work Internal"

    if not ignore_home_restrict:
        only_home = person.get('only_home_dept', False)
        if only_home:
            target_context = target_dept
            if "שישי בוקר" in target_dept:
                target_context = "שיקום" if "שיקום" in target_dept else "פנימית גריאטרית"
            home = emp_night_dept(ctx, person_name, str(check_date)[:7]) or str(person.get('dept', '') or '')
            if home != 'כללי' and home != target_context:
                return False, f"Restricted to Home Dept ({home})"

    req_date_str = requests_df['date'].astype(str)
    if not requests_df[(requests_df['employee'] == person_name) & (req_date_str == check_date)
                       & (requests_df['status'] == "אילוץ")].empty:
        return False, "User Restriction (Blocked)"

    try:
        max_quota = int(person.get('monthly_quota', 6))
    except Exception:
        max_quota = 6
    if max_quota == 0:
        return False, "Quota is 0 (Inactive)"
    if not ignore_quota:
        prefix = check_date[:7]
        current = len([s for s in schedule_data
                       if s['employee'] == person_name and str(s['date']).startswith(prefix)])
        if current >= max_quota:
            return False, f"Quota Exceeded ({current}/{max_quota})"

    check_d_obj = datetime.strptime(check_date, '%Y-%m-%d').date()
    if not ignore_rest:
        for offset in [-2, -1, 1, 2]:
            nearby = str(check_d_obj + timedelta(days=offset))
            if any(s for s in schedule_data if str(s['date']) == nearby and s['employee'] == person_name):
                return False, "Rest Violation (Worked nearby)"
    if any(s for s in schedule_data if str(s['date']) == check_date and s['employee'] == person_name):
        return False, "Already working this day"
    return True, "Valid"


# ── employee swap search (הגדרות → חיפוש החלפות) ─────────────────────────────
def find_swap_candidates(ctx, schedule_df, requests_df, staff_df, user_name, swap_date, swap_dept,
                         sel_month=None, year=2026, today=None):
    user_n = str(user_name).strip()
    sched_minus_user = schedule_df[
        ~((schedule_df['date'].astype(str) == swap_date) &
          (schedule_df['employee'].astype(str).str.strip() == user_n) &
          (schedule_df['dept'] == swap_dept))].copy()

    def _safe_q(v):
        try:
            return int(v)
        except Exception:
            return 6

    active_staff = staff_df[(staff_df['name'].astype(str).str.strip() != user_n) &
                            (staff_df['type'].astype(str).str.strip() != 'מנהל/ת')].copy()
    active_staff = active_staff[active_staff['monthly_quota'].apply(_safe_q) > 0]

    req_dates = requests_df['date'].astype(str)
    req_emps = requests_df['employee'].astype(str).str.strip()
    wished_set = set(req_emps[(req_dates == swap_date) & (requests_df['status'] == 'בקשה')])
    month_prefix = swap_date[:7]
    today_str = (today or date.today()).strftime('%Y-%m-%d')
    full, partial = [], []

    for _, cand_row in active_staff.iterrows():
        cand = str(cand_row['name']).strip()
        ok, _ = check_assignment_validity(ctx, sched_minus_user, cand, swap_date, swap_dept,
                                          staff_df, requests_df, ignore_quota=True)
        if not ok:
            continue
        their = schedule_df[(schedule_df['employee'].astype(str).str.strip() == cand) &
                            (schedule_df['date'].astype(str).str.startswith(month_prefix)) &
                            (schedule_df['date'].astype(str) >= today_str)]
        mutual = None
        for _, ts in their.iterrows():
            ts_date, ts_dept = str(ts['date']), ts['dept']
            sim = sched_minus_user[~((sched_minus_user['date'].astype(str) == ts_date) &
                                     (sched_minus_user['employee'].astype(str).str.strip() == cand) &
                                     (sched_minus_user['dept'] == ts_dept))]
            sim = pd.concat([sim, pd.DataFrame([{'date': swap_date, 'dept': swap_dept, 'employee': cand,
                                                 'is_manual': False, 'empty_reason': ''}])], ignore_index=True)
            ok_me, _ = check_assignment_validity(ctx, sim, user_n, ts_date, ts_dept, staff_df, requests_df,
                                                 ignore_quota=True)
            if ok_me:
                mutual = {'date': ts_date, 'dept': ts_dept}
                break
        info = {'name': cand, 'dept': str(cand_row.get('dept', '')), 'type': str(cand_row.get('type', '')),
                'wished': cand in wished_set, 'their_shift': mutual}
        (full if mutual else partial).append(info)

    full.sort(key=lambda x: (not x['wished'], x['name']))
    partial.sort(key=lambda x: (not x['wished'], x['name']))

    chain = []
    if swap_dept == 'פנימית גריאטרית':
        facs = sched_minus_user[(sched_minus_user['date'].astype(str) == swap_date) &
                                (sched_minus_user['dept'] == 'שיקום') &
                                (sched_minus_user['employee'].astype(str).str.strip() != user_n)]
        externals = staff_df[(staff_df['type'].astype(str).str.strip() == 'תורן חוץ') &
                             (staff_df['name'].astype(str).str.strip() != user_n)].copy()
        for _, fr in facs.iterrows():
            fac = str(fr['employee']).strip()
            fs = staff_df[staff_df['name'].astype(str).str.strip() == fac]
            if fs.empty or str(fs.iloc[0].get('type', '')).strip() != 'מתמחה':
                continue
            ok_fac, _ = check_assignment_validity(ctx, sched_minus_user, fac, swap_date, 'פנימית גריאטרית',
                                                  staff_df, requests_df, ignore_quota=True)
            if not ok_fac:
                continue
            sim = sched_minus_user[~((sched_minus_user['date'].astype(str) == swap_date) &
                                     (sched_minus_user['employee'].astype(str).str.strip() == fac) &
                                     (sched_minus_user['dept'] == 'שיקום'))].copy()
            sim = pd.concat([sim, pd.DataFrame([{'date': swap_date, 'dept': 'פנימית גריאטרית', 'employee': fac,
                                                 'is_manual': False, 'empty_reason': ''}])], ignore_index=True)
            for _, er in externals.iterrows():
                ext = str(er['name']).strip()
                ok_ext, _ = check_assignment_validity(ctx, sim, ext, swap_date, 'שיקום', staff_df, requests_df,
                                                      ignore_quota=True)
                if ok_ext:
                    chain.append({'facilitator_name': fac, 'facilitator_dept': str(fs.iloc[0].get('dept', '')),
                                  'facilitator_wished': fac in wished_set, 'external_name': ext,
                                  'external_wished': ext in wished_set})
                    break
    chain.sort(key=lambda x: (not x['facilitator_wished'], not x['external_wished'], x['facilitator_name']))
    return {'full': full, 'partial': partial, 'chain': chain}


def upcoming_shifts(ctx, user_name, today=None) -> list:
    sched = ctx.schedule
    t = (today or date.today()).strftime('%Y-%m-%d')
    m = sched[(sched['employee'].astype(str).str.strip() == str(user_name).strip()) &
              (sched['date'].astype(str) >= t)].sort_values('date')
    return [{'date': str(r['date']), 'dept': r['dept']} for _, r in m.iterrows()]


def create_swap_request(ctx, user_name, swap_date, swap_dept, kind, candidate, their_shift=None, chain_ext=''):
    """Append a pending swap_requests row (6408-6490)."""
    row = {'requester': user_name, 'requester_date': swap_date, 'requester_dept': swap_dept,
           'candidate': candidate, 'swap_type': kind,
           'created_at': now_str('%Y-%m-%d %H:%M'), 'status': 'pending'}
    if kind == 'full':
        row.update(candidate_date=their_shift['date'], candidate_dept=their_shift['dept'])
    elif kind == 'partial':
        row.update(candidate_date='', candidate_dept='')
    elif kind == 'chain':
        row.update(candidate_date=swap_date, candidate_dept='פנימית גריאטרית',
                   chain_ext=chain_ext, chain_ext_dept='שיקום')
    else:
        raise ValueError(kind)
    # Keep appy's column order for each kind
    order = ['requester', 'requester_date', 'requester_dept', 'candidate', 'candidate_date', 'candidate_dept',
             'swap_type'] + (['chain_ext', 'chain_ext_dept'] if kind == 'chain' else []) + ['created_at', 'status']
    new = pd.DataFrame([{k: row[k] for k in order}])
    existing = ctx.swap_requests
    combined = new if existing.empty else pd.concat([existing, new], ignore_index=True)
    ctx.save("swap_requests", combined)
    ctx.swap_requests = combined
    return row


def pending_swap_requests(ctx) -> list:
    sr = ctx.swap_requests
    if sr.empty or 'status' not in sr.columns:
        return []
    p = sr[sr['status'].astype(str).str.strip() == 'pending']
    return [{'index': int(i), **{k: ('' if pd.isna(v) else str(v)) for k, v in r.items()}} for i, r in p.iterrows()]


def approve_swap_request(ctx, idx):
    """Apply a pending swap to the schedule (full / partial / chain), mark approved."""
    sr = ctx.swap_requests
    req = sr.loc[idx]
    r_date, r_dept = str(req.get('requester_date', '')), str(req.get('requester_dept', ''))
    candidate, c_date, c_dept = str(req.get('candidate', '')), str(req.get('candidate_date', '')), str(req.get('candidate_dept', ''))
    stype = str(req.get('swap_type', 'partial'))
    chain_ext = str(req.get('chain_ext', ''))
    requester = str(req.get('requester', ''))

    sched = ctx.schedule
    mask_req = (sched['date'].astype(str) == r_date) & (sched['dept'] == r_dept)
    if stype == 'chain':
        sched.loc[mask_req, 'employee'] = '---'
        sched.loc[mask_req, 'is_manual'] = True
        mask_fac = ((sched['date'].astype(str) == r_date) & (sched['dept'] == 'שיקום') &
                    (sched['employee'].astype(str).str.strip() == candidate))
        sched.loc[mask_fac, 'employee'] = '---'
        sched.loc[mask_fac, 'is_manual'] = True
        sched.loc[mask_req, 'employee'] = candidate
        mask_sha = ((sched['date'].astype(str) == r_date) & (sched['dept'] == 'שיקום') &
                    (sched['employee'].astype(str).str.strip().isin(['---', ''])))
        if mask_sha.any():
            sched.loc[mask_sha, 'employee'] = chain_ext
            sched.loc[mask_sha, 'is_manual'] = True
        else:
            sched = pd.concat([sched, pd.DataFrame([{'date': r_date, 'dept': 'שיקום', 'employee': chain_ext,
                                                     'is_manual': True, 'empty_reason': ''}])], ignore_index=True)
    else:
        sched.loc[mask_req, 'employee'] = candidate
        sched.loc[mask_req, 'is_manual'] = True
        if stype == 'full' and c_date:
            mask_c = (sched['date'].astype(str) == c_date) & (sched['dept'] == c_dept)
            sched.loc[mask_c, 'employee'] = requester
            sched.loc[mask_c, 'is_manual'] = True
    ctx.schedule = sched
    ctx.save("schedule", sched)
    sr.loc[idx, 'status'] = 'approved'
    ctx.save("swap_requests", sr)
    ctx.swap_requests = sr.copy()


def reject_swap_request(ctx, idx):
    sr = ctx.swap_requests
    sr.loc[idx, 'status'] = 'rejected'
    ctx.save("swap_requests", sr)
    ctx.swap_requests = sr.copy()


# ── admin manual tool + cleanup ──────────────────────────────────────────────
def is_blocked(ctx, employee, date_str) -> bool:
    r = ctx.requests
    return not r[(r['employee'] == employee) & (r['date'] == date_str) & (r['status'] == "אילוץ")].empty


def manual_assign(ctx, date_str, dept, employee):
    """Overwrite (date, dept) with a manual row; refuses blocked employees (6581-6607)."""
    if is_blocked(ctx, employee, date_str):
        raise ValueError(f"לא ניתן לשבץ את {employee} ב-{date_str}. יש לו אילוץ על יום זה.")
    s = ctx.schedule
    s = s[~((s['date'] == date_str) & (s['dept'] == dept))]
    s = pd.concat([s, pd.DataFrame([{'date': date_str, 'dept': dept, 'employee': employee,
                                     'is_manual': True, 'empty_reason': ''}])], ignore_index=True)
    ctx.schedule = s
    ctx.save("schedule", s)


def manual_unassign(ctx, date_str, dept):
    s = ctx.schedule
    s = s[~((s['date'] == str(date_str)) & (s['dept'] == dept))]
    ctx.schedule = s
    ctx.save("schedule", s)


def clear_month(ctx, year, month, only_auto=True):
    """🧹 delete auto rows (keep manual) or 💥 delete everything for the month."""
    s = ctx.schedule
    prefix = f"{year}-{month:02d}"
    if 'is_manual' not in s.columns:
        s['is_manual'] = False
    in_month = s['date'].astype(str).str.startswith(prefix)
    if only_auto:
        im = s['is_manual']
        manual = (im == True) | (im.astype(str).str.upper() == 'TRUE')  # noqa: E712
        to_delete = in_month & ~manual
    else:
        to_delete = in_month
    s = s[~to_delete]
    ctx.schedule = s
    ctx.save("schedule", s)


def unfilled_shifts(ctx) -> list:
    s = ctx.schedule
    if s.empty:
        return []
    f = s[s['employee'] == '---']
    return [{'date': str(r['date']), 'dept': r['dept'], 'empty_reason': str(r.get('empty_reason', ''))}
            for _, r in f.iterrows()]


def _emp_can_take_dept(ctx, emp_name, dept_name):
    sf = ctx.staff
    row = sf[sf['name'] == emp_name]
    if not row.empty and row['type'].iloc[0] == 'תורן חוץ' and 'פנימית' in dept_name:
        return False, f"שגיאה: לא ניתן לשבץ את {emp_name} (תורן חוץ) לפנימית גריאטרית!"
    return True, ""


def apply_suggestion(ctx, row_date, row_dept, sugg):
    """Execute a scheduler swap suggestion for an unfilled slot (6679-6749)."""
    if sugg['type'] == 'direct_swap':
        checks = [(sugg['conflicted_emp'], row_dept), (sugg['replacement_emp'], sugg['source_dept'])]
    elif sugg['type'] == 'move_shift':
        checks = [(sugg['conflicted_emp'], row_dept), (sugg['replacement_emp'], sugg['conflict_dept'])]
    else:
        checks = []
    for e, d in checks:
        ok, msg = _emp_can_take_dept(ctx, e, d)
        if not ok:
            raise ValueError(msg)
    s = ctx.schedule
    if sugg['type'] == 'direct_swap':
        s.loc[(s['date'] == sugg['target_date']) & (s['dept'] == sugg['source_dept']), 'employee'] = sugg['replacement_emp']
        here = (s['date'] == sugg['target_date']) & (s['dept'] == row_dept)
        s.loc[here, 'employee'] = sugg['conflicted_emp']
        s.loc[here, 'empty_reason'] = ''
    elif sugg['type'] == 'move_shift':
        s.loc[(s['date'] == sugg['conflict_date']) & (s['dept'] == sugg['conflict_dept']), 'employee'] = sugg['replacement_emp']
        here = (s['date'] == row_date) & (s['dept'] == row_dept)
        s.loc[here, 'employee'] = sugg['conflicted_emp']
        s.loc[here, 'empty_reason'] = ''
    elif sugg['type'] == 'triple_swap':
        s.loc[(s['date'] == sugg['target_date']) & (s['dept'] == sugg['dept_b_origin']), 'employee'] = sugg['emp_c']
        s.loc[(s['date'] == sugg['target_date']) & (s['dept'] == sugg['dept_a_origin']), 'employee'] = sugg['emp_b']
        here = (s['date'] == sugg['target_date']) & (s['dept'] == row_dept)
        s.loc[here, 'employee'] = sugg['emp_a']
        s.loc[here, 'empty_reason'] = ''
    ctx.schedule = s
    ctx.save("schedule", s)


# ── admin swap finder (draw_calendar_view → 🔍 מצא החלפות אפשריות) ─────────
def _is_morning(dept):
    return 'שישי בוקר' in dept or 'שיקום (1)' in dept or 'שיקום (2)' in dept


def _advanced_ok(date1, dept1, date2, dept2):
    if _is_morning(dept1) != _is_morning(dept2):
        return False
    d1 = datetime.strptime(date1, '%Y-%m-%d')
    d2 = datetime.strptime(date2, '%Y-%m-%d')
    return (d1.weekday() in [4, 5]) == (d2.weekday() in [4, 5])


def _consecutive_violation(emp, new_date, schedule_data):
    d_obj = datetime.strptime(new_date, '%Y-%m-%d').date()
    for off in [-1, 1]:
        cs = str(d_obj + timedelta(days=off))
        if any(s for s in schedule_data if s['date'] == cs and s['employee'] == emp):
            return True
    return False


def admin_swap_options(ctx, t_date_str, target_dept):
    """direct / exchange / mutual_cross / circular options for one slot (5507-5818)."""
    sche_df = ctx.schedule
    cur = sche_df[(sche_df['date'] == t_date_str) &
                  (sche_df['dept'].astype(str).str.strip() == target_dept.strip())]
    current_emp = cur.iloc[0]['employee'] if not cur.empty else "---"
    staff_df, requests_df = ctx.staff, ctx.requests
    prefix = t_date_str[:7]
    recs = [s for s in sche_df.to_dict('records') if str(s['date']).startswith(prefix)]

    def valid(p, d, k):
        return check_assignment_validity(ctx, recs, p, d, k, staff_df, requests_df,
                                         ignore_quota=True, ignore_home_restrict=True, ignore_rest=True)

    direct, exchange, fail = [], [], {}
    ignorable = ["Quota Exceeded", "Restricted to Home Dept", "Rest Violation", "Already working"]
    for _, person in staff_df.iterrows():
        p = person['name']
        if str(p).upper() == 'ADMIN' or p == '---' or p == current_emp:
            continue
        ok, reason = valid(p, t_date_str, target_dept)
        if ok:
            direct.append(p)
            continue
        fail[reason] = fail.get(reason, 0) + 1
        if any(i in reason for i in ignorable):
            other = next((s for s in recs if str(s['date']) == t_date_str and s['employee'] == p), None)
            if other:
                other_dept = other['dept']
                ok2, reason2 = valid(p, t_date_str, target_dept)
                if (ok2 or reason2 == "Already working this day") and current_emp != "---":
                    ok_a, reason_a = valid(current_emp, t_date_str, other_dept)
                    if (ok_a or reason_a == "Already working this day") and _is_morning(target_dept) == _is_morning(other_dept):
                        exchange.append({'name': p, 'dept': other_dept})

    mutual = []
    if current_emp != "---":
        for s in recs:
            if s['date'] == t_date_str:
                continue
            other = s['employee']
            if other in ("---", 'ADMIN') or other == current_emp:
                continue
            if not valid(other, t_date_str, target_dept)[0]:
                continue
            if not valid(current_emp, s['date'], s['dept'])[0]:
                continue
            if not _advanced_ok(t_date_str, target_dept, s['date'], s['dept']):
                continue
            if _consecutive_violation(current_emp, s['date'], recs) or _consecutive_violation(other, t_date_str, recs):
                continue
            mutual.append({'b_name': other, 'b_date': s['date'], 'b_dept': s['dept']})

    circular = []
    dests_a = []
    if current_emp != "---":
        for s in recs:
            if s['date'] == t_date_str:
                continue
            b = s['employee']
            if b in ("---", 'ADMIN') or b == current_emp:
                continue
            if valid(current_emp, s['date'], s['dept'])[0]:
                dests_a.append(s)
    repl_a = []
    for _, person in staff_df.iterrows():
        c = person['name']
        if c in (current_emp, 'ADMIN', '---'):
            continue
        if any(s['date'] == t_date_str and s['employee'] == c for s in recs):
            continue
        if valid(c, t_date_str, target_dept)[0]:
            repl_a.append(c)
    for b_rec in dests_a[:50]:
        b, date_2, dept_2 = b_rec['employee'], b_rec['date'], b_rec['dept']
        for c in repl_a:
            if c == b:
                continue
            for c_rec in [s for s in recs if s['employee'] == c and s['date'] != t_date_str and s['date'] != date_2]:
                date_3, dept_3 = c_rec['date'], c_rec['dept']
                if not valid(b, date_3, dept_3)[0]:
                    continue
                if not _advanced_ok(t_date_str, target_dept, date_2, dept_2):
                    continue
                if _consecutive_violation(current_emp, date_2, recs):
                    continue
                if not _advanced_ok(date_2, dept_2, date_3, dept_3):
                    continue
                if _consecutive_violation(b, date_3, recs):
                    continue
                if not _advanced_ok(date_3, dept_3, t_date_str, target_dept):
                    continue
                if _consecutive_violation(c, t_date_str, recs):
                    continue
                circular.append({'b_name': b, 'b_date': date_2, 'b_dept': dept_2,
                                 'c_name': c, 'c_date': date_3, 'c_dept': dept_3})
                if len(circular) > 10:
                    break
            if len(circular) > 10:
                break
        if len(circular) > 10:
            break
    return {'current': current_emp, 'direct': direct, 'exchange': exchange, 'mutual_cross': mutual,
            'circular': circular, 'fail_reasons': fail, 'date': t_date_str, 'dept': target_dept}


def execute_direct(ctx, t_date, dept, replacement):
    s = ctx.schedule
    s = s[~((s['date'] == t_date) & (s['dept'] == dept))]
    s = pd.concat([s, pd.DataFrame([{'date': t_date, 'dept': dept, 'employee': replacement,
                                     'is_manual': True, 'empty_reason': ''}])], ignore_index=True)
    ctx.schedule = s
    ctx.save("schedule", s)


def execute_exchange(ctx, t_date, dept, current_emp, b, b_dept):
    s = ctx.schedule
    ma = (s['date'] == t_date) & (s['dept'] == dept)
    mb = (s['date'] == t_date) & (s['dept'] == b_dept)
    s.loc[ma, 'employee'] = b
    s.loc[mb, 'employee'] = current_emp
    s.loc[ma | mb, 'is_manual'] = True
    ctx.save("schedule", s)


def execute_mutual_cross(ctx, t_date, dept, current_emp, b_name, b_date, b_dept):
    s = ctx.schedule
    ma = (s['date'] == t_date) & (s['dept'] == dept)
    mb = (s['date'] == b_date) & (s['dept'] == b_dept)
    s.loc[ma, 'employee'] = b_name
    s.loc[ma, 'is_manual'] = True
    s.loc[mb, 'employee'] = current_emp
    s.loc[mb, 'is_manual'] = True
    ctx.save("schedule", s)


def execute_circular(ctx, t_date, dept, current_emp, item):
    s = ctx.schedule
    m1 = (s['date'] == t_date) & (s['dept'] == dept)
    m2 = (s['date'] == item['b_date']) & (s['dept'] == item['b_dept'])
    m3 = (s['date'] == item['c_date']) & (s['dept'] == item['c_dept'])
    s.loc[m1, 'employee'] = item['c_name']
    s.loc[m1, 'is_manual'] = True
    s.loc[m2, 'employee'] = current_emp
    s.loc[m2, 'is_manual'] = True
    s.loc[m3, 'employee'] = item['b_name']
    s.loc[m3, 'is_manual'] = True
    ctx.save("schedule", s)


# ── admin availability gate (draw_calendar_view head) ─────────────────────────
def admin_availability(ctx, year, month):
    """(show, {date: available}, {date: wished}) — shown only once every active employee submitted."""
    prefix = f"{year}-{month:02d}"
    active = ctx.staff[ctx.staff['type'].isin(['מתמחה', 'תורן חוץ']) &
                       ~ctx.staff['name'].isin(['---', 'ADMIN'])]
    reqs = ctx.requests[ctx.requests['date'].astype(str).str.startswith(prefix)] \
        if not ctx.requests.empty else pd.DataFrame()
    submitted = set(reqs['employee'].astype(str).str.strip().unique()) if not reqs.empty else set()
    all_active = set(active['name'].dropna().astype(str).str.strip().tolist())
    show = bool(all_active) and all_active.issubset(submitted)
    avail, wished = {}, {}
    if show:
        blocked, wish = {}, {}
        for _, r in reqs.iterrows():
            emp, d = str(r['employee']).strip(), str(r['date'])[:10]
            if r['status'] == 'אילוץ':
                blocked.setdefault(emp, set()).add(d)
            elif r['status'] == 'בקשה':
                wish.setdefault(emp, set()).add(d)
        recs = ctx.schedule.to_dict('records') if not ctx.schedule.empty else []
        for day in range(1, calendar.monthrange(year, month)[1] + 1):
            ds = f"{year}-{month:02d}-{day:02d}"
            assigned = {s['employee'] for s in recs if str(s['date']) == ds and s['employee'] != '---'}
            w, a = [], []
            for _, e in active.iterrows():
                n = str(e['name']).strip()
                if ds in blocked.get(n, set()) or n in assigned:
                    continue
                (w if ds in wish.get(n, set()) else a).append(n)
            wished[ds] = w
            avail[ds] = a
    return show, avail, wished


def month_schedule(ctx, year, month) -> list:
    s = ctx.schedule
    if s.empty:
        return []
    m = s[s['date'].astype(str).str.startswith(f"{year}-{month:02d}")]
    return [{k: ('' if pd.isna(v) else v) for k, v in r.items()} for r in m.to_dict('records')]


def night_calendar(ctx, year, month, viewer, is_admin) -> dict:
    """Night calendar read model (draw_calendar_view). Non-admins see only their own
    rows and unfilled ('---') slots; admins also get empty reasons, every
    employee's blocks/wishes per day and, once everyone submitted, availability."""
    prefix = f"{year}-{month:02d}"
    s = ctx.schedule
    m = s[s['date'].astype(str).str.startswith(prefix)] if not s.empty else s
    me = str(viewer).strip()
    days = {}
    for _, r in m.iterrows():
        emp = str(r['employee']).strip()
        if not is_admin and emp != me and r['employee'] != '---':
            continue
        days.setdefault(str(r['date']), []).append({
            'dept': r['dept'], 'employee': r['employee'],
            'is_manual': str(r.get('is_manual', '')).strip().lower() == 'true',
            'empty_reason': (str(r.get('empty_reason', '') or '') if is_admin and r['employee'] == '---' else '')})
    out = {'year': year, 'month': month, 'slots': days,
           'special_days': [{'date': str(r['date']), 'description': r['description'], 'day_type': r.get('day_type', '')}
                            for _, r in ctx.special_days.iterrows() if str(r['date']).startswith(prefix)]}
    if is_admin:
        reqs = ctx.requests[ctx.requests['date'].astype(str).str.startswith(prefix)] if not ctx.requests.empty else ctx.requests
        out['requests'] = {}
        for _, r in reqs.iterrows():
            out['requests'].setdefault(str(r['date']), []).append({'employee': r['employee'], 'status': r['status']})
        show, avail, wished = admin_availability(ctx, year, month)
        out['availability'] = {'shown': show, 'available': avail, 'wished': wished}
    return out
