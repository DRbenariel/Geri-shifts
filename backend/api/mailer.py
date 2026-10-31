"""Gmail SMTP sender, same settings and behaviour as appy.send_notification_email.

Sends synchronously inside the request (a background thread would lose its CPU
once Cloud Run has responded). Never raises: a mail failure must not fail the
action that triggered it.
"""
from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText


class SmtpMailer:
    def __init__(self, sender: str, password: str, server: str = "smtp.gmail.com", port: int = 587):
        self.sender, self.password, self.server, self.port = sender, password, server, port

    def send(self, to, subject, body):
        if not (self.sender and self.password and to):
            return
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"], msg["From"], msg["To"] = subject, self.sender, to
            msg.attach(MIMEText(body, "html", "utf-8"))
            with smtplib.SMTP(self.server, self.port, timeout=15) as s:
                s.starttls()
                s.login(self.sender, self.password)
                s.sendmail(self.sender, to, msg.as_string())
        except Exception:
            pass
