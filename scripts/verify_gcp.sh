#!/usr/bin/env bash
set -euo pipefail

required=(GCP_PROJECT_ID CLOUD_RUN_SERVICE_URL STORAGE_BUCKET)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: ${name}" >&2
    exit 2
  fi
done

GCP_REGION="${GCP_REGION:-us-central1}"
TASKS_LOCATION="${TASKS_LOCATION:-$GCP_REGION}"
TASKS_QUEUE="${TASKS_QUEUE:-caseclosed-jobs}"
VECTOR_LOCATION="${VECTOR_LOCATION:-$GCP_REGION}"
VECTOR_PRIVATE_COLLECTION="${VECTOR_PRIVATE_COLLECTION:-caseclosed-matters}"
VECTOR_LEGAL_COLLECTION="${VECTOR_LEGAL_COLLECTION:-caseclosed-law}"
ENABLE_VECTOR_SEARCH="${ENABLE_VECTOR_SEARCH:-false}"
PYTHON_BIN="${PYTHON_BIN:-python}"

failures=0
check() {
  local label="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    echo "ok: ${label}"
  else
    echo "failed: ${label}" >&2
    failures=$((failures + 1))
  fi
}

check "Cloud Run liveness" curl --fail --silent --show-error \
  "${CLOUD_RUN_SERVICE_URL%/}/livez"
check "Cloud Run readiness" curl --fail --silent --show-error \
  "${CLOUD_RUN_SERVICE_URL%/}/readyz"
check "Cloud Tasks queue" gcloud tasks queues describe "$TASKS_QUEUE" \
  --project "$GCP_PROJECT_ID" --location "$TASKS_LOCATION"
if [[ "$ENABLE_VECTOR_SEARCH" == "true" ]]; then
  check "private Vector Search collection" gcloud vector-search collections describe \
    "$VECTOR_PRIVATE_COLLECTION" --project "$GCP_PROJECT_ID" --location "$VECTOR_LOCATION"
  check "shared-law Vector Search collection" gcloud vector-search collections describe \
    "$VECTOR_LEGAL_COLLECTION" --project "$GCP_PROJECT_ID" --location "$VECTOR_LOCATION"
  check "private Vector Search index" gcloud vector-search collections indexes describe \
    matter-evidence-index --collection "$VECTOR_PRIVATE_COLLECTION" \
    --project "$GCP_PROJECT_ID" --location "$VECTOR_LOCATION"
  check "shared-law Vector Search index" gcloud vector-search collections indexes describe \
    shared-law-index --collection "$VECTOR_LEGAL_COLLECTION" \
    --project "$GCP_PROJECT_ID" --location "$VECTOR_LOCATION"
else
  echo "skipped: Vector Search (cost-saving Firestore fallback is configured)"
fi
check "staging bucket" gcloud storage buckets describe "gs://${STORAGE_BUCKET}"

if [[ -n "${DOCUMENT_AI_PROCESSOR_ID:-}" ]]; then
  check "Document AI processor" "$PYTHON_BIN" scripts/create_document_ai_processor.py
else
  echo "skipped: Document AI processor (DOCUMENT_AI_PROCESSOR_ID is unset)"
fi

if (( failures > 0 )); then
  echo "${failures} production check(s) failed" >&2
  exit 1
fi
echo "All configured production checks passed"
