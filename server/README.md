# NumbyAI Server

FastAPI backend for NumbyAI. Handles CSV parsing, AI-powered transaction categorization, budgets, and the dashboard API.

See the [main README](../README.md) for full setup instructions.

## Quick Reference

```bash
# From the repo root:
make restart          # Full system start (migrations + build + server)
make check-python     # Ruff + mypy + pytest
make setup-ollama     # Install Ollama + pull the default model

# From this directory:
.venv/bin/alembic upgrade head                           # Run migrations
.venv/bin/uvicorn app.main:asgi_app --reload --port 8000 # Start server
.venv/bin/pytest tests --cov=app --cov-report=term-missing
```
