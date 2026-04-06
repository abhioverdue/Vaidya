.PHONY: up down build logs shell migrate migration rollback seed verify test lint format setup clean

# ── Docker ────────────────────────────────────────────────────────────────────
up:
	docker compose up -d
	@echo ""
	@echo "  API docs : http://localhost:8000/docs"
	@echo "  Health   : http://localhost:8000/health"
	@echo "  Grafana  : http://localhost:3000  (admin / grafana_secret)"
	@echo ""

down:
	docker compose down

build:
	docker compose build --no-cache

logs:
	docker compose logs -f api celery_worker

shell:
	docker compose exec api bash

# ── Database ──────────────────────────────────────────────────────────────────
migrate:
	@echo "Running Alembic migrations..."
	docker compose exec api alembic upgrade head
	@echo "Migrations complete."

migration:
	@test -n "$(MSG)" || (echo "Usage: make migration MSG='describe the change'" && exit 1)
	docker compose exec api alembic revision --autogenerate -m "$(MSG)"

rollback:
	docker compose exec api alembic downgrade -1

seed:
	@echo "Verifying seed data..."
	docker compose exec postgres psql -U vaidya -d vaidya \
	  -c "SELECT 'hospitals' as table, COUNT(*) FROM hospitals UNION ALL SELECT 'asha_workers', COUNT(*) FROM asha_workers;"

verify:
	@echo "Running health check..."
	curl -sf http://localhost:8000/health | python3 -m json.tool
	@echo ""
	@echo "Running smoke test (requires GEMINI_API_KEY in .env)..."
	curl -sf -X POST http://localhost:8000/api/v1/diagnose/predict/text \
	  -H "Content-Type: application/json" \
	  -d '{"text":"I have fever and cough for three days","language":"en"}' \
	  | python3 -m json.tool | head -20

# ── Dev ───────────────────────────────────────────────────────────────────────
test:
	docker compose exec api pytest -v --tb=short

test-cov:
	docker compose exec api pytest -v --cov=app --cov-report=term-missing

lint:
	docker compose exec api ruff check app/ tests/
	docker compose exec api ruff format --check app/ tests/

format:
	docker compose exec api ruff format app/ tests/

# ── First-time setup (fresh machine) ─────────────────────────────────────────
setup: build up migrate seed
	@echo ""
	@echo "  Vaidya is ready."
	@echo "  Set GEMINI_API_KEY in .env then run: make verify"
	@echo ""

clean:
	docker compose down -v --remove-orphans
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -exec rm -rf {} + 2>/dev/null || true
