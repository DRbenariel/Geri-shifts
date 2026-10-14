"""Parity: geri_core must produce the same output as the original appy.py functions
on the same data. `legacy` runs the real appy.py code (see legacy.py)."""
import calendar
import io as _io
import random

import openpyxl
import pandas as pd
import pytest

from fixtures import MONTH, YEAR
from geri_core import absences, daily, exports, night, people, scheduling

DEPTS = [None, "שיקום גריאטרי א'", "שיקום גריאטרי ב'", 'פנימית גריאטרית', 'זה״ב']
YM = f"{YEAR}-{MONTH:02d}"
NDAYS = calendar.monthrange(YEAR, MONTH)[1]


def all_names(ctx):
    return ctx.staff['name'].astype(str).tolist()


def test_derive_auto_status_every_cell(ctx, legacy):
    ns, _, _ = legacy
    checked = 0
    for emp in all_names(ctx):
        for d in range(1, NDAYS + 1):
            ds = f"{YM}-{d:02d}"
            for dept in DEPTS:
                assert daily.derive_auto_status(ctx, ds, emp, dept) == ns['_derive_auto_status'](ds, emp, dept), (emp, ds, dept)
                checked += 1
    assert checked > 3000


def test_dept_resolution(ctx, legacy):
    ns, _, _ = legacy
    for emp in all_names(ctx) + ['לא קיים']:
        for ym in ('2026-10', YM, '2026-12'):
            assert people.emp_dept_for_date(ctx, emp, ym + '-01') == ns['_emp_dept_for_date'](emp, ym + '-01')
            assert people.emp_night_dept(ctx, emp, ym) == ns['_emp_night_dept'](emp, ym)


def test_small_helpers(ctx, legacy):
    ns, _, _ = legacy
    for dept in DEPTS[1:]:
        assert people.get_dept_managers(ctx, dept) == ns['_get_dept_managers'](dept)
        assert daily.incoming_transfers(ctx, dept, YM) == ns['_incoming_transfers'](dept, YM)
        for d in range(1, NDAYS + 1):
            ds = f"{YM}-{d:02d}"
            assert daily.get_night_duty(ctx, ds, dept) == ns['_get_night_duty'](ds, dept)
            assert daily.get_fri_shift_workers(ctx, ds, dept) == ns['_get_fri_shift_workers'](ds, dept)
    names = all_names(ctx)
    assert people.sort_employees_by_role(ctx, names) == ns['_sort_employees_by_role'](names)
    for emp in names:
        assert people.cycle_for_role(ctx, emp) == ns['_cycle_for_role'](emp)
        assert people.manual_statuses_for_role(ctx, emp) == ns['_manual_statuses_for_role'](emp)


def test_check_assignment_validity(ctx, legacy):
    ns, _, _ = legacy
    rnd = random.Random(1)
    sched = ctx.schedule
    for _ in range(600):
        p = rnd.choice(all_names(ctx) + ['---'])
        ds = f"{YM}-{rnd.randint(1, NDAYS):02d}"
        dept = rnd.choice(['שיקום', 'פנימית גריאטרית', 'שישי בוקר - שיקום (1)', 'שישי בוקר - פנימית (2)'])
        flags = dict(ignore_quota=rnd.random() < .5, ignore_home_restrict=rnd.random() < .3, ignore_rest=rnd.random() < .3)
        assert (night.check_assignment_validity(ctx, sched, p, ds, dept, ctx.staff, ctx.requests, **flags) ==
                ns['check_assignment_validity'](sched, p, ds, dept, ctx.staff, ctx.requests, **flags))


def _fill_november(ctx, legacy):
    """Run both greedy schedulers; returns (core_result, legacy_schedule)."""
    ns, st, _ = legacy
    res = scheduling.run_smart_scheduling(ctx, YEAR, MONTH, save=False)
    ns['run_smart_scheduling'](YEAR, MONTH)
    return res, st.session_state.schedule, st


def _norm(df):
    return (df.astype(str).sort_values(['date', 'dept']).reset_index(drop=True))


def test_greedy_scheduler(ctx, legacy):
    res, legacy_sched, st = _fill_november(ctx, legacy)
    pd.testing.assert_frame_equal(_norm(res.schedule), _norm(legacy_sched))
    assert res.swap_suggestions == st.session_state.get('swap_suggestions', {})
    assert res.messages[0][1] == next(m for k, m in st.messages if k == 'info')


def test_greedy_weekends_only(ctx, legacy):
    ns, st, _ = legacy
    res = scheduling.run_smart_scheduling(ctx, YEAR, MONTH, only_weekends=True, save=False)
    ns['run_smart_scheduling'](YEAR, MONTH, only_weekends=True)
    pd.testing.assert_frame_equal(_norm(res.schedule), _norm(st.session_state.schedule))


def test_find_swap_candidates(ctx, legacy):
    ns, st, _ = legacy
    _fill_november(ctx, legacy)
    sched = ctx.schedule
    shifts = sched[sched['date'].astype(str).str.startswith(YM) & (sched['employee'] != '---')]
    for _, s in shifts.sample(25, random_state=3).iterrows():
        a = night.find_swap_candidates(ctx, sched, ctx.requests, ctx.staff, s['employee'], s['date'], s['dept'], MONTH)
        b = ns['find_swap_candidates'](sched, ctx.requests, ctx.staff, s['employee'], s['date'], s['dept'], MONTH)
        assert a == b


def test_absence_conflicts(ctx, legacy):
    ns, _, _ = legacy
    for _, r in ctx.absence_requests.iterrows():
        emp = r['employee']
        dept = people.emp_dept_for_date(ctx, emp, r['start_date'])
        for d in (dept, '', 'שיקום'):
            assert (absences.absence_conflicts(ctx, emp, d, r['start_date'], r['end_date'], exclude_id=r['id']) ==
                    ns['_absence_conflicts'](emp, d, r['start_date'], r['end_date'], exclude_id=r['id']))
    c = absences.absence_conflicts(ctx, 'x', "שיקום גריאטרי א'", f"{YM}-01", f"{YM}-30")
    assert absences.format_conflict_question(c) == ns['_format_absence_conflict_question'](c)


@pytest.mark.parametrize('verb', ['approve', 'reject'])
def test_absence_approve_reject(ctx, legacy, verb):
    ns, st, io = legacy
    pending = ctx.absence_requests[ctx.absence_requests['status'] == 'pending']['id'].tolist()
    for rid in pending:
        if verb == 'approve':
            assert absences.approve_request(ctx, rid, 'מנהל') == ns['_approve_request'](rid, 'מנהל')
        else:
            assert absences.reject_request(ctx, rid, 'מנהל') == ns['_reject_request'](rid, 'מנהל')
    drop = ['responded_at']
    pd.testing.assert_frame_equal(ctx.absence_requests.drop(columns=drop).astype(str).reset_index(drop=True),
                                  st.session_state.absence_requests.drop(columns=drop).astype(str).reset_index(drop=True))
    pd.testing.assert_frame_equal(_wsd(ctx.work_schedule_daily), _wsd(st.session_state.work_schedule_daily))
    assert [e[:2] for e in ctx.mailer.sent] == [e[:2] for e in io.emails]
    # status is now identical everywhere
    for emp in all_names(ctx):
        for d in range(1, NDAYS + 1):
            ds = f"{YM}-{d:02d}"
            assert daily.derive_auto_status(ctx, ds, emp) == ns['_derive_auto_status'](ds, emp)


def _wsd(df):
    return df.astype(str).sort_values(['date', 'employee']).reset_index(drop=True)


def test_delete_and_migrate(ctx, legacy):
    ns, st, _ = legacy
    rid = ctx.absence_requests['id'].iloc[0]
    assert absences.delete_absence_request(ctx, rid) == ns['_delete_absence_request'](rid)
    args = ('נועה ברק', "שיקום גריאטרי א'", 'פנימית גריאטרית', YM)
    assert absences.migrate_requests_on_dept_change(ctx, *args) == ns['_migrate_requests_on_dept_change'](*args)
    pd.testing.assert_frame_equal(ctx.absence_requests.astype(str).reset_index(drop=True),
                                  st.session_state.absence_requests.astype(str).reset_index(drop=True))
    pd.testing.assert_frame_equal(_wsd(ctx.work_schedule_daily), _wsd(st.session_state.work_schedule_daily))


def test_wsd_upsert_delete(ctx, legacy):
    ns, st, _ = legacy
    ops = [('upsert', f"{YM}-07", 'שירה לוי', 'פנימית גריאטרית', '202', True, 'n', ''),
           ('upsert', f"{YM}-10", 'נועה ברק', 'פנימית גריאטרית', 'אחר', True, '', ''),     # side stays כחול
           ('upsert', f"{YM}-10", 'נועה ברק', 'פנימית גריאטרית', 'עובד', True, '', 'ורוד'),
           ('delete', f"{YM}-18", 'נועה ברק')]
    for op in ops:
        if op[0] == 'upsert':
            daily.wsd_upsert(ctx, *op[1:])
            ns['_wsd_upsert'](*op[1:])
        else:
            daily.wsd_delete(ctx, *op[1:])
            ns['_wsd_delete'](*op[1:])
    pd.testing.assert_frame_equal(_wsd(ctx.work_schedule_daily), _wsd(st.session_state.work_schedule_daily))
    assert ctx.wsd_index == st.session_state.wsd_index


def test_batched_day_data(ctx, legacy):
    ns, _, _ = legacy
    _fill_november(ctx, legacy)
    for dept in DEPTS[1:]:
        assert exports.build_batched_day_data(ctx, dept, YM, MONTH) == ns['_build_batched_day_data'](dept, YM, MONTH)


def _cells(xbytes):
    wb = openpyxl.load_workbook(_io.BytesIO(xbytes))
    out = {}
    for ws in wb.worksheets:
        out[ws.title] = {
            'cells': [[c.value for c in row] for row in ws.iter_rows()],
            'fills': [[c.fill.fgColor.rgb for c in row] for row in ws.iter_rows()],
            'breaks': [b.id for b in ws.row_breaks.brk],
            'rtl': ws.sheet_view.rightToLeft,
        }
    return out


def test_excel_exports_identical(ctx, legacy):
    ns, _, _ = legacy
    _fill_november(ctx, legacy)
    for dept in DEPTS[1:]:
        a, an = exports.dept_batched_excel(ctx, dept, YM, MONTH)
        b, bn = ns['_export_dept_grid_batched'](dept, YM, MONTH)
        assert an == bn
        if a:
            assert _cells(a) == _cells(b)
        a, an = exports.dept_grid_excel(ctx, dept, YM, MONTH)
        b, bn = ns['_export_dept_grid_excel'](dept, YM, MONTH)
        assert an == bn
        if a:
            assert _cells(a) == _cells(b)
    a, an = exports.all_depts_batched_excel(ctx, YM, MONTH)
    b, bn = ns['_export_all_depts_batched'](YM, MONTH)
    assert an == bn and _cells(a) == _cells(b)
    for emp in ('נועה ברק', 'דפנה ירון', 'יעל כרמי'):
        dd = people.emp_dept_for_date(ctx, emp, f"{YM}-01")
        a, an = exports.personal_excel(ctx, emp, MONTH, daily_dept=dd)
        b, bn = ns['_export_personal_schedule_excel'](emp, MONTH, daily_dept=dd)
        assert an == bn and _cells(a) == _cells(b)


def test_sheet_exports(ctx, legacy):
    ns, st, io = legacy
    _fill_november(ctx, legacy)
    for dept in DEPTS[1:4]:
        ok = ns['_export_dept_grid'](dept, YM, MONTH)
        df = exports.dept_sheet_df(ctx, dept, YM, MONTH)
        assert ok == (df is not None)
        if ok:
            pd.testing.assert_frame_equal(df, io.writes[exports.wsd_sheet_name(dept, YM)])
    ok, err = ns['_export_schedule_wide'](MONTH)
    assert ok, err
    pd.testing.assert_frame_equal(exports.schedule_wide_df(ctx, MONTH), io.writes['Schedule_Export'])


def _stress(frames):
    """Interns + 3 externals all blocked on the 21st → empty slots with swap suggestions."""
    from fixtures import EXTERNALS, INTERNS
    extra = [{'employee': n, 'date': f"{YM}-21", 'status': 'אילוץ'} for n in INTERNS[:11] + EXTERNALS[:3]]
    frames['requests'] = pd.concat([frames['requests'], pd.DataFrame(extra)], ignore_index=True)
    return frames


@pytest.fixture
def stressed(frames):
    from geri_core import DataContext, MemoryStore
    from legacy import load_legacy, seed_session
    ctx = DataContext.load(MemoryStore(_stress(frames)))
    ns, st, io = load_legacy()
    seed_session(ns, st, io, ctx)
    return ctx, (ns, st, io)


def test_greedy_scheduler_stressed(stressed):
    ctx, legacy = stressed
    res, legacy_sched, st = _fill_november(ctx, legacy)
    assert (res.schedule['employee'] == '---').sum() >= 2
    assert res.swap_suggestions, "stress fixture should produce swap suggestions"
    pd.testing.assert_frame_equal(_norm(res.schedule), _norm(legacy_sched))
    assert res.swap_suggestions == st.session_state.get('swap_suggestions', {})


def test_find_swap_candidates_all_pnim(ctx, legacy):
    """Every פנימית shift. NOTE: the 3-way chain branch is unreachable in appy.py —
    the facilitator is validated for פנימית against a schedule that still holds
    their own שיקום shift that day, so check_assignment_validity always answers
    "Already working this day". The port keeps that behaviour (parity first);
    fixing it is tracked separately in SCREENS_PLAN.md."""
    ns, _, _ = legacy
    _fill_november(ctx, legacy)
    sched = ctx.schedule
    pn = sched[sched['date'].astype(str).str.startswith(YM) & (sched['dept'] == 'פנימית גריאטרית')
               & (sched['employee'] != '---')]
    chains = 0
    for _, s in pn.iterrows():
        a = night.find_swap_candidates(ctx, sched, ctx.requests, ctx.staff, s['employee'], s['date'], s['dept'], MONTH)
        assert a == ns['find_swap_candidates'](sched, ctx.requests, ctx.staff, s['employee'], s['date'], s['dept'], MONTH)
        chains += len(a['chain'])
    assert chains == 0   # pinned legacy behaviour, see docstring
