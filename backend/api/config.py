"""Runtime configuration from environment variables (Cloud Run / Secret Manager).

  GSHEETS_CREDENTIALS  service-account JSON (same variable daily_report.py reads)
  SPREADSHEET_URL      the Google Sheet
  SESSION_SECRET       HMAC key for the session cookie
  API_READ_ONLY        "1" (default) blocks every write to the Sheet
  COOKIE_SECURE        "1" (default) sends the cookie over HTTPS only; "0" for local http
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass


@dataclass
class Settings:
    session_secret: str
    read_only: bool = True
    cookie_secure: bool = True
    credentials: dict | None = None
    spreadsheet_url: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        secret = os.environ.get("SESSION_SECRET", "")
        if len(secret) < 32:
            raise RuntimeError("SESSION_SECRET must be set (32+ characters)")
        creds = os.environ.get("GSHEETS_CREDENTIALS")
        return cls(
            session_secret=secret,
            read_only=os.environ.get("API_READ_ONLY", "1") != "0",
            cookie_secure=os.environ.get("COOKIE_SECURE", "1") != "0",
            credentials=json.loads(creds) if creds else None,
            spreadsheet_url=os.environ.get("SPREADSHEET_URL", ""),
        )
