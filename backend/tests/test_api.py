"""API layer: login/session, tabs per role, server-side permission checks, read-only guard."""
import hashlib

import pytest
from fastapi.testclient import TestClient

from api import session
from api.config import Settings
from api.main import create_app
from fixtures import ADMINS, EXTERNALS, INTERNS, MANAGERS, SENIORS, build
from geri_core import MemoryStore

SECRET = "t" * 40
PW = "pw-123"


@pytest.fixture
def store():
    frames = build()
    frames['staff']['password'] = hashlib.sha256(PW.encode()).hexdigest()
    return MemoryStore(frames)


@pytest.fixture
def client(store):
    app = create_app(Settings(session_secret=SECRET, read_only=True, cookie_secure=False), store_factory=lambda: store)
    return TestClient(app)


def login(client, name, pw=PW):
    return client.post("/api/auth/login", json={"username": name, "password": pw})


USERS = {
    'מנהל על': ADMINS[0][0], 'מנהל/ת': ADMINS[1][0], 'מנהל מחלקה': MANAGERS[0][0],
    'רופא בכיר': SENIORS[0], 'מתמחה': INTERNS[0], 'תורן חוץ': EXTERNALS[0],
}
TABS = {
    'מנהל על': ['settings', 'night', 'staff', 'reports', 'oncall', 'gantt', 'work', 'requests'],
    'מנהל/ת': ['settings', 'oncall', 'gantt', 'work', 'requests'],
    'מנהל מחלקה': ['settings', 'work', 'requests'],
    'רופא בכיר': ['settings', 'submit', 'work'],
    'מתמחה': ['settings', 'night', 'submit', 'work'],
    'תורן חוץ': ['settings', 'night', 'submit'],
}
HOME = {'מנהל על': 'reports', 'מנהל/ת': 'gantt', 'מנהל מחלקה': 'work', 'רופא בכיר': 'work',
        'מתמחה': 'submit', 'תורן חוץ': 'submit'}


def test_session_token_roundtrip_and_tamper():
    t = session.sign(SECRET, "נועה ברק", now=1000)
    assert session.verify(SECRET, t, now=1001) == "נועה ברק"
    assert session.verify(SECRET, t, now=1000 + session.MAX_AGE + 1) is None      # expired
    assert session.verify("other" * 10, t, now=1001) is None                       # wrong key
    payload, mac = t.rsplit(".", 1)
    forged = session.sign(SECRET, "ענבל רז", now=1000).rsplit(".", 1)[0]
    assert session.verify(SECRET, f"{forged}.{mac}", now=1001) is None             # swapped payload


@pytest.mark.parametrize("role", list(USERS))
def test_login_returns_role_tabs(client, role):
    r = login(client, USERS[role])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body['role'] == role
    assert body['tabs'] == TABS[role]
    assert body['home'] == HOME[role]
    assert {'active_month', 'active_year', 'daily_active_month', 'daily_active_year'} <= set(body['settings'])
    assert client.get("/api/me").json()['name'] == USERS[role].strip()


def test_login_errors_and_no_hash_upgrade(client, store):
    assert login(client, "אין כזה").json()['detail'] == "שם המשתמש לא נמצא במערכת"
    assert login(client, INTERNS[0], "wrong").json()['detail'] == "סיסמה שגויה"
    assert login(client, INTERNS[0]).status_code == 200
    # Streamlit still reads SHA-256 only, so the API must not rewrite password hashes.
    assert not str(store.read('staff')['password'].iloc[0]).startswith('$2')


def test_requires_session(client):
    assert client.get("/api/me").status_code == 401
    client.cookies.set(session.COOKIE, "garbage.value")
    assert client.get("/api/me").status_code == 401


def test_no_session_is_refused_before_any_sheet_read(store):
    loads = []
    app = create_app(Settings(session_secret=SECRET, read_only=True, cookie_secure=False),
                     store_factory=lambda: loads.append(1) or store)
    c = TestClient(app)
    assert c.get("/api/me").status_code == 401
    c.cookies.set(session.COOKIE, "garbage.value")
    assert c.get("/api/night/2026-11").status_code == 401
    assert loads == []


def test_sheet_load_is_shared_across_requests_and_cleared_by_writes(store):
    loads = []

    class Counting:
        def read_many(self, names):
            loads.append(1)
            return {n: store.read(n) for n in names}

        def __getattr__(self, k):
            return getattr(store, k)

    app = create_app(Settings(session_secret=SECRET, read_only=True, cookie_secure=False, cache_seconds=60),
                     store_factory=Counting)
    c = TestClient(app)
    assert login(c, INTERNS[0]).status_code == 200            # login writes nothing: cache kept
    assert c.get("/api/me").status_code == 200
    assert c.get("/api/me").status_code == 200
    assert len(loads) == 1


def test_quota_error_is_not_retried_by_every_queued_request(store):
    import gspread
    from types import SimpleNamespace
    calls = []

    class OverQuota:
        def read_many(self, names):
            calls.append(1)
            raise gspread.exceptions.APIError(SimpleNamespace(
                status_code=429, json=lambda: {'error': {'code': 429, 'message': 'quota', 'status': 'x'}},
                text='quota'))

    app = create_app(Settings(session_secret=SECRET, read_only=True, cookie_secure=False, cache_seconds=60),
                     store_factory=OverQuota)
    c = TestClient(app)
    for _ in range(4):
        r = login(c, INTERNS[0])
        assert r.status_code == 503 and r.json()['detail'] == "המערכת עמוסה כרגע. נסה/י שוב בעוד דקה."
    assert len(calls) == 1


def test_store_writes_clear_the_cache():
    from api.store import CacheClearingStore
    cleared = []
    s = CacheClearingStore(MemoryStore(), lambda: cleared.append(1))
    s.read('staff')
    assert cleared == []
    s.write('staff', build()['staff'])
    s.append_row('analytics_log', ['a'], header=['x'])
    assert len(cleared) == 2


def test_gsheet_read_many_pads_rows_and_skips_missing_tabs():
    from types import SimpleNamespace
    from geri_core.store import GSheetStore

    class FakeSheet:
        def worksheets(self):
            return [SimpleNamespace(title='staff'), SimpleNamespace(title='settings')]

        def values_batch_get(self, ranges):
            assert ranges == ["'staff'", "'settings'"]
            return {'valueRanges': [{'values': [['name', 'type', 'email'], ['א', 'מתמחה']]}, {}]}

    s = GSheetStore({}, "")
    s._sh = FakeSheet()
    got = s.read_many(('staff', 'swap_requests', 'settings'))
    assert got['staff'].to_dict('records') == [{'name': 'א', 'type': 'מתמחה', 'email': ''}]
    assert got['swap_requests'].empty and got['settings'].empty


def test_logout(client):
    login(client, INTERNS[0])
    client.post("/api/auth/logout")
    assert client.get("/api/me").status_code == 401


@pytest.mark.parametrize("role, path, code", [
    ('מתמחה', "/api/staff", 403),
    ('מתמחה', "/api/reports/2026-11", 403),
    ('מתמחה', "/api/absences/pending", 403),
    ('תורן חוץ', "/api/work/פנימית גריאטרית/2026-11", 403),
    ('מנהל/ת', "/api/night/2026-11", 403),
    ('רופא בכיר', "/api/night/2026-11", 403),
    ('מנהל מחלקה', "/api/gantt/2026-11", 403),
    ('מנהל על', "/api/staff", 200),
    ('מנהל/ת', "/api/gantt/2026-11", 200),
    ('מנהל/ת', "/api/oncall/2026-11", 200),
])
def test_role_permissions(client, role, path, code):
    login(client, USERS[role])
    assert client.get(path).status_code == code


def test_night_privacy(client):
    login(client, INTERNS[0])
    body = client.get("/api/night/2026-11").json()
    me = INTERNS[0].strip()
    for rows in body['slots'].values():
        assert all(r['employee'] in (me, '---') for r in rows)
        assert all(r['empty_reason'] == '' for r in rows)
    assert 'requests' not in body and 'availability' not in body
    client.post("/api/auth/logout")
    login(client, USERS['מנהל על'])
    admin = client.get("/api/night/2026-11").json()
    assert 'requests' in admin and 'availability' in admin


def test_work_scope(client):
    login(client, USERS['מנהל מחלקה'])                      # manages שיקום גריאטרי א'
    assert client.get("/api/work/שיקום גריאטרי א'/2026-11").status_code == 200
    assert client.get("/api/work/פנימית גריאטרית/2026-11").status_code == 403
    client.post("/api/auth/logout")
    login(client, INTERNS[1])
    mine = client.get("/api/work/me/2026-11").json()['dept']
    assert mine
    grid = client.get(f"/api/work/{mine}/2026-11")
    assert grid.status_code == 200 and grid.json()['editable'] is False
    other = next(d for d in ["שיקום גריאטרי א'", "שיקום גריאטרי ב'", 'פנימית גריאטרית'] if d != mine)
    assert client.get(f"/api/work/{other}/2026-11").status_code == 403


def test_bad_month(client):
    login(client, USERS['מנהל על'])
    assert client.get("/api/night/2026-13").status_code == 400
    assert client.get("/api/night/nov").status_code == 400


def test_read_only_store_blocks_writes(store):
    from api.store import ReadOnlyError, ReadOnlyStore
    ro = ReadOnlyStore(store)
    assert not ro.read('staff').empty
    with pytest.raises(ReadOnlyError):
        ro.write('staff', ro.read('staff'))


@pytest.mark.parametrize("role, path", [
    ('מנהל על', "/api/reports/2026-11"),
    ('מנהל על', "/api/swaps/pending"),
    ('מנהל על', "/api/special-days"),
    ('מנהל על', "/api/absences/pending"),
    ('מנהל על', "/api/absences/gantt/2026-11"),
    ('מנהל/ת', "/api/work/פנימית גריאטרית/2026-11"),
    ('מנהל מחלקה', "/api/absences/pending"),
    ('מנהל מחלקה', "/api/absences/gantt/2026-11"),
    ('מתמחה', "/api/absences/me/2026-11"),
    ('רופא בכיר', "/api/absences/me/2026-11"),
    ('תורן חוץ', "/api/night/2026-11"),
    ('מתמחה', "/api/night/2027-01"),          # a month with no data yet
    ('מתמחה', "/api/swaps/mine"),
    ('מנהל מחלקה', "/api/people"),
])
def test_read_endpoints_serialize(client, role, path):
    login(client, USERS[role])
    r = client.get(path)
    assert r.status_code == 200, r.text
    assert r.headers['content-type'].startswith('application/json')


def test_people_scoped_for_manager(client):
    login(client, USERS['מנהל על'])
    everyone = {r['name'] for r in client.get("/api/people").json()}
    client.post("/api/auth/logout")
    login(client, USERS['מנהל מחלקה'])
    mine = {r['name'] for r in client.get("/api/people").json()}
    assert mine and mine < everyone and USERS['מנהל מחלקה'] in mine
    client.post("/api/auth/logout")
    login(client, USERS['מתמחה'])
    assert client.get("/api/people").status_code == 403


def test_report_shift_split(client):
    login(client, USERS['מנהל על'])
    rows = client.get("/api/reports/2026-11").json()['shift_counts']
    assert rows and set(rows[0]) == {'employee', 'sh', 'pn', 'fri'}


def test_report_fairness_table(client, store):
    from geri_core import DataContext, reports
    login(client, USERS['מנהל על'])
    rows = client.get("/api/reports/2026-11").json()['fairness']
    assert rows and set(rows[0]) == {'name', 'wed', 'thu', 'friday_morning', 'net'}
    assert rows == reports.fairness(DataContext.load(store))
    assert all(r['net'] == r['wed'] - (r['thu'] + r['friday_morning']) for r in rows)
    assert [r['net'] for r in rows] == sorted((r['net'] for r in rows), reverse=True)
