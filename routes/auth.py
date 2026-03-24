"""
Google OAuth — browser redirect flow (backend only; no login UI templates yet).
"""
import logging

import requests
from flask import Blueprint, redirect, request, session, url_for
from flask_login import login_user, logout_user
from google_auth_oauthlib.flow import Flow

import config
from models.user import load_user, save_user

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")

_OAUTH_SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]


def _oauth_not_configured_response():
    return (
        "Google OAuth is not configured (set GOOGLE_OAUTH_CLIENT_SECRETS to a valid client_secret.json path).",
        503,
        {"Content-Type": "text/plain; charset=utf-8"},
    )


def _build_flow():
    if not config.GOOGLE_OAUTH_CLIENT_SECRETS:
        raise RuntimeError("OAuth client credentials missing")
    return Flow.from_client_secrets_file(
        config.GOOGLE_OAUTH_CLIENT_SECRETS,
        scopes=_OAUTH_SCOPES,
        redirect_uri=config.OAUTH_REDIRECT_URI,
    )


@auth_bp.route("/login")
def login():
    """Start Google OAuth; redirect to Google consent screen."""
    try:
        flow = _build_flow()
    except RuntimeError:
        return _oauth_not_configured_response()
    authorization_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    session["oauth_state"] = state
    return redirect(authorization_url)


@auth_bp.route("/callback")
def oauth_callback():
    """Exchange code for tokens, persist user, log in, redirect home."""
    try:
        flow = _build_flow()
    except RuntimeError:
        return _oauth_not_configured_response()

    if request.args.get("state") != session.get("oauth_state"):
        return "Invalid OAuth state", 400

    try:
        flow.fetch_token(authorization_response=request.url)
    except Exception:
        logging.exception("OAuth token exchange failed")
        return "Authentication failed", 400

    session.pop("oauth_state", None)
    creds = flow.credentials
    try:
        resp = requests.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {creds.token}"},
            timeout=15,
        )
        resp.raise_for_status()
        info = resp.json()
    except Exception:
        logging.exception("Failed to fetch Google userinfo")
        return "Failed to load profile", 400

    user_id = info.get("id")
    if not user_id:
        return "Missing user id from Google", 400

    save_user(
        {
            "id": user_id,
            "email": info.get("email"),
            "name": info.get("name"),
            "profile_pic": info.get("picture"),
        }
    )
    user = load_user(user_id)
    if user is None:
        return "Could not load user after save", 500

    login_user(user, remember=True)
    return redirect(url_for("main.index"))


@auth_bp.route("/logout")
def logout():
    """Log out and clear session; redirect to OAuth login."""
    logout_user()
    session.clear()
    return redirect(url_for("auth.login"))
