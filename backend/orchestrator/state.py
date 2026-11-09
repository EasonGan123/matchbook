"""Case state machine. The model can ask for a transition; only this table can grant it."""

STATES = ["OPEN", "CONTEXT_GATHERED", "DIAGNOSED", "DRAFTED", "PENDING_APPROVAL", "SENT",
          "AWAITING_VENDOR", "RESOLVED", "SYNCED", "ESCALATED"]

ALLOWED = {
    "OPEN": {"CONTEXT_GATHERED", "ESCALATED"},
    "CONTEXT_GATHERED": {"DIAGNOSED", "ESCALATED"},
    "DIAGNOSED": {"DRAFTED", "ESCALATED"},
    "DRAFTED": {"PENDING_APPROVAL", "ESCALATED"},
    "PENDING_APPROVAL": {"SENT", "RESOLVED", "ESCALATED"},
    "SENT": {"AWAITING_VENDOR", "RESOLVED"},
    "AWAITING_VENDOR": {"RESOLVED", "DIAGNOSED", "ESCALATED"},
    "RESOLVED": {"SYNCED"},
    "SYNCED": set(),
    "ESCALATED": set(),
}

TERMINAL = {"SYNCED", "ESCALATED"}


class IllegalTransition(Exception):
    pass


def check(frm: str, to: str) -> None:
    if to not in ALLOWED.get(frm, set()):
        raise IllegalTransition(f"{frm} → {to} is not allowed")
