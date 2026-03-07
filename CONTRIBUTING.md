# Contributing to NumbyAI

Thanks for your interest in contributing! Here's how to get started.

## Development Setup

1. Fork the repo and clone your fork.
2. Follow the [Quick Start](README.md#quick-start) instructions.
3. Install pre-commit hooks:

```bash
pip install pre-commit
pre-commit install
```

Pre-commit runs **ruff** and **mypy** on every commit, and **pytest** on every push.

## Making Changes

1. Create a feature branch from `main`.
2. Make your changes.
3. Run the quality gate before committing:

```bash
make check-python   # ruff + mypy + pytest
cd web && npm test   # frontend tests
```

4. Commit with a clear message describing the *why*, not just the *what*.
5. Open a pull request against `main`.

## Code Style

- **Python**: Enforced by [ruff](https://docs.astral.sh/ruff/) (config in `server/pyproject.toml`). Line length limit is 100 characters.
- **TypeScript**: Strict mode enabled. No explicit `any` types.
- **Categories**: Always import from `app.tools.category_helpers`. Never hardcode category strings.

## Tests

- Backend tests live in `server/tests/`. Run with `pytest tests --cov=app --cov-report=term-missing`.
- Frontend tests live in `web/src/__tests__/`. Run with `npm test` from the `web/` directory.
- The E2E categorization test (`make test-e2e`) requires a running Ollama instance.

## Reporting Issues

Open a GitHub issue with:
- Steps to reproduce
- Expected vs. actual behavior
- Your OS, Python version, and Node version

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
