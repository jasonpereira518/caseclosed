"""Firebase Authentication browser flows and secure server sessions."""
from datetime import timedelta
from urllib.parse import urlparse

from firebase_admin import auth as firebase_auth
from flask import Blueprint, jsonify, make_response, redirect, render_template, request, session, url_for
from flask_login import current_user, logout_user

import config
from services.firestore import get_firestore_client
from services.tenancy import ensure_user

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _safe_next(value):
    parsed = urlparse(value or "")
    return value if not parsed.netloc and not parsed.scheme and (value or "").startswith("/") else url_for("main.workspace")


@auth_bp.route("/login")
def login():
    if current_user.is_authenticated and not request.args.get("invite"):
        return redirect(_safe_next(request.args.get("next")))
    return render_template("login.html", firebase_config=config.FIREBASE_WEB_CONFIG,
                           next_url=_safe_next(request.args.get("next")),
                           invite_token=request.args.get("invite", ""))


@auth_bp.route("/session", methods=["POST"])
def create_session():
    data = request.get_json(silent=True) or {}
    id_token = data.get("id_token")
    if not id_token:
        return jsonify({"error": "id_token is required"}), 400
    origin = request.headers.get("Origin")
    if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
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


@auth_bp.route("/logout", methods=["GET", "POST"])
def logout():
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
