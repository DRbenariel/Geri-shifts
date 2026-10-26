"""Store wrapper for the read-only rollout phase (DEPLOY_PLAN step 2: read-only first)."""
from __future__ import annotations


READ_ONLY_MSG = "המערכת החדשה פתוחה כרגע לצפייה בלבד. שינויים נעשים עדיין באפליקציה הקיימת."


class ReadOnlyError(PermissionError):
    pass


class ReadOnlyStore:
    """Passes reads through; refuses every write, so nothing reaches the live Sheet."""

    def __init__(self, inner):
        self._inner = inner

    def read(self, name):
        return self._inner.read(name)

    def read_many(self, names):
        inner = getattr(self._inner, 'read_many', None)
        return inner(names) if inner else {n: self._inner.read(n) for n in names}

    def tab_url(self, name):
        return self._inner.tab_url(name)

    def titles(self):
        return self._inner.titles()

    def _refuse(self, *a, **k):
        raise ReadOnlyError(READ_ONLY_MSG)

    write = append_row = set_rtl = _refuse


class CacheClearingStore:
    """Calls on_write after every successful write, so the API's shared Sheet cache is dropped."""

    def __init__(self, inner, on_write):
        self._inner = inner
        self._on_write = on_write

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def _written(self, method, *a, **k):
        result = getattr(self._inner, method)(*a, **k)
        self._on_write()
        return result

    def write(self, *a, **k):
        return self._written('write', *a, **k)

    def append_row(self, *a, **k):
        return self._written('append_row', *a, **k)

    def set_rtl(self, *a, **k):
        return self._written('set_rtl', *a, **k)
