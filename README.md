# Case Closed

**Case Closed** is an AI-powered legal research assistant. It provides durable personal and team workspaces: matters, chats, documents, analysis, notes, and drafts are restored from the signed-in account on any device.

The public landing page is available at `/`. The authenticated litigation workspace is at `/app`, and the profile/team/data center is at `/account`. Clerk provides Google-only identity; Firestore remains authoritative for profiles, workspaces, roles, invitations, and matters.

---

## Features

From a user’s perspective, the app provides:

- **Background document ingestion** — Originals are retained in private, tenant-scoped Storage while extraction and OCR run asynchronously.
- **Intent-based, asynchronous chat** — Chat is acknowledged immediately; persisted jobs report progress while grounded Q&A or deeper research runs.
- **Strict source grounding** — Matter evidence and shared law are retrieved separately, and model citations must resolve to a retrieved source.
- **CourtListener case search with LLM-powered relevance ranking** — Cases are fetched from CourtListener, scored for relevance, and sorted with short explanations.
- **Legal document drafting (memo / brief)** — Generate draft memos or briefs from the current session context and retrieved cases.
- **Tabbed workspace** — **Analysis**, **Cases**, and **Draft** panels alongside the chat so you can review structured output, results, and generated text in one place.

---

## Tech stack

| Layer | Technology |
|--------|------------|
| Backend | Python, [Flask](https://flask.palletsprojects.com/) |
| Frontend | Vanilla JavaScript, HTML, CSS (server-rendered templates) |
| LLM | Google Gemini via [Vertex AI](https://cloud.google.com/vertex-ai) (`google-genai`) |
| Case search | [CourtListener](https://www.courtlistener.com/) REST API |
| PDF | [pdfminer.six](https://github.com/pdfminer/pdfminer.six) |
| Identity | Clerk (Firebase Authentication retained temporarily for rollback) |
| Database | Cloud Firestore |
| Background work | Google Cloud Tasks + Cloud Run |
| Retrieval | Google Cloud Vector Search with tenant filters |
| Documents and OCR | Private Cloud Storage originals + Document AI |
| Container | Docker (`python:3.11-slim`) |

---

## Project structure

```
caseclosed/
├── app.py              # Application entry point; Flask app + blueprint registration
├── config.py           # Centralized configuration (env-backed)
├── requirements.txt
├── Dockerfile
├── routes/             # Flask Blueprints
│   ├── chat.py         # POST /chat
│   ├── upload.py       # POST /upload
│   ├── analyze.py      # POST /analyze
│   ├── draft.py        # POST /draft
│   ├── context.py      # GET /context
│   └── main.py         # GET / (landing page), GET /app (workspace)
├── services/
│   ├── llm.py          # Gemini / Vertex AI calls
│   ├── jobs.py         # Idempotent matter jobs and atomic claims
│   ├── worker.py       # Background dispatcher
│   ├── retrieval.py    # Private/shared indexing and strict citations
│   ├── legal_corpus.py # Official-source registry and daily sync
│   ├── courtlistener.py
│   ├── pdf.py          # PDF save, extract, temp cleanup
│   ├── matters.py      # Normalized Firestore matter persistence
│   ├── tenancy.py      # Profiles, workspaces, roles, invites, authorization
│   └── storage.py      # Private files and signed downloads
├── models/
│   └── context.py      # Compatibility aggregate over normalized matter records
├── utils/
│   └── helpers.py      # Shared helpers (e.g. JSON extraction)
├── static/             # application and landing-page scripts, styles, and assets
├── templates/          # application and landing-page Jinja templates
└── assets/             # Diagrams / media for docs (e.g. architecture)
```

---

## Setup — run locally

1. **Clone** this repository.

2. **Credentials and environment**
   - Create a `.env` file in the project root (see [Environment variables](#environment-variables) below). Do not commit real secrets.
   - Add a Google Cloud **service account** JSON key as `key.json` in the project root (or set `GOOGLE_APPLICATION_CREDENTIALS` to another path). See [Google Cloud: service account keys](https://cloud.google.com/iam/docs/keys-create-delete).
   - Link the project to the Case Closed Clerk application, pull development keys, and configure Google as the only sign-in method in Clerk.
   - Customize the Clerk session token with `{ "userId": "{{user.external_id || user.id}}" }` so migrated Firebase users keep their existing app IDs.
   - Create a private Firebase Storage bucket and deploy the included Firestore/Storage rules. Firebase remains the data plane, not the identity provider.

3. **Install dependencies**

   ```bash
   pip install -r requirements.txt
   ```

4. **Run the app**

   ```bash
   python app.py
   ```

   The server listens on **port 5050** by default (`http://localhost:5050`). Override with the `PORT` variable if needed.

---

## Setup — Docker

Build and run with host port **5050** mapped to the container (the image sets `PORT=5050`):

```bash
docker build --no-cache -t caseclosed .
docker run -p 5050:5050 \
  --env-file .env \
  -v "$(pwd)/key.json:/app/key.json" \
  -e GOOGLE_APPLICATION_CREDENTIALS=/app/key.json \
  caseclosed
```

Then open `http://localhost:5050`.

To stop: `Ctrl+C`, or `docker stop <container-id>`.

---

## Environment variables

All values are read from the environment (and optionally `.env` via `python-dotenv`). **Never commit real tokens or keys.**

| Variable | Purpose |
|----------|---------|
| `FLASK_SECRET_KEY` | Secret key for Flask sessions (signing cookies). |
| `AUTH_PROVIDER` | Active identity provider: `clerk` (default) or temporary rollback value `firebase`. |
| `CLERK_PUBLISHABLE_KEY`, `CLERK_SECRET_KEY` | Clerk frontend and backend API keys. Never expose the secret key to browser code. |
| `CLERK_JWT_KEY` | Optional PEM public key for networkless Clerk session verification. |
| `CLERK_AUTHORIZED_PARTIES` | Comma-separated trusted origins checked against Clerk's `azp` claim. |
| `CLERK_WEBHOOK_SIGNING_SECRET` | Svix signing secret for `/webhooks/clerk`. |
| `ADMIN_EMAILS` | Comma-separated emails allowed to open `/admin/access` and approve early-access requests. New accounts start waitlisted (`access_status: pending`); accounts predating the gate pass automatically. Empty means the admin surface 404s for everyone. |
| `UPLOAD_FOLDER` | Directory where uploaded PDFs are written temporarily (defaults to the system temp directory). |
| `MAX_CONTENT_LENGTH` | Maximum upload size in bytes (default aligns with prior app limit). |
| `PORT` | HTTP port for `python app.py` (default **5050**). |
| `FLASK_DEBUG` | Set to `true` to enable Flask debug mode; otherwise treated as off. |
| `PROJECT_ID` | Google Cloud project ID for Vertex AI. |
| `GOOGLE_CLOUD_LOCATION` | Default region for Tasks, Vector Search, and other regional infrastructure (e.g. `us-central1`). |
| `GEMINI_LOCATION` | Gemini model endpoint, normally `global` (or an approved jurisdictional multi-region). |
| `COURTLISTENER_TOKEN` | Optional CourtListener API token for authenticated search requests. |
| `COURTLISTENER_BASE_URL` | CourtListener search API base URL (override only if needed). |
| `GOOGLE_APPLICATION_CREDENTIALS` | Optional standard Google Application Default Credentials path. Leave unset on Cloud Run to use its service identity. |
| `FIREBASE_CREDENTIALS` | Optional Firebase service-account path; otherwise Application Default Credentials are used. |
| `FIREBASE_WEB_CONFIG` | Public Firebase web configuration as one JSON object. |
| `FIREBASE_STORAGE_BUCKET` | Private bucket used for matter originals, avatars, and account exports. |
| `AUTH_COOKIE_SECURE` | Set `true` for HTTPS deployments; defaults from `APP_BASE_URL`. |
| `APP_BASE_URL` | Public application URL used in workspace invitations. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | SMTP delivery for team invitations. |
| `TASKS_MODE`, `TASKS_PROJECT_ID`, `TASKS_LOCATION`, `TASKS_QUEUE`, `TASKS_WORKER_URL`, `TASKS_WORKER_AUDIENCE`, `TASKS_SERVICE_ACCOUNT`, `INTERNAL_WORKER_TOKEN` | Chat, document, and account-export worker transport. Use `inline` locally and verified service-account OIDC in production. |
| `VECTOR_SEARCH_ENABLED`, `VECTOR_SEARCH_PROJECT_ID`, `VECTOR_SEARCH_LOCATION`, `VECTOR_PRIVATE_COLLECTION`, `VECTOR_LEGAL_COLLECTION`, `VECTOR_SEARCH_FIELD`, `VECTOR_EMBEDDING_MODEL`, `VECTOR_EMBEDDING_DIMENSIONS` | Tenant-safe private/shared semantic retrieval and its managed embedding schema. |
| `DOCUMENT_AI_PROCESSOR_ID`, `DOCUMENT_AI_LOCATION` | OCR fallback for scanned PDFs. |
| `LEGAL_SOURCE_REGISTRY`, `LEGAL_CORPUS_SYNC_TOKEN`, `LEGAL_CORPUS_SYNC_SERVICE_ACCOUNT`, `LEGAL_CORPUS_SYNC_AUDIENCE`, `LEGAL_CORPUS_DAILY_LIMIT` | Official jurisdiction feed adapters and protected daily sync. OIDC is preferred in production. |
| `CHAT_FAST_MODEL`, `CHAT_REASONING_MODEL` | Tiered GA model IDs for ordinary grounded answers and deeper analysis. Defaults are `gemini-3.5-flash-lite` and `gemini-3.6-flash`. |
| `CLARIFIER_MODEL` | Gemini model id for clarification / Q&A-style steps. |
| `SUMMARIZER_MODEL` | Gemini model id for case summarization. |
| `SCORER_MODEL` | Gemini model id for relevance scoring. |
| `ANALYZER_MODEL` | Gemini model id for structured legal analysis extraction. |
| `DRAFT_MODEL` | Gemini model id for memo/brief drafting. |
| `QUERY_MODEL` | Gemini model id for CourtListener query string generation. |

### Production preflight and infrastructure

Validate a completed production environment without changing cloud resources:

```bash
python scripts/preflight.py --production
```

The provisioning script defaults to a dry run. It needs an authenticated `gcloud` session plus the target service, URL, and bucket before it can apply IAM or create resources:

```bash
export GCP_PROJECT_ID=your-project
export CLOUD_RUN_SERVICE=caseclosed
export CLOUD_RUN_SERVICE_URL=https://your-service-url
export STORAGE_BUCKET=your-private-bucket

scripts/provision_gcp.sh --check
# Review the commands, then explicitly run --apply when ready.
```

The default deployment avoids always-on vector replicas and an empty daily sync job. Set `ENABLE_VECTOR_SEARCH=true` only when semantic-search volume justifies a billed index, and set `ENABLE_LEGAL_CORPUS_SYNC=true` only after official source feeds are configured.

After deployment, run `scripts/verify_gcp.sh`. Document AI processor creation remains a separate explicit step with `python scripts/create_document_ai_processor.py --apply`.

### Deploying to Cloud Run

`scripts/deploy_cloud_run.sh` is the only supported way to ship. It deploys with `--no-traffic` behind a revision tag, health-gates that tag's own URL, and requires a separate `--promote` to move traffic — so live traffic never lands on a revision nobody has checked.

```bash
./scripts/deploy_cloud_run.sh --profile domain              # build + deploy, no traffic
./scripts/deploy_cloud_run.sh --profile domain --promote    # shift traffic once verified
./scripts/deploy_cloud_run.sh --rollback caseclosed-00012-abc
```

Environment comes from two committed profiles in `deploy/`: `cloudrun.runapp.yaml` (the `*.run.app` URL with Clerk **development** keys) and `cloudrun.domain.yaml` (the public domain with Clerk **production** keys). Neither contains secrets; those are wired from Secret Manager by the script. `--env-vars-file` replaces the entire literal env set, so deleting a variable from a profile removes it from the service.

Two things worth knowing before your first deploy:

- **A missing variable fails the deploy, not the request.** `ENVIRONMENT` auto-becomes `production` on Cloud Run (`K_SERVICE` is always set), so `app.py` runs `require_runtime_config(production=True)` at import time. One absent value kills the gunicorn worker before it binds a port and the deploy fails with the opaque "container failed to start and listen on port". The script's preflight catches this locally first — and it renders the profile into a clean `git archive` tree, because `load_dotenv()` walks up from `config.py`'s own directory and would otherwise fill the gaps from your local `.env`.
- **Clerk production keys only work on the production domain.** A production Clerk instance serves its Frontend API from `clerk.<your-domain>` and sets its session cookie there, so loading a `pk_live_` key from a `*.run.app` origin makes that cookie third-party and sign-in fails. That is why the `runapp` profile exists: it proves boot, Cloud Tasks, Firestore, storage, and signed URLs without any DNS dependency.

The custom domain uses a **Cloud Run domain mapping**, not a load balancer — the mapping and its managed certificate are free, while a global external Application Load Balancer bills a forwarding rule (~$18/month) even at zero traffic. Avoid the Cloud Run console's "Custom domain" wizard, whose default path provisions exactly that.

```bash
gcloud domains verify example.com          # verify the PARENT domain, not the subdomain:
                                           # a CNAME must be the only record at its name
gcloud beta run domain-mappings create --service caseclosed \
  --domain app.example.com --region us-central1
# then add the CNAME the command prints (normally -> ghs.googlehosted.com)
```

### Deploying security rules

```bash
npx -y firebase-tools@latest deploy --only firestore:rules \
  --project YOUR_PROJECT_ID --config firebase.deploy.json
```

Use `firebase.deploy.json`, not `firebase.json` — the latter is excluded by `.dockerignore`/`.gcloudignore`.

Storage rules are deliberately **not** deployed. There is no Firebase-linked default bucket; the private bucket is locked down by IAM instead (uniform bucket-level access, public access prevention enforced, object access granted to the runtime service account alone). That is strictly stronger than a rules file, which would not apply to a non-Firebase bucket anyway. Do not "fix" this by linking the bucket to Firebase — it would weaken the current posture.

### Database migration

Back up Firestore, then inspect a dry-run report before applying the legacy migration:

```bash
python scripts/migrate_firestore_v2.py --report migration-report.json
python scripts/migrate_firestore_v2.py --apply --report migration-report-applied.json
```

The Firestore migration matches legacy users to Firebase identities through email, creates personal workspaces, normalizes owned contexts, and quarantines ownerless records instead of assigning them implicitly.

To move Firebase identities to Clerk, export users with the Firebase CLI and run the importer in dry-run mode before applying it. Use development Clerk keys for a rehearsal without `--write-firestore-mapping`. During the production cutover, use production Clerk keys and write the mapping before opening traffic:

```bash
firebase auth:export /tmp/caseclosed-firebase-users.json --format=json --project YOUR_PROJECT_ID
python scripts/migrate_firebase_user_to_clerk.py /tmp/caseclosed-firebase-users.json
python scripts/migrate_firebase_user_to_clerk.py /tmp/caseclosed-firebase-users.json --apply
# Production cutover only:
python scripts/migrate_firebase_user_to_clerk.py /tmp/caseclosed-firebase-users.json --apply --write-firestore-mapping
```

Password migrations require `FIREBASE_AUTH_SIGNER_KEY`, `FIREBASE_AUTH_SALT_SEPARATOR`, `FIREBASE_AUTH_ROUNDS`, and `FIREBASE_AUTH_MEMORY_COST`. Google-only users need no password hash parameters. The importer preserves each Firebase UID as Clerk `external_id`, is idempotent, and expects one user by default. Existing sessions are intentionally invalidated at cutover, so every user signs in once through Clerk; new users are provisioned synchronously on their first authenticated request and then reconciled by webhook.

Deploy `firestore.rules` and `storage.rules` to keep browsers out of the data plane; the Flask backend is the only authorized gateway.

See [BACKEND_ARCHITECTURE.md](BACKEND_ARCHITECTURE.md) for the complete chat/job/data flow, API contracts, retention policy, retrieval model, and production checklist. Copy `.env.example` as a configuration starting point.

---

## Demo & architecture

**Demo video:** [YouTube](https://youtu.be/-iNLur6breI)

[![Watch the demo](https://img.youtube.com/vi/-iNLur6breI/hqdefault.jpg)](https://youtu.be/-iNLur6breI)

**High-level architecture:**

![Case Closed architecture](assets/case_closed_architecture.png)

---

## Contributors

- Sai Yadavalli — AI Engineer  
- Jason Pereira — Frontend Developer & UI/UX Designer  

Initially built as part of an AI hackathon project. Now, backed by 1789 Student Venture Fund.
