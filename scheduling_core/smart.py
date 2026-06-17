"""
smart.py — run_smart_scheduling, ported from appy.py:3131-3644 (Streamlit-free).

The production night-shift assigner: greedy with scoring (quota usage, pacing,
fairness, dept bonus), soft/hard quotas, rest gap, intern Wed/Sat rule, wish
prioritization, starvation fallback, and the Friday-morning post-pass.

Differences vs the Streamlit original (behaviour-preserving for the schedule):
  - reads come from parameters instead of st.session_state,
  - the UI "swap suggestion" generation (appy.py:3427-3549) is dropped — it only
    populated st.session_state for the UI; the empty slot is still emitted as a
    '---' row so the schedule output is identical,
  - returns (schedule_list, balancing_msg) instead of writing to the DB.
"""
import calendar
from datetime import date, datetime, timedelta

import pandas as pd

from .calendars import is_functional_weekend, get_functional_day_type
from .validity import check_assignment_validity


def run_smart_scheduling(year, month, staff_df, schedule_df, requests_df,
                         special_days_df, only_weekends=False):
    num_days = calendar.monthrange(year, month)[1]
    staff_df = staff_df.copy()

    all_current_records = schedule_df.to_dict('records')

    new_schedule = []
    current_month_prefix = f"{year}-{month:02d}"

    for r in all_current_records:
        if not str(r['date']).startswith(current_month_prefix):
            new_schedule.append(r)
        else:
            if r['employee'] != '---':
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
        if str(s['date']).startswith(current_month_prefix):
            work_load[s['employee']] += 1
            if is_functional_weekend(dt, special_days_df) and "שישי בוקר" not in s.get('dept', ''):
                weekends_worked[s['employee']].add(dt.isocalendar()[1])

    avg_wed = sum(wed_counts.values()) / len(wed_counts) if wed_counts else 0
    avg_thu = sum(thu_counts.values()) / len(thu_counts) if thu_counts else 0
    priority_wed = [k for k, v in wed_counts.items() if v < avg_wed]
    priority_thu = [k for k, v in thu_counts.items() if v < avg_thu]

    balancing_msg = "**דוח איזון הוגנות (רב-חודשי):**\n"
    balancing_msg += f"- **רביעי:** ממוצע {avg_wed:.1f}. תועדפו: {len(priority_wed)} עובדים.\n"
    balancing_msg += f"- **חמישי:** ממוצע {avg_thu:.1f}. תועדפו: {len(priority_thu)} עובדים.\n"
    balancing_msg += "- **שישי בוקר:** האיזון מבוצע אוטומטית על סמך כל ההיסטוריה."

    all_dates = [date(year, month, d) for d in range(1, num_days + 1)]

    if only_weekends:
        sorted_dates = [d for d in all_dates if is_functional_weekend(d, special_days_df)]
    else:
        sorted_dates = ([d for d in all_dates if is_functional_weekend(d, special_days_df)]
                        + [d for d in all_dates if not is_functional_weekend(d, special_days_df)])

    def safe_int(val, default=0):
        try:
            if pd.isna(val) or val == "":
                return default
            return int(float(val))
        except (ValueError, TypeError):
            return default

    for d in sorted_dates:
        d_str = str(d)
        week_num = d.isocalendar()[1]

        for dept in ["פנימית גריאטרית", "שיקום"]:
            if any(s for s in new_schedule if s['date'] == d_str and s['dept'] == dept):
                continue

            candidates = []
            failure_reasons = []

            for _, person in staff_df.iterrows():
                name = person['name']
                if person['type'] == 'תורן חוץ' and dept == 'פנימית גריאטרית':
                    continue
                if any(s for s in new_schedule if s['date'] == d_str and s['employee'] == name):
                    continue

                only_home = person.get('only_home_dept', False)
                if only_home:
                    target_context = dept
                    if "שישי בוקר" in dept:
                        target_context = "שיקום" if "שיקום" in dept else "פנימית גריאטרית"
                    if person['dept'] != 'כללי' and person['dept'] != target_context:
                        continue

                monthly_quota = safe_int(person['monthly_quota'], 0)
                if work_load[name] >= monthly_quota:
                    failure_reasons.append(f"{name}: מכסה מלאה ({monthly_quota})")
                    continue

                if d.day < 15 and monthly_quota > 0 and work_load[name] >= monthly_quota * 0.5:
                    failure_reasons.append(f"{name}: שמירת מכסה (חצי ראשון)")
                    continue

                weekend_quota = safe_int(person['weekend_quota'], 0)
                if is_functional_weekend(d, special_days_df) and len(weekends_worked[name]) >= weekend_quota and week_num not in weekends_worked[name]:
                    failure_reasons.append(f"{name}: מכסת סופ\"ש")
                    continue

                gap_days = [-2, -1, 1, 2]
                has_rest_conflict = False
                for offset in gap_days:
                    if any(s for s in new_schedule if s['date'] == str(d + timedelta(days=offset)) and s['employee'] == name):
                        has_rest_conflict = True
                        break
                if has_rest_conflict:
                    failure_reasons.append(f"{name}: מרווח מנוחה")
                    continue

                if person['type'] == 'מתמחה':
                    if d.weekday() == 5:  # שבת
                        if any(s for s in new_schedule if s['date'] == str(d - timedelta(days=3)) and s['employee'] == name):
                            failure_reasons.append(f"{name}: שובץ ברביעי")
                            continue
                    if d.weekday() == 2:  # רביעי
                        if any(s for s in new_schedule if s['date'] == str(d + timedelta(days=3)) and s['employee'] == name):
                            failure_reasons.append(f"{name}: משובץ בשבת")
                            continue
                        fri_check = str(d + timedelta(days=2))
                        if any(s for s in new_schedule if s['date'] == fri_check and s['employee'] == name):
                            failure_reasons.append(f"{name}: משובץ בשישי הקרוב")
                            continue

                if not requests_df[(requests_df['employee'] == name) & (requests_df['date'] == d_str) & (requests_df['status'] == "אילוץ")].empty:
                    failure_reasons.append(f"{name}: אילוץ")
                    continue

                candidates.append(person)

            if candidates:
                requesters = requests_df[(requests_df['date'] == d_str) & (requests_df['status'] == "בקשה")]['employee'].tolist()
                wish_candidates = [c for c in candidates if c['name'] in requesters]
                final_pool = wish_candidates if wish_candidates else candidates

                def calculate_score(cand):
                    name = cand['name']
                    quota = safe_int(cand['monthly_quota'], 1)
                    usage_ratio = work_load[name] / quota if quota > 0 else 1.0
                    score = -usage_ratio * 100
                    last_day = last_assignment.get(name, -999)
                    days_diff = d.toordinal() - last_day
                    score += days_diff * 2
                    current_day_in_month = d.day
                    month_progress = current_day_in_month / num_days
                    expected_shifts = quota * month_progress
                    actual_shifts = work_load[name]
                    pacing_score = (expected_shifts - actual_shifts) * 500
                    score += pacing_score
                    if dept == "שיקום" and cand['type'] == 'תורן חוץ':
                        if d.weekday() in [3, 4, 5] or is_functional_weekend(d, special_days_df):
                            score += 2000
                    if cand['type'] == 'מתמחה':
                        if d.weekday() == 2:
                            score -= wed_counts[name] * 200
                        if d.weekday() == 3:
                            score -= thu_counts[name] * 200
                    cand_dept = cand['dept']
                    if cand_dept == dept or cand_dept == 'כללי':
                        score += 500
                    else:
                        score -= 5000
                    return score

                final_choice = max(final_pool, key=calculate_score)['name']
                new_schedule.append({'date': d_str, 'dept': dept, 'employee': final_choice, 'is_manual': False, 'empty_reason': ''})
                work_load[final_choice] += 1
                last_assignment[final_choice] = d.toordinal()
                if d.weekday() == 2:
                    wed_counts[final_choice] += 1
                if d.weekday() == 3:
                    thu_counts[final_choice] += 1
                if is_functional_weekend(d, special_days_df):
                    weekends_worked[final_choice].add(week_num)
            else:
                # starvation fallback
                fallback_pool = []
                for _, cand in staff_df.iterrows():
                    c_name = cand['name']
                    if c_name == '---' or str(c_name).upper() == 'ADMIN':
                        continue
                    if cand['type'] == 'תורן חוץ' and dept == 'פנימית גריאטרית':
                        continue
                    if any(s for s in new_schedule if s['date'] == d_str and s['employee'] == c_name):
                        continue
                    req = requests_df[(requests_df['employee'] == c_name) & (requests_df['date'] == d_str) & (requests_df['status'] == 'אילוץ')]
                    if not req.empty:
                        continue
                    monthly_quota = safe_int(cand['monthly_quota'], 0)
                    if work_load.get(c_name, 0) >= monthly_quota:
                        continue
                    weekend_quota = safe_int(cand['weekend_quota'], 0)
                    if is_functional_weekend(d, special_days_df) and len(weekends_worked.get(c_name, set())) >= weekend_quota and week_num not in weekends_worked.get(c_name, set()):
                        continue
                    fallback_pool.append(c_name)

                if fallback_pool:
                    fallback_choice = min(fallback_pool, key=lambda x: work_load.get(x, 0))
                    new_schedule.append({'date': d_str, 'dept': dept, 'employee': fallback_choice, 'is_manual': False, 'empty_reason': 'הושלם מחוסר ברירה (הגמשת חוקים)'})
                    work_load[fallback_choice] += 1
                    last_assignment[fallback_choice] = d.toordinal()
                    if d.weekday() == 2:
                        wed_counts[fallback_choice] += 1
                    if d.weekday() == 3:
                        thu_counts[fallback_choice] += 1
                    if is_functional_weekend(d, special_days_df):
                        weekends_worked[fallback_choice].add(week_num)
                    continue

                # no candidate at all → emit an empty slot (UI suggestion logic dropped)
                reason = "לא נמצא פתרון אוטומטי"
                if failure_reasons:
                    reason += " (סיבות לדוגמה: " + ", ".join(list(set(failure_reasons))[:3]) + ")"
                new_schedule.append({'date': d_str, 'dept': dept, 'employee': '---', 'is_manual': False, 'empty_reason': reason})

    # ── Friday-morning post-pass (4 slots per Friday) ──
    fridays = [d for d in all_dates if d.weekday() == 4 or get_functional_day_type(d, special_days_df) == 'כמו שישי (ערב חג)']
    for fri_date in fridays:
        fri_str = str(fri_date)
        sat_date = fri_date + timedelta(days=1)
        sat_str = str(sat_date)

        fri_worker_pnimia = next((s['employee'] for s in new_schedule if s['date'] == fri_str and s['dept'] == 'פנימית גריאטרית'), None)
        sat_worker_pnimia = next((s['employee'] for s in new_schedule if s['date'] == sat_str and s['dept'] == 'פנימית גריאטרית'), None)

        has_pnimia_1 = any(s for s in new_schedule if s['date'] == fri_str and s['dept'] == 'שישי בוקר - פנימית (1)')
        has_pnimia_2 = any(s for s in new_schedule if s['date'] == fri_str and s['dept'] == 'שישי בוקר - פנימית (2)')

        if not has_pnimia_1 and fri_worker_pnimia and fri_worker_pnimia != '---':
            new_schedule.append({'date': fri_str, 'dept': 'שישי בוקר - פנימית (1)', 'employee': fri_worker_pnimia, 'is_manual': False, 'empty_reason': 'נגזר אוטומטית משישי'})
        if not has_pnimia_2 and sat_worker_pnimia and sat_worker_pnimia != '---':
            new_schedule.append({'date': fri_str, 'dept': 'שישי בוקר - פנימית (2)', 'employee': sat_worker_pnimia, 'is_manual': False, 'empty_reason': 'נגזר אוטומטית משבת'})

        fri_worker_rehab = next((s['employee'] for s in new_schedule if s['date'] == fri_str and s['dept'] == 'שיקום'), None)
        sat_worker_rehab = next((s['employee'] for s in new_schedule if s['date'] == sat_str and s['dept'] == 'שיקום'), None)

        def handle_rehab_morning(worker_name, source_day, slot_num):
            target_dept = f'שישי בוקר - שיקום ({slot_num})'
            if any(s for s in new_schedule if s['date'] == fri_str and s['dept'] == target_dept):
                return
            if not worker_name or worker_name == '---':
                return
            w_type = None
            if worker_name in staff_df['name'].values:
                w_type = staff_df[staff_df['name'] == worker_name]['type'].iloc[0]
            if w_type == 'מתמחה':
                new_schedule.append({'date': fri_str, 'dept': target_dept, 'employee': worker_name, 'is_manual': False, 'empty_reason': f'נגזר אוטומטית מ{source_day}'})
            else:
                candidates = []
                for _, row in staff_df.iterrows():
                    if row['type'] == 'מתמחה' and row['dept'] == 'שיקום' and row['name'] != worker_name:
                        emp = row['name']
                        is_blocked = not requests_df[(requests_df['employee'] == emp) & (requests_df['date'] == fri_str) & (requests_df['status'] == "אילוץ")].empty
                        if is_blocked:
                            continue
                        has_rest_conflict = any(
                            s['employee'] == emp and s['date'] == str(fri_date + timedelta(days=offset))
                            for s in new_schedule for offset in [-2, -1, 1, 2]
                        )
                        if has_rest_conflict:
                            continue
                        if any(s['employee'] == emp and s['date'] == fri_str for s in new_schedule):
                            continue
                        monthly_quota = safe_int(row['monthly_quota'], 0)
                        if work_load.get(emp, 0) >= monthly_quota:
                            continue
                        fri_morning_count = len([s for s in new_schedule if s['employee'] == emp and 'שישי בוקר' in s['dept']])
                        candidates.append((emp, fri_morning_count))
                if candidates:
                    candidates.sort(key=lambda x: x[1])
                    best_candidate = candidates[0][0]
                    new_schedule.append({'date': fri_str, 'dept': target_dept, 'employee': best_candidate, 'is_manual': False, 'empty_reason': f'השלמה במקום {worker_name}'})
                    work_load[best_candidate] += 1
                else:
                    new_schedule.append({'date': fri_str, 'dept': target_dept, 'employee': '---', 'is_manual': False, 'empty_reason': 'לא נמצא מחליף לבוקר'})

        handle_rehab_morning(fri_worker_rehab, "שישי", "1")
        handle_rehab_morning(sat_worker_rehab, "שבת", "2")

    final_df = pd.DataFrame(new_schedule)
    if not final_df.empty:
        final_df = final_df.drop_duplicates(subset=['date', 'dept'], keep='first')

    return final_df.to_dict('records'), balancing_msg
