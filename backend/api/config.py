"""Runtime configuration from environment variables (Cloud Run / Secret Manager).

  GSHEETS_CREDENTIALS  service-account JSON (same variable daily_report.py reads)
  SPREADSHEET_URL      the Google Sheet
  SESSION_SECRET       HMAC key for the session cookie
  API_READ_ONLY        "1" (default) blocks every write to the Sheet
  API_WRITE_SHEETS     ";"- (or ",") separated sheets the new UI may still write while API_READ_ONLY=1 (the
                       screen-by-screen rollout); "WSD_*" allows every per-dept export tab. Empty = none
  COOKIE_SECURE        "1" (default) sends the cookie over HTTPS only; "0" for local http
  STREAMLIT_PARALLEL   "1" (default) keeps new passwords SHA-256 so the Streamlit app can still read them
  SMTP_USER / SMTP_PASSWORD   Gmail sender for absence notifications (optional)
  API_CACHE_SECONDS    "60" (default) shares one Sheet load across requests; any write clears it. "0" = no cache
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass


@dataclass
class Settings:
    session_secret: str
    read_only: bool = True
    write_sheets: frozenset = frozenset()
    cookie_secure: bool = True
    credentials: dict | None = None
    spreadsheet_url: str = ""
    streamlit_parallel: bool = True
    smtp_user: str = ""
    smtp_password: str = ""
    cache_seconds: float = 0

    @classmethod
    def from_env(cls) -> "Settings":
        secret = os.environ.get("SESSION_SECRET", "")
        if len(secret) < 32:
            raise RuntimeError("SESSION_SECRET must be set (32+ characters)")
        creds = os.environ.get("GSHEETS_CREDENTIALS")
        settings = cls(
            session_secret=secret,
            read_only=os.environ.get("API_READ_ONLY", "1") != "0",
            write_sheets=frozenset(s.strip() for s in re.split(r"[,;]", os.environ.get("API_WRITE_SHEETS", "")) if s.strip()),
            cookie_secure=os.environ.get("COOKIE_SECURE", "1") != "0",
            credentials=json.loads(creds) if creds else None,
            spreadsheet_url=os.environ.get("SPREADSHEET_URL", ""),
            streamlit_parallel=os.environ.get("STREAMLIT_PARALLEL", "1") != "0",
            smtp_user=os.environ.get("SMTP_USER", ""),
            smtp_password=os.environ.get("SMTP_PASSWORD", ""),
            cache_seconds=float(os.environ.get("API_CACHE_SECONDS", "60")),
        )
        check_write_sheets(settings.write_sheets)
        return settings

    def can_write(self, sheet: str) -> bool:
        return not self.read_only or sheet_allowed(sheet, self.write_sheets)


# Opening a sheet also needs the sheets its actions write along with it (absence approval fills
# work_schedule_daily, a Gantt save moves absences, a swap approval moves the schedule). Opening only part
# would let the first save land and the second be refused, leaving the Sheet half-updated.
REQUIRES = {
    "absence_requests": {"work_schedule_daily"},
    "work_schedule_daily": {"absence_requests"},
    "dept_rotation": {"absence_requests", "work_schedule_daily"},
    "schedule": {"swap_requests"},
    "swap_requests": {"schedule"},
}


def check_write_sheets(allowed) -> None:
    for sheet in allowed:
        missing = REQUIRES.get(sheet, set()) - set(allowed)
        if missing:
            raise RuntimeError(f"API_WRITE_SHEETS opens {sheet} without {sorted(missing)}, which its actions also write")


def sheet_allowed(sheet: str, allowed) -> bool:
    return sheet in allowed or any(a.endswith("*") and sheet.startswith(a[:-1]) for a in allowed)
