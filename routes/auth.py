"""Clerk authentication flows with a temporary Firebase rollback path."""
from datetime import timedelta
from urllib.parse import urlparse

from flask import Blueprint, jsonify, make_response, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, logout_user

import config
from services.firestore import get_firestore_client
from services.tenancy import ensure_user

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


# Browsers strip ASCII tab/CR/LF before parsing a URL, so "/<TAB>\evil.com"
# must be normalized before it is inspected rather than after.
_URL_STRIPPED_CHARS = str.maketrans("", "", "\t\r\n")


def _safe_next(value):
    """Accept only same-origin, path-relative destinations.

    urlparse on its own is not enough: browsers normalize "\\" to "/" inside a
    special scheme, so "/\\evil.com" -- which urlparse reports as a relative
    path with no netloc -- resolves to https://evil.com. That matters because
    the value is reflected raw into data-next (templates/login.html) and handed
    to window.location.assign() by static/firebase_auth.js, which applies
    exactly that normalization.
    """
    candidate = (value or "").translate(_URL_STRIPPED_CHARS).strip()
    parsed = urlparse(candidate)
    if (candidate.startswith("/")
            and not candidate.startswith(("//", "/\\"))
            and not parsed.scheme
            and not parsed.netloc):
        return candidate
    return url_for("main.workspace")


@auth_bp.route("/login")
def login():
    next_url = _safe_next(request.args.get("next"))
    invite_token = request.args.get("invite", "")
    if current_user.is_authenticated:
        if invite_token:
            return redirect(url_for("auth.complete_login", next=next_url, invite=invite_token))
        return redirect(next_url)
    complete_url = url_for("auth.complete_login", next=next_url, invite=invite_token)
    sso_callback_url = url_for("auth.sso_callback", next=next_url, invite=invite_token)
    return render_template(
        "login.html",
        firebase_config=config.FIREBASE_WEB_CONFIG,
        next_url=next_url,
        invite_token=invite_token,
        complete_url=complete_url,
        sso_callback_url=sso_callback_url,
        error=request.args.get("error", ""),
    )


@auth_bp.route("/sso-callback")
def sso_callback():
    """Land here after Google redirects back mid-OAuth; finish the Clerk handshake client-side."""
    if config.AUTH_PROVIDER != "clerk":
        return redirect(url_for("auth.login"))
    next_url = _safe_next(request.args.get("next"))
    invite_token = request.args.get("invite", "")
    complete_url = url_for("auth.complete_login", next=next_url, invite=invite_token)
    if current_user.is_authenticated:
        return redirect(complete_url)
    return render_template(
        "auth_callback.html",
        next_url=next_url,
        invite_token=invite_token,
        complete_url=complete_url,
    )


@auth_bp.route("/session", methods=["POST"])
def create_session():
    if config.AUTH_PROVIDER != "firebase":
        return jsonify({"error": "Firebase session exchange is disabled"}), 404
    from firebase_admin import auth as firebase_auth

    data = request.get_json(silent=True) or {}
    id_token = data.get("id_token")
    if not id_token:
        return jsonify({"error": "id_token is required"}), 400
    origin = request.headers.get("Origin")
    expected_origin = (config.APP_BASE_URL if config.ENVIRONMENT == "production"
                       else request.host_url).rstrip("/")
    if origin and origin.rstrip("/") != expected_origin:
        return jsonify({"error": "invalid origin"}), 403
    try:
        get_firestore_client()
        claims = firebase_auth.verify_id_token(id_token, check_revoked=True)
        provider = (claims.get("firebase") or {}).get("sign_in_provider")
        if provider == "password" and not claims.get("email_verified"):
            return jsonify({"error": "verify your email address before signing in"}), 403
        profile = ensure_user(claims)
        expires = timedelta(days=config.AUTH_SESSION_DAYS)
        cookie = firebase_auth.create_session_cookie(id_token, expires_in=expires)
    except Exception:
        return jsonify({"error": "authentication failed"}), 401
    response = make_response(jsonify({"status": "ok", "profile": profile}))
    response.set_cookie(config.AUTH_SESSION_COOKIE, cookie,
                        max_age=int(expires.total_seconds()), httponly=True,
                        secure=config.AUTH_COOKIE_SECURE, samesite="Lax", path="/")
    session.clear()
    return response


@auth_bp.route("/complete")
@login_required
def complete_login():
    """Finish app-specific onboarding after Clerk establishes its session."""
    next_url = _safe_next(request.args.get("next"))
    invite_token = request.args.get("invite", "")
    if invite_token:
        from services.tenancy import AuthorizationError, ValidationError, accept_invitation

        try:
            accept_invitation(str(current_user.get_id()), current_user.email, invite_token)
        except (AuthorizationError, ValidationError) as exc:
            return redirect(url_for("auth.login", next=next_url, error=str(exc)))
    session.clear()
    return redirect(next_url)


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
    if config.AUTH_PROVIDER == "clerk":
        session.clear()
        return render_template("logout.html", redirect_url=url_for("main.index"))
    from firebase_admin import auth as firebase_auth

    cookie = request.cookies.get(config.AUTH_SESSION_COOKIE)
    if cookie:
        try:
            get_firestore_client()
            claims = firebase_auth.verify_session_cookie(cookie)
            firebase_auth.revoke_refresh_tokens(claims["uid"])
        except Exception:
            pass
    logout_user()
    session.clear()
    response = make_response(redirect(url_for("main.index")))
    response.delete_cookie(config.AUTH_SESSION_COOKIE, path="/")
    return response
