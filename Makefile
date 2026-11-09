# Matchbook: run everything from the repo root.
.PHONY: install dev api web reset test eval demo-check fixtures extract mcp

install:            ## install backend + frontend deps
	cd backend && uv sync
	cd frontend && pnpm install

dev:                ## API on :8000 and web on :3000
	@echo "API http://localhost:8000  ·  Web http://localhost:3000"
	@trap 'kill 0' INT TERM; \
	  (cd backend && uv run uvicorn api.main:app --port 8000 --reload) & \
	  (cd frontend && pnpm dev) & \
	  wait

api:
	cd backend && uv run uvicorn api.main:app --port 8000 --reload

web:
	cd frontend && pnpm dev

reset:              ## reseed the demo database
	cd backend && uv run python -m db.seed

test:               ## engine/validator unit tests + the eval suite
	cd backend && uv run pytest -q

eval:               ## nine-case scorecard (writes evals/results/latest.json)
	cd backend && uv run python ../evals/run_evals.py

demo-check:         ## click through the demo in Chrome (needs `make dev` running)
	cd backend && uv run python ../scripts/demo_check.py ../demo-shots

fixtures:           ## regenerate the fictional PDFs
	cd backend && uv run python ../scripts/make_fixtures.py

extract:            ## contract PDFs -> terms JSON with Claude vision (needs API key), then reseed
	cd backend && uv run python -m extract.contracts && uv run python -m db.seed

mcp:                ## serve the read tools over MCP (stdio)
	cd backend && uv run python -m mcp_server.server
