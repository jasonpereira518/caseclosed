import os
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"  # DEV ONLY — remove for production

import config
from flask import Flask, jsonify, redirect, request, url_for
from flask_login import LoginManager

from routes import register_blueprints

PROTECTED_JSON_PATHS = frozenset({"/chat", "/upload", "/analyze", "/draft", "/context"})

login_manager = LoginManager()


@login_manager.user_loader
def load_user(user_id):
    from models.user import load_user as load_user_from_store

    return load_user_from_store(user_id)


@login_manager.unauthorized_handler
def unauthorized():
    if request.path in PROTECTED_JSON_PATHS:
        return jsonify({"error": "unauthorized"}), 401
    return redirect(url_for("auth.login"))


app = Flask(__name__)
app.secret_key = config.SECRET_KEY
app.config["UPLOAD_FOLDER"] = config.UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH

login_manager.init_app(app)
login_manager.login_view = "auth.login"

register_blueprints(app)

# =====================================================
# RUN
# =====================================================
if __name__ == "__main__":
    print("AI Paralegal Assistant (Multi-Agent) is running...")
    app.run(host="0.0.0.0", port=config.PORT, debug=config.DEBUG)
