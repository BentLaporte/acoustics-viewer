"""Command line interface: python -m calc <command> ...

  airborne   DnT,w (C; Ctr) from level files of the source room, the receiving room, the
             background and the reverberation time
  impact     L'nT,w (C_I) from tapping machine, background and reverberation time files
  building   evaluate every measurement of a building project file (.json), optionally write
             the PDF report
  info       what is in an SVL file (instrument, date and time, levels)

Output is text for people (default), JSON for programs (--format json) or CSV (per band).
Exit status: 0 = done, 2 = bad input (message on stderr), 1 = with --strict: a requirement
is not met / not conclusive, or a measurement could not be calculated. See docs/cli.md.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import os
import sys
from pathlib import Path

import numpy as np

from svl.parser import SvlError, read_svl
from svl.rt import read_rt

from .airborne import compute_airborne
from .building import (AIRBORNE_BASES, IMPACT_BASES, Evaluated, equipment_used, evaluate_project,
                       load_project)
from .impact import compute_impact
from .iso717 import BANDS
from .results import SCHEMA_VERSION, _list, _num, evaluated_to_dict

RT_KINDS = ["t30", "t20", "edt"]


class CliError(Exception):
    """Bad input: reported as 'error: ...' on stderr, exit status 2."""


# ----------------------------------------------------------------------------- small helpers
def _f(x, nd=1, width=6) -> str:
    return f"{'-':>{width}}" if x is None or not np.isfinite(x) else f"{x:{width}.{nd}f}"


def _when(i) -> str:
    return "" if i.measured_at is None else i.measured_at.strftime("%d/%m/%Y %H:%M")


def _file_line(role: str, infos) -> str:
    parts = []
    for i in infos:
        extra = ", ".join(x for x in (_when(i), f"{i.instrument} #{i.serial}" if i.instrument else "") if x)
        parts.append(f"{i.name} ({extra})" if extra else i.name)
    return f"  {role:<11} {', '.join(parts)}"


def _signed(v) -> str:
    return "-" if v is None else f"{v:+d}"


def _bands_table(ev: Evaluated) -> list[str]:
    r, rt = ev.result, ev.rating
    air = ev.kind == "airborne"
    if air:
        head = ["Hz", "L1", "L2 meas", "Lb", "L2 corr", "T [s]", "D", "DnT", "ref", "dev"]
    else:
        head = ["Hz", "Li meas", "Lb", "Li corr", "T [s]", "L'nT", "ref", "dev"]
    lines = ["".join(f"{h:>8}" for h in head)]
    for i, hz in enumerate(BANDS):
        star = "*" if r.status[i] == "limit" else " "
        raw, corr = (r.l2_raw[i], r.l2[i]) if air else (r.li_raw[i], r.li[i])
        ref = "-" if rt is None else f"{int(rt.curve[i])}"
        dev = "-" if rt is None or rt.deviations[i] == 0 else f"{rt.deviations[i]:.1f}"
        cells = ([f"{int(hz)}", _f(r.l1[i], 1, 7), _f(raw, 1, 7), _f(r.lb[i], 1, 7), _f(corr, 1, 7),
                  _f(r.t[i], 3, 7), _f(r.d[i], 1, 7), _f(r.dnt[i], 1, 7)] if air else
                 [f"{int(hz)}", _f(raw, 1, 7), _f(r.lb[i], 1, 7), _f(corr, 1, 7), _f(r.t[i], 3, 7),
                  _f(r.lnt[i], 1, 7)])
        lines.append("".join(f"{c:>8}" for c in cells) + f"{ref:>8}{dev:>8}{star}")
    return lines


def format_measurement_text(ev: Evaluated) -> str:
    """Human readable result of one airborne or impact calculation."""
    air = ev.kind == "airborne"
    title = "Airborne sound insulation (DnT,w)" if air else "Impact sound insulation (L'nT,w)"
    out = [title, ""]
    if not ev.ok:
        return "\n".join(out + [f"  Could not be calculated: {ev.error}"])
    r, rt = ev.result, ev.rating
    out.append("Files:")
    out += [_file_line(role, infos) for role, infos in r.info.items()]
    out += ["", f"Reverberation time used: {r.t_kind.upper()}   (levels in dB, T in s, "
                "* = band within 6 dB of the background)", ""]
    out += _bands_table(ev)
    out.append("")
    if rt is None:
        out.append("Rating not possible: no reverberation time in some bands.")
    elif air:
        out.append(f"DnT,w = {rt.value} dB   C = {_signed(r.c)}   Ctr = {_signed(r.ctr)}")
    else:
        out.append(f"L'nT,w = {rt.value} dB   C_I = {_signed(r.ci)}   "
                   f"(L'nT,w + C_I = {rt.value + r.ci})")
    if rt is not None:
        out.append(f"Reference curve shifted {rt.shift:+d} dB; sum of unfavourable deviations "
                   f"{rt.unfavourable_sum:.1f} dB (maximum 32.0 dB)")
    if ev.requirement is not None:
        chk = ev.check
        sym = "at least" if air else "at most"
        margin = "" if chk.margin is None else f" ({chk.margin:+d} dB)"
        out.append(f"Requirement {ev.basis_label} {sym} {ev.requirement} dB: "
                   f"{chk.text or chk.status}{margin}")
    if ev.notes:
        out += ["", "Remarks:"] + [f"  - {n}" for n in ev.notes]
    return "\n".join(out)


def format_measurement_csv(ev: Evaluated) -> str:
    d = evaluated_to_dict(ev)
    if not ev.ok or "bands" not in d:
        raise CliError(f"no values to write: {ev.error}")
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    cols = {k: v for k, v in d["bands"].items() if v is not None}
    w.writerow(["band_hz", *cols])
    for i, hz in enumerate(d["bands_hz"]):
        w.writerow([hz, *("" if v[i] is None else v[i] for v in cols.values())])
    return buf.getvalue().rstrip("\n")


def _counts(evs) -> dict:
    c = {"complies": 0, "fails": 0, "inconclusive": 0, "no_result": 0, "none": 0}
    for e in evs:
        c[e.check.status] += 1
    c["errors"] = sum(1 for e in evs if not e.ok)
    return c


def building_to_dict(project, evs) -> dict:
    return {"schema_version": SCHEMA_VERSION, "project": project.name,
            "reverberation_time_used": project.rt_kind,
            "airborne_basis": AIRBORNE_BASES[project.airborne_basis],
            "impact_basis": IMPACT_BASES[project.impact_basis],
            "summary": _counts(evs),
            "equipment": [{"instrument": t, "serial": s, "used_for": list(roles)}
                          for t, s, roles in equipment_used(evs)],
            "measurements": [evaluated_to_dict(e) for e in evs]}


def format_building_text(project, evs) -> str:
    out = [f"Building: {project.name}   (reverberation time {project.rt_kind.upper()}, "
           f"airborne {AIRBORNE_BASES[project.airborne_basis]}, "
           f"impact {IMPACT_BASES[project.impact_basis]})", ""]
    rows = [("kind", "measurement", "value", "C / C_I", "Ctr", "requirement", "check")]
    for e in evs:
        r = e.result
        value = "-" if e.value is None else f"{e.value}"
        if e.kind == "airborne":
            c, ctr = (_signed(r.c), _signed(r.ctr)) if r and e.rating else ("-", "-")
        else:
            c, ctr = (_signed(r.ci), "") if r and e.rating else ("-", "")
        req = "" if e.requirement is None else f"{'>=' if e.kind == 'airborne' else '<='} {e.requirement}"
        chk = e.check
        check = "ERROR: " + (e.error or "") if not e.ok else (
            chk.text + ("" if chk.margin is None else f" ({chk.margin:+d} dB)") if req else "")
        rows.append((e.kind, e.name, value, c, ctr, req, check))
    widths = [max(len(str(r[i])) for r in rows) for i in range(len(rows[0]) - 1)]
    for r in rows:
        out.append("  ".join(str(r[i]).ljust(widths[i]) for i in range(len(widths))) + "  " + r[-1])
    c = _counts(evs)
    out += ["", f"{len(evs)} measurement(s): {c['complies']} comply, {c['fails']} do not comply, "
                f"{c['inconclusive']} not conclusive, {c['none']} without requirement, "
                f"{c['errors']} with errors"]
    for e in evs:
        if e.ok and e.notes:
            out.append(f"  remark - {e.name}: {'; '.join(e.notes)}")
    return "\n".join(out)


def format_building_csv(project, evs) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(["kind", "name", "source_or_tapping_room", "receiver_room", "comment",
                "single_number_db", "C_or_CI", "Ctr", "requirement_db", "check", "margin_db",
                "error"])
    for e in evs:
        r = e.result
        ok = r is not None and e.rating is not None
        c = (r.c if e.kind == "airborne" else r.ci) if ok else ""
        ctr = r.ctr if (ok and e.kind == "airborne") else ""
        chk = e.check
        w.writerow([e.kind, e.name, e.source_room, e.receiver_room, e.comment,
                    "" if e.value is None else e.value, c, ctr,
                    "" if e.requirement is None else e.requirement,
                    "" if chk.status == "none" else chk.status,
                    "" if chk.margin is None else chk.margin, e.error or ""])
    return buf.getvalue().rstrip("\n")


# ----------------------------------------------------------------------------- info
def describe_file(path) -> dict:
    """What an SVL file contains (level file or reverberation time file)."""
    path = Path(path)
    if not path.exists():
        raise CliError(f"file not found: {path}")
    errors = []
    try:
        f = read_svl(path)
        total = f.leq_total()
        from svl.parser import ISO_SLICE
        return {"file": path.name, "kind": "level", "instrument": f.device.label,
                "serial": f.device.serial, "software_code": f.device.firmware,
                "measured_at": f.measured_at.isoformat() if f.measured_at else None,
                "name_in_file": f.name, "duration_s": f.duration_s,
                "laeq_db": _num(round(f.laeq_total(), 2)),
                "lzeq_db_by_band_hz": {str(int(hz)): _num(round(v, 2)) for hz, v in
                                       zip(BANDS, total[ISO_SLICE])}}
    except SvlError as exc:
        errors.append(str(exc))
    try:
        r = read_rt(path)
        return {"file": path.name, "kind": "reverberation", "instrument": r.device.label,
                "serial": r.device.serial,
                "measured_at": r.measured_at.isoformat() if r.measured_at else None,
                "name_in_file": r.name, "records": len(r.levels), "step_s": 0.02,
                **{f"{k}_s_by_band_hz": {str(int(hz)): v for hz, v in
                                          zip(BANDS, _list(r.at(BANDS, k), 3))}
                   for k in RT_KINDS}}
    except SvlError as exc:
        errors.append(str(exc))
    reasons = "; ".join(dict.fromkeys(e.split(": ", 1)[-1] for e in errors))   # same reason once
    raise CliError(f"{path.name} is not a readable level or reverberation time file ({reasons})")


def format_info_text(d: dict) -> str:
    out = [f"{d['file']}: {d['kind']} file, {d['instrument']} #{d['serial']}, measured "
           f"{d['measured_at'] or 'unknown'}"]
    if d["kind"] == "level":
        out.append(f"  {d['duration_s']} s, LAeq {d['laeq_db']} dB")
        out.append("  LZeq per band [dB]: " + ", ".join(f"{k} Hz {v}" for k, v in
                                                       d["lzeq_db_by_band_hz"].items()))
    else:
        out.append(f"  {d['records']} records of {d['step_s']} s")
        for k in RT_KINDS:
            out.append(f"  {k.upper()} [s]: " + ", ".join(
                f"{b} Hz {'-' if v is None else v}" for b, v in d[f"{k}_s_by_band_hz"].items()))
    return "\n".join(out)


# ----------------------------------------------------------------------------- commands
def _emit(text: str, args) -> None:
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
        print(f"written: {args.output}", file=sys.stderr)
    else:
        print(text)


def _checked(files, role: str) -> list[str]:
    paths = [str(p) for p in files]
    for p in paths:
        if not Path(p).exists():
            raise CliError(f"file not found: {p}   ({role})")
    return paths


def _single(args) -> Evaluated:
    air = args.command == "airborne"
    try:
        if air:
            res = compute_airborne(_checked(args.source, "source"), _checked(args.receiver, "receiver"),
                                   _checked(args.background, "background"), _checked(args.rt, "rt"),
                                   args.rt_kind)
            ev = Evaluated("airborne", "airborne", "", "", res)
        else:
            res = compute_impact(_checked(args.tapping, "tapping"), _checked(args.background, "background"),
                                 _checked(args.rt, "rt"), args.rt_kind)
            ev = Evaluated("impact", "impact", "", "", res)
    except (SvlError, ValueError) as exc:
        raise CliError(str(exc)) from None
    ev.requirement, ev.basis = args.requirement, args.basis
    return ev


def cmd_measurement(args) -> int:
    ev = _single(args)
    if args.format == "json":
        text = json.dumps(evaluated_to_dict(ev), indent=2, ensure_ascii=False, allow_nan=False)
    elif args.format == "csv":
        text = format_measurement_csv(ev)
    else:
        text = format_measurement_text(ev)
    _emit(text, args)
    return 1 if args.strict and ev.check.status in ("fails", "inconclusive", "no_result") else 0


def cmd_building(args) -> int:
    path = Path(args.project)
    if not path.exists():
        raise CliError(f"project file not found: {path}")
    try:
        project = load_project(path)
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        raise CliError(f"{path.name} is not a readable building project: {exc}") from None
    evs = evaluate_project(project)
    if args.format == "json":
        text = json.dumps(building_to_dict(project, evs), indent=2, ensure_ascii=False, allow_nan=False)
    elif args.format == "csv":
        text = format_building_csv(project, evs)
    else:
        text = format_building_text(project, evs)
    _emit(text, args)
    if args.pdf:
        try:
            from export.pdf_report import ReportOptions, build_pdf_report
        except ImportError as exc:
            raise CliError(f"PDF export needs reportlab and matplotlib: {exc}") from None
        when = dt.date.fromisoformat(args.date) if args.date else None
        options = ReportOptions(per_measurement_pages=not args.no_measurement_pages,
                                per_band_tables=not args.no_band_tables,
                                room_photos=not args.no_photos, file_dates=not args.no_dates,
                                date=when)
        try:
            build_pdf_report(project, evs, args.pdf, options)
        except OSError as exc:
            raise CliError(f"could not write {args.pdf}: {exc}") from None
        print(f"report written: {args.pdf}", file=sys.stderr)
    bad = any((not e.ok) or e.check.status in ("fails", "inconclusive", "no_result") for e in evs)
    return 1 if args.strict and bad else 0


def cmd_info(args) -> int:
    infos = [describe_file(p) for p in args.files]
    if args.format == "json":
        text = json.dumps(infos[0] if len(infos) == 1 else infos, indent=2, ensure_ascii=False,
                          allow_nan=False)
    else:
        text = "\n".join(format_info_text(d) for d in infos)
    _emit(text, args)
    return 0


# ----------------------------------------------------------------------------- parser
def _common(p, formats=("text", "json", "csv")):
    p.add_argument("--format", choices=formats, default="text",
                   help="text (default), json (for programs) or csv")
    p.add_argument("--output", metavar="FILE", help="write the result to FILE instead of the screen")
    p.add_argument("--strict", action="store_true",
                   help="exit status 1 if a requirement is not met or not conclusive, or a "
                        "measurement could not be calculated")


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="python -m calc", description="Building acoustics from Svantek SVL files.",
        epilog="Several files after one option are averaged (levels: energy average per band; "
               "reverberation times: arithmetic mean). Details: docs/cli.md")
    sub = ap.add_subparsers(dest="command", required=True)

    a = sub.add_parser("airborne", help="DnT,w (C; Ctr) between a source and a receiving room")
    a.add_argument("--source", nargs="+", required=True, metavar="SVL", help="source room level file(s)")
    a.add_argument("--receiver", nargs="+", required=True, metavar="SVL", help="receiving room level file(s)")
    a.add_argument("--background", nargs="+", required=True, metavar="SVL", help="background level file(s) of the receiving room")
    a.add_argument("--rt", nargs="+", required=True, metavar="SVL", help="reverberation time file(s) of the receiving room")
    a.add_argument("--rt-kind", choices=RT_KINDS, default="t30", help="which reverberation time to use (default t30)")
    a.add_argument("--requirement", type=int, metavar="DB", help="required value in dB (airborne: at least)")
    a.add_argument("--basis", choices=list(AIRBORNE_BASES), default="w",
                   help="what the requirement is checked against: w = DnT,w (default), wc = DnT,w + C, wctr = DnT,w + Ctr")
    _common(a)

    i = sub.add_parser("impact", help="L'nT,w (C_I) in a receiving room")
    i.add_argument("--tapping", nargs="+", required=True, metavar="SVL", help="tapping machine level file(s) in the receiving room")
    i.add_argument("--background", nargs="+", required=True, metavar="SVL", help="background level file(s) of the receiving room")
    i.add_argument("--rt", nargs="+", required=True, metavar="SVL", help="reverberation time file(s) of the receiving room")
    i.add_argument("--rt-kind", choices=RT_KINDS, default="t30", help="which reverberation time to use (default t30)")
    i.add_argument("--requirement", type=int, metavar="DB", help="required value in dB (impact: at most)")
    i.add_argument("--basis", choices=list(IMPACT_BASES), default="w",
                   help="what the requirement is checked against: w = L'nT,w (default), wci = L'nT,w + C_I")
    _common(i)

    b = sub.add_parser("building", help="evaluate a building project file (.json)")
    b.add_argument("project", metavar="PROJECT.json")
    _common(b)
    b.add_argument("--pdf", metavar="FILE", help="also write the PDF report")
    b.add_argument("--no-measurement-pages", action="store_true", help="PDF: leave out the page per measurement")
    b.add_argument("--no-band-tables", action="store_true", help="PDF: leave out the values per band under the curves")
    b.add_argument("--no-photos", action="store_true", help="PDF: leave out the room photos")
    b.add_argument("--no-dates", action="store_true", help="PDF: leave out the date and time of the files")
    b.add_argument("--date", metavar="YYYY-MM-DD", help="PDF: report date (default today)")

    n = sub.add_parser("info", help="show what an SVL file contains")
    n.add_argument("files", nargs="+", metavar="SVL")
    n.add_argument("--format", choices=("text", "json"), default="text")
    n.add_argument("--output", metavar="FILE")
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command in ("airborne", "impact"):
            return cmd_measurement(args)
        if args.command == "building":
            return cmd_building(args)
        return cmd_info(args)
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except BrokenPipeError:                       # e.g. "... | head": stop quietly
        try:
            sys.stdout = open(os.devnull, "w")
        except OSError:
            pass
        return 0
