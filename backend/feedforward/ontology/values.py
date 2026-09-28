"""
Parsing of reported amounts as European composition tables write them.

CIQUAL, CREA and Fineli do not only publish numbers. They publish "12,5"
(decimal comma), "< 0,5" (below the limit of quantification), "traces" /
"tr" / "tracce", and "-" or empty for "not analysed". Treating those as
0 or as the bare number would be wrong in different ways, so each becomes a
qualified value:

  exact      a measured or calculated number
  less_than  below the stated limit; ``amount`` is the limit
  trace      present, not quantified; ``amount`` is None
  missing    not reported; ``amount`` is None

``engine_amount`` is what the graph uses. It is conservative: a food is
never recommended on the strength of a value below detection, so
less_than and trace contribute 0. The database keeps the qualifier and the
bound, so nothing is lost.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

EXACT = "exact"
LESS_THAN = "less_than"
TRACE = "trace"
MISSING = "missing"
QUALIFIERS = (EXACT, LESS_THAN, TRACE, MISSING)

_TRACE_WORDS = {"tr", "tr.", "trace", "traces", "traccia", "tracce", "spår", "jälkiä"}
_MISSING_WORDS = {"", "-", "--", "n.d.", "nd", "n.a.", "na", "n/a", "…", "...", "?"}
_NUMBER = re.compile(r"^[+-]?\d+(?:[.,]\d+)?(?:[eE][+-]?\d+)?$")


@dataclass(frozen=True)
class ReportedValue:
    amount: float | None
    qualifier: str = EXACT

    @property
    def engine_amount(self) -> float:
        if self.qualifier == EXACT and self.amount is not None:
            return self.amount
        return 0.0


def _to_float(text: str) -> float:
    # A single comma is a decimal separator in every EU table we read.
    # Thousands separators do not occur in per-100 g composition data.
    return float(text.replace(",", "."))


def parse_value(raw) -> ReportedValue:
    """Parse one cell. Numbers pass through; strings are interpreted."""
    if raw is None:
        return ReportedValue(None, MISSING)
    if isinstance(raw, bool):
        raise ValueError(f"not a nutrient amount: {raw!r}")
    if isinstance(raw, (int, float)):
        if raw != raw:  # NaN, as pandas writes empty cells
            return ReportedValue(None, MISSING)
        return ReportedValue(float(raw), EXACT)
    text = str(raw).strip().lower()
    if text in _MISSING_WORDS:
        return ReportedValue(None, MISSING)
    if text in _TRACE_WORDS:
        return ReportedValue(None, TRACE)
    if text.startswith("<"):
        bound = text.lstrip("<=").strip()
        if _NUMBER.match(bound):
            return ReportedValue(_to_float(bound), LESS_THAN)
        raise ValueError(f"unparseable bound: {raw!r}")
    if _NUMBER.match(text):
        return ReportedValue(_to_float(text), EXACT)
    raise ValueError(f"unparseable amount: {raw!r}")
