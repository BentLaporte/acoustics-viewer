"""In-situ tolerance of the Belgian requirements, pure functions.

NBN S 01-400-1:2022 (dwellings), clauses 5.4, 6.4 and 8.4 ("Bijzonderheden"); NBN S 01-400-3:2026
(non-residential buildings) 5.2, 6.2 and 8.4 use the same numbers. Only when measured values are
checked against the in-situ requirements, a result (rounded to whole dB) complies when it is at
most the tolerance worse than the requirement:

  airborne (D_A >= requirement - tolerance)       2 dB
  impact (L'nT,w <= requirement + tolerance)      2 dB
  installation noise (<= requirement + tolerance) 1 dB

For receiving rooms smaller than 25 m3 that are not bedrooms the tolerance is 2 dB larger
(4, 4 and 3 dB). An unknown volume gets the normal tolerance: the safe side.
NBN S 01-400-2 (schools, draft 2012) has 2 dB without the volume rule; not implemented.
"""
from __future__ import annotations

TOLERANCE_DB = {"airborne": 2, "impact": 2, "installation": 1}
SMALL_ROOM_M3 = 25.0
SMALL_ROOM_EXTRA_DB = 2


def is_small_room(volume: float | None, bedroom: bool) -> bool:
    """Smaller than 25 m3 and not a bedroom: the larger tolerance applies."""
    return volume is not None and volume < SMALL_ROOM_M3 and not bedroom


def in_situ_tolerance(kind: str, volume: float | None = None, bedroom: bool = False) -> int:
    """The tolerance in dB for a measurement of this kind in this receiving room."""
    extra = SMALL_ROOM_EXTRA_DB if is_small_room(volume, bedroom) else 0
    return TOLERANCE_DB[kind] + extra
