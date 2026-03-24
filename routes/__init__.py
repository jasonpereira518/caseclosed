from .auth import auth_bp
from .main import main_bp
from .upload import upload_bp
from .chat import chat_bp
from .analyze import analyze_bp
from .draft import draft_bp
from .context import context_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(analyze_bp)
    app.register_blueprint(draft_bp)
    app.register_blueprint(context_bp)

