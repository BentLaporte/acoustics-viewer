"""A building: rooms, airborne and impact measurements between them (no GUI dependencies).

Model
  * Room       a named room with optional reverberation time files (needed when the room is
               a receiving room) and an optional own background measurement.
  * Airborne   source room + receiving room, level files of both rooms.
  * Impact     receiving room (+ optional tapping room), tapping machine level files.
  * Project    the building background (used by every room without its own background),
               the reverberation time kind, and the lists above.

Every measurement is evaluated on its own with the same calculations as the single
measurement pages; an error in one measurement never stops the others.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from .airborne import AirborneResult, compute_airborne
from .impact import ImpactResult, compute_impact

SCHEMA_VERSION = 2          # 2: measurements have a comment instead of a stored name


# Quantities a requirement can be checked against (chosen per building and measurement type)
AIRBORNE_BASES = {"w": "DnT,w", "wc": "DnT,w + C", "wctr": "DnT,w + Ctr"}
IMPACT_BASES = {"w": "L'nT,w", "wci": "L'nT,w + C_I"}


def natural_key(text: str):
    """Sort key that orders numbers numerically and puts numbers before letters,
    ignoring case: '0.2.02' < '0.10.01' < 'B.1.02' < 'B.G.02'."""
    parts = [t for t in re.split(r"(\d+)", text) if t != ""]
    return [(0, int(t), "") if t.isdigit() else (1, 0, t.casefold()) for t in parts]


def situation_name(kind: str, source_room: str, receiver_room: str, comment: str = "") -> str:
    """'airborne <source room> to <receiving room> (<comment>)' - the automatic name."""
    core = f"{kind} {source_room} to {receiver_room}" if source_room else \
        f"{kind} to {receiver_room}"
    comment = comment.strip()
    return f"{core} ({comment})" if comment else core


@dataclass
class Room:
    name: str
    rt_files: list[str] = field(default_factory=list)
    background_files: list[str] = field(default_factory=list)   # empty = building background


@dataclass
class AirborneSituation:
    source_room: str
    receiver_room: str
    source_files: list[str] = field(default_factory=list)
    receiver_files: list[str] = field(default_factory=list)
    comment: str = ""
    requirement: int | None = None      # dB: DnT,w (+ C / Ctr) must be at least this

    kind = "airborne"

    @property
    def base_name(self) -> str:
        return situation_name(self.kind, self.source_room, self.receiver_room, self.comment)


@dataclass
class ImpactSituation:
    receiver_room: str
    tapping_files: list[str] = field(default_factory=list)
    tapping_room: str = ""          # room where the tapping machine stood (informative)
    comment: str = ""               # e.g. the floor covering: tile, carpet...
    requirement: int | None = None  # dB: L'nT,w (+ C_I) must be at most this

    kind = "impact"

    @property
    def base_name(self) -> str:
        return situation_name(self.kind, self.tapping_room, self.receiver_room, self.comment)


@dataclass
class Project:
    name: str = "Building"
    background_files: list[str] = field(default_factory=list)
    rt_kind: str = "t30"
    airborne_basis: str = "w"       # what airborne requirements are checked against
    impact_basis: str = "w"         # what impact requirements are checked against
    rooms: list[Room] = field(default_factory=list)
    airborne: list[AirborneSituation] = field(default_factory=list)
    impact: list[ImpactSituation] = field(default_factory=list)

    def room(self, name: str) -> Room | None:
        return next((r for r in self.rooms if r.name == name), None)

    def sort_rooms(self) -> None:
        """Keep the rooms in natural alphabetical order (numbers as numbers)."""
        self.rooms.sort(key=lambda r: natural_key(r.name))

    def situation_names(self) -> list[str]:
        """Unique automatic names: airborne measurements first, then impact, entry order.
        Two measurements that would get the same name are told apart with ' #2', ' #3'..."""
        seen: dict[str, int] = {}
        names = []
        for s in [*self.airborne, *self.impact]:
            base = s.base_name
            seen[base] = seen.get(base, 0) + 1
            names.append(base if seen[base] == 1 else f"{base} #{seen[base]}")
        return names

    def background_for(self, room: Room) -> list[str]:
        return room.background_files or self.background_files


# ----------------------------------------------------------------------------- evaluation
@dataclass
class Check:
    """Outcome of comparing a measurement with its requirement."""
    status: str                    # none | no_result | complies | fails | inconclusive
    margin: int | None = None      # dB, positive = better than required

    @property
    def text(self) -> str:
        return {"none": "", "no_result": "no result", "complies": "Complies",
                "fails": "Does not comply", "inconclusive": "Not conclusive"}[self.status]


@dataclass
class Evaluated:
    kind: str                      # 'airborne' | 'impact'
    name: str
    source_room: str               # tapping room for impact (may be '')
    receiver_room: str
    result: AirborneResult | ImpactResult | None
    error: str | None = None
    comment: str = ""
    requirement: int | None = None
    basis: str = "w"

    @property
    def label(self) -> str:
        """Short text for charts: '<source> -> <receiving room> (<comment>)', without the type."""
        core = f"{self.source_room} \u2192 {self.receiver_room}" if self.source_room else \
            f"\u2192 {self.receiver_room}"
        return f"{core} ({self.comment})" if self.comment else core

    @property
    def ok(self) -> bool:
        return self.result is not None

    @property
    def rating(self):
        return None if self.result is None else self.result.rating

    @property
    def basis_label(self) -> str:
        return (AIRBORNE_BASES if self.kind == "airborne" else IMPACT_BASES)[self.basis]

    @property
    def assessed(self) -> int | None:
        """The value the requirement is checked against (DnT,w, DnT,w + C, ...)."""
        r = self.result
        if r is None or r.rating is None:
            return None
        w = r.rating.value
        if self.kind == "airborne":
            return w + {"w": 0, "wc": r.c, "wctr": r.ctr}[self.basis]
        return w + (r.ci if self.basis == "wci" else 0)

    def _limit_matters(self) -> bool:
        """Could bands that are only a limit value (close to the background) change the
        assessed value? Pass results are always safe (airborne DnT can only be higher, impact
        L'nT only lower than calculated); a failure is only sure if the limit bands do not
        matter."""
        r = self.result
        lim = r.status == "limit"
        if not lim.any():
            return False
        if self.basis == "w":
            return bool(np.any(r.rating.deviations[lim] > 0))
        if self.basis == "wci":                       # C_I sums 100 - 2500 Hz only
            return bool(lim[:15].any())
        return True                                   # C / Ctr use all 16 bands

    @property
    def check(self) -> Check:
        if self.requirement is None:
            return Check("none")
        value = self.assessed
        if value is None:
            return Check("no_result")
        margin = value - self.requirement if self.kind == "airborne" \
            else self.requirement - value
        if margin >= 0:
            return Check("complies", margin)
        return Check("inconclusive" if self._limit_matters() else "fails", margin)

    @property
    def curve(self) -> np.ndarray | None:
        """DnT (airborne) or L'nT (impact) per band, 100 ... 3150 Hz."""
        if self.result is None:
            return None
        return self.result.dnt if self.kind == "airborne" else self.result.lnt

    @property
    def value(self) -> int | None:
        return None if self.rating is None else self.rating.value

    @property
    def notes(self) -> list[str]:
        if self.error:
            return [self.error]
        r = self.result
        notes = []
        if r.rating is None:
            missing = ", ".join(str(int(f)) for f in r.bands[~np.isfinite(self.curve)])
            notes.append(f"no rating: reverberation time missing at {missing} Hz")
        if r.n_limit:
            side = "lower" if self.kind == "airborne" else "upper"
            notes.append(f"{r.n_limit} band(s) within 6 dB of background ({side} limit)")
        counts = [len(v) for k, v in r.names.items() if k != "background"]
        if any(c > 1 for c in counts):
            notes.append("averaged over several files")
        return notes


def _need(files, what: str):
    if not files:
        raise ValueError(f"no {what}")


def _evaluate_airborne(project: Project, s: AirborneSituation, name: str) -> Evaluated:
    try:
        recv = project.room(s.receiver_room)
        if recv is None:
            raise ValueError(f"receiving room '{s.receiver_room}' does not exist")
        if project.room(s.source_room) is None:
            raise ValueError(f"source room '{s.source_room}' does not exist")
        _need(s.source_files, "source room level files")
        _need(s.receiver_files, "receiving room level files")
        _need(recv.rt_files, f"reverberation time files for room '{recv.name}'")
        bg = project.background_for(recv)
        _need(bg, "background files (building or room)")
        res = compute_airborne(s.source_files, s.receiver_files, bg, recv.rt_files,
                               project.rt_kind)
        return Evaluated("airborne", name, s.source_room, s.receiver_room, res,
                         comment=s.comment, requirement=s.requirement,
                         basis=project.airborne_basis)
    except Exception as exc:                         # one bad measurement must not stop the rest
        return Evaluated("airborne", name, s.source_room, s.receiver_room, None,
                         _error_text(exc), s.comment, s.requirement, project.airborne_basis)


def _evaluate_impact(project: Project, s: ImpactSituation, name: str) -> Evaluated:
    try:
        recv = project.room(s.receiver_room)
        if recv is None:
            raise ValueError(f"receiving room '{s.receiver_room}' does not exist")
        _need(s.tapping_files, "tapping machine level files")
        _need(recv.rt_files, f"reverberation time files for room '{recv.name}'")
        bg = project.background_for(recv)
        _need(bg, "background files (building or room)")
        res = compute_impact(s.tapping_files, bg, recv.rt_files, project.rt_kind)
        return Evaluated("impact", name, s.tapping_room, s.receiver_room, res,
                         comment=s.comment, requirement=s.requirement,
                         basis=project.impact_basis)
    except Exception as exc:
        return Evaluated("impact", name, s.tapping_room, s.receiver_room, None,
                         _error_text(exc), s.comment, s.requirement, project.impact_basis)


def _error_text(exc: Exception) -> str:
    if isinstance(exc, FileNotFoundError):
        return f"file not found: {Path(str(exc.filename)).name}"
    return str(exc) or exc.__class__.__name__


def evaluate_project(project: Project) -> list[Evaluated]:
    """Evaluate all airborne measurements, then all impact measurements (entry order)."""
    names = project.situation_names()
    n = len(project.airborne)
    return ([_evaluate_airborne(project, s, names[i]) for i, s in enumerate(project.airborne)] +
            [_evaluate_impact(project, s, names[n + i]) for i, s in enumerate(project.impact)])


def airborne_details_files(project: Project, s: AirborneSituation) -> dict:
    """Files of a measurement in the roles of the single-measurement page."""
    recv = project.room(s.receiver_room)
    return {"source": s.source_files, "receiver": s.receiver_files,
            "background": project.background_for(recv) if recv else project.background_files,
            "rt": recv.rt_files if recv else []}


def impact_details_files(project: Project, s: ImpactSituation) -> dict:
    recv = project.room(s.receiver_room)
    return {"tapping": s.tapping_files,
            "background": project.background_for(recv) if recv else project.background_files,
            "rt": recv.rt_files if recv else []}


# ----------------------------------------------------------------------------- saving
def _rel(paths, base: Path) -> list[str]:
    out = []
    for p in paths:
        try:
            out.append(Path(os.path.relpath(p, base)).as_posix())
        except ValueError:                           # e.g. another drive on Windows
            out.append(str(p))
    return out


def _abs(paths, base: Path) -> list[str]:
    return [str(p) if Path(p).is_absolute() else str((base / p).resolve()) for p in paths]


def project_to_dict(project: Project, base: Path) -> dict:
    return {
        "schema": SCHEMA_VERSION,
        "name": project.name,
        "rt_kind": project.rt_kind,
        "airborne_basis": project.airborne_basis,
        "impact_basis": project.impact_basis,
        "background_files": _rel(project.background_files, base),
        "rooms": [{"name": r.name, "rt_files": _rel(r.rt_files, base),
                   "background_files": _rel(r.background_files, base)}
                  for r in project.rooms],
        "airborne": [{"source_room": s.source_room, "receiver_room": s.receiver_room,
                      "comment": s.comment, "requirement": s.requirement,
                      "source_files": _rel(s.source_files, base),
                      "receiver_files": _rel(s.receiver_files, base)}
                     for s in project.airborne],
        "impact": [{"receiver_room": s.receiver_room, "tapping_room": s.tapping_room,
                    "comment": s.comment, "requirement": s.requirement,
                    "tapping_files": _rel(s.tapping_files, base)}
                   for s in project.impact],
    }


def _legacy_comment(name: str) -> str:
    """Schema 1 stored a free name; a trailing '(...)' in it becomes the comment."""
    m = re.search(r"\(([^()]*)\)\s*$", name or "")
    return m.group(1).strip() if m else ""


def project_from_dict(d: dict, base: Path) -> Project:
    schema = d.get("schema")
    if schema not in (1, SCHEMA_VERSION):
        raise ValueError(f"unsupported project file version: {schema!r}")

    def comment(s: dict) -> str:
        return s["comment"] if schema == SCHEMA_VERSION else _legacy_comment(s.get("name", ""))

    def basis(key: str, allowed: dict) -> str:
        return d.get(key) if d.get(key) in allowed else "w"

    project = Project(
        name=d.get("name", "Building"),
        rt_kind=d.get("rt_kind", "t30"),
        airborne_basis=basis("airborne_basis", AIRBORNE_BASES),
        impact_basis=basis("impact_basis", IMPACT_BASES),
        background_files=_abs(d.get("background_files", []), base),
        rooms=[Room(r["name"], _abs(r.get("rt_files", []), base),
                    _abs(r.get("background_files", []), base)) for r in d.get("rooms", [])],
        airborne=[AirborneSituation(s["source_room"], s["receiver_room"],
                                    _abs(s.get("source_files", []), base),
                                    _abs(s.get("receiver_files", []), base), comment(s),
                                    s.get("requirement"))
                  for s in d.get("airborne", [])],
        impact=[ImpactSituation(s["receiver_room"], _abs(s.get("tapping_files", []), base),
                                s.get("tapping_room", ""), comment(s), s.get("requirement"))
                for s in d.get("impact", [])])
    project.sort_rooms()
    return project


def save_project(project: Project, path) -> None:
    """Write the project; file paths are stored relative to the project file when possible,
    so the project keeps working when the whole folder is moved."""
    path = Path(path).resolve()
    project.sort_rooms()
    path.write_text(json.dumps(project_to_dict(project, path.parent), indent=2,
                               ensure_ascii=False), encoding="utf-8")


def load_project(path) -> Project:
    path = Path(path).resolve()
    return project_from_dict(json.loads(path.read_text(encoding="utf-8")), path.parent)
