.PHONY: up down build logs test seed shell clean lint help

# ── Docker Compose shortcuts ──────────────────────────────────────────────────
up:          ## Start all services in detached mode
	docker-compose up -d --build

down:        ## Stop and remove containers
	docker-compose down

build:       ## Rebuild the app image
	docker-compose build app

logs:        ## Tail logs from the app container
	docker-compose logs -f app

logs-all:    ## Tail logs from all containers
	docker-compose logs -f

restart:     ## Restart the app container only
	docker-compose restart app

# ── Testing ───────────────────────────────────────────────────────────────────
test:        ## Run test suite (no Docker needed — uses mocks)
	cd app && pip install -q -r requirements.txt && \
	PYTHONPATH=. pytest ../tests -v

test-cov:    ## Run tests with coverage report
	cd app && PYTHONPATH=. pytest ../tests -v --cov=. --cov-report=html

# ── Data ──────────────────────────────────────────────────────────────────────
seed:        ## Seed sample documents (service must be running)
	pip install -q httpx && python3 scripts/seed_data.py

smoke:       ## Run smoke tests against running service
	bash scripts/sample_requests.sh

# ── Dev helpers ───────────────────────────────────────────────────────────────
shell:       ## Open a shell inside the app container
	docker-compose exec app bash

lint:        ## Run ruff linter (install: pip install ruff)
	cd app && ruff check .

format:      ## Auto-format with ruff
	cd app && ruff format .

clean:       ## Remove Docker volumes (wipes all data!)
	docker-compose down -v

# ── Info ──────────────────────────────────────────────────────────────────────
help:        ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
