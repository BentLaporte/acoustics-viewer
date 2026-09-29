"""Dialogs to add and edit rooms and measurements of a building."""
from __future__ import annotations

from PySide6 import QtCore, QtWidgets

from calc.building import (AIRBORNE_BASES, IMPACT_BASES, AirborneSituation, ImpactSituation,
                           Project, Room, situation_name)

from .widgets import FileRow


def _warn(parent, text):
    QtWidgets.QMessageBox.warning(parent, "Check the input", text)


class RoomDialog(QtWidgets.QDialog):
    """Name, reverberation time files and an optional own background of a room."""

    def __init__(self, settings, taken_names, room: Room | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Room" if room is None else f"Room {room.name}")
        self.setMinimumWidth(650)
        self.taken = set(taken_names)
        lay = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        self.name = QtWidgets.QLineEdit(room.name if room else "")
        self.name.setPlaceholderText("e.g. Living room 2.01")
        form.addRow("Name:", self.name)
        lay.addLayout(form)
        self.rt = FileRow("Reverberation time", settings)
        self.rt.set_paths(room.rt_files if room else [], notify=False)
        lay.addWidget(self.rt)
        hint = QtWidgets.QLabel("The reverberation time is needed when this room is a receiving "
                                "room. Several decays are averaged.")
        hint.setStyleSheet("color: #666666;")
        lay.addWidget(hint)
        self.own_bg = QtWidgets.QCheckBox("This room has its own background measurement "
                                          "(otherwise the building background is used)")
        lay.addWidget(self.own_bg)
        self.bg = FileRow("Own background", settings)
        self.bg.set_paths(room.background_files if room else [], notify=False)
        self.own_bg.setChecked(bool(room and room.background_files))
        self.bg.setEnabled(self.own_bg.isChecked())
        self.own_bg.toggled.connect(self.bg.setEnabled)
        lay.addWidget(self.bg)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok |
                                             QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def accept(self):
        name = self.name.text().strip()
        if not name:
            return _warn(self, "Give the room a name.")
        if name in self.taken:
            return _warn(self, f"There is already a room called '{name}'.")
        super().accept()

    def room(self) -> Room:
        return Room(self.name.text().strip(), self.rt.paths(),
                    self.bg.paths() if self.own_bg.isChecked() else [])


class RoomCombo(QtWidgets.QWidget):
    """Drop-down with the rooms of the project and a button to create a new room."""

    def __init__(self, project: Project, settings, label: str, allow_empty=False):
        super().__init__()
        self.project, self.settings = project, settings
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.combo = QtWidgets.QComboBox()
        self.combo.setMinimumWidth(260)
        self.allow_empty = allow_empty
        self.new_button = QtWidgets.QPushButton("New room...")
        self.new_button.clicked.connect(self.new_room)
        lay.addWidget(self.combo)
        lay.addWidget(self.new_button)
        lay.addStretch(1)
        self.fill()

    def fill(self, select: str | None = None):
        current = select if select is not None else self.combo.currentData()
        self.combo.clear()
        if self.allow_empty:
            self.combo.addItem("(not specified)", "")
        for r in self.project.rooms:
            self.combo.addItem(r.name, r.name)
        i = self.combo.findData(current)
        if i >= 0:
            self.combo.setCurrentIndex(i)

    def new_room(self):
        dlg = RoomDialog(self.settings, [r.name for r in self.project.rooms], parent=self)
        if dlg.exec():
            room = dlg.room()
            self.project.rooms.append(room)
            self.project.sort_rooms()
            self.fill(select=room.name)

    def value(self) -> str:
        return self.combo.currentData() or ""

    def set_value(self, name: str):
        i = self.combo.findData(name)
        if i >= 0:
            self.combo.setCurrentIndex(i)


class RequirementSpin(QtWidgets.QWidget):
    """'DnT,w >= [ 54 ] dB' - 0 means: no requirement."""

    def __init__(self, project: Project, kind: str, value: int | None = None):
        super().__init__()
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        if kind == "airborne":
            text, sym = AIRBORNE_BASES[project.airborne_basis], "\u2265"
        else:
            text, sym = IMPACT_BASES[project.impact_basis], "\u2264"
        lay.addWidget(QtWidgets.QLabel(f"{text} {sym}"))
        self.spin = QtWidgets.QSpinBox()
        self.spin.setRange(0, 120)
        self.spin.setSuffix(" dB")
        self.spin.setSpecialValueText("no requirement")
        self.spin.setMinimumWidth(130)
        self.spin.setValue(value or 0)
        lay.addWidget(self.spin)
        lay.addStretch(1)

    def value(self) -> int | None:
        return self.spin.value() or None


class RequirementsDialog(QtWidgets.QDialog):
    """Set the requirement of several measurements at once."""

    def __init__(self, project: Project, n_airborne: int, n_impact: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set requirement")
        self.setMinimumWidth(460)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(QtWidgets.QLabel("Give the selected measurements the same requirement "
                                       "(0 = remove the requirement)."))
        self.rows = {}
        for kind, n in (("airborne", n_airborne), ("impact", n_impact)):
            if not n:
                continue
            row = QtWidgets.QHBoxLayout()
            check = QtWidgets.QCheckBox(f"{n} {kind}:")
            check.setChecked(True)
            spin = RequirementSpin(project, kind)
            check.toggled.connect(spin.setEnabled)
            row.addWidget(check)
            row.addWidget(spin, 1)
            lay.addLayout(row)
            self.rows[kind] = (check, spin)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok |
                                             QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def values(self) -> dict:
        """kind -> requirement (None = remove) for the kinds that are ticked."""
        return {k: spin.value() for k, (check, spin) in self.rows.items() if check.isChecked()}


class SituationDialog(QtWidgets.QDialog):
    """Add or edit an airborne or an impact measurement.

    The name is generated: '<type> <source room> to <receiving room> (<comment>)'.
    """

    def __init__(self, kind: str, project: Project, settings, taken_names,
                 situation=None, parent=None):
        super().__init__(parent)
        assert kind in ("airborne", "impact")
        self.kind, self.project, self.taken = kind, project, set(taken_names)
        self.setWindowTitle(("Airborne" if kind == "airborne" else "Impact") + " measurement")
        self.setMinimumWidth(720)
        lay = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        if kind == "airborne":
            self.source = RoomCombo(project, settings, "Source room")
            self.receiver = RoomCombo(project, settings, "Receiving room")
            form.addRow("Source room:", self.source)
            form.addRow("Receiving room:", self.receiver)
            self.rooms = (self.source, self.receiver)
        else:
            self.source = RoomCombo(project, settings, "Tapping room", allow_empty=True)
            self.receiver = RoomCombo(project, settings, "Receiving room")
            form.addRow("Tapping machine in room:", self.source)
            form.addRow("Receiving room:", self.receiver)
            self.rooms = (self.source, self.receiver)
        self.comment = QtWidgets.QLineEdit(situation.comment if situation else "")
        self.comment.setPlaceholderText("optional, e.g. tile, carpet, door open, position 2")
        form.addRow("Comment:", self.comment)
        self.requirement = RequirementSpin(project, kind,
                                           situation.requirement if situation else None)
        form.addRow("Requirement:", self.requirement)
        lay.addLayout(form)
        self.preview = QtWidgets.QLabel()
        self.preview.setStyleSheet("padding: 4px; background: #f4f6f7; border: 1px solid #d5d8dc;")
        self.preview.setWordWrap(True)
        lay.addWidget(self.preview)
        if kind == "airborne":
            self.f1 = FileRow("Source room levels", settings)
            self.f2 = FileRow("Receiving room levels", settings)
            files = (self.f1, self.f2)
            if situation:
                self.f1.set_paths(situation.source_files, notify=False)
                self.f2.set_paths(situation.receiver_files, notify=False)
                self.source.set_value(situation.source_room)
                self.receiver.set_value(situation.receiver_room)
        else:
            self.f1 = FileRow("Tapping machine levels", settings)
            files = (self.f1,)
            if situation:
                self.f1.set_paths(situation.tapping_files, notify=False)
                self.source.set_value(situation.tapping_room)
                self.receiver.set_value(situation.receiver_room)
        for row in files:
            lay.addWidget(row)
        note = QtWidgets.QLabel("Reverberation time and background come from the receiving room "
                                "(and the building). Several files per row are averaged.")
        note.setStyleSheet("color: #666666;")
        lay.addWidget(note)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok |
                                             QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        for combo in self.rooms:
            combo.combo.currentIndexChanged.connect(self.update_preview)
            combo.new_button.clicked.connect(self.refresh_combos)
        self.comment.textChanged.connect(self.update_preview)
        self.update_preview()

    def name(self) -> str:
        return situation_name(self.kind, self.source.value(), self.receiver.value(),
                              self.comment.text())

    def update_preview(self, *_):
        self.preview.setText(f"Name: <b>{self.name()}</b>")

    def refresh_combos(self):
        """A room created in one drop-down must show up in the other."""
        for combo in self.rooms:
            combo.fill()
        self.update_preview()

    def accept(self):
        if not self.receiver.value():
            return _warn(self, "Choose the receiving room (create it with 'New room...').")
        if self.kind == "airborne":
            if not self.source.value():
                return _warn(self, "Choose the source room (create it with 'New room...').")
            if self.source.value() == self.receiver.value():
                return _warn(self, "Source room and receiving room must be different rooms.")
        if self.name() in self.taken:
            return _warn(self, f"There is already a measurement called '{self.name()}'.\n"
                               "Add a comment to tell them apart (e.g. the floor covering "
                               "or the position).")
        super().accept()

    def situation(self):
        comment = self.comment.text().strip()
        if self.kind == "airborne":
            return AirborneSituation(self.source.value(), self.receiver.value(),
                                     self.f1.paths(), self.f2.paths(), comment,
                                     self.requirement.value())
        return ImpactSituation(self.receiver.value(), self.f1.paths(), self.source.value(),
                               comment, self.requirement.value())
