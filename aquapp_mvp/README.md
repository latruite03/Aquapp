# Aquapp MVP

Local-first aquarium monitoring web app for uploading photos, browsing history, and requesting cautious analysis suggestions.

## Prerequisites
- Python 3.11+
- Git (optional)

## Setup
```bash
cd aquapp_mvp
python -m venv .venv
```

Activate your virtual environment:
- Windows (PowerShell):
  ```powershell
  .\.venv\Scripts\Activate.ps1
  ```
- Windows (cmd):
  ```cmd
  .\.venv\Scripts\activate.bat
  ```
- macOS/Linux:
  ```bash
  source .venv/bin/activate
  ```

Install dependencies:
```bash
pip install -r requirements.txt
```

## Configure OpenAI
Copy `.env.example` to `.env` and update the key:
```bash
cp .env.example .env
```

Set these environment variables (or update `.env`):
- `OPENAI_API_KEY` (required for analysis)
- `OPENAI_MODEL` (optional, default `gpt-4o-mini`)

## Initialize the database
```bash
python scripts/init_db.py
```

## Run the app
```bash
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 in your browser.

## Minimal test checklist
- Launch server
- Upload one JPG/PNG
- See it in history
- Open photo detail
- Click analyze (with key configured) and see JSON-based advice rendered
- With no key configured, analyze shows friendly error

## Windows troubleshooting
- **Port already in use**: Stop the existing process or use a different port: `uvicorn app.main:app --reload --port 8001`
- **Virtual environment activation**: Ensure PowerShell execution policy allows scripts. If needed:
  ```powershell
  Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
  ```
