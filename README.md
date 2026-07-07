# nigeria2_backend

Minimal FastAPI backend for the Nigeria 2.0 project.

## Setup

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```bash
uvicorn app.main:app --reload
```

- API root: http://127.0.0.1:8000/
- Hello:    http://127.0.0.1:8000/api/hello
- Health:   http://127.0.0.1:8000/health
- Docs:     http://127.0.0.1:8000/docs
