"""Fail-fast validation for local and production runtime configuration."""
from __future__ import annotations

from urllib.parse import urlparse

import config


def validate_runtime_config(*, production: bool = False) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    if config.ENVIRONMENT not in {"development", "test", "production"}:
        errors.append("ENVIRONMENT must be development, test, or production")

    if not config.PROJECT_ID:
        errors.append("PROJECT_ID is required")
    if not config.GEMINI_LOCATION:
        errors.append("GEMINI_LOCATION is required")
    if production and config.SECRET_KEY in {"dev-secret", "replace-me", ""}:
        errors.append("SECRET_KEY/FLASK_SECRET_KEY must be a production secret")
    if production and not config.AUTH_COOKIE_SECURE:
        errors.append("AUTH_COOKIE_SECURE must be true in production")
    if production and not config.APP_BASE_URL.startswith("https://"):
        errors.append("APP_BASE_URL must use HTTPS in production")

    if config.TASKS_MODE not in {"inline", "cloud"}:
        errors.append("TASKS_MODE must be inline or cloud")
    if production and config.TASKS_MODE != "cloud":
        errors.append("TASKS_MODE must be cloud in production")
    if config.TASKS_MODE == "cloud":
        required = {
            "TASKS_PROJECT_ID": config.TASKS_PROJECT_ID,
            "TASKS_LOCATION": config.TASKS_LOCATION,
            "TASKS_QUEUE": config.TASKS_QUEUE,
            "TASKS_WORKER_URL": config.TASKS_WORKER_URL,
            "TASKS_WORKER_AUDIENCE": config.TASKS_WORKER_AUDIENCE,
            "TASKS_SERVICE_ACCOUNT": config.TASKS_SERVICE_ACCOUNT,
        }
        errors.extend(f"{name} is required in cloud task mode"
                      for name, value in required.items() if not value)
        if config.TASKS_WORKER_URL and not _https_url(config.TASKS_WORKER_URL):
            errors.append("TASKS_WORKER_URL must be an HTTPS URL")

    if config.VECTOR_SEARCH_ENABLED:
        required = {
            "VECTOR_SEARCH_PROJECT_ID": config.VECTOR_SEARCH_PROJECT_ID,
            "VECTOR_SEARCH_LOCATION": config.VECTOR_SEARCH_LOCATION,
            "VECTOR_PRIVATE_COLLECTION": config.VECTOR_PRIVATE_COLLECTION,
            "VECTOR_LEGAL_COLLECTION": config.VECTOR_LEGAL_COLLECTION,
            "VECTOR_SEARCH_FIELD": config.VECTOR_SEARCH_FIELD,
            "VECTOR_EMBEDDING_MODEL": config.VECTOR_EMBEDDING_MODEL,
        }
        errors.extend(f"{name} is required when Vector Search is enabled"
                      for name, value in required.items() if not value)
        if config.VECTOR_EMBEDDING_DIMENSIONS <= 0:
            errors.append("VECTOR_EMBEDDING_DIMENSIONS must be positive")
    elif production:
        warnings.append("Vector Search is disabled; Firestore lexical fallback is not intended for scale")

    if config.DOCUMENT_AI_PROCESSOR_ID and not config.DOCUMENT_AI_LOCATION:
        errors.append("DOCUMENT_AI_LOCATION is required with DOCUMENT_AI_PROCESSOR_ID")
    elif production and not config.DOCUMENT_AI_PROCESSOR_ID:
        warnings.append("Document AI is not configured; scanned PDFs will fail extraction")

    if production and not config.FIREBASE_STORAGE_BUCKET:
        errors.append("FIREBASE_STORAGE_BUCKET is required for transient cloud ingestion")
    if production and not (config.LEGAL_CORPUS_SYNC_TOKEN
                           or config.LEGAL_CORPUS_SYNC_SERVICE_ACCOUNT):
        warnings.append("Legal corpus synchronization is disabled because neither OIDC nor a token is configured")

    for index, source in enumerate(config.LEGAL_SOURCE_REGISTRY):
        if not isinstance(source, dict):
            errors.append(f"LEGAL_SOURCE_REGISTRY[{index}] must be an object")
            continue
        if not source.get("official"):
            errors.append(f"LEGAL_SOURCE_REGISTRY[{index}] must explicitly set official=true")
        if not _https_url(str(source.get("url") or "")):
            errors.append(f"LEGAL_SOURCE_REGISTRY[{index}].url must use HTTPS")

    configured_models = {model for model in (
        config.CHAT_FAST_MODEL, config.CHAT_REASONING_MODEL, config.CLARIFIER_MODEL,
        config.SUMMARIZER_MODEL, config.SCORER_MODEL, config.ANALYZER_MODEL,
        config.DRAFT_MODEL, config.QUERY_MODEL, config.TIMELINE_MODEL,
        config.STRENGTH_MODEL,
    )}
    legacy_models = sorted(model for model in configured_models
                           if str(model).startswith("gemini-2.5-"))
    if legacy_models:
        warnings.append("Gemini 2.5 models are scheduled for retirement; migrate these model IDs: "
                        + ", ".join(legacy_models))
    preview_models = sorted(model for model in configured_models
                            if "preview" in str(model).lower())
    if production and preview_models:
        warnings.append("Preview Gemini models are configured for production: "
                        + ", ".join(preview_models))

    return {"valid": not errors, "errors": errors, "warnings": warnings,
            "mode": "production" if production else "development"}


def require_runtime_config(*, production: bool = False) -> dict:
    report = validate_runtime_config(production=production)
    if not report["valid"]:
        raise RuntimeError("Invalid runtime configuration: " + "; ".join(report["errors"]))
    return report


def _https_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme == "https" and bool(parsed.netloc)
