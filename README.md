# Matchbook

**The agent that fixes the invoices that don't match.**

Ramp's three-way match already blocks a bill that disagrees with its PO or receipt.
Matchbook picks up the blocked bill, finds the root cause, drafts the fix, routes it
through approval, and follows up until a corrected bill syncs back.
Ramp catches it. Matchbook closes it.

All vendors, people and figures in this repo are fictional.

## Run it

```bash
make install      # uv + pnpm
make dev          # API :8000, web :3000
```

Open http://localhost:3000, open **Acme Industrial Supply**, press **Run Matchbook**,
approve the draft, then **Fast-forward follow-up**.

| Command | What it does |
| --- | --- |
| `make test` | Variance engine and validator unit tests, plus the nine-case eval |
| `make eval` | Prints the scorecard; also on the `/evals` page |
| `make reset` | Reseeds the demo (also the **Reset** link in the header) |
| `make demo-check` | Clicks through the whole demo in Chrome and saves screenshots |
| `make extract` | Extracts contract terms from the PDFs with Claude vision, then reseeds |
| `make mcp` | Serves the read tools over MCP (stdio) |

### Views

Two switches in the header, remembered per browser:

- **Simple / Detailed**: visuals only, or visuals plus the full text layer (engine findings, evidence ids, number trace, message thread, documents, full agent log).
- **Editorial / Ramp**: Matchbook's pitch look (paper, serif, red pen), or Ramp's design language taken from the tokens on ramp.com (white, warm grays, the "solar" lime accent, sans headings; Inter stands in for the licensed Lausanne). The Ramp theme uses no Ramp logo or wordmark. The red pen marks stay in both themes as Matchbook's signature.

### Live vs replay

| Mode | When | What runs |
| --- | --- | --- |
| `live` | `ANTHROPIC_API_KEY` is set | Claude (`claude-opus-5-5`) makes every model call; each response is recorded to `fixtures/replays/recorded/` |
| `replay` (recorded) | No key, recordings exist | Recorded Claude responses are replayed |
| `replay` (scripted) | No key, no recordings | Hand-written model turns from `backend/agent/scripted.py` |

In every mode the tools, variance engine, validator, state machine and mock Ramp run for
real; only model output is replayed. The header and the scorecard always show which
mode is active. **A scripted eval run tests the pipeline and guardrails, not Claude.**
Report model metrics only from live or recorded runs.

To record real runs: set the key, run `make eval` once, then demo offline with the
recordings.

## How it works

```
Ramp Bill Pay (mock)          Matchbook backend                         Claude
───────────────────           ─────────────────                         ──────
bills, POs, receipts   ──▶    ingest: one case per blocked bill
vendors, contracts             + contract sweep (stale PO prices)
                               │
                               ▼
                         tool-use loop  ◀───── read tools only ─────▶  reads, decides which
                               │                                        tool to call next
                               ▼
                         variance engine (Python, integer cents)
                               │
                               ▼
                         diagnosis: enum + cited evidence ─────────▶   classifies root cause
                         guardrails: citations exist, engine agrees,
                         conflicts escalate, injections logged
                               │
                               ▼
                         playbook → variables (code) → draft ──────▶   writes the message as
                         validator: every number traced                 a {{template}}
                               │
                               ▼
approval request  ◀──────  PENDING_APPROVAL ── person approves
                               │
                               ▼
                         send → follow-up every 3 days → reply ────▶   reads the reply
                         re-match with the same engine
bill synced       ◀──────  RESOLVED → SYNCED
```

Case states: `OPEN → CONTEXT_GATHERED → DIAGNOSED → DRAFTED → PENDING_APPROVAL → SENT →
AWAITING_VENDOR → RESOLVED → SYNCED`, and from any stage `→ ESCALATED`. Transitions are
enforced in `orchestrator/state.py`.

## Repo

```
backend/
  api/            FastAPI: mock Ramp (/ramp/...) and Matchbook (/api/...), SSE stream
  ramp_client/    RampClient protocol; MockRampClient (SQLite), LiveRampClient (stub)
  agent/          tools, prompts, tool-use loop, live/replay model client, scripted turns
  engine/         variance engine, money formatting, draft validator
  orchestrator/   case service, state machine, playbooks, follow-up and vendor simulator
  extract/        contract PDF → terms JSON with Claude vision
  mcp_server/     the read tools over MCP
  db/             schema (append-only audit log), seed loader
  tests/          engine and validator tests
frontend/         Next.js: inbox, case view, scorecard
fixtures/         seed.json, scenarios.json, generated PDFs, extraction cache, replays
evals/            nine-case harness and results
scripts/          PDF generator, browser demo check
```

## Guardrails, and where they live

| Control | Code |
| --- | --- |
| The model never writes an amount. Drafts are templates; code fills in the numbers, and the validator rejects any typed dollar figure or untraceable number | `engine/validator.py` |
| Math in code: integer cents, contract price effective on the invoice date | `engine/variance.py` |
| Every root cause cites evidence the agent actually retrieved; a diagnosis the engine doesn't support is escalated | `orchestrator/service.py` (`_run_case`) |
| Conflicting contracts or `UNKNOWN` go to a person | same |
| Read-only agent tools; writes happen only in the orchestrator after approval | `agent/tools.py`, `orchestrator/service.py` |
| Vendor text is wrapped as untrusted data, scanned for instructions, and logged | `agent/tools.py` (`scan_injection`) |
| Outbound mail goes only to the contact on file or the PO's buyer | `orchestrator/service.py` |
| Append-only audit log, enforced by SQLite triggers | `db/schema.sql` |
| One case per bill; reruns are no-ops | `cases.bill_id UNIQUE`, `ingest()` |

## Decision log

- **Code does the math, Claude does the reading.** Price, quantity and tolerance checks
  must be exact and auditable, so they are deterministic and unit-tested. Claude handles
  what rules can't: picking the governing contract, reading clauses, judging intent in a
  reply, writing to a person.
- **Root cause is a fixed enum through a strict tool.** It keeps output testable. Opus 5.5
  rejects forced `tool_choice`, so tools are `strict: true` and the prompt names the
  terminal tool.
- **Templates instead of free-text amounts.** Even a correct model can mistype a number.
  Variables make it impossible for the model to add one.
- **MCP for the tool layer.** The same read tools are served over MCP
  (`mcp_server/`), matching how Ramp's own ramp-mcp exposes its Developer API. The agent
  calls them in-process during the demo: same functions, one less process to fail on stage.
- **`RampClient` adapter.** Going live means implementing `LiveRampClient`, not changing
  the agent. Mock field names are simplified; check them against docs.ramp.com. Write
  scopes for approval requests are an open question for Ramp.
- **SQLite.** No setup, one file, trivial reset. The audit log's append-only rule is
  enforced in the database, not just in code.
- **Replay mode with a visible label.** The demo must survive bad venue wifi, and nobody
  should mistake scripted responses for model results.
- **Simulated clock for follow-ups.** The cadence is real (every 3 days); fast-forward
  advances the clock instead of waiting days.
- **Contract terms extracted once and cached.** Vision runs once per contract, not per
  case. Until `make extract` has run, terms come from the fixture's ground truth and the
  UI labels them that way.

## Known gaps

- `LiveRampClient` is a stub.
- When a corrected bill still doesn't match, the case escalates instead of looping back
  to a fresh diagnosis.
- The corrected invoice arrives as a structured bill, as if Ramp's own OCR had ingested
  it; Claude classifies the reply but does not read the attachment.
