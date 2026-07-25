"""Send the digest via SMTP using an existing mailbox (e.g. Gmail with an App Password).

Required env vars: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, DIGEST_TO.
For Gmail: SMTP_HOST=smtp.gmail.com, SMTP_PORT=587, SMTP_USER=you@gmail.com,
SMTP_PASS=<16-char App Password from https://myaccount.google.com/apppasswords>
(a regular account password will NOT work if 2FA is enabled, which it should be).
"""
import os
import smtplib
from email.mime.text import MIMEText
from datetime import date


def send_digest(html: str, has_content: bool, subject_prefix: str = "VAD Monitor"):
    to_addr = os.environ.get("DIGEST_TO")
    host = os.environ.get("SMTP_HOST")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER")
    password = os.environ.get("SMTP_PASS")

    if not all([to_addr, host, user, password]):
        print("[mailer] skipped: SMTP_HOST/SMTP_USER/SMTP_PASS/DIGEST_TO not fully set")
        return

    subject = f"{subject_prefix} — {date.today().isoformat()}" + ("" if has_content else " (cisza w tym tygodniu)")
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr

    with smtplib.SMTP(host, port) as server:
        server.starttls()
        server.login(user, password)
        server.sendmail(user, [to_addr], msg.as_string())
    print(f"[mailer] sent digest to {to_addr}")
