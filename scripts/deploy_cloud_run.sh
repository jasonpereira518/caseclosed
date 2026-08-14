#!/usr/bin/env bash
# Deploy Case Closed to Cloud Run.
#
# The deploy always lands with --no-traffic behind a revision tag, is health
# gated on that tag's own URL, and is promoted by a separate --promote run. That
# is the whole rollback story: traffic never moves onto a revision nobody has
# checked.
#
#   ./scripts/deploy_cloud_run.sh --profile runapp            # deploy #1, no traffic
#   ./scripts/deploy_cloud_run.sh --profile runapp --promote  # shift traffic to it
#   ./scripts/deploy_cloud_run.sh --profile domain            # deploy #2, the cutover
#   ./scripts/deploy_cloud_run.sh --rollback caseclosed-00007-abc
#
# The single most valuable step here is the rendered-env preflight. app.py runs
# require_runtime_config(production=True) at import time, and ENVIRONMENT
# auto-becomes "production" on Cloud Run, so one missing variable kills the
# gunicorn worker before it binds a port and the deploy fails with the opaque
# "container failed to start and listen on port". Catching that locally costs
# seconds; catching it in Cloud Build costs a full build.
set -euo pipefail

PROJECT_ID="case-closed-491121"
REGION="us-central1"
SERVICE="caseclosed"
RUNTIME_SA="caseclosed-runtime@${PROJECT_ID}.iam.gserviceaccount.com"
AR_REPO="cloud-run-source-deploy"

SECRETS="SECRET_KEY=caseclosed-flask-secret:latest"
SECRETS+=",COURTLISTENER_TOKEN=caseclosed-courtlistener-token:latest"
SECRETS+=",CLERK_SECRET_KEY=caseclosed-clerk-secret-key:latest"
SECRETS+=",CLERK_WEBHOOK_SIGNING_SECRET=caseclosed-clerk-webhook-secret:latest"

PROFILE=""
TAG=""
PROMOTE=false
DRY_RUN=false
PRINT_ENV=false
SKIP_TESTS=false
ALLOW_DIRTY=false
ROLLBACK=""

die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \?//'
  cat <<'EOF'

Flags:
  --profile runapp|domain   which env-var profile to deploy (required unless --rollback)
  --tag NAME                revision tag (default: git short sha)
  --promote                 shift 100% of traffic to --tag, then re-verify
  --dry-run                 render env, run preflight, print the command, stop
  --print-env               dump the rendered env and stop
  --skip-tests              skip pytest
  --allow-dirty             permit deploying an uncommitted working tree
  --rollback REVISION       send 100% of traffic to REVISION and exit
EOF
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --profile) PROFILE="${2:-}"; shift 2 ;;
    --tag) TAG="${2:-}"; shift 2 ;;
    --promote) PROMOTE=true; shift ;;
    --dry-run) DRY_RUN=true; shift ;;
    --print-env) PRINT_ENV=true; shift ;;
    --skip-tests) SKIP_TESTS=true; shift ;;
    --allow-dirty) ALLOW_DIRTY=true; shift ;;
    --rollback) ROLLBACK="${2:-}"; shift 2 ;;
    -h|--help) usage ;;
    *) die "unknown flag: $1" ;;
  esac
done

cd "$(dirname "$0")/.."

if [[ -n "$ROLLBACK" ]]; then
  step "Rolling traffic back to ${ROLLBACK}"
  gcloud run services update-traffic "$SERVICE" \
    --project "$PROJECT_ID" --region "$REGION" --to-revisions "${ROLLBACK}=100"
  exit 0
fi

[[ "$PROFILE" == "runapp" || "$PROFILE" == "domain" ]] || usage
ENV_FILE="deploy/cloudrun.${PROFILE}.yaml"
[[ -f "$ENV_FILE" ]] || die "missing $ENV_FILE"

if $PRINT_ENV; then cat "$ENV_FILE"; exit 0; fi

# ---------------------------------------------------------------- fail fast
step "Preflight checks"

command -v gcloud >/dev/null || die "gcloud is not installed"
[[ -n "$(gcloud config get-value account 2>/dev/null)" ]] || die "run: gcloud auth login"

if grep -q 'REPLACE_WITH' "$ENV_FILE"; then
  die "$ENV_FILE still has REPLACE_WITH placeholders. Fill in the Clerk keys first."
fi

if ! $ALLOW_DIRTY && [[ -n "$(git status --porcelain)" ]]; then
  die "working tree is dirty. Commit first, or pass --allow-dirty.
     'gcloud run deploy --source .' ships the working tree either way, so an
     uncommitted deploy produces an artifact you cannot bisect or reproduce."
fi

[[ -n "$TAG" ]] || TAG="g$(git rev-parse --short=7 HEAD)"

if ! $SKIP_TESTS; then
  step "Running tests"
  python -m pytest -q
fi

# Render the exact env that is about to be deployed and run the real validator
# against it. config.py calls load_dotenv(), and python-dotenv walks up from
# config.py's own directory -- so it finds the repo's .env no matter what CWD we
# use, and a naive preflight would be silently filled in from local values and
# pass while the real deploy fails. Exporting from a clean `git archive` tree
# (where .env, being gitignored, does not exist) is what makes this honest.
step "Validating the rendered production env"
PREFLIGHT_DIR="$(mktemp -d)"
trap 'rm -rf "$PREFLIGHT_DIR"' EXIT
git archive HEAD | tar -x -C "$PREFLIGHT_DIR"

ENV_KV=()
while IFS= read -r line; do
  [[ -n "$line" ]] && ENV_KV+=("$line")
done < <(awk -F': ' '/^[A-Z_]+:/ { key=$1; sub(/^[^:]*: /, "", $0); val=$0;
                                   gsub(/^"|"$/, "", val); print key "=" val }' "$ENV_FILE")

env -i PATH="$PATH" HOME="$HOME" \
  "${ENV_KV[@]}" \
  SECRET_KEY='preflight-placeholder-not-deployed' \
  CLERK_SECRET_KEY='sk_preflight_placeholder' \
  CLERK_WEBHOOK_SIGNING_SECRET='whsec_preflight_placeholder' \
  COURTLISTENER_TOKEN='preflight-placeholder' \
  python3 "$PREFLIGHT_DIR/scripts/preflight.py" --production \
  || die "preflight failed -- this deploy would fail to start the container"

step "Checking cost guardrails"
if ! gcloud artifacts repositories describe "$AR_REPO" \
      --project "$PROJECT_ID" --location "$REGION" \
      --format='value(cleanupPolicies)' 2>/dev/null | grep -q .; then
  die "Artifact Registry repo '$AR_REPO' has no cleanup policy.
     The repo is near the 500 MB free tier and each image is ~120 MB, so the
     next builds will start billing. Apply it first:
       gcloud artifacts repositories set-cleanup-policies $AR_REPO \\
         --location $REGION --project $PROJECT_ID \\
         --policy infra/artifact-cleanup-policy.json"
fi

for secret in caseclosed-flask-secret caseclosed-courtlistener-token \
              caseclosed-clerk-secret-key caseclosed-clerk-webhook-secret; do
  gcloud secrets versions describe latest --secret "$secret" --project "$PROJECT_ID" \
    --format='value(state)' 2>/dev/null | grep -q ENABLED \
    || die "secret '$secret' is missing or has no enabled version"
done

PREV_REV="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" \
  --region "$REGION" --format='value(status.latestReadyRevisionName)')"
step "Current revision (rollback target): ${PREV_REV:-<none>}"

# ------------------------------------------------------------------- deploy
DEPLOY_CMD=(gcloud run deploy "$SERVICE"
  --project "$PROJECT_ID"
  --region "$REGION"
  --source .
  --service-account "$RUNTIME_SA"
  --env-vars-file "$ENV_FILE"
  --set-secrets "$SECRETS"
  --allow-unauthenticated
  --port 8080
  --cpu 1
  --memory 1Gi
  # The live service runs at 20, not gcloud's default of 80. Specify it so the
  # revision is fully reproducible rather than inherited.
  --concurrency 20
  --timeout 300
  # These two are the Cloud Run free-tier guardrail. --no-cpu-throttling or any
  # --min-instances >= 1 switches to instance-based billing. Always explicit.
  --min-instances 0
  --cpu-throttling
  --max-instances 10
  --no-cpu-boost
  --ingress all
  --labels "app=caseclosed,managed-by=deploy-script"
  --revision-suffix "$(git rev-parse --short=7 HEAD)-$(date +%H%M%S)"
  --tag "$TAG"
  --no-traffic
  --quiet)

if $DRY_RUN; then
  step "Dry run -- would execute:"
  printf '%q ' "${DEPLOY_CMD[@]}"; echo
  exit 0
fi

step "Deploying (no traffic) as tag '${TAG}'"
"${DEPLOY_CMD[@]}"

NEW_REV="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" \
  --region "$REGION" --format='value(status.latestCreatedRevisionName)')"

# --set-secrets replaces the whole secret set, which is what drops the /secrets
# volume mount the old revision used for the dead OAuth client. Assert it.
if [[ -n "$(gcloud run revisions describe "$NEW_REV" --project "$PROJECT_ID" \
            --region "$REGION" --format='value(spec.volumes)')" ]]; then
  die "revision $NEW_REV still has a secret volume mount; add --clear-volumes"
fi

HOST="$(gcloud run services describe "$SERVICE" --project "$PROJECT_ID" \
  --region "$REGION" --format='value(status.url)' | sed 's|https://||')"
TAG_URL="https://${TAG}---${HOST}"

step "Health gating ${TAG_URL}"
curl -fsS --max-time 60 "${TAG_URL}/livez" >/dev/null || die "/livez failed on the new revision"
READY="$(curl -fsS --max-time 60 "${TAG_URL}/readyz")" || die "/readyz failed on the new revision"
echo "$READY"
grep -q '"status": *"ready"' <<<"$READY" || die "/readyz did not report ready"

cat <<EOF

Deployed ${NEW_REV} with no traffic.
  verify:   ${TAG_URL}
  promote:  $0 --profile ${PROFILE} --tag ${TAG} --promote
  rollback: $0 --rollback ${PREV_REV}
EOF

if $PROMOTE; then
  step "Promoting ${TAG} to 100% of traffic"
  gcloud run services update-traffic "$SERVICE" \
    --project "$PROJECT_ID" --region "$REGION" --to-tags "${TAG}=100"
  curl -fsS --max-time 60 "https://${HOST}/readyz" && echo
  printf '\nLive. Roll back with: %s --rollback %s\n' "$0" "$PREV_REV"
fi
