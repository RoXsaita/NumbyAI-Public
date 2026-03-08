# Contributing to NumbyAI

Thanks for your interest. Contributions are welcome — bug fixes, new bank format support, UI improvements, and docs.

## Local setup

```bash
# Clone and set up the backend
git clone https://github.com/RoXsaita/NumbyAI-Public.git
cd NumbyAI-Public

cp server/.env.example server/.env

cd server
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
alembic upgrade head

# Build the frontend
cd ../web
npm install && npm run build

# Start the server
cd ..
make restart
```

App runs at http://localhost:8000. You need [Ollama](https://ollama.com) running locally (`make setup-ollama` handles this).

## Running tests

```bash
# Python: lint + types + tests
make check-python

# Or individually from server/
ruff check app tests
mypy
pytest tests

# Frontend
cd web && npm test
```

All checks must pass before submitting a PR.

## Commit conventions

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add Monzo CSV support
fix: skip BOM character in UTF-8 exports
docs: add ING format to README
refactor: simplify column scoring logic
test: add fixture for Barclays business account
chore: bump ruff to 0.9
```

One concern per commit. Keep commits small and focused — see [CLAUDE.md](CLAUDE.md) for the full conventions used in this repo.

## What to work on

Check the [Issues](https://github.com/RoXsaita/NumbyAI-Public/issues) tab. Good first issues are tagged `good first issue`.

High-value areas:
- New bank statement fixtures (real-world CSVs with tricky formats)
- Parser edge cases (encoding issues, unusual date formats, multi-currency)
- Frontend UX improvements
- Documentation and examples

## PR expectations

- Keep PRs focused — one feature or fix per PR
- Include tests for new behaviour where practical
- Add a fixture CSV if you're fixing a parser bug (see `server/tests/fixtures/`)
- The CI gate (`make check-python` + `npm test`) must be green

## Reporting issues

Open a GitHub issue with steps to reproduce, expected vs. actual behaviour, and your OS/Python/Node versions.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).
