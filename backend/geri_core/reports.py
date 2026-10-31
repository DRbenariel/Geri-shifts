"""דוחות וניהול data + analytics log (appy.py:3007-3045, 7244-7694)."""
from __future__ import annotations

import calendar
import importlib.util
import os
import uuid
from datetime import datetime

import pandas as pd

from .constants import ANALYTICS_COLUMNS


# ── dashboard ────────────────────────────────────────────────────────────────
def submission_status(ctx, year, month) -> dict:
    prefix = f"{year}-{month:02d}"
    rel = ctx.staff[ctx.staff['type'].isin(['מתמחה', 'תורן חוץ'])]
    reqs = ctx.requests.copy()
    if not reqs.empty:
        reqs['date'] = reqs['date'].astype(str)
        reqs['employee'] = reqs['employee'].astype(str).str.strip()
    rows, submitted = [], 0
    for _, emp in rel.iterrows():
        name = str(emp['name']).strip()
        n_c = n_w = 0
        if not reqs.empty:
            u = reqs[(reqs['employee'] == name) & (reqs['date'].str.startswith(prefix))]
            n_c = len(u[u['status'] == 'אילוץ'])
            n_w = len(u[u['status'] == 'בקשה'])
        ok = (n_c + n_w) > 0
        submitted += ok
        rows.append({'name': name, 'type': emp['type'], 'submitted': ok, 'blocks': n_c, 'wishes': n_w})
    return {'total': len(rel), 'submitted': submitted, 'pending': len(rel) - submitted, 'rows': rows}


def shift_counts(ctx, year, month) -> list:
    s = ctx.schedule
    if s.empty:
        return []
    m = s[s['date'].astype(str).str.startswith(f"{year}-{month:02d}")]
    if m.empty:
        return []
    fri = m['dept'].astype(str).str.contains("שישי בוקר", na=False)
    reg = m[~fri]['employee'].value_counts()
    morn = m[fri]['employee'].value_counts()
    df = pd.DataFrame({'regular': reg, 'friday_morning': morn}).fillna(0).astype(int)
    return [{'employee': k, **v} for k, v in df.to_dict('index').items()]


def fairness(ctx) -> list:
    """Wed / Thu / Fri-morning counts for interns across ALL history (7373-7420)."""
    full = ctx.schedule.copy()
    if full.empty:
        return []
    full['date_dt'] = pd.to_datetime(full['date'])
    full['weekday'] = full['date_dt'].dt.weekday
    types = ctx.staff.set_index('name')['type'].to_dict()
    full['staff_type'] = full['employee'].map(types)
    interns = full[full['staff_type'] == 'מתמחה']
    out = []
    for name in ctx.staff[ctx.staff['type'] == 'מתמחה']['name'].tolist():
        e = interns[interns['employee'] == name]
        wed = len(e[e['weekday'] == 2])
        thu = len(e[e['weekday'] == 3])
        fri = len(e[e['dept'].str.contains('שישי בוקר')])
        out.append({'name': name, 'wed': wed, 'thu': thu, 'friday_morning': fri, 'net': wed - (thu + fri)})
    return sorted(out, key=lambda r: r['net'], reverse=True)


# ── daily problem report ─────────────────────────────────────────────────────
def _load_daily_report_module():
    # The repo keeps daily_report.py at its root (GitHub Actions and Streamlit run it there); the
    # Cloud Run image gets a copy next to geri_core, made before each deploy (DEPLOY_PLAN).
    here = os.path.dirname(__file__)
    path = next(p for p in (os.path.join(here, '..', 'daily_report.py'), os.path.join(here, '..', '..', 'daily_report.py'))
                if os.path.exists(p))
    spec = importlib.util.spec_from_file_location("daily_report", os.path.abspath(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def run_problem_scan(ctx, year, month, analyze=None) -> list:
    """'🔄 הרץ סריקה עכשיו': analyze_month → overwrite daily_report sheet."""
    analyze = analyze or _load_daily_report_module().analyze_month
    problems = analyze(year, month, ctx.staff.copy(), ctx.requests.copy())
    if not problems:
        problems = [{'severity': 'תקין', 'problem_type': 'ללא בעיות',
                     'description': f'לא נמצאו בעיות צפויות לחודש {month}/{year}', 'day': 0}]
    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    df = pd.DataFrame([{'generated_at': now, 'month': f"{year}-{month:02d}", 'severity': p['severity'],
                        'problem_type': p['problem_type'], 'description': p['description']} for p in problems])
    ctx.save('daily_report', df)
    return problems


SEVERITY_ORDER = {'קריטי': 0, 'אזהרה': 1, 'מידע': 2, 'תקין': 3}


def problem_report(ctx) -> dict:
    df = ctx.store.read("daily_report") if ctx.store else pd.DataFrame()
    if df.empty:
        return {'generated_at': None, 'month': None, 'rows': [], 'headline': None}
    peak = df[df.get('problem_type', pd.Series(dtype=str)) == 'ימי שיא חסימה'] if 'problem_type' in df.columns else df.iloc[0:0]
    headline = {'critical': int((peak['severity'] == 'קריטי').sum()) if not peak.empty else 0,
                'warning': int((peak['severity'] == 'אזהרה').sum()) if not peak.empty else 0}
    df = df.assign(_o=df['severity'].map(SEVERITY_ORDER).fillna(9)).sort_values('_o', kind='stable')
    return {'generated_at': df['generated_at'].iloc[0] if 'generated_at' in df.columns else None,
            'month': df['month'].iloc[0] if 'month' in df.columns else None,
            'rows': df.drop(columns='_o').to_dict('records'), 'headline': headline}


# ── analytics ────────────────────────────────────────────────────────────────
def analytics_row(event_type, detail_1='', detail_2='', session=None) -> list:
    s = session or {}
    now = datetime.now()
    return [str(uuid.uuid4()), str(s.get('session_id', '')), now.strftime('%Y-%m-%d %H:%M:%S'),
            str(s.get('user_name', '')), str(s.get('user_role', '')), event_type, str(detail_1), str(detail_2),
            str(s.get('device_type', 'unknown')), str(s.get('ua', ''))[:200], str(s.get('vp_width', '')),
            str(s.get('active_month', '')), str(now.day)]


def log_event(store, event_type, detail_1='', detail_2='', session=None):
    """Append-only; never raises."""
    try:
        store.append_row('analytics_log', analytics_row(event_type, detail_1, detail_2, session),
                         header=ANALYTICS_COLUMNS)
    except Exception:
        pass


def analytics_summary(ctx, year, month) -> dict:
    """Sections A–I of '📈 ניתוח שימוש במערכת' as plain data."""
    alog = ctx.store.read("analytics_log") if ctx.store else pd.DataFrame()
    if alog.empty or 'event_type' not in alog.columns:
        return {'empty': True}
    logins = alog[alog['event_type'] == 'login_success']
    submits = alog[alog['event_type'] == 'constraint_submit']
    out = {'empty': False}
    out['kpi'] = {'logins': len(logins), 'unique_users': int(alog['user_name'].nunique()),
                  'mobile_pct': int((logins['device_type'] == 'mobile').sum() / len(logins) * 100) if len(logins) else 0,
                  'avg_submits_per_month': float(submits.groupby('active_month').size().mean()) if len(submits) else 0.0}
    per_user = []
    for u, g in alog.groupby('user_name'):
        lg = g[g['event_type'] == 'login_success']
        per_user.append({'user': u, 'logins': int((g['event_type'] == 'login_success').sum()),
                         'submits': int((g['event_type'] == 'constraint_submit').sum()),
                         'swap_searches': int((g['event_type'] == 'swap_search').sum()),
                         'swap_requests': int((g['event_type'] == 'swap_request_sent').sum()),
                         'device': lg['device_type'].value_counts().index[0] if len(lg) else 'unknown'})
    out['per_user'] = per_user
    reqs = ctx.requests
    dim = calendar.monthrange(year, month)[1]
    blocks = []
    if not reqs.empty:
        b = reqs[(reqs['status'] == 'אילוץ') & reqs['date'].astype(str).str.startswith(f"{year}-{month:02d}")]
        for emp, n in b.groupby('employee').size().items():
            pct = round(n / dim * 100, 1)
            blocks.append({'employee': emp, 'blocks': int(n), 'pct': pct,
                           'level': 'red' if pct > 60 else 'yellow' if pct > 40 else 'green'})
    out['blocking'] = sorted(blocks, key=lambda r: -r['pct'])
    tv = alog[alog['event_type'] == 'tab_view']
    out['tab_entries'] = tv[tv['detail_2'] == 'enter'].groupby('detail_1').size().to_dict()
    ex = tv[tv['detail_2'] != 'enter'].copy()
    ex['s'] = pd.to_numeric(ex['detail_2'], errors='coerce')
    out['tab_avg_seconds'] = ex.dropna(subset=['s']).groupby('detail_1')['s'].mean().round(1).to_dict()
    hrs = pd.to_datetime(logins['timestamp'], errors='coerce').dt.hour
    out['logins_by_hour'] = hrs.value_counts().reindex(range(24), fill_value=0).astype(int).tolist()
    out['devices'] = logins['device_type'].value_counts().to_dict()
    lt = logins.assign(ts=pd.to_datetime(logins['timestamp'], errors='coerce')).sort_values(['user_name', 'ts'])
    lt['gap'] = (lt['ts'] - lt.groupby('user_name')['ts'].shift(1)).dt.total_seconds() / 60
    out['reload_suspects'] = lt[lt['gap'] < 5]['user_name'].unique().tolist()
    sd = pd.to_numeric(submits['day_of_month'].astype(str).str.extract(r'(\d+)')[0], errors='coerce').dropna().astype(int)
    out['submits_by_day'] = sd.value_counts().reindex(range(1, 32), fill_value=0).astype(int).tolist()
    return out
