# AGENTS.md — notes for contributing LLMs / agents

Read this before making changes to `nigeria2_backend`.

## ⚠️ This is a PUBLIC repository — never commit secrets

This repo is public on GitHub. **Do not commit any secrets, credentials, or
private data**, including:

- API keys, tokens, passwords, database URLs with credentials
- `.env` files (already covered by `.gitignore`)
- Cloud/provider keys (AWS, GitHub tokens, etc.)
- Private user data

Configuration and secrets belong in **environment variables**, set in the
Coolify dashboard under **Environment Variables** — not in the code or the repo.
Read them at runtime with `os.environ` / `os.getenv`. If you add a new env var,
document its **name only** (never its value) in this file or the README, and add
a placeholder to a committed `.env.example` if helpful.

## How deployment works

The API is deployed with **Coolify** (Nixpacks build pack) and served at
**https://api.nigeria2.com**.

- **Auto-deploy:** pushing to the `main` branch triggers Coolify to rebuild and
  redeploy automatically. There is no separate deploy step — `git push` is the
  deploy.
- **Build:** Nixpacks detects Python via `requirements.txt` and installs deps.
- **Start command (configured in Coolify):**
  `uvicorn app.main:app --host 0.0.0.0 --port 8000`
  The app must bind `0.0.0.0` (not `127.0.0.1`) so Coolify's proxy can reach it,
  and the exposed port (`8000`) must match Coolify's "Ports Exposes" setting.
- **Verify a deploy:** after pushing, poll a changed/new endpoint until it goes
  live, e.g. `curl https://api.nigeria2.com/api/ping`.

## Local development

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate   | macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Interactive docs at http://127.0.0.1:8000/docs

## Conventions

- Keep new HTTP endpoints under the `/api/...` prefix.
- Pin dependency versions in `requirements.txt`.
- If you change the start command or exposed port, update this file so the
  Coolify config and the docs stay in sync.
