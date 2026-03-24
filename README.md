# Case Closed

**Case Closed** is an AI-powered legal research assistant. It helps you describe a matter (or upload a PDF), surfaces relevant case law from CourtListener, explains relevance, and drafts memo- or brief-style documents—all in a single browser session.

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
│   └── main.py         # GET / (renders UI)
├── services/
│   ├── llm.py          # Gemini / Vertex AI calls
│   ├── courtlistener.py
│   └── pdf.py          # PDF save, extract, temp cleanup
├── models/
│   └── context.py      # In-memory session context + eviction helpers
├── utils/
│   └── helpers.py      # Shared helpers (e.g. JSON extraction)
├── static/             # script.js, style.css, icons
├── templates/          # base.html, chat.html
└── assets/             # Diagrams / media for docs (e.g. architecture)
```

---

## Setup — run locally

1. **Clone** this repository.

2. **Credentials and environment**
   - Create a `.env` file in the project root (see [Environment variables](#environment-variables) below). Do not commit real secrets.
   - Add a Google Cloud **service account** JSON key as `key.json` in the project root (or set `GOOGLE_APPLICATION_CREDENTIALS` to another path). See [Google Cloud: service account keys](https://cloud.google.com/iam/docs/keys-create-delete).

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
| `CLARIFIER_MODEL` | Gemini model id for clarification / Q&A-style steps. |
| `SUMMARIZER_MODEL` | Gemini model id for case summarization. |
| `SCORER_MODEL` | Gemini model id for relevance scoring. |
| `ANALYZER_MODEL` | Gemini model id for structured legal analysis extraction. |
| `DRAFT_MODEL` | Gemini model id for memo/brief drafting. |
| `QUERY_MODEL` | Gemini model id for CourtListener query string generation. |

---

## Demo & architecture

**Demo video:** [YouTube](https://youtu.be/-iNLur6breI)

[![Watch the demo](https://img.youtube.com/vi/-iNLur6breI/hqdefault.jpg)](https://youtu.be/-iNLur6breI)

**High-level architecture:**

![Case Closed architecture](assets/case_closed_architecture.png)

---

## Contributors

- Sai Yadavalli — AI Engineer  
- Sedat Unal — Full-stack Developer  
- Jason Pereira — Frontend Developer & UI/UX Designer  
- Saksham Anand — Backend Developer  

Built as part of an AI hackathon project.
