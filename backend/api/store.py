"""Store wrapper for the read-only rollout phase (DEPLOY_PLAN step 2: read-only first)."""
from __future__ import annotations


READ_ONLY_MSG = "המערכת החדשה פתוחה כרגע לצפייה בלבד. שינויים נעשים עדיין באפליקציה הקיימת."


class ReadOnlyError(PermissionError):
    pass


class ReadOnlyStore:
    """Passes reads through; refuses every write except to the sheets in `allowed` (API_WRITE_SHEETS)."""

    def __init__(self, inner, allowed=frozenset()):
        self._inner = inner
        self._allowed = allowed

    def read(self, name):
        return self._inner.read(name)

    def read_many(self, names):
        inner = getattr(self._inner, 'read_many', None)
        return inner(names) if inner else {n: self._inner.read(n) for n in names}

    def tab_url(self, name):
        return self._inner.tab_url(name)

    def titles(self):
        return self._inner.titles()

    def _gate(self, name):
        from .config import sheet_allowed
        if not sheet_allowed(name, self._allowed):
            raise ReadOnlyError(READ_ONLY_MSG)

    def write(self, name, *a, **k):
        self._gate(name)
        return self._inner.write(name, *a, **k)

    def append_row(self, name, *a, **k):
        self._gate(name)
        return self._inner.append_row(name, *a, **k)

    def set_rtl(self, name, *a, **k):
        self._gate(name)
        return self._inner.set_rtl(name, *a, **k)


class CacheClearingStore:
    """Calls on_write after every successful write, so the API's shared Sheet cache is dropped."""

    def __init__(self, inner, on_write, cached=None):
        self._inner = inner
        self._on_write = on_write
        # Sheets the cache holds; a write elsewhere (analytics_log, an export tab) keeps the cache.
        self._cached = set(cached) if cached is not None else None

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def _written(self, method, *a, **k):
        result = getattr(self._inner, method)(*a, **k)
        sheet = a[0] if a else k.get('name')
        if self._cached is None or sheet in self._cached:
            self._on_write()
        return result

    def write(self, *a, **k):
        return self._written('write', *a, **k)

    def append_row(self, *a, **k):
        return self._written('append_row', *a, **k)

    def set_rtl(self, *a, **k):
        return self._written('set_rtl', *a, **k)
