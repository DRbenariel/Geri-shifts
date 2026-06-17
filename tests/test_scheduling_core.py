"""
Deterministic unit tests for scheduling_core (no Google Sheets needed).

Run:  python tests/test_scheduling_core.py
"""
import os
import sys
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scheduling_core import (
    is_functional_weekend, check_assignment_validity, find_swap_candidates,
)


def _staff():
    return pd.DataFrame([
        {'name': 'אינטרן א', 'type': 'מתמחה',  'dept': 'שיקום',          'monthly_quota': 6, 'weekend_quota': 2, 'only_home_dept': False},
        {'name': 'אינטרן ב', 'type': 'מתמחה',  'dept': 'פנימית גריאטרית', 'monthly_quota': 6, 'weekend_quota': 2, 'only_home_dept': False},
        {'name': 'חוץ ג',    'type': 'תורן חוץ', 'dept': 'שיקום',          'monthly_quota': 6, 'weekend_quota': 2, 'only_home_dept': False},
    ])


def _requests(rows=None):
    cols = ['employee', 'date', 'status']
    return pd.DataFrame(rows or [], columns=cols)


def test_validity():
    staff = _staff()
    sched = []  # empty schedule
    # valid intern on rehab
    ok, _ = check_assignment_validity(sched, 'אינטרן א', '2026-06-10', 'שיקום', staff, _requests())
    assert ok, "intern should be valid on empty schedule"

    # external cannot work internal
    ok, why = check_assignment_validity(sched, 'חוץ ג', '2026-06-10', 'פנימית גריאטרית', staff, _requests())
    assert not ok and 'External' in why, why

    # blocked (אילוץ)
    reqs = _requests([{'employee': 'אינטרן א', 'date': '2026-06-10', 'status': 'אילוץ'}])
    ok, why = check_assignment_validity(sched, 'אינטרן א', '2026-06-10', 'שיקום', staff, reqs)
    assert not ok and 'Blocked' in why, why

    # rest-gap violation (worked 1 day earlier)
    sched2 = [{'date': '2026-06-09', 'dept': 'שיקום', 'employee': 'אינטרן א'}]
    ok, why = check_assignment_validity(sched2, 'אינטרן א', '2026-06-10', 'שיקום', staff, _requests())
    assert not ok and 'Rest' in why, why

    # quota exceeded
    full_sched = [{'date': f'2026-06-{d:02d}', 'dept': 'שיקום', 'employee': 'אינטרן א'} for d in (1, 4, 7, 12, 15, 18)]
    ok, why = check_assignment_validity(full_sched, 'אינטרן א', '2026-06-25', 'שיקום', staff, _requests())
    assert not ok and 'Quota' in why, why
    # ...but ignore_quota bypasses it
    ok, _ = check_assignment_validity(full_sched, 'אינטרן א', '2026-06-25', 'שיקום', staff, _requests(), ignore_quota=True)
    assert ok
    print("test_validity OK")


def test_swaps():
    staff = _staff()
    # user 'אינטרן א' works rehab on the 10th; 'אינטרן ב' works rehab on the 20th.
    sched = pd.DataFrame([
        {'date': '2099-06-10', 'dept': 'שיקום', 'employee': 'אינטרן א', 'is_manual': False, 'empty_reason': ''},
        {'date': '2099-06-20', 'dept': 'שיקום', 'employee': 'אינטרן ב', 'is_manual': False, 'empty_reason': ''},
    ])
    res = find_swap_candidates(sched, _requests(), staff, 'אינטרן א', '2099-06-10', 'שיקום', 6, year=2099)
    names_full = {c['name'] for c in res['full']}
    assert 'אינטרן ב' in names_full, f"expected mutual swap with אינטרן ב, got {res}"
    print("test_swaps OK")


def test_weekend():
    sd = pd.DataFrame(columns=['date', 'description', 'day_type'])
    assert is_functional_weekend(date(2026, 6, 5), sd)   # Friday
    assert is_functional_weekend(date(2026, 6, 6), sd)   # Saturday
    assert not is_functional_weekend(date(2026, 6, 8), sd)  # Monday
    sd2 = pd.DataFrame([{'date': '2026-06-08', 'description': 'חג', 'day_type': 'כמו שבת (חג)'}])
    assert is_functional_weekend(date(2026, 6, 8), sd2)   # holiday Monday
    print("test_weekend OK")


if __name__ == '__main__':
    test_validity()
    test_swaps()
    test_weekend()
    print("ALL PASS")
