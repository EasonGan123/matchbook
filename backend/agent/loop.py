"""The tool-use loop. The model chooses which read tools to call; code decides what happens next."""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field

from agent.llm import LLMError


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    turns: int = 0

    def add(self, u) -> None:
        if u is None:
            return
        self.input_tokens += (getattr(u, "input_tokens", 0) or 0) + (getattr(u, "cache_read_input_tokens", 0) or 0) \
            + (getattr(u, "cache_creation_input_tokens", 0) or 0)
        self.output_tokens += getattr(u, "output_tokens", 0) or 0


@dataclass
class AgentResult:
    output: dict
    usage: Usage = field(default_factory=Usage)


def pace() -> float:
    return float(os.environ.get("MATCHBOOK_PACE", "0"))


def run_agent(*, llm, stage: str, system: str, user: str, tools: list, terminal: str, toolbox=None,
              emit=lambda *a, **k: None, max_turns: int = 12) -> AgentResult:
    messages: list = [{"role": "user", "content": user}]
    usage = Usage()
    for _ in range(max_turns):
        if pace():
            time.sleep(pace())
        resp = llm.create(stage, system=system, tools=tools, messages=messages)
        usage.turns += 1
        usage.add(getattr(resp, "usage", None))
        if resp.stop_reason == "refusal":
            raise LLMError("model declined the request")
        if resp.stop_reason == "max_tokens":
            raise LLMError("response hit max_tokens")

        for b in resp.content:
            if b.type == "text" and b.text.strip():
                emit("model", b.text.strip(), {"stage": stage})
        tool_uses = [b for b in resp.content if b.type == "tool_use"]
        messages.append({"role": "assistant", "content": resp.content})
        if not tool_uses:
            messages.append({"role": "user", "content": f"Please finish by calling {terminal}."})
            continue

        results, final = [], None
        for tu in tool_uses:
            args = tu.input if isinstance(tu.input, dict) else vars(tu.input)
            if tu.name == terminal:
                final = args
                results.append({"type": "tool_result", "tool_use_id": tu.id, "content": "recorded"})
                continue
            if toolbox is None:
                results.append({"type": "tool_result", "tool_use_id": tu.id, "is_error": True,
                                "content": "no tools available in this stage"})
                continue
            t0 = time.time()
            out = toolbox.call(tu.name, args)
            emit("tool", tu.name, {"input": args, "output": json.loads(out), "ms": int((time.time() - t0) * 1000)})
            toolbox.flush()
            if pace():
                time.sleep(pace() / 2)
            results.append({"type": "tool_result", "tool_use_id": tu.id, "content": out})
        messages.append({"role": "user", "content": results})
        if final is not None:
            return AgentResult(output=final, usage=usage)
    raise LLMError(f"no {terminal} after {max_turns} turns")
