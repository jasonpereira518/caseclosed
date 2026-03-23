import os
import tempfile

from dotenv import load_dotenv

load_dotenv()

# Flask app settings
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret")
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

# Model configuration
CLARIFIER_MODEL = os.getenv("CLARIFIER_MODEL", "gemini-2.5-flash")
SUMMARIZER_MODEL = os.getenv("SUMMARIZER_MODEL", "gemini-2.5-flash")
SCORER_MODEL = os.getenv("SCORER_MODEL", "gemini-2.5-flash")
ANALYZER_MODEL = os.getenv("ANALYZER_MODEL", "gemini-2.5-pro")
DRAFT_MODEL = os.getenv("DRAFT_MODEL", "gemini-2.5-pro")
QUERY_MODEL = os.getenv("QUERY_MODEL", "gemini-2.5-pro")
