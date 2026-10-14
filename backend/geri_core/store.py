"""Sheet storage backends.

`SheetStore` is the only place that touches Google Sheets. `GSheetStore` ports
appy.py's `_fetch_live` / `save_to_db` / `log_event` I/O; `MemoryStore` keeps
the same interface in memory for tests and local previews.
"""
from __future__ import annotations

import time
from typing import Protocol

import pandas as pd

from .normalize import clean_sheet_values

RETRYABLE_API_STATUS = {429, 500, 502, 503, 504}


class SaveError(RuntimeError):
    """Raised when a write fails after retries (same message as appy.save_to_db)."""


class SheetStore(Protocol):
    def read(self, name: str) -> pd.DataFrame: ...
    def write(self, name: str, df: pd.DataFrame, is_rtl: bool = False) -> None: ...
    def append_row(self, name: str, row: list, header: list | None = None) -> None: ...
    def set_rtl(self, name: str) -> None: ...
    def tab_url(self, name: str) -> str: ...
    def titles(self) -> set: ...


def to_sheet_values(df: pd.DataFrame) -> list:
    """NaN/None-safe stringification (appy.save_to_db)."""
    df_str = df.where(pd.notna(df), '').fillna('').astype(str)
    return [df_str.columns.tolist()] + df_str.values.tolist()


class MemoryStore:
    """In-memory store with the same semantics: reads return copies of what was written."""

    def __init__(self, sheets: dict | None = None):
        self.sheets: dict[str, pd.DataFrame] = {}
        self.rtl: set = set()
        self.writes: list = []          # (name, rows) audit for tests
        for k, v in (sheets or {}).items():
            self.sheets[k] = v.copy()

    def read(self, name):
        if name not in self.sheets:
            return pd.DataFrame()
        # Round-trip through the same stringify + clean path a real sheet uses.
        return clean_sheet_values(to_sheet_values(self.sheets[name]))

    def write(self, name, df, is_rtl=False):
        self.sheets[name] = df.copy()
        self.writes.append((name, len(df)))
        if is_rtl:
            self.rtl.add(name)

    def append_row(self, name, row, header=None):
        cur = self.sheets.get(name)
        if cur is None:
            cur = pd.DataFrame(columns=header or [str(i) for i in range(len(row))])
        cur = pd.concat([cur, pd.DataFrame([dict(zip(cur.columns, row))])], ignore_index=True)
        self.sheets[name] = cur

    def set_rtl(self, name):
        self.rtl.add(name)

    def tab_url(self, name):
        return f"memory://{name}"

    def titles(self):
        return set(self.sheets)


class GSheetStore:
    """Google Sheets via gspread service account. Retries 429 and transient 5xx."""

    def __init__(self, credentials: dict, spreadsheet_url: str, sleep=time.sleep):
        self._creds = dict(credentials)
        self._url = spreadsheet_url
        self._sleep = sleep
        self._sh = None

    def _spreadsheet(self):
        import gspread
        if self._sh is None:
            gc = gspread.service_account_from_dict(self._creds)
            self._sh = gc.open_by_url(self._url)
        return self._sh

    def _retry(self, fn, attempts=4):
        import gspread
        last = None
        for attempt in range(attempts):
            try:
                return fn()
            except gspread.exceptions.APIError as e:
                last = e
                if e.response.status_code in RETRYABLE_API_STATUS and attempt < attempts - 1:
                    self._sleep(2 ** attempt)
                    continue
                raise
        raise last

    def read(self, name):
        import gspread
        try:
            return self._retry(lambda: clean_sheet_values(
                self._spreadsheet().worksheet(name).get_all_values()))
        except gspread.exceptions.WorksheetNotFound:
            return pd.DataFrame()

    def write(self, name, df, is_rtl=False):
        """Write-then-trim (never clear first), as appy.save_to_db."""
        import gspread
        data = to_sheet_values(df)
        n_rows = len(data)
        n_cols = max((len(r) for r in data), default=1)

        def _do():
            sh = self._spreadsheet()
            try:
                ws = sh.worksheet(name)
            except gspread.exceptions.WorksheetNotFound:
                ws = sh.add_worksheet(title=name, rows=max(n_rows, 1), cols=max(n_cols, 1))
            ws.update(range_name='A1', values=data, value_input_option='RAW')
            try:
                ws.resize(rows=max(n_rows, 1), cols=max(n_cols, 1))
            except Exception:
                pass
            if is_rtl:
                try:
                    sh.batch_update({"requests": [{
                        "updateSheetProperties": {
                            "properties": {"sheetId": ws.id, "rightToLeft": True,
                                           "gridProperties": {"columnCount": 8}},
                            "fields": "rightToLeft,gridProperties.columnCount"}}]})
                    ws.format('A1:H1', {'textFormat': {'bold': True}, 'horizontalAlignment': 'CENTER'})
                    ws.format('A2:H100', {'horizontalAlignment': 'CENTER', 'verticalAlignment': 'MIDDLE'})
                except Exception:
                    pass

        try:
            self._retry(_do)
        except Exception as e:
            raise SaveError(f"שגיאה קריטית בשמירה לגיליון '{name}': {e}") from e

    def append_row(self, name, row, header=None):
        import gspread
        sh = self._spreadsheet()
        try:
            ws = sh.worksheet(name)
        except gspread.exceptions.WorksheetNotFound:
            ws = sh.add_worksheet(name, rows=5000, cols=max(len(row), 1))
            if header:
                ws.append_row(header, value_input_option='USER_ENTERED')
        self._retry(lambda: ws.append_row(row, value_input_option='USER_ENTERED'))

    def set_rtl(self, name):
        sh = self._spreadsheet()
        ws = sh.worksheet(name)
        sh.batch_update({"requests": [{"updateSheetProperties": {
            "properties": {"sheetId": ws.id, "rightToLeft": True}, "fields": "rightToLeft"}}]})

    def tab_url(self, name):
        sh = self._spreadsheet()
        return f"{sh.url}#gid={sh.worksheet(name).id}"

    def titles(self):
        return {ws.title for ws in self._spreadsheet().worksheets()}
