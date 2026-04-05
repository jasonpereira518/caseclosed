import os
import tempfile

from dotenv import load_dotenv

load_dotenv()

# Flask app settings
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret")
SECRET_KEY = os.getenv("SECRET_KEY", FLASK_SECRET_KEY)
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", tempfile.gettempdir())
MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 50 * 1024 * 1024))
PORT = int(os.getenv("PORT", 5050))
DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

# File handling
ALLOWED_EXTENSIONS = {"pdf"}

# External service credentials/config
PROJECT_ID = os.getenv("PROJECT_ID")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
COURTLISTENER_TOKEN = os.getenv("COURTLISTENER_TOKEN")
COURTLISTENER_BASE_URL = os.getenv("COURTLISTENER_BASE_URL", "https://www.courtlistener.com/api/rest/v4/search/")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS", "key.json")

# Firebase / Firestore (context persistence)
FIREBASE_CREDENTIALS = os.getenv("FIREBASE_CREDENTIALS", "key.json")
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "user_contexts")
FIRESTORE_USERS_COLLECTION = os.getenv("FIRESTORE_USERS_COLLECTION", "users")

# Google OAuth (backend)
GOOGLE_OAUTH_CLIENT_SECRETS = os.getenv("GOOGLE_OAUTH_CLIENT_SECRETS", "client_secret.json")
OAUTH_REDIRECT_URI = os.getenv("OAUTH_REDIRECT_URI", "http://localhost:5050/auth/callback")

# Model configuration
CLARIFIER_MODEL = os.getenv("CLARIFIER_MODEL", "gemini-2.5-flash-lite")
SUMMARIZER_MODEL = os.getenv("SUMMARIZER_MODEL", "gemini-2.5-flash-lite")
SCORER_MODEL = os.getenv("SCORER_MODEL", "gemini-2.5-flash-lite")
ANALYZER_MODEL = os.getenv("ANALYZER_MODEL", "gemini-2.5-flash-lite")
DRAFT_MODEL = os.getenv("DRAFT_MODEL", "gemini-2.5-flash-lite")
QUERY_MODEL = os.getenv("QUERY_MODEL", "gemini-2.5-flash-lite")
TIMELINE_MODEL = os.getenv("TIMELINE_MODEL", "gemini-2.5-flash-lite")
STATUTES_MODEL = os.getenv("STATUTES_MODEL", "gemini-2.5-flash-lite")
STRENGTH_MODEL = os.getenv("STRENGTH_MODEL", "gemini-2.5-flash-lite")
