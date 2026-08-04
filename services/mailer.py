"""Small SMTP adapter for workspace invitations."""
import smtplib
from email.message import EmailMessage

import config


def send_workspace_invitation(recipient: str, workspace_name: str, invite_url: str):
    if not config.SMTP_HOST or not config.SMTP_FROM:
        if config.DEBUG:
            return False
        raise RuntimeError("SMTP_HOST and SMTP_FROM are required for invitations")
    message = EmailMessage()
    message["Subject"] = f"Join {workspace_name} on Case Closed"
    message["From"] = config.SMTP_FROM
    message["To"] = recipient
    message.set_content(
        f"You have been invited to {workspace_name} on Case Closed.\n\n"
        f"Accept this single-use invitation within {config.INVITATION_TTL_DAYS} days:\n{invite_url}\n"
    )
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as client:
        client.starttls()
        if config.SMTP_USERNAME:
            client.login(config.SMTP_USERNAME, config.SMTP_PASSWORD or "")
        client.send_message(message)
    return True
