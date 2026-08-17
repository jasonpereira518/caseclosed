"""Small SMTP adapter for workspace invitations and access approvals."""
import smtplib
from email.message import EmailMessage

import config


def _deliver(message: EmailMessage) -> bool:
    if not config.SMTP_HOST or not config.SMTP_FROM:
        if config.DEBUG:
            return False
        raise RuntimeError("SMTP_HOST and SMTP_FROM are required to send email")
    message["From"] = config.SMTP_FROM
    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=15) as client:
        client.starttls()
        if config.SMTP_USERNAME:
            client.login(config.SMTP_USERNAME, config.SMTP_PASSWORD or "")
        client.send_message(message)
    return True


def send_workspace_invitation(recipient: str, workspace_name: str, invite_url: str):
    message = EmailMessage()
    message["Subject"] = f"Join {workspace_name} on Case Closed"
    message["To"] = recipient
    message.set_content(
        f"You have been invited to {workspace_name} on Case Closed.\n\n"
        f"Accept this single-use invitation within {config.INVITATION_TTL_DAYS} days:\n{invite_url}\n"
    )
    return _deliver(message)


def send_access_request_notification(recipient: str, requester_email: str):
    message = EmailMessage()
    message["Subject"] = "New Case Closed access request"
    message["To"] = recipient
    message.set_content(
        f"{requester_email} signed in to Case Closed and is waiting for early access.\n\n"
        f"Review the request:\n{config.APP_BASE_URL}/admin/access\n"
    )
    return _deliver(message)


def send_access_approved(recipient: str):
    message = EmailMessage()
    message["Subject"] = "You're in — Case Closed early access"
    message["To"] = recipient
    message.set_content(
        "Your Case Closed early-access request has been approved.\n\n"
        f"Sign in with your Google account to start a matter:\n{config.APP_BASE_URL}/auth/login\n\n"
        "Case Closed does not provide legal advice. All output should be reviewed "
        "by a qualified attorney before use.\n"
    )
    return _deliver(message)
