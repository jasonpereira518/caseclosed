import os
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # DEV ONLY — remove for production

import config
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
        "/timeline/add",
        "/intake",
    }
)
# Note: login JSON responses for these paths use _is_protected_json_path(request.path),
# which normalizes trailing slashes (e.g. /case/describe/ matches /case/describe).


def _is_protected_json_path(path: str) -> bool:
    """Match PROTECTED_JSON_PATHS even when the client uses a trailing slash."""
    key = path.rstrip("/") or "/"
    return key in PROTECTED_JSON_PATHS

login_manager = LoginManager()


@login_manager.user_loader
def load_user(user_id):
    from models.user import load_user as load_user_from_store

    return load_user_from_store(user_id)


@login_manager.unauthorized_handler
def unauthorized():
    if _is_protected_json_path(request.path):
        return jsonify({"error": "unauthorized"}), 401
    return redirect(url_for("auth.login"))


app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["UPLOAD_FOLDER"] = config.UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

login_manager.init_app(app)
login_manager.login_view = "auth.login"

register_blueprints(app)

_missing = {
    "/case/ask",
    "/chat/case/ask",
    "/case/describe",
    "/chat/case/describe",
    "/case/treatment",
    "/chat/case/treatment",
} - {r.rule for r in app.url_map.iter_rules()}
if _missing:
    raise RuntimeError(
        f"chat blueprint did not register expected POST case-ask paths; missing: {sorted(_missing)}. "
        "Check routes.chat (case_ask decorators) and routes.register_blueprints."
    )

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    print("AI Paralegal Assistant (Multi-Agent) is running...")
    app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG)
