from .auth import auth_bp
from .main import main_bp
from .upload import upload_bp
from .chat import chat_bp
from .analyze import analyze_bp
from .draft import draft_bp
from .context import context_bp
from .intake import intake_bp
from .notes import notes_bp
from .search import search_bp
from .demo import demo_bp
from .account import account_bp, internal_bp


def register_blueprints(app):
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(chat_bp)
    app.register_blueprint(analyze_bp)
    app.register_blueprint(draft_bp)
    app.register_blueprint(context_bp)
    app.register_blueprint(intake_bp)
    app.register_blueprint(notes_bp)
    app.register_blueprint(search_bp)
    app.register_blueprint(demo_bp)
    app.register_blueprint(account_bp)
    app.register_blueprint(internal_bp)
