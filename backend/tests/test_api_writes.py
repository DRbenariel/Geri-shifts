"""Write endpoints: read-only gate, role/scope checks, conflict confirmation, legacy password hashes.

Uses an in-memory store with writes enabled; nothing here touches a real Sheet.
"""
import hashlib

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app
from api.store import READ_ONLY_MSG
from fixtures import ADMINS, EXTERNALS, INTERNS, MANAGERS, SENIORS, build
from geri_core import MemoryStore
from geri_core import staff as core_staff

SECRET = "w" * 40
PW = "pw-123"
SHA = hashlib.sha256(PW.encode()).hexdigest()
SUPER, ADMIN = ADMINS[0][0], ADMINS[1][0]
MGR_A = MANAGERS[0][0]                       # שיקום גריאטרי א'


@pytest.fixture
def store():
    frames = build()
    frames['staff']['password'] = SHA
    return MemoryStore(frames)


def _client(store, read_only):
    app = create_app(Settings(session_secret=SECRET, read_only=read_only, cookie_secure=False),
                     store_factory=lambda: store)
    return TestClient(app)


@pytest.fixture
def rw(store):
    yield _client(store, read_only=False)
    core_staff.use_legacy_hashes(False)


def as_(client, name):
    client.post("/api/auth/logout")
    assert client.post("/api/auth/login", json={"username": name, "password": PW}).status_code == 200
    return client


def test_read_only_gate_refuses_every_write(store):
    ro = _client(store, read_only=True)
    as_(ro, SUPER)                                           # login still works
    for method, path, body in [("POST", "/api/me/password", {"current": PW, "new": "a", "confirm": "a"}),
                               ("PUT", "/api/settings/active_month", {"month": 3}),
                               ("POST", "/api/night/2026-11/auto", {})]:
        r = ro.request(method, path, json=body)
        assert r.status_code == 403 and r.json()['detail'] == READ_ONLY_MSG
    assert store.read('staff')['password'].iloc[0] == SHA     # nothing changed


def test_password_change_stays_sha256_while_streamlit_runs(rw, store):
    as_(rw, INTERNS[0])
    r = rw.post("/api/me/password", json={"current": PW, "new": "new-pw", "confirm": "new-pw"})
    assert r.status_code == 200, r.text
    row = store.read('staff')
    stored = row[row['name'].str.strip() == INTERNS[0].strip()]['password'].iloc[0]
    assert stored == hashlib.sha256(b"new-pw").hexdigest()
    assert rw.post("/api/me/password", json={"current": "bad", "new": "x", "confirm": "x"}).status_code == 400


def test_new_employee_gets_sha256_default_password(rw, store):
    as_(rw, SUPER)
    r = rw.post("/api/staff", json={"name": "עובד חדש", "type": "מתמחה", "dept": "שיקום"})
    assert r.status_code == 200, r.text
    st = store.read('staff')
    assert st[st['name'] == "עובד חדש"]['password'].iloc[0] == hashlib.sha256(b"1234").hexdigest()


def test_constraints_only_for_the_open_month(rw):
    as_(rw, EXTERNALS[0])
    s = rw.get("/api/me").json()['settings']
    ym = f"{s['active_year']}-{s['active_month']:02d}"
    assert rw.put(f"/api/constraints/{ym}", json={"blocked": [3], "wishes": [5]}).status_code == 200
    assert rw.get(f"/api/constraints/{ym}").json() == {"employee": EXTERNALS[0], "blocked": [3], "wishes": [5]}
    other = f"{s['active_year'] + 1}-{s['active_month']:02d}"
    assert rw.put(f"/api/constraints/{other}", json={"blocked": [3]}).status_code == 403
    r = rw.put(f"/api/constraints/{ym}", json={"blocked": [], "wishes": [1, 2, 3]})
    assert r.status_code == 400                                           # more than 2 wishes
    # an employee can't read or write someone else's constraints
    assert rw.get(f"/api/constraints/{ym}?employee={INTERNS[0]}").json()['employee'] == EXTERNALS[0]


def test_superadmin_edits_any_employee_without_rules(rw):
    as_(rw, SUPER)
    r = rw.put("/api/constraints/2026-11", json={"employee": INTERNS[1], "blocked": [1, 2, 3, 4, 5], "wishes": []})
    assert r.status_code == 200, r.text
    assert rw.put("/api/constraints/2026-11", json={"blocked": [1], "wishes": [1]}).status_code == 400   # no employee


def _pending_ids(client):
    return [r['id'] for r in client.get("/api/absences/pending").json()]


def test_approve_needs_scope_and_confirms_conflicts(rw, store):
    as_(rw, SUPER)
    all_ids = _pending_ids(rw)
    assert all_ids
    as_(rw, MANAGERS[1][0])                                # שיקום ב׳: some pending requests are outside
    mine = set(_pending_ids(rw))
    outside = [i for i in all_ids if i not in mine]
    assert outside and mine
    assert rw.post(f"/api/absences/{outside[0]}/approve", json={}).status_code == 403
    assert rw.post(f"/api/absences/{outside[0]}/reject").status_code == 403
    as_(rw, SUPER)
    rid = all_ids[0]
    r = rw.post(f"/api/absences/{rid}/approve", json={})
    if r.status_code == 409:                                  # overlap: same question as Streamlit
        assert r.json()['detail']
        r = rw.post(f"/api/absences/{rid}/approve", json={"force": True})
    assert r.status_code == 200, r.text
    ar = store.read('absence_requests')
    assert ar[ar['id'].astype(str) == str(rid)]['status'].iloc[0] == 'approved'
    assert rw.post("/api/absences/nope/approve", json={}).status_code == 404


def test_employee_cannot_manage_absences(rw):
    as_(rw, INTERNS[0])
    assert rw.post("/api/absences/x/approve", json={}).status_code == 403
    assert rw.post("/api/absences", json={"employee": INTERNS[1], "start": "2026-11-02",
                                          "end": "2026-11-02", "type": "חופש"}).status_code == 403


def test_work_cell_scope(rw):
    as_(rw, MGR_A)
    grid = rw.get("/api/work/שיקום גריאטרי א'/2026-11").json()
    emp = next(r['employee'] for r in grid['rows'] if r['employee'] != MGR_A)
    ok = rw.post("/api/work/cell/cycle", json={"dept": "שיקום גריאטרי א'", "date": "2026-11-03", "employee": emp})
    assert ok.status_code == 200, ok.text
    assert rw.post("/api/work/cell/cycle", json={"dept": "פנימית גריאטרית", "date": "2026-11-03",
                                                 "employee": INTERNS[0]}).status_code == 403
    assert rw.post("/api/work/cell/cycle", json={"dept": "שיקום גריאטרי א'", "date": "2026-11-03",
                                                 "employee": "לא קיים"}).status_code == 400
    as_(rw, SENIORS[0])
    assert rw.post("/api/work/cell/cycle", json={"dept": "שיקום גריאטרי א'", "date": "2026-11-03",
                                                 "employee": SENIORS[0]}).status_code == 403


def test_swaps_only_for_own_shift_and_server_found_options(rw, store):
    sched = store.read('schedule')
    shift = sched[sched['employee'].astype(str).str.strip() == INTERNS[1].strip()].iloc[0]
    as_(rw, INTERNS[1])
    res = rw.get("/api/swaps/search", params={"date": shift['date'], "dept": shift['dept']})
    assert res.status_code == 200, res.text
    assert rw.post("/api/swaps", json={"date": shift['date'], "dept": shift['dept'], "kind": "partial",
                                       "candidate": "מישהו מומצא"}).status_code == 400
    other = sched[(sched['employee'].astype(str).str.strip() != INTERNS[1].strip()) & (sched['employee'] != '---')].iloc[0]
    assert rw.get("/api/swaps/search", params={"date": other['date'], "dept": other['dept']}).status_code == 403
    body = res.json()
    assert body['partial']
    c = body['partial'][0]['name']
    ok = rw.post("/api/swaps", json={"date": shift['date'], "dept": shift['dept'], "kind": "partial", "candidate": c})
    assert ok.status_code == 200, ok.text
    dup = rw.post("/api/swaps", json={"date": shift['date'], "dept": shift['dept'], "kind": "partial", "candidate": c})
    assert dup.status_code == 409


def test_special_days_and_settings_superadmin_only(rw, store):
    as_(rw, ADMIN)
    assert rw.post("/api/special-days", json={"date": "2026-12-24", "description": "x", "day_type": "לידיעה בלבד"}).status_code == 403
    assert rw.put("/api/settings/active_month", json={"month": 12}).status_code == 403
    as_(rw, SUPER)
    n = len(store.read('special_days'))
    assert rw.post("/api/special-days", json={"date": "2026-12-24", "description": "ערב חג", "day_type": "לידיעה בלבד"}).status_code == 200
    assert len(store.read('special_days')) == n + 1
    assert rw.post("/api/special-days", json={"date": "2026-12-24", "description": "x", "day_type": "סתם"}).status_code == 400
    assert rw.put("/api/settings/active_month", json={"month": 12}).json()['active_month'] == 12


def test_manual_night_assign_refuses_blocked_employee(rw, store):
    req = store.read('requests')
    blk = req[req['status'] == 'אילוץ'].iloc[0]
    as_(rw, SUPER)
    r = rw.put("/api/night/slot", json={"date": blk['date'], "dept": "שיקום", "employee": blk['employee']})
    assert r.status_code == 400 and "אילוץ" in r.json()['detail']
    assert rw.put("/api/night/slot", json={"date": "2026-11-03", "dept": "לא קיים", "employee": INTERNS[0]}).status_code == 400


def test_cell_undo_restores_computed_status(rw):
    as_(rw, MGR_A)
    dept = "שיקום גריאטרי א'"
    grid = rw.get(f"/api/work/{dept}/2026-11").json()
    row = next(r for r in grid['rows'] if r['employee'] != MGR_A)
    cell = next(c for c in row['cells'] if not c['manual'] and not c['locked'] and c['status'] not in ('תורנות', None))
    body = {"dept": dept, "date": f"2026-11-{cell['day']:02d}", "employee": row['employee']}
    assert rw.post("/api/work/cell/cycle", json=body).status_code == 200
    assert rw.request("DELETE", "/api/work/cell", json=body).status_code == 200
    after = rw.get(f"/api/work/{dept}/2026-11").json()
    c2 = next(r for r in after['rows'] if r['employee'] == row['employee'])['cells'][cell['day'] - 1]
    assert c2['status'] == cell['status'] and not c2['manual']
    as_(rw, SENIORS[0])
    assert rw.request("DELETE", "/api/work/cell", json=body).status_code == 403


XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def test_excel_exports_respect_scope(rw):
    as_(rw, MGR_A)
    r = rw.get("/api/export/work/שיקום גריאטרי א'/2026-11")
    assert r.status_code == 200 and r.headers['content-type'] == XLSX and r.content[:2] == b'PK'
    assert "filename*=UTF-8''" in r.headers['content-disposition']
    assert rw.get("/api/export/work/פנימית גריאטרית/2026-11").status_code == 403
    assert rw.get("/api/export/work-all/2026-11").status_code == 403
    as_(rw, SUPER)
    assert rw.get("/api/export/work-all/2026-11").headers['content-type'] == XLSX
    assert rw.get("/api/export/work/לא קיים/2026-11").status_code == 404
    as_(rw, INTERNS[1])
    assert rw.get("/api/export/work/שיקום גריאטרי א'/2026-11").status_code == 403
    assert rw.get("/api/export/me/2026-11").headers['content-type'] == XLSX


def test_excel_export_works_in_read_only_but_sheet_export_does_not(store):
    ro = _client(store, read_only=True)
    as_(ro, MGR_A)
    assert ro.get("/api/export/work/שיקום גריאטרי א'/2026-11").status_code == 200
    r = ro.post("/api/export/work/שיקום גריאטרי א'/2026-11/sheet")
    assert r.status_code == 403 and r.json()['detail'] == READ_ONLY_MSG


def test_sheet_export_writes_tab_and_returns_url(rw, store):
    as_(rw, MGR_A)
    r = rw.post("/api/export/work/שיקום גריאטרי א'/2026-11/sheet")
    assert r.status_code == 200, r.text
    assert r.json()['url'].startswith("memory://WSD_")
    assert any(n.startswith("WSD_") for n in store.sheets)
    assert rw.post("/api/export/work/פנימית גריאטרית/2026-11/sheet").status_code == 403


def test_temp_transfer_roundtrip(rw, store):
    dept = "שיקום גריאטרי א'"
    as_(rw, MGR_A)
    grid = rw.get(f"/api/work/{dept}/2026-11").json()
    assert grid['editable'] and grid['transfer_candidates']
    on_board = {r['employee'] for r in grid['rows']}
    who = next(n for n in grid['transfer_candidates'] if n not in on_board and n in INTERNS)
    body = {"dept": dept, "date": "2026-11-04", "employee": who}
    assert rw.post("/api/work/transfer", json=body).status_code == 200
    after = rw.get(f"/api/work/{dept}/2026-11").json()
    assert after['transfers'][who]['days'] == [4]
    assert rw.request("DELETE", "/api/work/transfer", json=body).status_code == 200
    assert who not in rw.get(f"/api/work/{dept}/2026-11").json()['transfers']
    ro = _client(store, read_only=True)
    as_(ro, MGR_A)
    g = ro.get(f"/api/work/{dept}/2026-11").json()
    assert g['editable'] is False and g['transfer_candidates']           # form still shown while read-only
    assert ro.post("/api/work/transfer", json=body).status_code == 403
    as_(ro, SENIORS[0])
    mine = ro.get("/api/work/me/2026-11").json()['dept']
    if mine:
        assert ro.get(f"/api/work/{mine}/2026-11").json()['transfer_candidates'] is None


def test_clear_month_auto_keeps_manual(rw, store):
    as_(rw, SUPER)
    assert rw.put("/api/night/slot", json={"date": "2026-11-05", "dept": "שיקום", "employee": EXTERNALS[0]}).status_code == 200
    before = store.read('schedule')
    before = before[before['date'].astype(str).str.startswith('2026-11')]
    manual = before[before['is_manual'].astype(str).str.upper() == 'TRUE']
    assert len(manual) < len(before)                          # the month has auto rows to clear
    assert rw.post("/api/night/2026-11/clear", json={"mode": "auto"}).status_code == 200
    s = store.read('schedule')
    nov = s[s['date'].astype(str).str.startswith('2026-11')]
    assert len(nov) == len(manual) and EXTERNALS[0] in set(nov['employee'])
    assert rw.post("/api/night/2026-11/clear", json={"mode": "all"}).status_code == 200
    s = store.read('schedule')
    assert not s['date'].astype(str).str.startswith('2026-11').any()
    as_(rw, ADMIN)
    assert rw.post("/api/night/2026-11/clear", json={"mode": "all"}).status_code == 403
