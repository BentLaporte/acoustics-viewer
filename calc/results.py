"""Calculation results as plain dictionaries (JSON), for the command line and for other programs.

The layout is documented in docs/cli.md and fixed by SCHEMA_VERSION: names are never changed
without raising the version. Missing numbers (a band without reverberation time...) are null.
"""
from __future__ import annotations

import math

import numpy as np

from .building import AIRBORNE_BASES, IMPACT_BASES, Evaluated
from .iso717 import BANDS, REF_AIRBORNE, REF_IMPACT, LIMIT_DB

SCHEMA_VERSION = 1


def _num(x):
    """float/np.float -> float, NaN -> None (JSON has no NaN); ints stay ints."""
    if x is None:
        return None
    if isinstance(x, (bool, np.bool_)):
        return bool(x)
    if isinstance(x, (int, np.integer)):
        return int(x)
    x = float(x)
    return None if math.isnan(x) else x


def _list(values, nd: int | None = None):
    out = []
    for v in np.asarray(values).tolist():
        v = _num(v)
        out.append(round(v, nd) if (nd is not None and isinstance(v, float)) else v)
    return out


def _files(info) -> dict:
    return {role: [{"name": i.name,
                    "measured_at": i.measured_at.isoformat() if i.measured_at else None,
                    "instrument": i.instrument, "serial": i.serial} for i in infos]
            for role, infos in (info or {}).items()}


def evaluated_to_dict(ev: Evaluated, bands: bool = True) -> dict:
    """One measurement (airborne or impact) with its rating, requirement check and, if
    bands=True, the values per one-third-octave band."""
    airborne = ev.kind == "airborne"
    out = {
        "schema_version": SCHEMA_VERSION,
        "kind": ev.kind,
        "name": ev.name,
        "source_room" if airborne else "tapping_room": ev.source_room,
        "receiver_room": ev.receiver_room,
        "comment": ev.comment,
        "ok": ev.ok,
        "error": ev.error,
        "remarks": [] if ev.error else ev.notes,
        "result": None,
        "requirement": None,
        "files": {},
    }
    r = ev.result
    if r is None:
        return out
    rating = r.rating
    result = {
        "quantity": "DnT,w" if airborne else "L'nT,w",
        "single_number_db": None if rating is None else rating.value,
        "C" if airborne else "CI": None if rating is None else (r.c if airborne else r.ci),
        "reference_curve_shift_db": None if rating is None else rating.shift,
        "unfavourable_deviation_sum_db": None if rating is None else round(rating.unfavourable_sum, 1),
        "unfavourable_deviation_limit_db": LIMIT_DB,
        "reverberation_time_used": r.t_kind,
        "bands_close_to_background": int(r.n_limit),
    }
    if airborne:
        result["Ctr"] = None if rating is None else r.ctr
    out["result"] = result
    if ev.requirement is not None:
        chk = ev.check
        out["requirement"] = {
            "compared_quantity": ev.basis_label,
            "direction": ">=" if airborne else "<=",
            "value_db": ev.requirement,
            "assessed_value_db": ev.assessed,
            "check": chk.status,                 # complies | fails | inconclusive | no_result
            "margin_db": chk.margin,             # positive = better than required
        }
    out["files"] = _files(r.info)
    if bands:
        out["bands_hz"] = [int(b) for b in BANDS]
        if airborne:
            out["bands"] = {
                "source_level_db": _list(r.l1, 2),
                "receiver_level_measured_db": _list(r.l2_raw, 2),
                "background_level_db": _list(r.lb, 2),
                "receiver_level_corrected_db": _list(r.l2, 2),
                "background_correction": [str(s) for s in r.status],   # ok | corrected | limit
                "reverberation_time_s": _list(r.t, 3),
                "level_difference_D_db": _list(r.d, 2),
                "standardized_level_difference_DnT_db": _list(r.dnt, 2),
                "reference_curve_unshifted_db": _list(REF_AIRBORNE),
            }
        else:
            out["bands"] = {
                "tapping_level_measured_db": _list(r.li_raw, 2),
                "background_level_db": _list(r.lb, 2),
                "tapping_level_corrected_db": _list(r.li, 2),
                "background_correction": [str(s) for s in r.status],
                "reverberation_time_s": _list(r.t, 3),
                "standardized_impact_level_LnT_db": _list(r.lnt, 2),
                "reference_curve_unshifted_db": _list(REF_IMPACT),
            }
        out["bands"]["reference_curve_shifted_db"] = None if rating is None else _list(rating.curve)
        out["bands"]["unfavourable_deviation_db"] = None if rating is None else _list(rating.deviations, 1)
    return out


def bases_text(kind: str) -> dict:
    """The allowed --basis values of a kind, with the quantity they stand for."""
    return dict(AIRBORNE_BASES if kind == "airborne" else IMPACT_BASES)


def installation_to_dict(r, requirement: int | None = None) -> dict:
    """One installation noise measurement (calc.installation.InstallationResult)."""
    from .installation import METHODS, check_requirement
    margin = None if requirement is None else requirement - r.value
    return {
        "schema_version": SCHEMA_VERSION,
        "kind": "installation",
        "ok": True,
        "error": None,
        "remarks": r.notes,
        "result": {
            "quantity": r.symbol,                                # LAeq,nT | LAFmax,nT
            "single_number_db": r.value,                         # whole dB (ISO 10052 7.3)
            "standardized_level_unrounded_db": round(r.lnt, 2),
            "measured_level_db": round(r.level, 2),              # L_XY, energy average
            "reverberation_index_k_db": round(r.k, 2),
            "method": r.method,
            "method_text": METHODS[r.method],
            "background_level_laeq_db": None if r.background is None else round(r.background, 2),
            "background_affected": r.background_affected,        # < 6 dB above the background
        },
        "requirement": None if requirement is None else {
            "compared_quantity": r.symbol,
            "direction": "<=",
            "value_db": requirement,
            "assessed_value_db": r.value,
            "check": check_requirement(r, requirement),          # complies | fails | inconclusive
            "margin_db": margin,                                 # positive = better than required
        },
        "recordings": [
            {"file": rec.path.name, "start_s": rec.start, "end_s": rec.end, "duration_s": d,
             "level_db": round(float(lv), 2),
             "margin_to_background_db": None if r.margins is None else round(float(m), 2)}
            for rec, d, lv, m in zip(r.recordings, r.durations, r.levels,
                                     r.margins if r.margins is not None else [None] * len(r.levels))],
        "reverberation": {
            "octave_s": {str(o): round(t, 3) for o, t in r.t_octaves.items()},
            "third_octave_s": {str(int(hz)): _num(round(t, 3)) for hz, t in r.t_thirds.items()},
            "t20_instead_of_t30_hz": sorted(int(hz) for hz in r.t20_used),
        },
        "files": _files(r.info),
    }
