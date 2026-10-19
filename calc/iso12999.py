"""Measurement uncertainty of the single-number values, ISO 12999-1:2020, pure functions.

A field measurement in a building to check a requirement is situation B of 5.2 (the in-situ
standard deviation; the standard's own example in A.3 uses it). The standard uncertainties of
the single-number values are those of 7.2 Table 3 (ISO 717-1) and 7.3 Table 5 (ISO 717-2):

  DnT,w, DnT,w + C (100-3150 Hz)       0,9 dB
  DnT,w + Ctr (100-3150 Hz)            1,1 dB
  L'nT,w, L'nT,w + CI                  1,0 dB

  U = k u                                                             clause 8, formula (2)

The coverage factor k = 1 is Bent's choice (Table 8: 68 % two-sided, 84 % one-sided; the
examples in clause 8 and A.3 use it too). The tables do not cover receiving rooms smaller than
25 m3 (7.2), and installation noise is outside the scope of ISO 12999-1 (sound insulation only).
"""
from __future__ import annotations

SITUATION = "B"
COVERAGE_K = 1.0
CONFIDENCE = {"two_sided": 68, "one_sided": 84}      # % for k = 1, Table 8

# standard uncertainty u in dB per (kind, basis), situation B; basis as in calc.building
STANDARD_UNCERTAINTY = {
    ("airborne", "w"): 0.9,         # Table 3: DnT,w
    ("airborne", "wc"): 0.9,        # Table 3: DnT,w + C100-3150
    ("airborne", "wctr"): 1.1,      # Table 3: DnT,w + Ctr,100-3150
    ("impact", "w"): 1.0,           # Table 5: L'nT,w
    ("impact", "wci"): 1.0,         # Table 5: L'nT,w + CI
}


def expanded_uncertainty(kind: str, basis: str, k: float = COVERAGE_K) -> float | None:
    """U = k u in dB, to 0,1 dB; None when ISO 12999-1 gives no value (installation noise)."""
    u = STANDARD_UNCERTAINTY.get((kind, basis))
    return None if u is None else round(k * u, 1)
