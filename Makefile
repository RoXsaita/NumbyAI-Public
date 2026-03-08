.PHONY: restart stop logs ensure-venv ensure-python-tools ensure-frontend setup-ollama test-e2e check-python clear-db

LOG_DIR ?= $(CURDIR)/server/logs
LOG_FILE ?= $(LOG_DIR)/numbyai-backend.log
VENV_DIR ?= $(CURDIR)/server/.venv
DEV_REQUIREMENTS ?= $(CURDIR)/server/requirements-dev.txt
PYTHON ?= python3

stop:
	@echo "=========================================="
	@echo "Stopping NumbyAI - All Services"
	@echo "=========================================="
	@echo ""
	@echo "Stopping servers on all ports..."
	@lsof -ti:8000 | xargs kill -9 2>/dev/null && echo "✓ Backend server (port 8000) stopped" || echo "  No process on port 8000"
	@echo ""
	@echo "Checking for any remaining uvicorn processes..."
	@pkill -f "uvicorn app.main:asgi_app" 2>/dev/null && echo "✓ Additional uvicorn processes stopped" || echo "  No additional uvicorn processes found"
	@echo ""
	@echo "=========================================="
	@echo "✓ All services stopped"
	@echo "=========================================="

ensure-venv:
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "Creating backend virtualenv..."; \
		$(PYTHON) -m venv "$(VENV_DIR)" || exit 1; \
	fi
	@if [ ! -x "$(VENV_DIR)/bin/pip" ]; then \
		echo "✗ Missing pip in virtualenv. Recreate with $(PYTHON) -m venv $(VENV_DIR)"; \
		exit 1; \
	fi
	@if [ ! -f "$(VENV_DIR)/.deps-installed" ] || [ server/requirements.txt -nt "$(VENV_DIR)/.deps-installed" ]; then \
		echo "Installing backend dependencies..."; \
		"$(VENV_DIR)/bin/pip" install -r server/requirements.txt > /dev/null && \
		touch "$(VENV_DIR)/.deps-installed" && \
		echo "✓ Backend dependencies installed" || \
		(echo "✗ Backend dependency install failed" && exit 1); \
	fi

ensure-python-tools: ensure-venv
	@if [ -f "$(DEV_REQUIREMENTS)" ] && ( [ ! -f "$(VENV_DIR)/.dev-deps-installed" ] || [ "$(DEV_REQUIREMENTS)" -nt "$(VENV_DIR)/.dev-deps-installed" ] ); then \
		echo "Installing Python dev tools..."; \
		"$(VENV_DIR)/bin/pip" install -r "$(DEV_REQUIREMENTS)" > /dev/null && \
		touch "$(VENV_DIR)/.dev-deps-installed" && \
		echo "✓ Python dev tools installed" || \
		(echo "✗ Python dev tool install failed" && exit 1); \
	fi

check-python: ensure-python-tools
	@echo "Running Python quality checks..."
	@cd server && .venv/bin/ruff check app tests
	@cd server && .venv/bin/mypy
	@cd server && .venv/bin/pytest tests --cov=app --cov-report=term-missing

ensure-frontend:
	@if [ ! -d "web/node_modules" ] || [ web/package-lock.json -nt "web/node_modules/.deps-installed" ]; then \
		echo "Installing frontend dependencies..."; \
		cd web && npm install > /dev/null && \
		touch node_modules/.deps-installed && \
		echo "✓ Frontend dependencies installed" || \
		(echo "✗ Frontend dependency install failed" && exit 1); \
	fi

restart: ensure-venv ensure-frontend
	@echo "=========================================="
	@echo "Restarting NumbyAI - Full System Restart"
	@echo "=========================================="
	@echo ""
	@echo "Step 1: Stopping all servers..."
	@lsof -ti:8000 | xargs kill -9 2>/dev/null || true
	@sleep 1
	@echo "✓ All servers stopped"
	@echo ""
	@echo "Step 2: Running database migrations..."
	@cd server && .venv/bin/alembic upgrade head > /dev/null 2>&1 && echo "✓ Database migrations applied" || echo "⚠ Database migration check completed"
	@echo ""
	@echo "Step 3: Building frontend app..."
	@cd web && npm run build > /dev/null 2>&1 && echo "✓ Frontend built successfully" || (echo "✗ Frontend build failed" && exit 1)
	@echo ""
	@echo "Step 4: Starting backend server on port 8000..."
	@mkdir -p $(LOG_DIR)
	@cd server && PYTHONUNBUFFERED=1 .venv/bin/uvicorn app.main:asgi_app --host 0.0.0.0 --port 8000 --reload > $(LOG_FILE) 2>&1 &
	@sleep 3
	@echo "✓ Backend server starting (logs: $(LOG_FILE))"
	@echo ""
	@echo "Step 5: Verifying services are responding..."
	@sleep 2
	@curl -s http://localhost:8000/health > /dev/null && echo "✓ Backend health check passed" || echo "⚠ Backend not responding yet (may need a moment)"
	@echo ""
	@echo "=========================================="
	@echo "✓ Restart complete!"
	@echo "=========================================="
	@echo ""
	@echo "🎯 FRONTEND APP (Click to open):"
	@echo "   👉 http://localhost:8000"
	@echo ""
	@echo "📊 BACKEND API:"
	@echo "   Health:   http://localhost:8000/health"
	@echo ""
	@echo "Backend logs: tail -f $(LOG_FILE) (or: make logs)"
	@echo "To stop: make stop"
	@echo ""
	@echo "Opening frontend in browser..."
	@open http://localhost:8000 2>/dev/null || xdg-open http://localhost:8000 2>/dev/null || echo "  (Please open http://localhost:8000 manually)"

logs:
	@if [ -f $(LOG_FILE) ]; then \
		echo "Tailing logs: $(LOG_FILE)"; \
		tail -f $(LOG_FILE); \
	else \
		echo "Log file not found: $(LOG_FILE)"; \
	fi

clear-db:		## Delete the SQLite database (run make restart to recreate)
	@rm -f server/finance_recon.db && echo "✓ Database cleared" || echo "  No database file found"

setup-ollama:		## Install Ollama and pull qwen3.5:9b
	bash server/scripts/setup_ollama.sh

test-e2e: ensure-venv		## Run end-to-end categorization test
	cd server && .venv/bin/python tests/test_e2e_categorization.py
