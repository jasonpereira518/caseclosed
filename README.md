# Case Closed

**Case Closed** is an AI-powered legal research assistant. It provides durable personal and team workspaces: matters, chats, documents, analysis, notes, and drafts are restored from the signed-in account on any device.

The public landing page is available at `/`. The authenticated litigation workspace is at `/app`, and the profile/team/data center is at `/account`. Firebase Authentication supports Google, verified email/password, and email magic links.

---

## Features

From a user’s perspective, the app provides:

- **PDF upload and automatic legal analysis** — Upload a PDF; text is extracted and structured facts, parties, issues, and related fields are inferred for the session.
- **Chat-based legal case intake with a clarification loop** — Describe your situation in chat; the assistant may ask follow-up questions before running a full search.
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
| Private files | Firebase / Google Cloud Storage |
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
| `GOOGLE_CLOUD_LOCATION` | Vertex AI region (e.g. `us-central1`). |
| `COURTLISTENER_TOKEN` | Optional CourtListener API token for authenticated search requests. |
| `COURTLISTENER_BASE_URL` | CourtListener search API base URL (override only if needed). |
| `GOOGLE_APPLICATION_CREDENTIALS` | Path to the GCP service account JSON file (default `key.json` in the working directory). |
| `FIREBASE_CREDENTIALS` | Optional Firebase service-account path; otherwise Application Default Credentials are used. |
| `FIREBASE_WEB_CONFIG` | Public Firebase web configuration as one JSON object. |
| `FIREBASE_STORAGE_BUCKET` | Private bucket name used for documents, avatars, and exports. |
| `AUTH_COOKIE_SECURE` | Set `true` for HTTPS deployments; defaults from `APP_BASE_URL`. |
| `APP_BASE_URL` | Public application URL used in workspace invitations. |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM` | SMTP delivery for team invitations. |
| `CLOUD_TASKS_QUEUE`, `CLOUD_TASKS_LOCATION`, `JOB_WORKER_SECRET` | Optional durable background processing for large account exports. Without a queue, local development processes exports inline. |
| `CLARIFIER_MODEL` | Gemini model id for clarification / Q&A-style steps. |
| `SUMMARIZER_MODEL` | Gemini model id for case summarization. |
| `SCORER_MODEL` | Gemini model id for relevance scoring. |
| `ANALYZER_MODEL` | Gemini model id for structured legal analysis extraction. |
| `DRAFT_MODEL` | Gemini model id for memo/brief drafting. |
| `QUERY_MODEL` | Gemini model id for CourtListener query string generation. |

### Database migration

Back up Firestore, then inspect a dry-run report before applying the legacy migration:

```bash
python scripts/migrate_firestore_v2.py --report migration-report.json
python scripts/migrate_firestore_v2.py --apply --report migration-report-applied.json
```

The migration matches legacy users to Firebase identities through email, creates personal workspaces, normalizes owned contexts, and quarantines ownerless records instead of assigning them implicitly.

Deploy `firestore.rules` and `storage.rules` to keep browsers out of the data plane; the Flask backend is the only authorized gateway.

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
