# ScanSnap AI Pipeline

An automated, event-driven background ingestion engine in Python that monitors local scanner watch folders, verifies file write completion, classifies and organizes client documents, and routes payloads to cloud Large Language Model (LLM) endpoints.

---

## Features

- **Event-Driven Directory Monitoring**: Uses `watchdog` to detect new or moved files without polling loops.
- **File Stability & Lock Verification**: Debounces incoming files to ensure writes are fully committed before processing.
- **Client Organization**: Automatically classifies and organizes legal, corporate, and billing documents into structured client directories.
- **Multi-Provider AI Dispatcher**: Pre-configured support for OpenRouter, DeepSeek, OpenAI, and Groq with exponential backoff and retry handling.
- **Thread-Safe Processing Queue**: Decouples file detection from LLM inference using a worker pool.
- **Security by Default**: Configured to ensure API keys, local credentials, and client documents are never committed to version control.

---

## Security & Privacy Notice

> [!IMPORTANT]
> **No Secrets or Client Data in Git**:
> - `settings.json` is ignored in `.gitignore` to prevent API key exposure.
> - All client folders, PDFs, and Word documents (`*.pdf`, `*.docx`) are ignored by default.
> - Always use `settings.example.json` or `.env.example` as templates.

---

## Quickstart

### 1. Prerequisites
- Python 3.10+
- PyMuPDF (`fitz`), `watchdog`, `python-docx`

Install dependencies:
```bash
pip install -r requirements.txt
```

### 2. Configuration
Copy the configuration template:
```bash
cp settings.example.json settings.json
```
Edit `settings.json` with your monitored folder path and API key:
```json
{
  "watch_directories": [
    "./Temporary/Unprocessed"
  ],
  "provider": "openrouter",
  "model_name": "google/gemini-2.5-flash-lite",
  "api_key": "YOUR_OPENROUTER_API_KEY_HERE",
  "num_workers": 2,
  "stability_timeout": 30
}
```

Alternatively, configure credentials via environment variables:
```bash
export AI_API_KEY="your_api_key_here"
export AI_PROVIDER="openrouter"
export WATCH_DIR="./Temporary/Unprocessed"
```

### 3. Running the Pipeline
Run the background ingestion daemon:
```bash
python main.py
```

Optional command-line flags:
```bash
python main.py --help
python main.py --mock                # Run in mock mode without outbound API calls
python main.py --enable-wrapup       # Enable automatic batch wrapup & client folder organization
python main.py --workers 4           # Specify worker concurrency
```

### 4. Running Tests
Run the test suite to verify pipeline integrity:
```bash
python -m unittest discover tests
```

---

## Docker Deployment

Build and start the container with Docker Compose:
```bash
docker-compose up -d
```
Credentials can be passed via `.env` file or environment variables (`AI_API_KEY`).
