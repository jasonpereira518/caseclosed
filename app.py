import os
import logging

import config

if config.OAUTH_REDIRECT_URI.startswith(("http://localhost", "http://127.0.0.1")):
    os.environ.setdefault("OAUTHLIB_INSECURE_TRANSPORT", "1")

from flask import Flask, jsonify, redirect, request, url_for
from flask_login import LoginManager

from routes import register_blueprints

PROTECTED_JSON_PATHS = frozenset(
    {
        "/chat",
        "/upload",
        "/analyze",
        "/draft",
        "/draft/export",
        "/context",
        "/case/ask",
        "/chat/case/ask",
        "/case/describe",
        "/chat/case/describe",
        "/case/treatment",
        "/chat/case/treatment",
        "/case/bookmark",
        "/session/track-time",
        "/timeline/add",
        "/intake",
        "/documents/toggle",
        "/documents/delete",
        "/case/notes",
        "/search",
    }
)
# Note: login JSON responses for these paths use _is_protected_json_path(request.path),
# which normalizes trailing slashes (e.g. /case/describe/ matches /case/describe).


def _is_protected_json_path(path: str) -> bool:
    """Match PROTECTED_JSON_PATHS even when the client uses a trailing slash."""
    key = path.rstrip("/") or "/"
    return key in PROTECTED_JSON_PATHS or key.startswith("/api/") or key in {"/contexts", "/contexts/new", "/contexts/switch", "/contexts/rename", "/contexts/delete"}

login_manager = LoginManager()


@login_manager.user_loader
def load_user(user_id):
    from models.user import load_user as load_user_from_store

    return load_user_from_store(user_id)


@login_manager.request_loader
def load_user_from_identity_provider(req):
    """Authenticate the one identity provider selected for this deployment."""
    if config.AUTH_PROVIDER == "clerk":
        from services.clerk_auth import authenticate_clerk_request

        try:
            return authenticate_clerk_request(req)
        except Exception as exc:
            logging.info("Clerk request authentication failed: %s", exc.__class__.__name__)
            return None
    if config.AUTH_PROVIDER == "firebase":
        cookie = req.cookies.get(config.AUTH_SESSION_COOKIE)
        if not cookie:
            return None
        try:
            from firebase_admin import auth as firebase_auth
            from services.firestore import get_firestore_client
            from models.user import load_user as load_user_from_store

            get_firestore_client()
            claims = firebase_auth.verify_session_cookie(cookie, check_revoked=True)
            return load_user_from_store(claims["uid"])
        except Exception as exc:
            logging.info("Firebase session authentication failed: %s", exc.__class__.__name__)
    return None


@login_manager.unauthorized_handler
def unauthorized():
    if _is_protected_json_path(request.path):
        return jsonify({"error": "unauthorized"}), 401
    return redirect(url_for("auth.login"))


app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["UPLOAD_FOLDER"] = config.UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH


@app.context_processor
def identity_template_context():
    return {
        "auth_provider": config.AUTH_PROVIDER,
        "clerk_enabled": config.AUTH_PROVIDER == "clerk" and bool(
            config.CLERK_PUBLISHABLE_KEY
            and config.CLERK_SECRET_KEY
            and config.CLERK_FRONTEND_API_URL
        ),
        "clerk_publishable_key": config.CLERK_PUBLISHABLE_KEY,
        "clerk_frontend_api_url": config.CLERK_FRONTEND_API_URL,
    }

if config.ENVIRONMENT == "production":
    from services.runtime_config import require_runtime_config
    require_runtime_config(production=True)

login_manager.init_app(app)
login_manager.login_view = "auth.login"

register_blueprints(app)

# PROTECTED_JSON_PATHS decides whether an unauthenticated request gets a 401
# JSON body or an HTML redirect (see unauthorized() above). If a path in it
# were ever renamed, removed, or its blueprint failed to register, callers
# would silently start getting redirected instead of 401ed. Checking every
# entry here (not just a hand-picked subset) is the single source of truth
# for "did every protected route actually register."
_registered_paths = {r.rule for r in app.url_map.iter_rules()}
_missing = {path for path in PROTECTED_JSON_PATHS
            if path not in _registered_paths and f"{path}/" not in _registered_paths}
if _missing:
    raise RuntimeError(
        f"PROTECTED_JSON_PATHS references paths with no registered route: {sorted(_missing)}. "
        "A route was renamed, removed, or a blueprint failed to register -- fix the "
        "mismatch, or update PROTECTED_JSON_PATHS if the path was intentionally removed."
    )

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    print("AI Paralegal Assistant (Multi-Agent) is running...")
    app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG)
