"""DataContext: everything appy.py kept in st.session_state, without Streamlit.

One context is built per API request (`DataContext.load(store)`), so every
request sees fresh sheet data. Derived indexes (`wsd_index`, `approved_map`)
are rebuilt lazily whenever their source frame is replaced — the equivalent of
appy's `_rebuild_wsd_index()` / `_build_approved_map()` calls.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from .constants import ABSENCE_TYPE_TO_STATUS, SHEET_COLUMNS
from .normalize import is_true, norm_dr
from .store import SheetStore

_INDEXED = {'work_schedule_daily': '_wsd_index', 'absence_requests': '_approved_map'}


class DataContext:
    FRAMES = ('staff', 'schedule', 'requests', 'special_days', 'swap_requests', 'konenut',
              'dept_rotation', 'absence_requests', 'work_schedule_daily', 'settings')

    # wsd_year_prefix: appy.py loads only '2026' WSD rows and then saves the whole
    # session frame back — which silently deletes every other year's rows on the
    # next write. Default None loads all years so a save never drops data.
    def __init__(self, store: SheetStore | None = None, mailer=None, wsd_year_prefix: str | None = None):
        self.store = store
        self.mailer = mailer
        self.wsd_year_prefix = wsd_year_prefix
        self._wsd_index = None
        self._approved_map = None
        for f in self.FRAMES:
            object.__setattr__(self, f, pd.DataFrame())

    # Replacing a source frame invalidates its derived index.
    def __setattr__(self, key, value):
        object.__setattr__(self, key, value)
        if key in _INDEXED:
            object.__setattr__(self, _INDEXED[key], None)

    # ── loading ────────────────────────────────────────────────────────
    @classmethod
    def load(cls, store: SheetStore, mailer=None, **kw) -> "DataContext":
        ctx = cls(store=store, mailer=mailer, **kw)
        ctx.set_frames({name: store.read(name) for name in cls.FRAMES})
        return ctx

    @classmethod
    def from_frames(cls, frames: dict, store: SheetStore | None = None, mailer=None, **kw) -> "DataContext":
        ctx = cls(store=store, mailer=mailer, **kw)
        ctx.set_frames(frames)
        return ctx

    def set_frames(self, frames: dict):
        """Apply the same per-sheet normalisation appy.py does at session start (3704-3790)."""
        staff = frames.get('staff', pd.DataFrame()).copy()
        if 'only_home_dept' not in staff.columns:
            staff['only_home_dept'] = False
        else:
            staff['only_home_dept'] = staff['only_home_dept'].apply(is_true)
        for c in ('email', 'manage_depts', 'recurring_absent_days'):
            if c not in staff.columns:
                staff[c] = ''
        if 'manual_schedule_only' not in staff.columns:
            staff['manual_schedule_only'] = False
        else:
            staff['manual_schedule_only'] = staff['manual_schedule_only'].apply(is_true)
        self.staff = staff

        self.schedule = frames.get('schedule', pd.DataFrame()).copy()
        if self.schedule.empty and 'date' not in self.schedule.columns:
            self.schedule = pd.DataFrame(columns=SHEET_COLUMNS['schedule'])
        self.requests = frames.get('requests', pd.DataFrame()).copy()
        if self.requests.empty and 'date' not in self.requests.columns:
            self.requests = pd.DataFrame(columns=SHEET_COLUMNS['requests'])

        sd = frames.get('special_days', pd.DataFrame()).copy()
        if 'day_type' not in sd.columns:
            sd['day_type'] = 'רגיל'
        self.special_days = sd

        self.swap_requests = frames.get('swap_requests', pd.DataFrame()).copy()

        k = frames.get('konenut', pd.DataFrame()).copy()
        if k.empty or 'date' not in k.columns:
            k = pd.DataFrame(columns=SHEET_COLUMNS['konenut'])
        for c in ('pnim_dr', 'rehab_dr1', 'rehab_dr2'):
            if c not in k.columns:
                k[c] = ''
        k['date'] = k['date'].astype(str)
        for c in ('pnim_dr', 'rehab_dr1', 'rehab_dr2'):
            k[c] = k[c].fillna('').astype(str)
        self.konenut = k

        dr = frames.get('dept_rotation', pd.DataFrame()).copy()
        if dr.empty or 'employee' not in dr.columns:
            dr = pd.DataFrame(columns=['employee', 'year_month', 'daily_dept'])
        self.dept_rotation = norm_dr(dr)

        ar = frames.get('absence_requests', pd.DataFrame()).copy()
        if ar.empty or 'employee' not in ar.columns:
            ar = pd.DataFrame(columns=SHEET_COLUMNS['absence_requests'])
        self.absence_requests = ar

        wsd = frames.get('work_schedule_daily', pd.DataFrame()).copy()
        if wsd.empty or 'date' not in wsd.columns:
            wsd = pd.DataFrame(columns=SHEET_COLUMNS['work_schedule_daily'])
        elif self.wsd_year_prefix:
            wsd = wsd[wsd['date'].astype(str).str.startswith(self.wsd_year_prefix)]
        if 'side' not in wsd.columns:
            wsd['side'] = ''
        self.work_schedule_daily = wsd

        st_df = frames.get('settings', pd.DataFrame()).copy()
        if 'key' not in st_df.columns:
            st_df = pd.DataFrame([{'key': 'active_month', 'value': str(date.today().month + 1)}])
        self.settings = st_df

    # ── persistence ────────────────────────────────────────────────────
    def save(self, name: str, df: pd.DataFrame, is_rtl: bool = False):
        """Synchronous write (replaces appy's save_to_db and fire-and-forget _save_async)."""
        if self.store is not None:
            self.store.write(name, df, is_rtl=is_rtl)

    def fetch_live(self, name: str) -> pd.DataFrame:
        """Fresh read right before a merge-write (appy._fetch_live)."""
        if self.store is None:
            return pd.DataFrame()
        return self.store.read(name)

    def send_email(self, to_address, subject, body_html):
        """Never raises (appy.send_notification_email)."""
        if self.mailer is None or not to_address:
            return
        try:
            self.mailer.send(to_address, subject, body_html)
        except Exception:
            pass

    # ── derived indexes ────────────────────────────────────────────────
    @property
    def wsd_index(self) -> dict:
        if self._wsd_index is None:
            object.__setattr__(self, '_wsd_index', build_wsd_index(self.work_schedule_daily))
        return self._wsd_index

    @property
    def approved_map(self) -> dict:
        if self._approved_map is None:
            object.__setattr__(self, '_approved_map', build_approved_map(self.absence_requests))
        return self._approved_map


def build_wsd_index(wsd: pd.DataFrame) -> dict:
    """(date_str, employee) → {status, note, is_manual, daily_dept, side} (appy._rebuild_wsd_index)."""
    idx = {}
    if not wsd.empty and 'date' in wsd.columns:
        for _, r in wsd.iterrows():
            key = (str(r['date']), str(r.get('employee', '')).strip())
            raw_manual = r.get('is_manual', False)
            idx[key] = {
                'status': str(r.get('status', 'עובד')),
                'note': str(r.get('note', '') or ''),
                'is_manual': raw_manual if isinstance(raw_manual, bool)
                else str(raw_manual).strip().lower() == 'true',
                'daily_dept': str(r.get('daily_dept', '') or ''),
                'side': str(r.get('side', '') or ''),
            }
    return idx


def build_approved_map(ar: pd.DataFrame) -> dict:
    """employee → [(start, end, status_type)] for approved absences (appy._build_approved_map)."""
    result = {}
    try:
        if not ar.empty and 'status' in ar.columns:
            ar2 = ar.copy()
            ar2['status'] = ar2['status'].astype(str).str.lower()
            ar2['employee'] = ar2['employee'].astype(str).str.strip()
            ar2['start_date'] = ar2['start_date'].astype(str)
            ar2['end_date'] = ar2['end_date'].astype(str)
            ar2['type'] = ar2['type'].astype(str).str.strip()
            for _, r in ar2[ar2['status'] == 'approved'].iterrows():
                try:
                    sd = datetime.strptime(r['start_date'], '%Y-%m-%d').date()
                    ed = datetime.strptime(r['end_date'], '%Y-%m-%d').date()
                except Exception:
                    continue
                atype = ABSENCE_TYPE_TO_STATUS.get(r['type'], r['type'])
                result.setdefault(r['employee'], []).append((sd, ed, atype))
    except Exception:
        pass
    return result


def now_str(fmt='%Y-%m-%d %H:%M:%S') -> str:
    return datetime.now().strftime(fmt)


def daterange(sd: date, ed: date):
    cur = sd
    while cur <= ed:
        yield cur
        cur += timedelta(days=1)
