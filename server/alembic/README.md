# Database Migrations

Alembic migrations for the Finance Budgeting App database schema.

## Overview

This directory contains database migrations that evolve the schema over time. Migrations are run automatically during deployment or manually via the Alembic CLI.

## Migration History

| Version | Description |
|---------|-------------|
| 001 | Initial schema - base tables |
| 002 | Add insights column |
| 003 | Category summaries table |
| 004 | Parsing and statement insights |
| 005 | Statement periods table |
| 006 | Categorization preferences |
| 007 | Budgets table |
| 008 | Category insights |

## Usage

```bash
# Apply all pending migrations
alembic upgrade head

# Rollback one migration
alembic downgrade -1

# Create new migration
alembic revision -m "description"

# Show current revision
alembic current

# Show migration history
alembic history
```

## Creating Migrations

1. Make changes to SQLAlchemy models in `app/database.py`
2. Generate migration: `alembic revision --autogenerate -m "description"`
3. Review generated migration in `versions/`
4. Test migration: `alembic upgrade head`
5. Commit migration file

## Configuration

The `alembic.ini` file in the parent directory configures:
- Database URL (from environment or default)
- Migration script location
- Logging settings

## Best Practices

- Always test migrations in development before production
- Keep migrations small and focused
- Use descriptive migration messages
- Never modify a migration that has been applied to production
- Include both upgrade and downgrade functions
