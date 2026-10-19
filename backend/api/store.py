"""Store wrapper for the read-only rollout phase (DEPLOY_PLAN step 2: read-only first)."""
from __future__ import annotations


class ReadOnlyError(PermissionError):
    pass


class ReadOnlyStore:
    """Passes reads through; refuses every write, so nothing reaches the live Sheet."""

    def __init__(self, inner):
        self._inner = inner

    def read(self, name):
        return self._inner.read(name)

    def tab_url(self, name):
        return self._inner.tab_url(name)

    def titles(self):
        return self._inner.titles()

    def _refuse(self, *a, **k):
        raise ReadOnlyError("המערכת החדשה פתוחה כרגע לצפייה בלבד. שינויים נעשים עדיין באפליקציה הקיימת.")

    write = append_row = set_rtl = _refuse
