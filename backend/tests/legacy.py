"""Run the ORIGINAL appy.py functions without Streamlit, for parity tests.

appy.py executes UI code at import time, so instead of importing it we parse it
with `ast`, keep only imports, constant assignments and function definitions,
and exec those against a stub `streamlit` module whose `session_state` holds the
same frames a DataContext holds. Sheet I/O, email and analytics are redirected
to in-memory recorders.
"""
from __future__ import annotations

import ast
import os
import sys
import types

import pandas as pd

APPY = os.path.join(os.path.dirname(__file__), '..', '..', 'appy.py')
_STUB_MODULES = ('streamlit', 'streamlit_shadcn_ui', 'streamlit_antd_components', 'streamlit_gsheets',
                 'ui_components', 'streamlit.components', 'streamlit.components.v1')


class SessionState(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError as e:
            raise AttributeError(k) from e

    def __setattr__(self, k, v):
        self[k] = v

    def __delattr__(self, k):
        del self[k]


class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, *a, **k):
        self.calls.append((a, k))


class FakeStreamlit(types.ModuleType):
    def __init__(self):
        super().__init__('streamlit')
        self.session_state = SessionState()
        self.secrets = {}
        self.messages = []

        def cache_data(*a, **k):
            def deco(f):
                f.clear = lambda: None
                return f
            if a and callable(a[0]):
                return deco(a[0])
            return deco
        cache_data.clear = lambda: None
        self.cache_data = cache_data

    def __getattr__(self, name):
        if name.startswith('__'):
            raise AttributeError(name)

        def _ui(*a, **k):
            self.messages.append((name, a[0] if a else None))
        return _ui


def _keep_assign(node, src):
    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
    names = [t.id for t in targets if isinstance(t, ast.Name)]
    if not names or len(names) != len(targets):
        return False
    text = ast.get_source_segment(src, node) or ''
    if 'st.' in text or 'session_state' in text:
        return False
    return all(n.startswith('_') or n.isupper() for n in names)


def load_legacy():
    """Return (namespace, fake_st, io) where io records writes/emails."""
    for m in _STUB_MODULES:
        sys.modules.setdefault(m, types.ModuleType(m))
    sys.modules['streamlit_gsheets'].GSheetsConnection = object
    st = FakeStreamlit()
    sys.modules['streamlit'] = st
    src = open(APPY, encoding='utf-8').read()
    tree = ast.parse(src)
    body = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            body.append(node)
        elif isinstance(node, ast.FunctionDef):
            body.append(node)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)) and _keep_assign(node, src):
            body.append(node)
    mod = ast.Module(body=body, type_ignores=[])
    ns = {'__name__': 'appy_legacy', '__file__': APPY}
    exec(compile(mod, APPY, 'exec'), ns)
    ns['st'] = st

    io = types.SimpleNamespace(writes={}, emails=[], sheets={})

    def save_to_db(name, df, is_rtl=False):
        io.writes[name] = df.copy()
        io.sheets[name] = df.copy()

    def get_db_data(name):
        return io.sheets.get(name, pd.DataFrame()).copy()

    ns['save_to_db'] = save_to_db
    ns['_save_async'] = save_to_db
    ns['get_db_data'] = get_db_data
    ns['_fetch_live'] = get_db_data
    ns['_fetch_sheet_data_silently'] = get_db_data
    ns['send_notification_email'] = lambda to, subj, body: io.emails.append((to, subj, body))
    ns['log_event'] = lambda *a, **k: None
    ns['_log_async'] = lambda *a, **k: None
    return ns, st, io


def seed_session(ns, st, io, ctx):
    """Copy a DataContext's normalised frames into the fake session_state."""
    st.session_state.clear()
    for f in ctx.FRAMES:
        st.session_state[f] = getattr(ctx, f).copy()
        io.sheets[f] = getattr(ctx, f).copy()
    ns['_rebuild_wsd_index']()
    ns['_build_approved_map']()
