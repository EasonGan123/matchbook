"""Draft validator: the model never writes a dollar amount.

Drafts are templates with {{variables}} filled by code from the variance engine.
After rendering, every number in the text must trace to a variable or to the evidence
the agent actually retrieved. Anything else is rejected.
"""
from __future__ import annotations

import re

NUM = re.compile(r"\$?\d[\d,]*(?:\.\d+)?")
VAR = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")


def _norm(tok: str) -> str:
    t = tok.replace("$", "").replace(",", "")
    if "." in t:
        t = t.rstrip("0").rstrip(".")
    return t.lstrip("0") or "0"


def numbers_in(text: str) -> set[str]:
    return {_norm(m.group()) for m in NUM.finditer(text or "")}


def render(template: str, variables: dict[str, str]) -> tuple[str, list[str]]:
    missing: list[str] = []

    def sub(m: re.Match) -> str:
        key = m.group(1)
        if key not in variables:
            missing.append(key)
            return m.group(0)
        return str(variables[key])

    return VAR.sub(sub, template), missing


def validate(template: str, variables: dict[str, str], evidence_text: str) -> dict:
    body, missing = render(template, variables)
    allowed_from_vars = set().union(*(numbers_in(str(v)) for v in variables.values())) if variables else set()
    allowed_from_evidence = numbers_in(evidence_text)
    literal_in_template = numbers_in(VAR.sub("", template))
    found = []
    for m in NUM.finditer(body):
        n = _norm(m.group())
        src = ("variable" if n in allowed_from_vars and n not in literal_in_template
               else "evidence" if n in allowed_from_evidence else None)
        found.append({"text": m.group(), "source": src})
    untraced = [f["text"] for f in found if f["source"] is None]
    # Dollar amounts must always come from variables, never typed by the model.
    literal_money = [m.group() for m in NUM.finditer(VAR.sub("", template)) if m.group().startswith("$")]
    untraced += [t for t in literal_money if t not in untraced]
    ok = not untraced and not missing
    return {
        "ok": ok,
        "body": body,
        "numbers": found,
        "untraced": untraced,
        "missing_variables": missing,
        "summary": (f"All {len(found)} numbers traced to the variance engine or source documents"
                    if ok else
                    f"Rejected: {len(untraced)} untraced number(s) {untraced}"
                    + (f", unknown variables {missing}" if missing else "")),
    }
