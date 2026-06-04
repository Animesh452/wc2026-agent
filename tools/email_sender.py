import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_HOST = "smtp-relay.brevo.com"
SMTP_PORT = 587


def send_match_reminder(to_email: str, team: str, match_date: str, minutes_before: int, venue: str = None):
    try:
        smtp_login = os.getenv("BREVO_SMTP_LOGIN")
        smtp_key = os.getenv("BREVO_SMTP_KEY")
        sender = os.getenv("BREVO_SENDER_EMAIL")

        if not all([smtp_login, smtp_key, sender]):
            return {"sent": False, "error": "Missing Brevo credentials"}

        venue_line = f"<p><strong>Venue:</strong> {venue}</p>" if venue else ""

        html = f"""
        <div style="font-family: -apple-system, sans-serif; max-width: 600px; margin: 0 auto;">
          <div style="background: linear-gradient(135deg, #38bdf8, #1e3a5f); padding: 24px; border-radius: 12px 12px 0 0; color: white;">
            <h1 style="margin: 0; font-size: 24px;">⚽ MatchDay Reminder</h1>
            <p style="margin: 8px 0 0; opacity: 0.9;">World Cup 2026</p>
          </div>
          <div style="background: #f8fafc; padding: 24px; border-radius: 0 0 12px 12px; border: 1px solid #e2e8f0;">
            <h2 style="color: #1e3a5f; margin: 0 0 12px;">{team} match starts in {minutes_before} minutes!</h2>
            <p style="color: #475569; font-size: 16px;"><strong>Match Date:</strong> {match_date}</p>
            {venue_line}
            <p style="color: #64748b; margin-top: 24px;">Set by your MatchDay AI assistant.</p>
          </div>
        </div>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"⚽ {team} match starting in {minutes_before} minutes"
        msg["From"] = f"MatchDay <{sender}>"
        msg["To"] = to_email
        msg.attach(MIMEText(html, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(smtp_login, smtp_key)
            server.sendmail(sender, [to_email], msg.as_string())

        print(f"  email sent to {to_email}")
        return {"sent": True}
    except Exception as e:
        print(f"  email error: {e}")
        return {"sent": False, "error": str(e)}