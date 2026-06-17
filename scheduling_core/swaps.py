"""
swaps.py — find_swap_candidates, lifted verbatim from appy.py:2714.

Employee-facing swap search. Returns three tiers:
  full    — mutual swap (candidate covers user's shift AND user can take one of theirs)
  partial — candidate covers user's shift, no mutual found
  chain   — 3-way (פנימית only): מתמחה moves שיקום→פנימית, תורן חוץ covers שיקום
Pure pandas/stdlib — no Streamlit.
"""
from datetime import date

import pandas as pd

from .validity import check_assignment_validity


def find_swap_candidates(schedule_df, requests_df, staff_df, user_name, swap_date, swap_dept, sel_month, year=2026):
    user_name_n = str(user_name).strip()

    sched_minus_user = schedule_df[
        ~((schedule_df['date'].astype(str) == swap_date) &
          (schedule_df['employee'].astype(str).str.strip() == user_name_n) &
          (schedule_df['dept'] == swap_dept))
    ].copy()

    def _safe_q(v):
        try:
            return int(v)
        except Exception:
            return 6

    active_staff = staff_df[
        (staff_df['name'].astype(str).str.strip() != user_name_n) &
        (staff_df['type'].astype(str).str.strip() != 'מנהל/ת')
    ].copy()
    active_staff = active_staff[active_staff['monthly_quota'].apply(_safe_q) > 0]

    req_dates = requests_df['date'].astype(str)
    req_emps = requests_df['employee'].astype(str).str.strip()
    wished_set = set(req_emps[(req_dates == swap_date) & (requests_df['status'] == 'בקשה')])

    month_prefix = swap_date[:7]
    full, partial = [], []

    for _, cand_row in active_staff.iterrows():
        cand_name = str(cand_row['name']).strip()

        ok, _ = check_assignment_validity(
            sched_minus_user, cand_name, swap_date, swap_dept,
            staff_df, requests_df,
            ignore_quota=True, ignore_home_restrict=False, ignore_rest=False
        )
        if not ok:
            continue

        _today_str = date.today().strftime('%Y-%m-%d')
        their_shifts = schedule_df[
            (schedule_df['employee'].astype(str).str.strip() == cand_name) &
            (schedule_df['date'].astype(str).str.startswith(month_prefix)) &
            (schedule_df['date'].astype(str) >= _today_str)   # exclude past shifts
        ]

        mutual = None
        for _, ts in their_shifts.iterrows():
            ts_date = str(ts['date'])
            ts_dept = ts['dept']

            sched_sim = sched_minus_user[
                ~((sched_minus_user['date'].astype(str) == ts_date) &
                  (sched_minus_user['employee'].astype(str).str.strip() == cand_name) &
                  (sched_minus_user['dept'] == ts_dept))
            ]
            sched_sim = pd.concat([sched_sim, pd.DataFrame([{
                'date': swap_date, 'dept': swap_dept, 'employee': cand_name,
                'is_manual': False, 'empty_reason': ''
            }])], ignore_index=True)

            ok_me, _ = check_assignment_validity(
                sched_sim, user_name_n, ts_date, ts_dept,
                staff_df, requests_df,
                ignore_quota=True, ignore_home_restrict=False, ignore_rest=False
            )
            if ok_me:
                mutual = {'date': ts_date, 'dept': ts_dept}
                break

        info = {
            'name': cand_name,
            'dept': str(cand_row.get('dept', '')),
            'type': str(cand_row.get('type', '')),
            'wished': cand_name in wished_set,
            'their_shift': mutual,
        }
        if mutual:
            full.append(info)
        else:
            partial.append(info)

    full.sort(key=lambda x: (not x['wished'], x['name']))
    partial.sort(key=lambda x: (not x['wished'], x['name']))

    # ── 3-way chain swap (only when user's shift is in פנימית גריאטרית) ──
    chain = []
    if swap_dept == 'פנימית גריאטרית':
        _facilitators_sched = sched_minus_user[
            (sched_minus_user['date'].astype(str) == swap_date) &
            (sched_minus_user['dept'] == 'שיקום') &
            (sched_minus_user['employee'].astype(str).str.strip() != user_name_n)
        ]
        _externals = staff_df[
            (staff_df['type'].astype(str).str.strip() == 'תורן חוץ') &
            (staff_df['name'].astype(str).str.strip() != user_name_n)
        ].copy()

        for _, _fac_row in _facilitators_sched.iterrows():
            _fac_name = str(_fac_row['employee']).strip()
            _fac_staff = staff_df[staff_df['name'].astype(str).str.strip() == _fac_name]
            if _fac_staff.empty:
                continue
            if str(_fac_staff.iloc[0].get('type', '')).strip() != 'מתמחה':
                continue  # must be מתמחה to work פנימית

            _ok_fac, _ = check_assignment_validity(
                sched_minus_user, _fac_name, swap_date, 'פנימית גריאטרית',
                staff_df, requests_df, ignore_quota=True
            )
            if not _ok_fac:
                continue

            _sched_sim = sched_minus_user[
                ~((sched_minus_user['date'].astype(str) == swap_date) &
                  (sched_minus_user['employee'].astype(str).str.strip() == _fac_name) &
                  (sched_minus_user['dept'] == 'שיקום'))
            ].copy()
            _sched_sim = pd.concat([_sched_sim, pd.DataFrame([{
                'date': swap_date, 'dept': 'פנימית גריאטרית', 'employee': _fac_name,
                'is_manual': False, 'empty_reason': ''
            }])], ignore_index=True)

            _fac_wished = _fac_name in wished_set
            for _, _ext_row in _externals.iterrows():
                _ext_name = str(_ext_row['name']).strip()
                _ok_ext, _ = check_assignment_validity(
                    _sched_sim, _ext_name, swap_date, 'שיקום',
                    staff_df, requests_df, ignore_quota=True
                )
                if _ok_ext:
                    chain.append({
                        'facilitator_name': _fac_name,
                        'facilitator_dept': str(_fac_staff.iloc[0].get('dept', '')),
                        'facilitator_wished': _fac_wished,
                        'external_name': _ext_name,
                        'external_wished': _ext_name in wished_set,
                    })
                    break  # one valid external per facilitator is enough

    chain.sort(key=lambda x: (not x['facilitator_wished'], not x['external_wished'], x['facilitator_name']))
    return {'full': full, 'partial': partial, 'chain': chain}
