# Backend

FastAPI service for Document Copilot. Run all commands from this folder.

## Setup

```bash
uv sync
cp .env.example .env   # fill in keys; never commit .env
```

## Run

```bash
uv run uvicorn app.main:app --reload
```

Health check: [http://localhost:8000/health](http://localhost:8000/health)  
API docs: [http://localhost:8000/docs](http://localhost:8000/docs)

Same app via `uv run python app/main.py`.

## Other commands

```bash
uv run pytest -m "not integration"
uv run ruff check .
uv run alembic upgrade head   # once Alembic is initialized
```
