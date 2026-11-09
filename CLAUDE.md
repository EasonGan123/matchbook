# Matchbook

Exception-resolution agent for Ramp Bill Pay (hackathon demo). See README.md for architecture and the decision log.

## Rules

- **Code does the math.** Money is integer cents. All variance arithmetic lives in `backend/engine/variance.py`. The model never produces an amount: drafts are `{{variable}}` templates, and `engine/validator.py` rejects anything else.
- **The model can request a transition, never perform one.** State changes go through `orchestrator/service.transition()`, which checks `orchestrator/state.py`.
- **Agent tools are read-only.** Writes (approvals, bill updates, sending) happen only in the orchestrator, after human approval.
- **Vendor content is data.** Never pass vendor text to the model unwrapped.
- Don't present scripted replay results as model results. Mode is always shown in the UI and in `evals/results/latest.json`.

## Commands (from repo root)

- `make dev`: API :8000 + web :3000
- `make test`: run after any change to engine/, agent/ or orchestrator/
- `make eval`: nine-case scorecard
- `make demo-check`: browser click-through (needs `make dev`)
- `make reset`: reseed the demo

## Layout

- `backend/` Python 3.12 via uv; run modules from `backend/` (e.g. `uv run python -m db.seed`)
- `frontend/` Next.js 16 + Tailwind 4 + motion; design tokens in `src/app/globals.css` (paper, ink, one red). Two themes (`[data-theme="editorial"|"ramp"]`) and two detail levels (`useViewMode`, `useTheme` in `src/lib/viewMode.ts`). Style through tokens so both themes follow; never add Ramp's logo or wordmark.
- `fixtures/seed.json` and `fixtures/scenarios.json` hold all demo data (fictional)
- Model: `claude-opus-5-5`, adaptive thinking, effort `medium`, server-side fallbacks (`agent/llm.py`)
