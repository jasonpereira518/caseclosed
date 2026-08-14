import os
import tempfile
import json
import base64

from dotenv import load_dotenv

load_dotenv()

# Flask app settings
FLASK_SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret")
SECRET_KEY = os.getenv("SECRET_KEY", FLASK_SECRET_KEY)
UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", tempfile.gettempdir())
# Cloud Run rejects HTTP/1 requests over 32 MiB at the front end, before Flask
# ever sees them, with an opaque error. Stay under it with multipart headroom.
MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", 30 * 1024 * 1024))
PORT = int(os.getenv("PORT", 5050))
DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"
ENVIRONMENT = os.getenv("ENVIRONMENT", "production" if os.getenv("K_SERVICE") else "development").lower()
APP_BASE_URL = os.getenv("APP_BASE_URL", "http://localhost:5050").rstrip("/")
# HSTS is the one header you cannot take back. Keep it dialable so the first
# days on a new domain can run at a short max-age before committing to a year.
HSTS_MAX_AGE = int(os.getenv("HSTS_MAX_AGE", 31536000))

# File handling
ALLOWED_EXTENSIONS = {"pdf"}

# External service credentials/config
PROJECT_ID = os.getenv("PROJECT_ID")
GOOGLE_CLOUD_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
GEMINI_LOCATION = os.getenv("GEMINI_LOCATION", "global")
COURTLISTENER_TOKEN = os.getenv("COURTLISTENER_TOKEN")
COURTLISTENER_BASE_URL = os.getenv("COURTLISTENER_BASE_URL", "https://www.courtlistener.com/api/rest/v4/search/")
GOOGLE_APPLICATION_CREDENTIALS = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

# Firebase / Firestore (context persistence). When unset, Firebase Admin uses
# Application Default Credentials (for example, the Cloud Run service identity).
FIREBASE_CREDENTIALS = os.getenv("FIREBASE_CREDENTIALS")
FIRESTORE_COLLECTION = os.getenv("FIRESTORE_COLLECTION", "user_contexts")
FIRESTORE_USERS_COLLECTION = os.getenv("FIRESTORE_USERS_COLLECTION", "users")
FIRESTORE_WORKSPACES_COLLECTION = os.getenv("FIRESTORE_WORKSPACES_COLLECTION", "workspaces")
FIRESTORE_MATTER_INDEX_COLLECTION = os.getenv("FIRESTORE_MATTER_INDEX_COLLECTION", "matter_index")
FIRESTORE_INVITATIONS_COLLECTION = os.getenv("FIRESTORE_INVITATIONS_COLLECTION", "workspace_invitations")
FIRESTORE_LEGAL_SOURCES_COLLECTION = os.getenv("FIRESTORE_LEGAL_SOURCES_COLLECTION", "legal_sources")
FIREBASE_STORAGE_BUCKET = os.getenv("FIREBASE_STORAGE_BUCKET")

# Background work. Cloud Tasks is the production transport; inline mode keeps
# local development usable without starting another process.
TASKS_MODE = os.getenv("TASKS_MODE", "inline").lower()
TASKS_PROJECT_ID = os.getenv("TASKS_PROJECT_ID", PROJECT_ID or "")
TASKS_LOCATION = os.getenv("TASKS_LOCATION", GOOGLE_CLOUD_LOCATION)
TASKS_QUEUE = os.getenv("TASKS_QUEUE", "caseclosed-jobs")
TASKS_WORKER_URL = os.getenv("TASKS_WORKER_URL", "")
TASKS_WORKER_AUDIENCE = os.getenv("TASKS_WORKER_AUDIENCE", TASKS_WORKER_URL)
TASKS_SERVICE_ACCOUNT = os.getenv("TASKS_SERVICE_ACCOUNT", "")
INTERNAL_WORKER_TOKEN = os.getenv("INTERNAL_WORKER_TOKEN", "")
JOB_MAX_ATTEMPTS = int(os.getenv("JOB_MAX_ATTEMPTS", "3"))

# Retrieval. Agent Retrieval / Vector Search 2.0 is optional locally; the
# Firestore lexical fallback follows the same tenant filters.
VECTOR_SEARCH_ENABLED = os.getenv("VECTOR_SEARCH_ENABLED", "false").lower() == "true"
VECTOR_SEARCH_PROJECT_ID = os.getenv("VECTOR_SEARCH_PROJECT_ID", PROJECT_ID or "")
VECTOR_SEARCH_LOCATION = os.getenv("VECTOR_SEARCH_LOCATION", GOOGLE_CLOUD_LOCATION)
VECTOR_PRIVATE_COLLECTION = os.getenv("VECTOR_PRIVATE_COLLECTION", "caseclosed-matters")
VECTOR_LEGAL_COLLECTION = os.getenv("VECTOR_LEGAL_COLLECTION", "caseclosed-law")
VECTOR_SEARCH_FIELD = os.getenv("VECTOR_SEARCH_FIELD", "text_embedding")
VECTOR_EMBEDDING_MODEL = os.getenv("VECTOR_EMBEDDING_MODEL", "gemini-embedding-001")
VECTOR_EMBEDDING_DIMENSIONS = int(os.getenv("VECTOR_EMBEDDING_DIMENSIONS", "3072"))
RETRIEVAL_TOP_K = int(os.getenv("RETRIEVAL_TOP_K", "8"))

# Document AI OCR is used when native extraction yields too little text.
DOCUMENT_AI_PROCESSOR_ID = os.getenv("DOCUMENT_AI_PROCESSOR_ID", "")
DOCUMENT_AI_LOCATION = os.getenv("DOCUMENT_AI_LOCATION", "us")

# Shared legal corpus synchronization.
LEGAL_CORPUS_SYNC_TOKEN = os.getenv("LEGAL_CORPUS_SYNC_TOKEN", "")
LEGAL_CORPUS_SYNC_SERVICE_ACCOUNT = os.getenv("LEGAL_CORPUS_SYNC_SERVICE_ACCOUNT", "")
LEGAL_CORPUS_SYNC_AUDIENCE = os.getenv(
    "LEGAL_CORPUS_SYNC_AUDIENCE",
    f"{os.getenv('APP_BASE_URL', 'http://localhost:5050').rstrip('/')}/internal/legal-corpus/sync")
LEGAL_CORPUS_DAILY_LIMIT = int(os.getenv("LEGAL_CORPUS_DAILY_LIMIT", "500"))
try:
    LEGAL_SOURCE_REGISTRY = json.loads(os.getenv("LEGAL_SOURCE_REGISTRY", "[]"))
except json.JSONDecodeError:
    LEGAL_SOURCE_REGISTRY = []

# Identity. Clerk is the active provider; Firebase remains available as a
# single-provider rollback during the migration window.
AUTH_PROVIDER = os.getenv("AUTH_PROVIDER", "clerk").strip().lower()
CLERK_PUBLISHABLE_KEY = os.getenv("CLERK_PUBLISHABLE_KEY", "").strip()
CLERK_SECRET_KEY = os.getenv("CLERK_SECRET_KEY", "").strip()
CLERK_JWT_KEY = os.getenv("CLERK_JWT_KEY", "").replace("\\n", "\n").strip()
CLERK_WEBHOOK_SIGNING_SECRET = os.getenv("CLERK_WEBHOOK_SIGNING_SECRET", "").strip()
CLERK_AUTHORIZED_PARTIES = [
    value.strip().rstrip("/")
    for value in os.getenv("CLERK_AUTHORIZED_PARTIES", APP_BASE_URL).split(",")
    if value.strip()
]
FIRESTORE_CLERK_WEBHOOK_EVENTS_COLLECTION = os.getenv(
    "FIRESTORE_CLERK_WEBHOOK_EVENTS_COLLECTION", "clerk_webhook_events")


def _clerk_frontend_api_url(publishable_key: str) -> str:
    if not publishable_key:
        return ""
    try:
        encoded = publishable_key.split("_", 2)[2]
        encoded += "=" * (-len(encoded) % 4)
        hostname = base64.urlsafe_b64decode(encoded).decode("utf-8").rstrip("$")
        return f"https://{hostname}" if hostname else ""
    except (IndexError, ValueError, UnicodeDecodeError):
        return ""


CLERK_FRONTEND_API_URL = os.getenv(
    "CLERK_FRONTEND_API_URL", _clerk_frontend_api_url(CLERK_PUBLISHABLE_KEY)
).rstrip("/")

# Firebase Authentication rollback configuration. FIREBASE_WEB_CONFIG is the
# intentionally public browser configuration object.
try:
    FIREBASE_WEB_CONFIG = json.loads(os.getenv("FIREBASE_WEB_CONFIG", "{}"))
except json.JSONDecodeError:
    FIREBASE_WEB_CONFIG = {}
AUTH_SESSION_COOKIE = os.getenv("AUTH_SESSION_COOKIE", "__session")
AUTH_SESSION_DAYS = int(os.getenv("AUTH_SESSION_DAYS", "5"))
AUTH_COOKIE_SECURE = os.getenv(
    "AUTH_COOKIE_SECURE", "true" if os.getenv("APP_BASE_URL", "").startswith("https://") else "false"
).lower() == "true"

# Workspace invitations. In production SMTP is required so invite secrets are
# not exposed in API responses. Development returns the URL to the caller.
SMTP_HOST = os.getenv("SMTP_HOST")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_FROM = os.getenv("SMTP_FROM")
INVITATION_TTL_DAYS = int(os.getenv("INVITATION_TTL_DAYS", "7"))

# Model configuration
CHAT_FAST_MODEL = os.getenv("CHAT_FAST_MODEL", "gemini-3.5-flash-lite")
CHAT_REASONING_MODEL = os.getenv("CHAT_REASONING_MODEL", "gemini-3.6-flash")
CLARIFIER_MODEL = os.getenv("CLARIFIER_MODEL", CHAT_FAST_MODEL)
SUMMARIZER_MODEL = os.getenv("SUMMARIZER_MODEL", CHAT_FAST_MODEL)
SCORER_MODEL = os.getenv("SCORER_MODEL", CHAT_FAST_MODEL)
ANALYZER_MODEL = os.getenv("ANALYZER_MODEL", CHAT_REASONING_MODEL)
DRAFT_MODEL = os.getenv("DRAFT_MODEL", CHAT_REASONING_MODEL)
QUERY_MODEL = os.getenv("QUERY_MODEL", CHAT_FAST_MODEL)
TIMELINE_MODEL = os.getenv("TIMELINE_MODEL", CHAT_REASONING_MODEL)
STATUTES_MODEL = os.getenv("STATUTES_MODEL", CHAT_REASONING_MODEL)
STRENGTH_MODEL = os.getenv("STRENGTH_MODEL", CHAT_REASONING_MODEL)
