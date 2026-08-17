import logging

import config

from flask import Flask, jsonify, redirect, request, url_for
from flask_login import LoginManager, current_user
from werkzeug.middleware.proxy_fix import ProxyFix

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
    """Authenticate the Clerk session presented with this request."""
    from services.clerk_auth import authenticate_clerk_request

    try:
        return authenticate_clerk_request(req)
    except Exception as exc:
        logging.info("Clerk request authentication failed: %s", exc.__class__.__name__)
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

# Cloud Run terminates TLS at Google's front end and speaks plain HTTP to this
# container. Without this, url_for(..., _external=True) emits http:// on the
# public domain (og:url, canonical) and request.is_secure is always False.
# x_host=0 is deliberate: Cloud Run does not set X-Forwarded-Host, it passes the
# real Host through untouched -- so trusting the header would let any client
# forge our hostname.
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0)

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=config.AUTH_COOKIE_SECURE,
    # Lax, not Strict: Clerk's Google sign-in is redirect-based
    # (static/auth.js authenticateWithRedirect), and Strict would also drop the
    # session on any inbound link from email or search.
    SESSION_COOKIE_SAMESITE="Lax",
)

# Report-only by design. Clerk's documented policy requires script-src and
# style-src 'unsafe-inline' because its components inject both at runtime, so an
# enforcing policy buys little -- while a wrong clerk_frontend_api_url (which is
# derived at runtime from the publishable key) would block clerk.browser.js and
# make sign-in impossible with no recovery short of a redeploy. Collect
# violations against the real domain first, then promote to enforcing.
CSP_REPORT_ONLY = "; ".join([
    "default-src 'self'",
    f"script-src 'self' 'unsafe-inline' {config.CLERK_FRONTEND_API_URL} "
    "https://challenges.cloudflare.com https://*.protect.clerk.com https://www.gstatic.com",
    "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
    "font-src 'self' https://fonts.gstatic.com",
    f"connect-src 'self' {config.CLERK_FRONTEND_API_URL} https://*.protect.clerk.com "
    "https://clerk-telemetry.com https://identitytoolkit.googleapis.com",
    "img-src 'self' data: https://img.clerk.com https://*.googleusercontent.com",
    "frame-src 'self' https://challenges.cloudflare.com https://*.protect.clerk.com",
    "worker-src 'self' blob:",
    "frame-ancestors 'self'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
])


@app.before_request
def redirect_to_https():
    """Cloud Run domain mappings serve plain HTTP without redirecting to HTTPS.

    Only act when the front end explicitly reported an http:// arrival. An
    absent X-Forwarded-Proto means a direct container hit -- Cloud Run's startup
    and liveness probes -- and 301ing those fails the health check.
    """
    if config.ENVIRONMENT != "production":
        return None
    if request.headers.get("X-Forwarded-Proto") != "http":
        return None
    if request.method not in ("GET", "HEAD"):
        return None
    return redirect(request.url.replace("http://", "https://", 1), code=301)


# The access gate: sign-in is the request for early access. Accounts created
# after the gate carry access_status="pending" until an admin approves them
# (routes/admin.py); accounts predating the gate have no access_status field
# and pass. Only the paths a gated user still needs are exempt — the public
# surface, auth (so they can sign out), machine endpoints, and the admin
# surface itself (which does its own, stricter check and 404s non-admins).
GATE_EXEMPT_PATHS = frozenset({
    "/", "/demo", "/demo/fixture", "/waitlist", "/privacy", "/terms",
    "/healthz", "/livez", "/readyz", "/favicon.ico",
})
GATE_EXEMPT_PREFIXES = ("/static/", "/auth/", "/webhooks/", "/internal/",
                        "/admin/", "/api/admin/")


@app.before_request
def enforce_access_gate():
    path = request.path
    if path in GATE_EXEMPT_PATHS or path.startswith(GATE_EXEMPT_PREFIXES):
        return None
    if not current_user.is_authenticated:
        return None  # 401/redirect handling stays with login_required
    if current_user.access_status in (None, "", "approved"):
        return None
    if _is_protected_json_path(path):
        return jsonify({"error": "access_pending"}), 403
    return redirect(url_for("main.waitlist"))


@app.after_request
def set_security_headers(response):
    """Baseline security headers on every response.

    setdefault, not assignment: /demo sets its own framing and cache headers
    (routes/demo.py) and tests/test_demo_route.py asserts them. setdefault runs
    after the route's own headers are merged, so it neither clobbers nor
    duplicates them.
    """
    headers = response.headers
    headers.setdefault("X-Content-Type-Options", "nosniff")
    headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    headers.setdefault("Content-Security-Policy", "frame-ancestors 'self'")
    headers.setdefault("Content-Security-Policy-Report-Only", CSP_REPORT_ONLY)
    headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if request.is_secure:
        headers.setdefault(
            "Strict-Transport-Security",
            f"max-age={config.HSTS_MAX_AGE}; includeSubDomains",
        )
    return response


@app.context_processor
def identity_template_context():
    return {
        "max_upload_bytes": config.MAX_CONTENT_LENGTH,
        "clerk_enabled": bool(
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
