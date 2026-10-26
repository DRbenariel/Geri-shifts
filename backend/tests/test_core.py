"""Behaviour tests for logic that lived inline in appy.py's UI code (no legacy
function to diff against), checked against the rules in that code."""
import hashlib

import pandas as pd
import pytest

from fixtures import EXTERNALS, INTERNS, MONTH, SENIORS, YEAR
from geri_core import absences, admin, constraints, daily, exports, night, reports, scheduling, staff
from geri_core.constants import default_tab_for_role, tabs_for_role

YM = f"{YEAR}-{MONTH:02d}"


# ── auth ─────────────────────────────────────────────────────────────────────
def _set_pw(ctx, name, stored):
    df = ctx.store.sheets['staff']
    df.loc[df['name'] == name, 'password'] = stored
    ctx.staff.loc[ctx.staff['name'] == name, 'password'] = stored


def test_login_sha256_then_upgrades_to_bcrypt(ctx):
    _set_pw(ctx, 'נועה ברק', hashlib.sha256(b'secret').hexdigest())
    u = staff.login(ctx, ' נועה ברק ', 'secret')
    assert u == {'name': 'נועה ברק', 'role': 'מתמחה'}
    stored = ctx.store.sheets['staff'].set_index('name').loc['נועה ברק', 'password']
    assert stored.startswith('$2')
    assert staff.login(ctx, 'נועה ברק', 'secret')['role'] == 'מתמחה'      # bcrypt path
    with pytest.raises(staff.AuthError, match='סיסמה שגויה'):
        staff.login(ctx, 'נועה ברק', 'wrong')
    with pytest.raises(staff.AuthError, match='לא נמצא'):
        staff.login(ctx, 'אין כזה', 'secret')


def test_login_matches_trailing_space_name(ctx):
    _set_pw(ctx, 'רוני אבן ', hashlib.sha256(b'pw').hexdigest())
    assert staff.login(ctx, 'רוני אבן', 'pw')['name'] == 'רוני אבן'


def test_change_password(ctx):
    _set_pw(ctx, 'גל שחר', hashlib.sha256(b'old').hexdigest())
    with pytest.raises(ValueError):
        staff.change_password(ctx, 'גל שחר', 'bad', 'n', 'n')
    with pytest.raises(ValueError):
        staff.change_password(ctx, 'גל שחר', 'old', 'a', 'b')
    staff.change_password(ctx, 'גל שחר', 'old', 'new', 'new')
    assert staff.verify_password('new', ctx.staff.set_index('name').loc['גל שחר', 'password'])


def test_staff_add_and_save_keep_passwords(ctx):
    staff.add_employee(ctx, 'חדש', 'מתמחה', 'שיקום')
    with pytest.raises(ValueError):
        staff.add_employee(ctx, 'חדש', 'מתמחה', 'שיקום')
    view = staff.staff_view(ctx)
    assert 'password' not in view['columns']
    rows = view['rows']
    rows = [dict(r, _original_name=r['name']) for r in rows]
    rows[0]['name'] = 'שם חדש'
    before = ctx.store.sheets['staff'].set_index('name')['password']
    staff.save_staff_table(ctx, rows, view['only_home'])
    after = ctx.store.sheets['staff'].set_index('name')['password']
    assert after['שם חדש'] == before[INTERNS[0]]          # renamed row keeps its hash
    assert staff.verify_password('1234', after['חדש'])


# ── night constraints ────────────────────────────────────────────────────────
def test_constraint_rules():
    assert constraints.validate(YEAR, MONTH, [], [1, 2, 3], 'מתמחה')[0].startswith('שגיאה: ניתן')
    errs = constraints.validate(YEAR, MONTH, [5, 12, 19, 26], [], 'מתמחה')     # every Thursday
    assert any('חמישי' in e for e in errs)
    errs = constraints.validate(YEAR, MONTH, [6, 7, 13, 14, 20], [], 'מתמחה')
    assert any('סוף שבוע' in e for e in errs)
    assert constraints.validate(YEAR, MONTH, [6, 7, 13, 14, 20], [], 'תורן חוץ') == []
    c = constraints.counters(YEAR, MONTH, [5], [1])
    assert c['total_thu'] == 4 and c['avail_thu'] == 3 and c['thu_ok']


def test_save_requests_merges_with_live_sheet(ctx):
    # another user's row written straight to the sheet after ctx loaded
    live = ctx.store.sheets['requests']
    ctx.store.sheets['requests'] = pd.concat(
        [live, pd.DataFrame([{'employee': 'אחר', 'date': f"{YM}-01", 'status': 'אילוץ'}])], ignore_index=True)
    constraints.save_requests(ctx, 'נועה ברק', YEAR, MONTH, [2, 9], [3], role='מתמחה')
    saved = ctx.store.sheets['requests']
    assert ((saved['employee'] == 'אחר')).any()
    mine = saved[(saved['employee'] == 'נועה ברק') & saved['date'].str.startswith(YM)]
    assert sorted(mine['date']) == [f"{YM}-02", f"{YM}-03", f"{YM}-09"]
    assert constraints.my_requests(ctx, 'נועה ברק', YEAR, MONTH) == ([2, 9], [3])
    with pytest.raises(ValueError):
        constraints.save_requests(ctx, 'נועה ברק', YEAR, MONTH, [2], [2], enforce_rules=False)


# ── night schedule ───────────────────────────────────────────────────────────
def test_cp_scheduler_respects_hard_constraints(ctx):
    res = scheduling.run_smart_scheduling_cp(ctx, YEAR, MONTH, save=True, time_limit=8, fallback_time_limit=3)
    assert res.method == 'cp' and res.total > 0
    s = res.schedule
    nov = s[s['date'].astype(str).str.startswith(YM)]
    assert not nov.duplicated(['date', 'dept']).any()
    types = ctx.staff.set_index('name')['type']
    blocked = set(zip(ctx.requests[ctx.requests['status'] == 'אילוץ']['employee'],
                      ctx.requests[ctx.requests['status'] == 'אילוץ']['date']))
    auto = nov[(nov['employee'] != '---') & (nov['is_manual'].astype(str) != 'True')]
    for _, r in auto.iterrows():
        assert (r['employee'], r['date']) not in blocked
        if r['dept'] == 'פנימית גריאטרית':
            assert types.get(r['employee']) != 'תורן חוץ'
    main = nov[nov['dept'].isin(['שיקום', 'פנימית גריאטרית']) & (nov['employee'] != '---')]
    quota = ctx.staff.set_index('name')['monthly_quota'].astype(int)
    for emp, n in main['employee'].value_counts().items():
        fri = nov[(nov['employee'] == emp) & nov['dept'].str.contains('שישי בוקר')]
        assert n <= quota[emp] + len(fri)
    assert 'schedule' in [w[0] for w in ctx.store.writes]


def test_manual_tool_and_cleanup(ctx):
    blocked = ctx.requests[ctx.requests['status'] == 'אילוץ'].iloc[0]
    with pytest.raises(ValueError):
        night.manual_assign(ctx, blocked['date'], 'שיקום', blocked['employee'])
    night.manual_assign(ctx, f"{YM}-28", 'שיקום', EXTERNALS[1])
    scheduling.run_smart_scheduling(ctx, YEAR, MONTH)
    night.clear_month(ctx, YEAR, MONTH, only_auto=True)
    left = ctx.schedule[ctx.schedule['date'].astype(str).str.startswith(YM)]
    assert set(left['is_manual'].astype(str).str.upper()) == {'TRUE'}
    assert len(left) == 3
    night.manual_unassign(ctx, f"{YM}-28", 'שיקום')
    night.clear_month(ctx, YEAR, MONTH, only_auto=False)
    assert not ctx.schedule['date'].astype(str).str.startswith(YM).any()
    assert ctx.schedule['date'].astype(str).str.startswith('2026-10').sum() == 62


def test_swap_request_full_cycle(ctx):
    scheduling.run_smart_scheduling(ctx, YEAR, MONTH)
    s = ctx.schedule
    a = s[(s['dept'] == 'שיקום') & s['date'].str.startswith(YM) & (s['employee'] != '---')].iloc[5]
    b = s[(s['dept'] == 'שיקום') & s['date'].str.startswith(YM) & (s['employee'] != a['employee'])
          & (s['employee'] != '---')].iloc[10]
    night.create_swap_request(ctx, a['employee'], a['date'], 'שיקום', 'full', b['employee'],
                              their_shift={'date': b['date'], 'dept': 'שיקום'})
    pend = night.pending_swap_requests(ctx)
    assert len(pend) == 1 and pend[0]['swap_type'] == 'full'
    night.approve_swap_request(ctx, pend[0]['index'])
    s2 = ctx.schedule.set_index(['date', 'dept'])['employee']
    assert s2[(a['date'], 'שיקום')] == b['employee'] and s2[(b['date'], 'שיקום')] == a['employee']
    assert night.pending_swap_requests(ctx) == []
    assert ctx.store.sheets['swap_requests']['status'].tolist() == ['approved']


def test_admin_swap_options_are_valid(ctx):
    scheduling.run_smart_scheduling(ctx, YEAR, MONTH)
    target = ctx.schedule[(ctx.schedule['date'] == f"{YM}-17") & (ctx.schedule['dept'] == 'שיקום')].iloc[0]
    opts = night.admin_swap_options(ctx, target['date'], 'שיקום')
    assert opts['current'] == target['employee']
    for p in opts['direct']:
        assert night.check_assignment_validity(ctx, ctx.schedule, p, target['date'], 'שיקום', ctx.staff, ctx.requests,
                                               ignore_quota=True, ignore_home_restrict=True, ignore_rest=True)[0]
    if opts['direct']:
        night.execute_direct(ctx, target['date'], 'שיקום', opts['direct'][0])
        row = ctx.schedule[(ctx.schedule['date'] == target['date']) & (ctx.schedule['dept'] == 'שיקום')]
        assert row['employee'].tolist() == [opts['direct'][0]] and row['is_manual'].tolist() == [True]


def test_admin_availability_gate(ctx):
    show, avail, wished = night.admin_availability(ctx, YEAR, MONTH)
    assert show is False                                     # INTERNS[5] never submitted
    constraints.save_requests(ctx, INTERNS[5], YEAR, MONTH, [1], [], enforce_rules=False)
    show, avail, wished = night.admin_availability(ctx, YEAR, MONTH)
    assert show and INTERNS[5] not in avail[f"{YM}-01"]


# ── day schedule ─────────────────────────────────────────────────────────────
def test_cycle_cell_per_role(ctx):
    d = f"{YM}-02"
    assert daily.cycle_cell(ctx, d, INTERNS[3], "שיקום גריאטרי א'") == 'חופש'      # עובד→חופש
    assert daily.cycle_cell(ctx, d, INTERNS[3], "שיקום גריאטרי א'") == '202'
    assert daily.cycle_cell(ctx, f"{YM}-02", SENIORS[3], 'פנימית גריאטרית') in ('חופש',)
    assert daily.cycle_cell(ctx, f"{YM}-02", SENIORS[3], 'פנימית גריאטרית') == 'אחרי תורנות'   # no 202 for seniors
    assert daily.cycle_cell(ctx, f"{YM}-02", 'יעל כרמי', "שיקום גריאטרי א'") == ''          # manager toggles
    assert daily.cycle_cell(ctx, f"{YM}-02", 'יעל כרמי', "שיקום גריאטרי א'") == 'עובד'
    with pytest.raises(ValueError):
        daily.set_cell(ctx, d, SENIORS[3], 'פנימית גריאטרית', '202', '')
    daily.set_cell(ctx, d, INTERNS[3], "שיקום גריאטרי א'", 'אחר', ' קורס ')
    assert daily.wsd_get_note(ctx, d, INTERNS[3]) == 'קורס'


def test_dept_grid_model(ctx):
    from geri_core.people import grid_employees
    g = daily.dept_grid(ctx, 'פנימית גריאטרית', YM, MONTH, grid_employees(ctx, 'פנימית גריאטרית', YM))
    assert set(g['side_groups']) == {'ורוד', 'כחול'}
    noa = next(r for r in g['rows'] if r['employee'] == 'נועה ברק')                  # transfer, blue side
    assert noa['side'] == 'כחול' and noa['transfer_days'] == [10, 18]
    assert all(c['locked'] for c in noa['cells'] if c['day'] not in (10, 18))
    assert g['unassigned_side'], 'side-less senior must be surfaced'
    sat = next(d for d in g['days'] if d['weekday'] == 6)
    assert g['rows'][0]['cells'][sat['day'] - 1]['blank_weekend'] or g['rows'][0]['cells'][sat['day'] - 1]['locked']
    assert any(d['konenut'] for d in g['days'])


def test_deleted_employee_left_in_gantt_gets_no_grid_row(ctx):
    from geri_core import people
    from geri_core.people import grid_employees
    dept = 'פנימית גריאטרית'
    gone = next(e for e in grid_employees(ctx, dept, YM) if e not in people.get_dept_managers(ctx, dept))
    ctx.staff = ctx.staff[ctx.staff['name'].astype(str).str.strip() != gone]   # deleted; rotation row stays
    assert gone in people.dept_roster(ctx, dept, YM)
    assert gone not in grid_employees(ctx, dept, YM)
    g = daily.dept_grid(ctx, dept, YM, MONTH, grid_employees(ctx, dept, YM))
    assert gone not in [r['employee'] for r in g['rows']]


def test_temp_transfer_add_remove(ctx):
    daily.add_temp_transfer(ctx, f"{YM}-03", SENIORS[0], "שיקום גריאטרי ב'")
    assert 3 in daily.incoming_transfers(ctx, "שיקום גריאטרי ב'", YM)[SENIORS[0]]['days']
    assert daily.wsd_delete(ctx, f"{YM}-03", SENIORS[0])
    assert SENIORS[0] not in daily.incoming_transfers(ctx, "שיקום גריאטרי ב'", YM)


# ── absences ─────────────────────────────────────────────────────────────────
def test_employee_day_absence_submit(ctx):
    rows = absences.submit_day_absences(ctx, INTERNS[0], 'מתמחה', YEAR, MONTH, [24, 25], [26])
    assert {r['status'] for r in rows} == {'pending'} and len(rows) == 3
    assert ctx.mailer.sent and ctx.mailer.sent[-1][0] == 'm0@example.org'
    # resubmitting replaces this month's pending rows (incl. the fixture's 3-4 range)
    absences.submit_day_absences(ctx, INTERNS[0], 'מתמחה', YEAR, MONTH, [24], [])
    mine = ctx.absence_requests[(ctx.absence_requests['employee'] == INTERNS[0]) &
                                (ctx.absence_requests['status'] == 'pending')]
    assert mine['start_date'].tolist() == [f"{YM}-24"]
    with pytest.raises(ValueError):
        absences.submit_day_absences(ctx, SENIORS[0], 'רופא בכיר', YEAR, MONTH, [], [5])
    with pytest.raises(PermissionError):
        absences.submit_day_absences(ctx, INTERNS[1], 'מתמחה', YEAR, MONTH, [5], [], requests_open=False)


def test_manager_absence_auto_approved_to_board(ctx):
    rows = absences.submit_day_absences(ctx, 'יעל כרמי', 'מנהל מחלקה', YEAR, MONTH, [24], [], requests_open=False)
    assert rows[0]['status'] == 'approved' and rows[0]['approved_by'] == 'יעל כרמי'
    assert daily.derive_auto_status(ctx, f"{YM}-24", 'יעל כרמי', "שיקום גריאטרי א'") == 'חופש'


def test_future_and_preapproved(ctx):
    r = absences.submit_future_absence(ctx, INTERNS[1], '2026-12-20', '2026-12-22', 'חופש עתידי', 'x')
    assert r['type'] == 'חופש' and r['status'] == 'pending' and r['no_dept_warning']
    with pytest.raises(ValueError):
        absences.add_preapproved_absence(ctx, INTERNS[1], f"{YM}-10", f"{YM}-08", 'חופש', '', 'admin')
    absences.add_preapproved_absence(ctx, INTERNS[1], f"{YM}-23", f"{YM}-24", 'היעדרות אחרת', '', 'admin')
    assert daily.derive_auto_status(ctx, f"{YM}-23", INTERNS[1]) == 'אחר'


def test_pending_scope_for_manager_and_conflicts(ctx):
    allp = absences.pending_requests(ctx)
    assert len(allp) == 3
    conflict_row = next(p for p in allp if p['employee'] == INTERNS[0])
    assert conflict_row['conflicts'] and 'האם לאשר' in conflict_row['conflict_question']
    mine = absences.pending_requests(ctx, manager='יעל כרמי')
    # legacy rule: dept_at_request is theirs OR the employee was on their roster in ANY month
    _, _, roster = absences.manager_scope(ctx, 'יעל כרמי')
    assert INTERNS[0] in [p['employee'] for p in mine]
    assert all(p['dept_at_request'] == "שיקום גריאטרי א'" or p['employee'] in roster for p in mine)
    assert len(mine) < len(allp) or roster >= {p['employee'] for p in allp}
    assert len(absences.pending_requests(ctx, dept_filter='פנימית גריאטרית')) == 2
    dl = absences.deletable_approved(ctx, manager_depts=["שיקום גריאטרי א'"])
    assert all("שיקום גריאטרי א'" in d['label'] for d in dl)


def test_absence_gantt_overlaps(ctx):
    g = absences.absence_gantt(ctx, YEAR, MONTH)
    assert g['by_dept']
    for (dept, day), emps in g['conflicts'].items():
        assert len(emps) >= 2
    mine = absences.absence_gantt(ctx, YEAR, MONTH, dept_filter={'פנימית גריאטרית'})
    assert set(mine['by_dept']) <= {'פנימית גריאטרית'}


def test_my_absence_calendar(ctx):
    cal = absences.my_absence_calendar(ctx, INTERNS[6], YEAR, MONTH)
    assert cal['approved_future'] == [16, 17, 18, 19]
    cal0 = absences.my_absence_calendar(ctx, INTERNS[0], YEAR, MONTH)
    assert cal0['pending'] == [3, 4] and 5 in cal0['night_shift'] and 6 in cal0['post_shift']


# ── admin ────────────────────────────────────────────────────────────────────
def test_settings(ctx):
    admin.make_daily_month_active(ctx, 12)
    m = admin.active_months(ctx)
    assert m['daily_active_month'] == 12 and m['daily_requests_open']
    admin.set_setting(ctx, 'daily_requests_open', 'False')
    assert admin.active_months(ctx)['daily_requests_open'] is False
    assert len(admin.rolling_months()) == 12


def test_gantt_save_validates_and_migrates(ctx):
    rows = admin.gantt_rows(ctx, YM)
    assign = {r['name']: r['dept'] or "שיקום גריאטרי א'" for r in rows}
    sides = {r['name']: r['side'] for r in rows}
    for n, d in assign.items():
        if d == 'פנימית גריאטרית' and not sides.get(n):
            sides[n] = 'ורוד'
    assign['רוני אבן'] = 'פנימית גריאטרית'
    sides['רוני אבן'] = ''
    with pytest.raises(ValueError, match='חובה לבחור צד'):
        admin.save_gantt(ctx, YM, assign, sides)
    sides['רוני אבן'] = 'ורוד'
    assign[INTERNS[0]] = 'פנימית גריאטרית'                 # שיקום א' → פנימית: pending request migrates
    sides[INTERNS[0]] = 'כחול'
    out = admin.save_gantt(ctx, YM, assign, sides)
    assert out['migrated'] == 1
    req = ctx.absence_requests[(ctx.absence_requests['employee'] == INTERNS[0]) &
                               (ctx.absence_requests['status'] == 'pending')].iloc[0]
    assert req['dept_at_request'] == 'פנימית גריאטרית'
    assert len(ctx.dept_rotation[ctx.dept_rotation['year_month'] == '2026-10']) == 16   # other months untouched


def test_gantt_manager_limited_to_managed_depts(ctx):
    rows = {r['name']: r for r in admin.gantt_rows(ctx, YM)}
    assert rows['יעל כרמי']['options'] == ["שיקום גריאטרי א'", '— לא שובץ —']
    assert 'רון צליק' not in rows                              # manual-plant-only manager


def test_konenut(ctx):
    assert 'דפנה ירון' in admin.konenut_doctors(ctx) and INTERNS[0] not in admin.konenut_doctors(ctx)
    admin.save_konenut_day(ctx, f"{YM}-20", 'דפנה ירון', '', 'עידו נחום')
    month = {d['date']: d for d in admin.konenut_month(ctx, YEAR, MONTH)}
    assert month[f"{YM}-20"]['rehab_dr2'] == 'עידו נחום'
    days = admin.konenut_month(ctx, YEAR, MONTH)
    days[0]['pnim_dr'] = 'חופשי '
    admin.save_konenut_month(ctx, YEAR, MONTH, days)
    assert admin.konenut_month(ctx, YEAR, MONTH)[0]['pnim_dr'] == 'חופשי'


def test_special_days(ctx):
    admin.add_special_day(ctx, f"{YM}-30", 'חג', 'כמו שבת (חג)')
    assert daily.derive_auto_status(ctx, f"{YM}-30", INTERNS[1]) == 'חופש'
    with pytest.raises(ValueError):
        admin.add_special_day(ctx, f"{YM}-29", '', 'כמו שבת (חג)')
    admin.delete_special_day(ctx, len(ctx.special_days) - 1)
    assert f"{YM}-30" not in ctx.store.sheets['special_days']['date'].tolist()


def test_init_db_is_additive(ctx):
    store = ctx.store
    store.sheets['settings'] = pd.DataFrame([{'key': 'active_month', 'value': '3'}])
    del store.sheets['konenut']
    admin.init_db(store)
    keys = store.sheets['settings']['key'].tolist()
    assert keys[0] == 'active_month' and store.sheets['settings']['value'].iloc[0] == '3'
    assert {'daily_active_month', 'daily_requests_open'} <= set(keys)


# ── exports / reports ────────────────────────────────────────────────────────
def test_export_dept_to_sheet(ctx):
    url = exports.export_dept_to_sheet(ctx, 'פנימית גריאטרית', YM, MONTH)
    name = exports.wsd_sheet_name('פנימית גריאטרית', YM)
    assert url == f"memory://{name}" and name in ctx.store.rtl


def test_reports(ctx):
    sub = reports.submission_status(ctx, YEAR, MONTH)
    assert sub['total'] == 16 and sub['pending'] == 1
    scheduling.run_smart_scheduling(ctx, YEAR, MONTH)
    assert reports.shift_counts(ctx, YEAR, MONTH)
    assert reports.fairness(ctx)[0]['net'] >= reports.fairness(ctx)[-1]['net']
    probs = reports.run_problem_scan(ctx, YEAR, MONTH, analyze=lambda *a: [
        {'severity': 'אזהרה', 'problem_type': 'ימי שיא חסימה', 'description': 'x'},
        {'severity': 'קריטי', 'problem_type': 'ימי שיא חסימה', 'description': 'y'}])
    rep = reports.problem_report(ctx)
    assert rep['headline'] == {'critical': 1, 'warning': 1} and rep['rows'][0]['severity'] == 'קריטי'
    assert len(probs) == 2


def test_analytics(ctx):
    sess = {'session_id': 's', 'user_name': 'נועה ברק', 'user_role': 'מתמחה', 'device_type': 'mobile', 'active_month': 11}
    reports.log_event(ctx.store, 'login_success', 'mobile', '390', session=sess)
    reports.log_event(ctx.store, 'constraint_submit', '4', '2', session=sess)
    a = reports.analytics_summary(ctx, YEAR, MONTH)
    assert a['kpi']['logins'] == 1 and a['kpi']['mobile_pct'] == 100
    assert a['per_user'][0]['submits'] == 1


def test_tabs_per_role():
    assert tabs_for_role('מנהל על') == ['הגדרות', 'סידור תורנויות', 'צוות', 'דוחות וניהול', 'סידור כוננויות',
                                         'גאנט חודשי', 'סידור עבודה', 'ניהול בקשות']
    assert tabs_for_role('מנהל/ת') == ['הגדרות', 'סידור כוננויות', 'גאנט חודשי', 'סידור עבודה', 'ניהול בקשות']
    assert tabs_for_role('מנהל מחלקה') == ['הגדרות', 'סידור עבודה', 'ניהול בקשות']
    assert tabs_for_role('מתמחה') == ['הגדרות', 'סידור תורנויות', 'הגשת בקשות', 'סידור עבודה']
    assert tabs_for_role('רופא בכיר') == ['הגדרות', 'הגשת בקשות', 'סידור עבודה']
    assert tabs_for_role('תורן חוץ') == ['הגדרות', 'סידור תורנויות', 'הגשת בקשות']
    assert default_tab_for_role('תורן חוץ') == 'הגשת בקשות'


def test_night_calendar_privacy(ctx):
    scheduling.run_smart_scheduling(ctx, YEAR, MONTH)
    emp = night.night_calendar(ctx, YEAR, MONTH, INTERNS[1], is_admin=False)
    names = {s['employee'] for v in emp['slots'].values() for s in v}
    assert names <= {INTERNS[1], '---'}
    assert 'requests' not in emp and all(not s['empty_reason'] for v in emp['slots'].values() for s in v)
    adm = night.night_calendar(ctx, YEAR, MONTH, 'ענבל רז', is_admin=True)
    assert len({s['employee'] for v in adm['slots'].values() for s in v}) > 5
    assert adm['requests'] and 'availability' in adm and len(adm['special_days']) == 3


def test_wsd_write_keeps_other_years(frames):
    """appy.py drops non-2026 WSD rows on the next write; the port must not."""
    from geri_core import DataContext, MemoryStore
    frames['work_schedule_daily'] = pd.concat([frames['work_schedule_daily'], pd.DataFrame([
        {'date': '2027-01-05', 'employee': INTERNS[1], 'daily_dept': "שיקום גריאטרי ב'", 'status': 'חופש',
         'note': '', 'is_manual': 'True', 'side': ''}])], ignore_index=True)
    store = MemoryStore(frames)
    ctx = DataContext.load(store)
    daily.wsd_upsert(ctx, f"{YM}-02", INTERNS[2], 'פנימית גריאטרית', 'אחר')
    assert '2027-01-05' in store.sheets['work_schedule_daily']['date'].tolist()
    legacy_like = DataContext.load(MemoryStore(frames), wsd_year_prefix='2026')
    daily.wsd_upsert(legacy_like, f"{YM}-02", INTERNS[2], 'פנימית גריאטרית', 'אחר')
    assert '2027-01-05' not in legacy_like.store.sheets['work_schedule_daily']['date'].tolist()   # the bug
