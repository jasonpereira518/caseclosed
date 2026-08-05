# Case Closed

**Case Closed** is an AI-powered legal research assistant. It provides durable personal and team workspaces: matters, chats, documents, analysis, notes, and drafts are restored from the signed-in account on any device.

The public landing page is available at `/`. The authenticated litigation workspace is at `/app`, and the profile/team/data center is at `/account`. Firebase Authentication supports Google, verified email/password, and email magic links.

---

## Features

From a user’s perspective, the app provides:

- **Background document ingestion** — Originals are staged transiently, OCR'd when necessary, and discarded after extracted text is indexed.
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
| Identity | Firebase Authentication |
| Database | Cloud Firestore |
| Background work | Google Cloud Tasks + Cloud Run |
| Retrieval | Google Cloud Vector Search with tenant filters |
| OCR / transient files | Document AI + private Cloud Storage staging |
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
   - In Firebase Authentication, enable Google, Email/Password, and Email Link providers and add the local/production hosts to Authorized domains.
   - Create a private Firebase Storage bucket, deploy the included Firestore/Storage rules, and place the Firebase web app configuration in `FIREBASE_WEB_CONFIG`.

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
| `UPLOAD_FOLDER` | Directory where uploaded PDFs are written temporarily (defaults to the system temp directory). |
| `MAX_CONTENT_LENGTH` | Maximum upload size in bytes (default aligns with prior app limit). |
| `PORT` | HTTP port for `python app.py` (default **5050**). |
| `FLASK_DEBUG` | Set to `true` to enable Flask debug mode; otherwise treated as off. |
| `PROJECT_ID` | Google Cloud project ID for Vertex AI. |
| `GOOGLE_CLOUD_LOCATION` | Default region for Tasks, Vector Search, and other regional infrastructure (e.g. `us-central1`). |
| `GEMINI_LOCATION` | Gemini model endpoint, normally `global` (or an approved jurisdictional multi-region). |
| `COURTLISTENER_TOKEN` | Optional CourtListener API token for authenticated search requests. |
| `COURTLISTENER_BASE_URL` | CourtListener search API base URL (override only if needed). |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to the GCP service account JSON file (default `key.json` in the working directory). |
| `FIREBASE_CREDENTIALS` | Optional Firebase service-account path; otherwise Application Default Credentials are used. |
| `FIREBASE_WEB_CONFIG` | Public Firebase web configuration as one JSON object. |
| `FIREBASE_STORAGE_BUCKET` | Private bucket used for transient ingestion staging, avatars, and account exports. |
| `AUTH_COOKIE_SECURE` | Set `true` for HTTPS deployments; defaults from `APP_BASE_URL`. |
| `APP_BASE_URL` | Public application URL used in workspace invitations. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | SMTP delivery for team invitations. |
| `CLOUD_TASKS_QUEUE`, `CLOUD_TASKS_LOCATION`, `JOB_WORKER_SECRET` | Optional durable background processing for large account exports. Without a queue, local development processes exports inline. |
| `TASKS_MODE`, `TASKS_PROJECT_ID`, `TASKS_LOCATION`, `TASKS_QUEUE`, `TASKS_WORKER_URL`, `TASKS_WORKER_AUDIENCE`, `TASKS_SERVICE_ACCOUNT`, `INTERNAL_WORKER_TOKEN` | Matter chat/document worker transport. Use `inline` locally and verified service-account OIDC in production. |
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

After deployment, run `scripts/verify_gcp.sh`. Document AI processor creation remains a separate explicit step with `python scripts/create_document_ai_processor.py --apply`.

### Database migration

Back up Firestore, then inspect a dry-run report before applying the legacy migration:

```bash
python scripts/migrate_firestore_v2.py --report migration-report.json
python scripts/migrate_firestore_v2.py --apply --report migration-report-applied.json
```

The migration matches legacy users to Firebase identities through email, creates personal workspaces, normalizes owned contexts, and quarantines ownerless records instead of assigning them implicitly.

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
