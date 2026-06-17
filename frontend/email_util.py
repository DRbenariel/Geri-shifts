"""
email_util.py — SMTP notifications, ported from appy.py:179.

Reads SMTP config from environment (SMTP_SERVER/SMTP_PORT/SMTP_SENDER/
SMTP_PASSWORD) instead of st.secrets. Wrapped in except — never raises.
"""
import os


def send_notification_email(to_address, subject, body_html):
    try:
        import smtplib
        from email.mime.multipart import MIMEMultipart
        from email.mime.text import MIMEText

        smtp_server = os.environ.get('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.environ.get('SMTP_PORT', '587'))
        sender = os.environ.get('SMTP_SENDER', '')
        password = os.environ.get('SMTP_PASSWORD', '')
        if not sender or not password or not to_address:
            return  # not configured — silently skip

        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = sender
        msg['To'] = to_address
        msg.attach(MIMEText(body_html, 'html', 'utf-8'))

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, to_address, msg.as_string())
    except Exception:
        pass  # email failure must never affect the request
