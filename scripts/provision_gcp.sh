#!/usr/bin/env bash
set -euo pipefail

apply=false
if [[ "${1:-}" == "--apply" ]]; then
  apply=true
elif [[ -n "${1:-}" && "${1:-}" != "--check" ]]; then
  echo "Usage: $0 [--check|--apply]" >&2
  exit 2
fi

required=(GCP_PROJECT_ID CLOUD_RUN_SERVICE CLOUD_RUN_SERVICE_URL STORAGE_BUCKET)
for name in "${required[@]}"; do
  if [[ -z "${!name:-}" ]]; then
    echo "Missing required environment variable: ${name}" >&2
    exit 2
  fi
done

GCP_REGION="${GCP_REGION:-us-central1}"
TASKS_LOCATION="${TASKS_LOCATION:-$GCP_REGION}"
TASKS_QUEUE="${TASKS_QUEUE:-caseclosed-jobs}"
TASKS_MAX_CONCURRENT_DISPATCHES="${TASKS_MAX_CONCURRENT_DISPATCHES:-5}"
TASKS_MAX_DISPATCHES_PER_SECOND="${TASKS_MAX_DISPATCHES_PER_SECOND:-2}"
VECTOR_LOCATION="${VECTOR_LOCATION:-$GCP_REGION}"
VECTOR_PRIVATE_COLLECTION="${VECTOR_PRIVATE_COLLECTION:-caseclosed-matters}"
VECTOR_LEGAL_COLLECTION="${VECTOR_LEGAL_COLLECTION:-caseclosed-law}"
VECTOR_SEARCH_FIELD="${VECTOR_SEARCH_FIELD:-text_embedding}"
VECTOR_EMBEDDING_MODEL="${VECTOR_EMBEDDING_MODEL:-gemini-embedding-001}"
VECTOR_EMBEDDING_DIMENSIONS="${VECTOR_EMBEDDING_DIMENSIONS:-3072}"
APP_SERVICE_ACCOUNT="${APP_SERVICE_ACCOUNT:-caseclosed-runtime@${GCP_PROJECT_ID}.iam.gserviceaccount.com}"
TASKS_SERVICE_ACCOUNT="${TASKS_SERVICE_ACCOUNT:-caseclosed-tasks@${GCP_PROJECT_ID}.iam.gserviceaccount.com}"
SCHEDULER_SERVICE_ACCOUNT="${SCHEDULER_SERVICE_ACCOUNT:-caseclosed-scheduler@${GCP_PROJECT_ID}.iam.gserviceaccount.com}"
CORPUS_SCHEDULE="${CORPUS_SCHEDULE:-15 3 * * *}"
ENABLE_VECTOR_SEARCH="${ENABLE_VECTOR_SEARCH:-false}"
ENABLE_LEGAL_CORPUS_SYNC="${ENABLE_LEGAL_CORPUS_SYNC:-false}"

run() {
  if $apply; then
    "$@"
  else
    printf 'would run:'
    printf ' %q' "$@"
    printf '\n'
  fi
}

ensure_service_account() {
  local email="$1"
  local account_id="${email%@*}"
  if $apply && gcloud iam service-accounts describe "$email" --project "$GCP_PROJECT_ID" >/dev/null 2>&1; then
    return
  fi
  run gcloud iam service-accounts create "$account_id" --project "$GCP_PROJECT_ID" \
    --display-name "$account_id"
}

ensure_collection() {
  local collection="$1"
  local display_name="$2"
  if $apply && gcloud vector-search collections describe "$collection" \
      --project "$GCP_PROJECT_ID" --location "$VECTOR_LOCATION" >/dev/null 2>&1; then
    return
  fi
  local data_schema
  data_schema='{"type":"object","properties":{"source_id":{"type":"string"},"document_id":{"type":"string"},"legal_source_id":{"type":"string"},"source_type":{"type":"string"},"title":{"type":"string"},"text":{"type":"string"},"locator":{"type":"string"},"canonical_url":{"type":"string"},"jurisdiction":{"type":"string"},"workspace_id":{"type":"string"},"matter_id":{"type":"string"},"owner_id":{"type":"string"},"included":{"type":"boolean"}}}'
  local vector_schema
  vector_schema="{\"${VECTOR_SEARCH_FIELD}\":{\"denseVector\":{\"dimensions\":${VECTOR_EMBEDDING_DIMENSIONS},\"vertexEmbeddingConfig\":{\"modelId\":\"${VECTOR_EMBEDDING_MODEL}\",\"taskType\":\"RETRIEVAL_DOCUMENT\",\"textTemplate\":\"{text}\"}}}}"
  run gcloud vector-search collections create "$collection" --project "$GCP_PROJECT_ID" \
    --location "$VECTOR_LOCATION" --display-name "$display_name" \
    --data-schema "$data_schema" --vector-schema "$vector_schema"
}

ensure_index() {
  local collection="$1"
  local index_id="$2"
  local filter_fields="$3"
  if $apply && gcloud vector-search collections indexes describe "$index_id" \
      --collection "$collection" --project "$GCP_PROJECT_ID" \
      --location "$VECTOR_LOCATION" >/dev/null 2>&1; then
    return
  fi
  run gcloud vector-search collections indexes create "$index_id" \
    --collection "$collection" --project "$GCP_PROJECT_ID" \
    --location "$VECTOR_LOCATION" --index-field "$VECTOR_SEARCH_FIELD" \
    --distance-metric cosine-distance --filter-fields "$filter_fields" \
    --store-fields source_id,document_id,legal_source_id,source_type,title,text,locator,canonical_url,jurisdiction,workspace_id,matter_id,included
}

mode=check
if $apply; then mode=apply; fi
echo "Case Closed Google Cloud provisioning (${mode})"
services=(run.googleapis.com cloudtasks.googleapis.com documentai.googleapis.com
  aiplatform.googleapis.com firestore.googleapis.com storage.googleapis.com iam.googleapis.com)
if [[ "$ENABLE_VECTOR_SEARCH" == "true" ]]; then
  services+=(vectorsearch.googleapis.com)
fi
if [[ "$ENABLE_LEGAL_CORPUS_SYNC" == "true" ]]; then
  services+=(cloudscheduler.googleapis.com)
fi
run gcloud services enable --project "$GCP_PROJECT_ID" "${services[@]}"

ensure_service_account "$APP_SERVICE_ACCOUNT"
ensure_service_account "$TASKS_SERVICE_ACCOUNT"
if [[ "$ENABLE_LEGAL_CORPUS_SYNC" == "true" ]]; then
  ensure_service_account "$SCHEDULER_SERVICE_ACCOUNT"
fi

runtime_roles=(roles/datastore.user roles/cloudtasks.enqueuer
  roles/documentai.apiUser roles/aiplatform.user
  # Secrets are delivered as Cloud Run secret env vars, read by the runtime
  # identity at instance start.
  roles/secretmanager.secretAccessor)
if [[ "$ENABLE_VECTOR_SEARCH" == "true" ]]; then
  runtime_roles+=(roles/vectorsearch.dataObjectWriter)
fi
for role in "${runtime_roles[@]}"; do
  run gcloud projects add-iam-policy-binding "$GCP_PROJECT_ID" \
    --member "serviceAccount:${APP_SERVICE_ACCOUNT}" --role "$role" --quiet
done
run gcloud storage buckets add-iam-policy-binding "gs://${STORAGE_BUCKET}" \
  --member "serviceAccount:${APP_SERVICE_ACCOUNT}" --role roles/storage.objectAdmin
run gcloud iam service-accounts add-iam-policy-binding "$TASKS_SERVICE_ACCOUNT" \
  --project "$GCP_PROJECT_ID" --member "serviceAccount:${APP_SERVICE_ACCOUNT}" \
  --role roles/iam.serviceAccountUser

# The runtime service account must be able to sign blobs AS ITSELF. On Cloud Run
# the ADC credentials come from the metadata server and carry no private key, so
# generate_signed_url() (services/storage.py) falls back to the IAM signBlob API,
# which requires this binding. Without it, document downloads, account exports,
# and user avatars all fail -- and the avatar failure is swallowed
# (services/tenancy.py returns "" on RuntimeError), so it shows up as a silently
# missing image on ordinary page loads rather than a visible error.
run gcloud iam service-accounts add-iam-policy-binding "$APP_SERVICE_ACCOUNT" \
  --project "$GCP_PROJECT_ID" --member "serviceAccount:${APP_SERVICE_ACCOUNT}" \
  --role roles/iam.serviceAccountTokenCreator

callers=("$TASKS_SERVICE_ACCOUNT")
if [[ "$ENABLE_LEGAL_CORPUS_SYNC" == "true" ]]; then
  callers+=("$SCHEDULER_SERVICE_ACCOUNT")
fi
for caller in "${callers[@]}"; do
  run gcloud run services add-iam-policy-binding "$CLOUD_RUN_SERVICE" \
    --project "$GCP_PROJECT_ID" --region "$GCP_REGION" \
    --member "serviceAccount:${caller}" --role roles/run.invoker
done

if ! $apply || ! gcloud tasks queues describe "$TASKS_QUEUE" --project "$GCP_PROJECT_ID" \
    --location "$TASKS_LOCATION" >/dev/null 2>&1; then
  run gcloud tasks queues create "$TASKS_QUEUE" --project "$GCP_PROJECT_ID" \
    --location "$TASKS_LOCATION" \
    --max-concurrent-dispatches "$TASKS_MAX_CONCURRENT_DISPATCHES" \
    --max-dispatches-per-second "$TASKS_MAX_DISPATCHES_PER_SECOND"
fi
run gcloud tasks queues update "$TASKS_QUEUE" --project "$GCP_PROJECT_ID" \
  --location "$TASKS_LOCATION" \
  --max-concurrent-dispatches "$TASKS_MAX_CONCURRENT_DISPATCHES" \
  --max-dispatches-per-second "$TASKS_MAX_DISPATCHES_PER_SECOND" \
  --max-attempts 5 --max-retry-duration 3600s \
  --min-backoff 10s --max-backoff 300s --max-doublings 5

if [[ "$ENABLE_VECTOR_SEARCH" == "true" ]]; then
  ensure_collection "$VECTOR_PRIVATE_COLLECTION" "Case Closed matter evidence"
  ensure_collection "$VECTOR_LEGAL_COLLECTION" "Case Closed shared law"
  ensure_index "$VECTOR_PRIVATE_COLLECTION" matter-evidence-index workspace_id,matter_id,included
  ensure_index "$VECTOR_LEGAL_COLLECTION" shared-law-index jurisdiction,source_type
else
  echo "Vector Search not provisioned (cost-saving default); Firestore retrieval remains active."
fi

corpus_url="${CLOUD_RUN_SERVICE_URL%/}/internal/legal-corpus/sync"
if [[ "$ENABLE_LEGAL_CORPUS_SYNC" == "true" ]]; then
  if ! $apply || ! gcloud scheduler jobs describe caseclosed-legal-corpus \
      --project "$GCP_PROJECT_ID" --location "$GCP_REGION" >/dev/null 2>&1; then
    run gcloud scheduler jobs create http caseclosed-legal-corpus \
      --project "$GCP_PROJECT_ID" --location "$GCP_REGION" \
      --schedule "$CORPUS_SCHEDULE" --time-zone America/New_York \
      --uri "$corpus_url" --http-method POST --attempt-deadline 30m \
      --max-retry-attempts 2 --oidc-service-account-email "$SCHEDULER_SERVICE_ACCOUNT" \
      --oidc-token-audience "${CLOUD_RUN_SERVICE_URL%/}"
  fi
else
  echo "Legal-corpus scheduler not provisioned until official source feeds are configured."
fi

if [[ "${APPLY_STAGING_LIFECYCLE:-false}" == "true" ]]; then
  run gcloud storage buckets update "gs://${STORAGE_BUCKET}" \
    --lifecycle-file infra/staging-lifecycle.json
else
  echo "Storage lifecycle not changed. Set APPLY_STAGING_LIFECYCLE=true after reviewing existing bucket rules."
fi

echo "Document AI processor creation is separate: python scripts/create_document_ai_processor.py --apply"
echo "Run python scripts/preflight.py --production against the final Cloud Run environment before traffic."
