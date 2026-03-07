# NumbyAI

**AI-powered personal finance transaction categorizer.**

Upload a bank statement CSV, and NumbyAI will automatically categorize every transaction using a local LLM (Ollama). Review the results on an interactive dashboard, set budgets, and teach the system your preferences so it gets smarter over time.

---

## Features

- **CSV Upload & Auto-parsing** — drag-and-drop any bank CSV; the AI figures out column mapping automatically.
- **AI Categorization** — transactions are sorted into 13 spending categories by a local LLM (no data leaves your machine).
- **Rule Engine** — saved user preferences (description patterns, amount ranges, bank filters) are applied before the LLM, making repeat categorizations instant.
- **Manual Review Queue** — transactions the AI is unsure about are flagged for your review.
- **Dashboard** — charts, category breakdowns, budget vs. actual, cash flow, and trends.
- **Budget Tracking** — set monthly budgets per category and see where you stand.
- **Privacy First** — runs entirely on your local machine. No cloud, no third-party APIs (unless you opt in).

## Architecture

```
┌──────────────────────────────────────────────────────┐
│                    Browser (:8000)                    │
│  ┌────────────────┐      ┌─────────────────────────┐ │
│  │  Upload Page    │      │  Dashboard              │ │
│  │  (SimpleUpload) │      │  Charts · Budgets ·     │ │
│  │                 │      │  Review · Trends        │ │
│  └────────────────┘      └─────────────────────────┘ │
└──────────────────┬───────────────────────────────────┘
                   │ REST API
┌──────────────────▼───────────────────────────────────┐
│              FastAPI Server (:8000)                   │
│  ┌───────────┐ ┌──────────┐ ┌──────────────────────┐ │
│  │ Statement │ │ Rule     │ │ Ollama LLM Service   │ │
│  │ Parser    │ │ Engine   │ │ (qwen3.5:9b)         │ │
│  └───────────┘ └──────────┘ └──────────────────────┘ │
│  ┌─────────────────────────────────────────────────┐  │
│  │         SQLite / PostgreSQL Database            │  │
│  └─────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────┘
                   │
┌──────────────────▼───────────────────────────────────┐
│              Ollama (:11434)                          │
│              Local LLM inference                     │
└──────────────────────────────────────────────────────┘
```

### Categorization Flow

1. **CSV uploaded** — the statement analyzer infers column mapping via LLM.
2. **Rule engine** — saved user rules (description match, amount, bank) categorize known patterns instantly.
3. **LLM batch** — remaining transactions are sent to Ollama in batches.
4. **Manual review** — anything the LLM can't confidently categorize is flagged as `MANUAL_REVIEW`.
5. **Dashboard** — results are stored and displayed with charts and budget tracking.

### Categories

Income, Housing & Utilities, Food & Groceries, Transportation, Insurance, Healthcare, Shopping, Entertainment, Travel, Debt Payments, Internal Transfers, Investments, Other.

## Prerequisites

| Dependency | Version | Notes |
|---|---|---|
| Python | 3.11+ | Backend runtime |
| Node.js | 18+ | Frontend build |
| Ollama | Latest | Local LLM inference |

## Quick Start

```bash
# 1. Clone the repo
git clone https://github.com/RoXsaita/NumbyAI-Public.git
cd NumbyAI-Public

# 2. Install Ollama and pull the default model
make setup-ollama

# 3. Copy the example env file
cp server/.env.example server/.env

# 4. Start everything (creates venv, installs deps, runs migrations, builds frontend, starts server)
make restart
```

The app will open at **http://localhost:8000**.

Upload the included `sample_bank_export.csv` to try it out, or use your own bank statement CSV.

## Project Structure

```
NumbyAI-Public/
├── server/                 # FastAPI backend
│   ├── app/
│   │   ├── main.py         # Routes and app entry point
│   │   ├── config.py       # Pydantic settings (.env)
│   │   ├── database.py     # SQLAlchemy models + session
│   │   ├── auth.py         # Optional Auth0 JWT validation
│   │   ├── prompts/        # LLM prompt templates
│   │   ├── schemas/        # Pydantic response schemas
│   │   ├── services/       # Business logic (Ollama, rules, parsing)
│   │   └── tools/          # Route handlers (categories, budgets, etc.)
│   ├── alembic/            # Database migrations
│   ├── tests/              # Pytest test suite
│   ├── scripts/            # Utility scripts (seed data, Ollama setup)
│   ├── requirements.txt
│   └── Dockerfile
├── web/                    # React 18 SPA (esbuild)
│   ├── src/
│   │   ├── components/     # SimpleUpload, ErrorBoundary
│   │   ├── widgets/        # Dashboard widget
│   │   ├── lib/            # API client, chart builders, data transforms
│   │   └── mocks/          # Mock data for offline development
│   ├── scripts/            # Build scripts
│   └── package.json
├── sample_bank_export.csv  # Example CSV for testing
├── Makefile                # Dev commands (restart, stop, check-python, etc.)
└── .github/workflows/      # CI (ruff + mypy + pytest)
```

## Configuration

All configuration is via environment variables. See [`server/.env.example`](server/.env.example) for the full list.

Key settings:

| Variable | Description | Default |
|---|---|---|
| `DATABASE_URL` | Database connection string | `sqlite:///./finance_recon.db` |
| `SECRET_KEY` | JWT signing key (change in prod!) | `dev-only-not-for-production` |
| `OLLAMA_URL` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Model to use for categorization | `qwen3.5:9b` |
| `AUTH0_DOMAIN` | Auth0 domain (optional) | Disabled (test user) |

Auth is **optional**. When `AUTH0_DOMAIN` is not set, the app runs in single-user mode with a built-in test user.

## Development

### Make Commands

```bash
make restart        # Stop, migrate, build frontend, start server
make stop           # Kill all services
make logs           # Tail backend logs
make check-python   # Run ruff + mypy + pytest
make setup-ollama   # Install Ollama + pull model
make test-e2e       # End-to-end categorization test (requires Ollama)
```

### Backend

```bash
cd server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# Run tests
pytest tests --cov=app --cov-report=term-missing

# Lint & type check
ruff check app tests
mypy

# Database migrations
alembic upgrade head
alembic revision --autogenerate -m "description"
```

### Frontend

```bash
cd web
npm install

# Production build (served by FastAPI)
npm run build

# Dev build with mock data (no backend needed)
DATA_SOURCE=mock npm run build:dev

# Run tests
npm test
```

There is no separate dev server — the FastAPI backend serves the built frontend as static files. After `npm run build`, refresh the browser.

### Seed Demo Data

To populate the database with realistic sample transactions for development:

```bash
cd server
.venv/bin/python scripts/seed_mock_data.py
```

## CSV Format

NumbyAI auto-detects column mappings from most bank CSV formats. At minimum, the CSV should contain columns for **date**, **description**, and **amount**. The AI analyzer handles variations in column names, date formats, and number formatting.

Example (`sample_bank_export.csv`):

```csv
Date,Description,Amount,Type,Balance
02/01/2026,DIRECT DEPOSIT - ACME CORP PAYROLL,3850.00,Credit,8942.31
02/01/2026,ZELLE PMT - LANDLORD RENT FEB,-1850.00,Debit,7092.31
02/01/2026,NETFLIX.COM,-15.99,Debit,7076.32
```

## Deployment

A `Dockerfile` and `railway.toml` are included for container deployment. For production:

1. Set `DATABASE_URL` to a PostgreSQL connection string.
2. Set `SECRET_KEY` to a secure random value.
3. Set `ENVIRONMENT=production`.
4. Ensure Ollama is accessible at `OLLAMA_URL`.

## License

[MIT](LICENSE)
