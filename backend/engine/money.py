"""Money is integer cents everywhere. Formatting lives here so drafts and UI agree."""


def usd(cents: int) -> str:
    sign = "-" if cents < 0 else ""
    cents = abs(int(cents))
    return f"{sign}${cents // 100:,}.{cents % 100:02d}"


def qty(n: int) -> str:
    return f"{int(n):,}"


def pct(numer: int, denom: int) -> float:
    return round(100.0 * numer / denom, 1) if denom else 0.0
