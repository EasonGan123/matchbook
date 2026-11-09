"""Model access: live Claude calls, or replay of recorded / scripted responses.

MATCHBOOK_MODE=live    call Claude, and record every response to fixtures/replays/recorded/
MATCHBOOK_MODE=replay  serve recorded responses if present, else hand-scripted ones (agent/scripted.py)
MATCHBOOK_MODE=auto    (default) live if Anthropic credentials are set, else replay

Tools always execute for real against the mock Ramp service; only model output is replayed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from types import SimpleNamespace

from db.conn import ROOT

MODEL = os.environ.get("MATCHBOOK_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("MATCHBOOK_EFFORT", "medium")
RECORDED = ROOT / "fixtures" / "replays" / "recorded"


def mode() -> str:
    m = os.environ.get("MATCHBOOK_MODE", "auto")
    if m == "auto":
        return "live" if (os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")) else "replay"
    return m


def _ns(x):
    if isinstance(x, dict):
        return SimpleNamespace(**{k: _ns(v) for k, v in x.items()})
    if isinstance(x, list):
        return [_ns(v) for v in x]
    return x


class LLMError(RuntimeError):
    pass


class LiveLLM:
    kind = "live"

    def __init__(self, scenario: str, record: bool = True):
        import anthropic
        self.client = anthropic.Anthropic()
        self.scenario = scenario
        self.record = record
        self.counters: dict[str, int] = {}

    def create(self, stage: str, *, system: str, tools: list, messages: list):
        import anthropic
        try:
            resp = self.client.beta.messages.create(
                model=MODEL,
                max_tokens=16000,
                system=system,
                tools=tools,
                messages=messages,
                thinking={"type": "adaptive"},
                output_config={"effort": EFFORT},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.RateLimitError as e:
            raise LLMError(f"rate limited: {e}") from e
        except anthropic.APIStatusError as e:
            raise LLMError(f"API error {e.status_code}: {e.message}") from e
        except anthropic.APIConnectionError as e:
            raise LLMError(f"connection error: {e}") from e
        if self.record:
            i = self.counters.get(stage, 0)
            self.counters[stage] = i + 1
            d = RECORDED / self.scenario
            d.mkdir(parents=True, exist_ok=True)
            (d / f"{stage}-{i:02d}.json").write_text(json.dumps(resp.model_dump(mode="json"), indent=1))
        return resp


class ReplayLLM:
    def __init__(self, scenario: str):
        self.scenario = scenario
        self.counters: dict[str, int] = {}
        self.kind = "replay-recorded" if (RECORDED / scenario).exists() else "replay-scripted"

    def create(self, stage: str, *, system: str, tools: list, messages: list):
        i = self.counters.get(stage, 0)
        self.counters[stage] = i + 1
        rec = RECORDED / self.scenario / f"{stage}-{i:02d}.json"
        if rec.exists():
            return _ns(json.loads(rec.read_text()))
        from agent.scripted import scripted_turn
        turn = scripted_turn(self.scenario, stage, i)
        if turn is None:
            raise LLMError(f"no replay for {self.scenario}/{stage}#{i}")
        return _ns(turn)


def get_llm(scenario: str):
    return LiveLLM(scenario) if mode() == "live" else ReplayLLM(scenario)


def block_to_param(b) -> dict:
    """Serialize a content block for the next request (replay objects are SimpleNamespace)."""
    if hasattr(b, "model_dump"):
        return b.model_dump(mode="json", exclude_none=True)
    return json.loads(json.dumps(b, default=lambda o: o.__dict__))
