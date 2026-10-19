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

    def tab_url(self, name):
        return self._inner.tab_url(name)

    def titles(self):
        return self._inner.titles()

    def _refuse(self, *a, **k):
        raise ReadOnlyError(READ_ONLY_MSG)

    write = append_row = set_rtl = _refuse
