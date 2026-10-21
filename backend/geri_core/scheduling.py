"""Night-shift auto-scheduling: greedy (appy.py:3978) and CP-SAT (appy.py:4502).

Both are faithful ports. Instead of st.info/st.warning they return a
`SchedulingResult`; instead of writing session state they set
`ctx.schedule` and save once (when `save=True`).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

import pandas as pd

from .days import get_functional_day_type, is_functional_weekend
from .night import check_assignment_validity
from .normalize import safe_int
from .people import emp_night_dept


@dataclass
class SchedulingResult:
    schedule: pd.DataFrame
    messages: list = field(default_factory=list)      # [(level, text)] level ∈ info|warning
    swap_suggestions: dict = field(default_factory=dict)
    method: str = 'greedy'
    filled: int = 0
    total: int = 0
    fallback: int = 0
    saved: bool = False


def _initial_state(ctx, staff_df, year, month):
    all_current = ctx.schedule.to_dict('records')
    prefix = f"{year}-{month:02d}"
    new_schedule = []
    for r in all_current:
        if not str(r['date']).startswith(prefix):
            new_schedule.append(r)
        elif r['employee'] != '---':
            new_schedule.append(r)
    work_load = {row['name']: 0 for _, row in staff_df.iterrows()}
    weekends_worked = {row['name']: set() for _, row in staff_df.iterrows()}
    last_assignment = {row['name']: -999 for _, row in staff_df.iterrows()}
    wed_counts = {row['name']: 0 for _, row in staff_df.iterrows()}
    thu_counts = {row['name']: 0 for _, row in staff_df.iterrows()}
    for s in new_schedule:
        if s['employee'] not in work_load or s['employee'] == '---':
            continue
        dt = datetime.strptime(s['date'], '%Y-%m-%d')
        if dt.weekday() == 2:
            wed_counts[s['employee']] += 1
        if dt.weekday() == 3:
            thu_counts[s['employee']] += 1
        if dt.toordinal() > last_assignment[s['employee']]:
            last_assignment[s['employee']] = dt.toordinal()
        if str(s['date']).startswith(prefix):
            work_load[s['employee']] += 1
            if is_functional_weekend(dt, ctx.special_days) and "שישי בוקר" not in s.get('dept', ''):
                weekends_worked[s['employee']].add(dt.isocalendar()[1])
    avg_wed = sum(wed_counts.values()) / len(wed_counts) if wed_counts else 0
    avg_thu = sum(thu_counts.values()) / len(thu_counts) if thu_counts else 0
    pw = [k for k, v in wed_counts.items() if v < avg_wed]
    pt = [k for k, v in thu_counts.items() if v < avg_thu]
    msg = (f"**דוח איזון הוגנות (רב-חודשי):**\n"
           f"- **רביעי:** ממוצע {avg_wed:.1f}. תועדפו: {len(pw)} עובדים.\n"
           f"- **חמישי:** ממוצע {avg_thu:.1f}. תועדפו: {len(pt)} עובדים.\n"
           f"- **שישי בוקר:** האיזון מבוצע אוטומטית על סמך כל ההיסטוריה.")
    return new_schedule, work_load, weekends_worked, last_assignment, wed_counts, thu_counts, msg


def _friday_post_pass(ctx, staff_df, new_schedule, work_load, all_dates):
    """Derive the 4 שישי בוקר slots per functional Friday (identical in both schedulers)."""
    req = ctx.requests
    fridays = [d for d in all_dates if d.weekday() == 4 or
               get_functional_day_type(d, ctx.special_days) == 'כמו שישי (ערב חג)']
    for fri_date in fridays:
        fri_str = str(fri_date)
        sat_str = str(fri_date + timedelta(days=1))
        fp = next((s['employee'] for s in new_schedule if s['date'] == fri_str and s['dept'] == 'פנימית גריאטרית'), None)
        sp = next((s['employee'] for s in new_schedule if s['date'] == sat_str and s['dept'] == 'פנימית גריאטרית'), None)
        has1 = any(s for s in new_schedule if s['date'] == fri_str and s['dept'] == 'שישי בוקר - פנימית (1)')
        has2 = any(s for s in new_schedule if s['date'] == fri_str and s['dept'] == 'שישי בוקר - פנימית (2)')
        if not has1 and fp and fp != '---':
            new_schedule.append({'date': fri_str, 'dept': 'שישי בוקר - פנימית (1)', 'employee': fp,
                                 'is_manual': False, 'empty_reason': 'נגזר אוטומטית משישי'})
        if not has2 and sp and sp != '---':
            new_schedule.append({'date': fri_str, 'dept': 'שישי בוקר - פנימית (2)', 'employee': sp,
                                 'is_manual': False, 'empty_reason': 'נגזר אוטומטית משבת'})
        fr = next((s['employee'] for s in new_schedule if s['date'] == fri_str and s['dept'] == 'שיקום'), None)
        sr = next((s['employee'] for s in new_schedule if s['date'] == sat_str and s['dept'] == 'שיקום'), None)

        def handle(worker_name, source_day, slot_num):
            target = f'שישי בוקר - שיקום ({slot_num})'
            if any(s for s in new_schedule if s['date'] == fri_str and s['dept'] == target):
                return
            if not worker_name or worker_name == '---':
                return
            w_type = None
            if worker_name in staff_df['name'].values:
                w_type = staff_df[staff_df['name'] == worker_name]['type'].iloc[0]
            if w_type == 'מתמחה':
                new_schedule.append({'date': fri_str, 'dept': target, 'employee': worker_name,
                                     'is_manual': False, 'empty_reason': f'נגזר אוטומטית מ{source_day}'})
                return
            cands = []
            ym = fri_str[:7]
            for _, row in staff_df.iterrows():
                if row['type'] != 'מתמחה' or row['name'] == worker_name:
                    continue
                if (emp_night_dept(ctx, row['name'], ym) or str(row.get('dept', '') or '')) != 'שיקום':
                    continue
                emp = row['name']
                if not req[(req['employee'] == emp) & (req['date'] == fri_str) & (req['status'] == "אילוץ")].empty:
                    continue
                if any(s['employee'] == emp and s['date'] == str(fri_date + timedelta(days=o))
                       for s in new_schedule for o in [-2, -1, 1, 2]):
                    continue
                if any(s['employee'] == emp and s['date'] == fri_str for s in new_schedule):
                    continue
                if work_load.get(emp, 0) >= safe_int(row['monthly_quota'], 0):
                    continue
                cnt = len([s for s in new_schedule if s['employee'] == emp and 'שישי בוקר' in s['dept']])
                cands.append((emp, cnt))
            if cands:
                cands.sort(key=lambda z: z[1])
                best = cands[0][0]
                new_schedule.append({'date': fri_str, 'dept': target, 'employee': best,
                                     'is_manual': False, 'empty_reason': f'השלמה במקום {worker_name}'})
                work_load[best] = work_load.get(best, 0) + 1
            else:
                new_schedule.append({'date': fri_str, 'dept': target, 'employee': '---',
                                     'is_manual': False, 'empty_reason': 'לא נמצא מחליף לבוקר'})

        handle(fr, "שישי", "1")
        handle(sr, "שבת", "2")


def _finalize(ctx, new_schedule, save):
    final_df = pd.DataFrame(new_schedule)
    if not final_df.empty:
        final_df = final_df.drop_duplicates(subset=['date', 'dept'], keep='first')
    ctx.schedule = final_df
    if save:
        ctx.save("schedule", final_df)
    return final_df


# ── greedy ────────────────────────────────────────────────────────────────────
def run_smart_scheduling(ctx, year, month, only_weekends=False, save=True) -> SchedulingResult:
    num_days = calendar.monthrange(year, month)[1]
    staff_df = ctx.staff.copy()
    reqs = ctx.requests
    sd_df = ctx.special_days
    (new_schedule, work_load, weekends_worked, last_assignment,
     wed_counts, thu_counts, balancing_msg) = _initial_state(ctx, staff_df, year, month)
    swap_suggestions = {}

    all_dates = [date(year, month, d) for d in range(1, num_days + 1)]
    if only_weekends:
        sorted_dates = [d for d in all_dates if is_functional_weekend(d, sd_df)]
    else:
        sorted_dates = ([d for d in all_dates if is_functional_weekend(d, sd_df)] +
                        [d for d in all_dates if not is_functional_weekend(d, sd_df)])

    for d in sorted_dates:
        d_str = str(d)
        week_num = d.isocalendar()[1]
        for dept in ["פנימית גריאטרית", "שיקום"]:
            if any(s for s in new_schedule if s['date'] == d_str and s['dept'] == dept):
                continue
            candidates, failure_reasons = [], []
            for _, person in staff_df.iterrows():
                name = person['name']
                if person['type'] == 'תורן חוץ' and dept == 'פנימית גריאטרית':
                    continue
                if any(s for s in new_schedule if s['date'] == d_str and s['employee'] == name):
                    continue
                if person.get('only_home_dept', False):
                    target_context = dept
                    if "שישי בוקר" in dept:
                        target_context = "שיקום" if "שיקום" in dept else "פנימית גריאטרית"
                    home = emp_night_dept(ctx, name, f"{year}-{month:02d}") or str(person.get('dept', '') or '')
                    if home != 'כללי' and home != target_context:
                        continue
                monthly_quota = safe_int(person['monthly_quota'], 0)
                if work_load[name] >= monthly_quota:
                    failure_reasons.append(f"{name}: מכסה מלאה ({monthly_quota})")
                    continue
                if d.day < 15 and monthly_quota > 0 and work_load[name] >= monthly_quota * 0.5:
                    failure_reasons.append(f"{name}: שמירת מכסה (חצי ראשון)")
                    continue
                weekend_quota = safe_int(person['weekend_quota'], 0)
                if (is_functional_weekend(d, sd_df) and len(weekends_worked[name]) >= weekend_quota
                        and week_num not in weekends_worked[name]):
                    failure_reasons.append(f"{name}: מכסת סופ\"ש")
                    continue
                if any(any(s for s in new_schedule if s['date'] == str(d + timedelta(days=o)) and s['employee'] == name)
                       for o in [-2, -1, 1, 2]):
                    failure_reasons.append(f"{name}: מרווח מנוחה")
                    continue
                if person['type'] == 'מתמחה':
                    if d.weekday() == 5 and any(s for s in new_schedule if s['date'] == str(d - timedelta(days=3)) and s['employee'] == name):
                        failure_reasons.append(f"{name}: שובץ ברביעי")
                        continue
                    if d.weekday() == 2:
                        if any(s for s in new_schedule if s['date'] == str(d + timedelta(days=3)) and s['employee'] == name):
                            failure_reasons.append(f"{name}: משובץ בשבת")
                            continue
                        if any(s for s in new_schedule if s['date'] == str(d + timedelta(days=2)) and s['employee'] == name):
                            failure_reasons.append(f"{name}: משובץ בשישי הקרוב")
                            continue
                if not reqs[(reqs['employee'] == name) & (reqs['date'] == d_str) & (reqs['status'] == "אילוץ")].empty:
                    failure_reasons.append(f"{name}: אילוץ")
                    continue
                candidates.append(person)

            if candidates:
                requesters = reqs[(reqs['date'] == d_str) & (reqs['status'] == "בקשה")]['employee'].tolist()
                wish = [c for c in candidates if c['name'] in requesters]
                pool = wish if wish else candidates

                def score(cand):
                    name = cand['name']
                    quota = safe_int(cand['monthly_quota'], 1)
                    usage = work_load[name] / quota if quota > 0 else 1.0
                    sc = -usage * 100
                    sc += (d.toordinal() - last_assignment.get(name, -999)) * 2
                    sc += (quota * (d.day / num_days) - work_load[name]) * 500
                    if dept == "שיקום" and cand['type'] == 'תורן חוץ':
                        if d.weekday() in [3, 4, 5] or is_functional_weekend(d, sd_df):
                            sc += 2000
                    if cand['type'] == 'מתמחה':
                        if d.weekday() == 2:
                            sc -= wed_counts[name] * 200
                        if d.weekday() == 3:
                            sc -= thu_counts[name] * 200
                    cd = emp_night_dept(ctx, name, d.strftime('%Y-%m')) or str(cand.get('dept', '') or '')
                    sc += 500 if (cd == dept or cd == 'כללי') else -5000
                    return sc

                choice = max(pool, key=score)['name']
                new_schedule.append({'date': d_str, 'dept': dept, 'employee': choice, 'is_manual': False, 'empty_reason': ''})
                work_load[choice] += 1
                last_assignment[choice] = d.toordinal()
                if d.weekday() == 2:
                    wed_counts[choice] += 1
                if d.weekday() == 3:
                    thu_counts[choice] += 1
                if is_functional_weekend(d, sd_df):
                    weekends_worked[choice].add(week_num)
                continue

            # starvation fallback
            fallback_pool = []
            for _, cand in staff_df.iterrows():
                c = cand['name']
                if c == '---' or str(c).upper() == 'ADMIN':
                    continue
                if cand['type'] == 'תורן חוץ' and dept == 'פנימית גריאטרית':
                    continue
                if any(s for s in new_schedule if s['date'] == d_str and s['employee'] == c):
                    continue
                if not reqs[(reqs['employee'] == c) & (reqs['date'] == d_str) & (reqs['status'] == 'אילוץ')].empty:
                    continue
                if work_load.get(c, 0) >= safe_int(cand['monthly_quota'], 0):
                    continue
                wq = safe_int(cand['weekend_quota'], 0)
                if (is_functional_weekend(d, sd_df) and len(weekends_worked.get(c, set())) >= wq
                        and week_num not in weekends_worked.get(c, set())):
                    continue
                fallback_pool.append(c)
            if fallback_pool:
                fc = min(fallback_pool, key=lambda x: work_load.get(x, 0))
                new_schedule.append({'date': d_str, 'dept': dept, 'employee': fc, 'is_manual': False,
                                     'empty_reason': 'הושלם מחוסר ברירה (הגמשת חוקים)'})
                work_load[fc] += 1
                last_assignment[fc] = d.toordinal()
                if d.weekday() == 2:
                    wed_counts[fc] += 1
                if d.weekday() == 3:
                    thu_counts[fc] += 1
                if is_functional_weekend(d, sd_df):
                    weekends_worked[fc].add(week_num)
                continue

            suggestions = _suggest_for_empty(ctx, staff_df, new_schedule, d, d_str, dept, swap_suggestions)
            if suggestions:
                final_msg = "לא נמצא שיבוץ מתאים עבור אף עובד.\n" + "\n".join(suggestions[:3])
            else:
                final_msg = "לא נמצא פתרון אוטומטי (סיבות לדוגמה: " + ", ".join(list(set(failure_reasons))[:3]) + ")"
            new_schedule.append({'date': d_str, 'dept': dept, 'employee': '---', 'is_manual': False,
                                 'empty_reason': final_msg})

    _friday_post_pass(ctx, staff_df, new_schedule, work_load, all_dates)
    final_df = _finalize(ctx, new_schedule, save)
    return SchedulingResult(schedule=final_df, messages=[('info', balancing_msg)],
                            swap_suggestions=swap_suggestions, method='greedy', saved=save)


def _suggest_for_empty(ctx, staff_df, new_schedule, d, d_str, dept, store):
    """Swap / move / triple suggestions for a slot nobody could fill (4278-4392)."""
    suggestions = []
    reqs = ctx.requests

    def ok(p, cd, td):
        return check_assignment_validity(ctx, new_schedule, p, cd, td, staff_df, reqs)[0]

    key = f"{d_str}_{dept}"
    for _, pa in staff_df.iterrows():
        a = pa['name']
        parallel = next((s for s in new_schedule if s['date'] == d_str and s['employee'] == a), None)
        if parallel:
            od = parallel['dept']
            for _, pb in staff_df.iterrows():
                b = pb['name']
                if b == a:
                    continue
                if ok(b, d_str, od):
                    suggestions.append(f"💡 החלפה: העבר את **{a}** מ-{od} לפה, ושבץ את **{b}** שם.")
                    store.setdefault(key, []).append({'type': 'direct_swap', 'target_date': d_str,
                                                      'conflicted_emp': a, 'source_dept': od,
                                                      'replacement_emp': b, 'desc': f"{a} ⬅️ {b} ({od})"})
                    break
        prev = next((s for s in new_schedule if s['employee'] == a and
                     s['date'] in [str(d - timedelta(days=i)) for i in [1, 2]]), None)
        if prev:
            cdate, cdept = prev['date'], prev['dept']
            for _, pb in staff_df.iterrows():
                b = pb['name']
                if b == a:
                    continue
                if ok(b, cdate, cdept):
                    fmt = datetime.strptime(cdate, '%Y-%m-%d').strftime('%d/%m/%Y')
                    suggestions.append(f"💡 הסטה: העבר את **{a}** מה-{fmt} לפה, ושבץ שם את **{b}**.")
                    store.setdefault(key, []).append({'type': 'move_shift', 'conflict_date': cdate,
                                                      'conflicted_emp': a, 'conflict_dept': cdept,
                                                      'replacement_emp': b, 'desc': f"הסטה: {a} (מ-{fmt}) ⬅️ {b}"})
                    break
        if parallel:
            od = parallel['dept']
            for _, pb in staff_df.iterrows():
                b = pb['name']
                if b == a:
                    continue
                pb_shift = next((s for s in new_schedule if s['date'] == d_str and s['employee'] == b), None)
                if pb_shift:
                    odb = pb_shift['dept']
                    for _, pc in staff_df.iterrows():
                        c = pc['name']
                        if c in [a, b]:
                            continue
                        if ok(c, d_str, odb):
                            suggestions.append(f"💡 שרשור: {a} לפה, {b} ל-{od}, {c} ל-{odb}.")
                            store.setdefault(key, []).append({'type': 'triple_swap', 'target_date': d_str,
                                                              'emp_a': a, 'dept_a_origin': od,
                                                              'emp_b': b, 'dept_b_origin': odb, 'emp_c': c,
                                                              'desc': f"שרשור: {a} ⬅️ {b} ⬅️ {c}"})
                            break
                    if len(suggestions) > 3:
                        break
    return suggestions


# ── CP-SAT ────────────────────────────────────────────────────────────────────
def run_smart_scheduling_cp(ctx, year, month, only_weekends=False, save=True,
                            time_limit=28.0, fallback_time_limit=10.0, num_workers=4) -> SchedulingResult:
    try:
        from ortools.sat.python import cp_model as cp
    except ImportError:
        r = run_smart_scheduling(ctx, year, month, only_weekends, save=save)
        r.messages.insert(0, ('warning', "⚠️ ortools לא מותקן — משתמש בשיבוץ חמדני"))
        return r

    num_days = calendar.monthrange(year, month)[1]
    staff_df = ctx.staff.copy()
    sd_df = ctx.special_days
    (new_schedule, work_load, weekends_worked, last_assignment,
     wed_counts, thu_counts, balancing_msg) = _initial_state(ctx, staff_df, year, month)
    all_dates = [date(year, month, d) for d in range(1, num_days + 1)]
    DEPTS = ["פנימית גריאטרית", "שיקום"]
    covered = {(str(s['date']), s['dept']) for s in new_schedule if s['employee'] not in ('---', '')}

    employees = []
    for _, row in staff_df.iterrows():
        name = str(row.get('name', '')).strip()
        if not name or name == '---' or name.upper() == 'ADMIN':
            continue
        if str(row.get('type', '')).strip() in ('מנהל/ת', 'מנהל מחלקה'):
            continue
        if safe_int(row.get('monthly_quota', 0), 0) == 0:
            continue
        employees.append(name)
    emp_row = {}
    for e in employees:
        rows = staff_df[staff_df['name'] == e]
        if not rows.empty:
            emp_row[e] = rows.iloc[0]
    emp_type = {e: str(emp_row[e].get('type', '')).strip() for e in employees if e in emp_row}
    emp_quota = {e: safe_int(emp_row[e].get('monthly_quota', 6), 6) for e in employees if e in emp_row}
    emp_wq = {e: safe_int(emp_row[e].get('weekend_quota', 0), 0) for e in employees if e in emp_row}
    emp_only_home = {}
    for e in employees:
        if e in emp_row:
            oh = emp_row[e].get('only_home_dept', False)
            emp_only_home[e] = oh if isinstance(oh, bool) else str(oh).strip().lower() == 'true'
    emp_home = {e: (emp_night_dept(ctx, e, f"{year}-{month:02d}") or str(emp_row[e].get('dept', '') or ''))
                for e in employees if e in emp_row}
    employees = [e for e in employees if e in emp_row]

    blocked, wishes = set(), set()
    for _, r in ctx.requests.iterrows():
        k = (str(r['employee']).strip(), str(r['date']))
        if str(r['status']) == 'אילוץ':
            blocked.add(k)
        elif str(r['status']) == 'בקשה':
            wishes.add(k)

    target_dates = [d for d in all_dates if is_functional_weekend(d, sd_df)] if only_weekends else all_dates
    slots = [(d, k) for d in target_dates for k in DEPTS if (str(d), k) not in covered]
    if not slots:
        return SchedulingResult(schedule=ctx.schedule, messages=[('info', f"✅ כל המשמרות כבר שובצו.\n\n{balancing_msg}")],
                                method='cp-noop')

    model = cp.CpModel()
    x = {}
    for e in employees:
        for d, k in slots:
            if (e, str(d)) in blocked:
                continue
            if k == "פנימית גריאטרית" and emp_type.get(e) == 'תורן חוץ':
                continue
            if emp_only_home.get(e) and emp_home.get(e, '') not in ('כללי', k):
                continue
            x[(e, d, k)] = model.new_bool_var(f"x|{e}|{d}|{k}")

    for d, k in slots:
        v = [x[(e, d, k)] for e in employees if (e, d, k) in x]
        if v:
            model.add(sum(v) <= 1)
    for e in employees:
        rem = emp_quota.get(e, 6) - work_load.get(e, 0)
        v = [x[(e, d, k)] for d, k in slots if (e, d, k) in x]
        if v:
            if rem <= 0:
                for vv in v:
                    model.add(vv == 0)
            else:
                model.add(sum(v) <= rem)
    for e in employees:
        for d in target_dates:
            v = [x[(e, d, k)] for k in DEPTS if (e, d, k) in x]
            if len(v) > 1:
                model.add(sum(v) <= 1)
    day_list = sorted(set(d for d, k in slots))
    for e in employees:
        lo = last_assignment.get(e, -999)
        for i, d1 in enumerate(day_list):
            v1 = [x[(e, d1, k)] for k in DEPTS if (e, d1, k) in x]
            if not v1:
                continue
            if lo != -999 and (d1.toordinal() - lo) <= 2:
                for vv in v1:
                    model.add(vv == 0)
            for off in [1, 2]:
                if i + off >= len(day_list):
                    break
                v2 = [x[(e, day_list[i + off], k)] for k in DEPTS if (e, day_list[i + off], k) in x]
                if v2:
                    model.add(sum(v1) + sum(v2) <= 1)
    dset = set(target_dates)
    for e in [e for e in employees if emp_type.get(e) == 'מתמחה']:
        for d in target_dates:
            vd = [x[(e, d, k)] for k in DEPTS if (e, d, k) in x]
            if not vd:
                continue
            if d.weekday() == 2:
                for gap in [2, 3]:
                    d2 = d + timedelta(days=gap)
                    if d2 in dset:
                        v2 = [x[(e, d2, k)] for k in DEPTS if (e, d2, k) in x]
                        if v2:
                            model.add(sum(vd) + sum(v2) <= 1)
            if d.weekday() == 5:
                d2 = d - timedelta(days=3)
                if d2 in dset:
                    v2 = [x[(e, d2, k)] for k in DEPTS if (e, d2, k) in x]
                    if v2:
                        model.add(sum(vd) + sum(v2) <= 1)
    wk_by_week = {}
    for d in target_dates:
        if is_functional_weekend(d, sd_df):
            wk_by_week.setdefault(d.isocalendar()[1], []).append(d)
    for e in employees:
        pre = weekends_worked.get(e, set())
        bools = []
        for w, wdays in wk_by_week.items():
            if w in pre:
                continue
            wv = [x[(e, d, k)] for d in wdays for k in DEPTS if (e, d, k) in x]
            if not wv:
                continue
            wb = model.new_bool_var(f"wknd|{e}|{w}")
            model.add(sum(wv) >= 1).only_enforce_if(wb)
            model.add(sum(wv) == 0).only_enforce_if(wb.negated())
            bools.append(wb)
        if bools:
            model.add(sum(bools) + len(pre) <= emp_wq.get(e, 0))
    for d, k in slots:
        ds = str(d)
        wv = [x[(e, d, k)] for e in employees if (e, ds) in wishes and (e, d, k) in x]
        nv = [x[(e, d, k)] for e in employees if (e, ds) not in wishes and (e, d, k) in x]
        if wv and nv:
            model.add(sum(nv) == 0)

    FILL = 50_000
    ov, oc = [], []
    for e in employees:
        q = max(emp_quota.get(e, 1), 1)
        lo = last_assignment.get(e, -999)
        for d, k in slots:
            v = x.get((e, d, k))
            if v is None:
                continue
            c = FILL
            c += int(-100 * work_load.get(e, 0) / q)
            c += int(2 * (d.toordinal() - lo if lo != -999 else 30))
            c += int(500 * (q * (d.day / num_days) - work_load.get(e, 0)))
            if emp_type.get(e) == 'תורן חוץ' and k == "שיקום":
                if d.weekday() in [3, 4, 5] or is_functional_weekend(d, sd_df):
                    c += 2000
            if emp_type.get(e) == 'מתמחה':
                if d.weekday() == 2:
                    c += int(-200 * wed_counts.get(e, 0))
                if d.weekday() == 3:
                    c += int(-200 * thu_counts.get(e, 0))
            c += 500 if emp_home.get(e, '') in (k, 'כללי') else -5000
            if (e, str(d)) in wishes:
                c += 1000
            ov.append(v)
            oc.append(int(c))
    if ov:
        model.maximize(cp.LinearExpr.weighted_sum(ov, oc))

    solver = cp.CpSolver()
    solver.parameters.max_time_in_seconds = float(time_limit)
    try:
        solver.parameters.num_workers = int(num_workers)
    except Exception:
        pass
    status = solver.solve(model)
    if status in (cp.INFEASIBLE, cp.UNKNOWN):
        r = run_smart_scheduling(ctx, year, month, only_weekends, save=save)
        r.messages.insert(0, ('warning', "⚠️ CP-SAT לא הצליח למצוא פתרון — עובר לשיבוץ חמדני"))
        return r

    filled = set()
    for e in employees:
        for d, k in slots:
            v = x.get((e, d, k))
            if v is not None and solver.value(v) == 1:
                ds = str(d)
                new_schedule.append({'date': ds, 'dept': k, 'employee': e, 'is_manual': False, 'empty_reason': ''})
                filled.add((ds, k))
                work_load[e] = work_load.get(e, 0) + 1
                if d.toordinal() > last_assignment.get(e, -999):
                    last_assignment[e] = d.toordinal()
                if d.weekday() == 2:
                    wed_counts[e] = wed_counts.get(e, 0) + 1
                if d.weekday() == 3:
                    thu_counts[e] = thu_counts.get(e, 0) + 1
                if is_functional_weekend(d, sd_df):
                    weekends_worked[e].add(d.isocalendar()[1])

    unfilled = [(d, k) for d, k in slots if (str(d), k) not in filled]
    fallback_cnt = 0
    if unfilled:
        m2 = cp.CpModel()
        x2 = {}
        for e in employees:
            for d, k in unfilled:
                ds = str(d)
                if (e, ds) in blocked:
                    continue
                if k == "פנימית גריאטרית" and emp_type.get(e) == 'תורן חוץ':
                    continue
                if work_load.get(e, 0) >= emp_quota.get(e, 6):
                    continue
                if any(s['date'] == ds and s['employee'] == e for s in new_schedule
                       if not str(s.get('empty_reason', '')).startswith('לא נמצא')):
                    continue
                x2[(e, d, k)] = m2.new_bool_var(f"x2|{e}|{d}|{k}")
        for d, k in unfilled:
            sv = [x2[(e, d, k)] for e in employees if (e, d, k) in x2]
            if sv:
                m2.add(sum(sv) <= 1)
        for e in employees:
            rem = emp_quota.get(e, 6) - work_load.get(e, 0)
            a2 = [x2[(e, d, k)] for d, k in unfilled if (e, d, k) in x2]
            if a2:
                if rem <= 0:
                    for vv in a2:
                        m2.add(vv == 0)
                else:
                    m2.add(sum(a2) <= rem)
        v2, c2 = [], []
        for e in employees:
            for d, k in unfilled:
                v = x2.get((e, d, k))
                if v is not None:
                    v2.append(v)
                    c2.append(50000 - work_load.get(e, 0) * 100)
        if v2:
            m2.maximize(cp.LinearExpr.weighted_sum(v2, c2))
        s2 = cp.CpSolver()
        s2.parameters.max_time_in_seconds = float(fallback_time_limit)
        st2 = s2.solve(m2)
        if st2 in (cp.OPTIMAL, cp.FEASIBLE):
            for e in employees:
                for d, k in unfilled:
                    v = x2.get((e, d, k))
                    if v is not None and s2.value(v) == 1:
                        ds = str(d)
                        new_schedule.append({'date': ds, 'dept': k, 'employee': e, 'is_manual': False,
                                             'empty_reason': 'הושלם מחוסר ברירה (הגמשת חוקים)'})
                        filled.add((ds, k))
                        work_load[e] = work_load.get(e, 0) + 1
                        fallback_cnt += 1

    still = [(d, k) for d, k in slots if (str(d), k) not in filled]
    for d, k in still:
        new_schedule.append({'date': str(d), 'dept': k, 'employee': '---', 'is_manual': False,
                             'empty_reason': 'לא נמצא פתרון (CP-SAT)'})

    _friday_post_pass(ctx, staff_df, new_schedule, work_load, all_dates)
    final_df = _finalize(ctx, new_schedule, save)

    n_total, n_filled = len(slots), len(slots) - len(still)
    method = "CP-SAT אופטימלי" if status == cp.OPTIMAL else "CP-SAT פתרון ישים"
    if status == cp.FEASIBLE:
        method += " (timeout)"
    note = f" ({fallback_cnt} בהגמשת חוקים)" if fallback_cnt else ""
    msg = f"✅ שיבוץ הושלם ({method}) — {n_filled}/{n_total} משמרות שובצו{note}.\n\n{balancing_msg}"
    return SchedulingResult(schedule=final_df, messages=[('info', msg)], method='cp', filled=n_filled,
                            total=n_total, fallback=fallback_cnt, saved=save)
