"""Add or edit an installation noise measurement of a building.

The level files are listed with their time window (the operating cycle of the installation).
The level history of the selected file is drawn; the window is chosen by dragging the shaded
region or by typing the start and end second. The result is calculated while you edit, with the
reverberation time and background of the room, so the effect of a window is visible at once.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from calc.building import InstallationSituation, Project, evaluate_situation, situation_name
from calc.installation import Recording
from svl.parser import SvlError, SvlFile, read_svl

from .building_dialogs import RequirementSpin, RoomCombo, _warn
from .level_history import LevelHistory, window_text  # noqa: F401  (also used by tests)

LE = chr(0x2264)                          # less than or equal sign
QUANTITY_TEXT = {"laeq": "LAeq,nT  -  stationary installation (ventilation, heat pump, pump)",
                 "lafmax": "LAFmax,nT  -  transient installation (toilet flush, lift, tap)"}
METHOD_TEXT = {"integrated": "Integrated: moving microphone through the room",
               "positions": "Positions: corner + two in the reverberant field (3 files, corner first)"}


class InstallationDialog(QtWidgets.QDialog):
    """Rooms, comment, quantity, method, requirement and the level files with their windows.
    The name is generated: 'installation <source room> to <room> (<comment>)'."""

    def __init__(self, project: Project, settings, taken_names,
                 situation: InstallationSituation | None = None, parent=None):
        super().__init__(parent)
        self.project, self.settings, self.taken = project, settings, set(taken_names)
        self.files: dict[Path, SvlFile | str] = {}       # read once: file or error text
        self.recordings: list[Recording] = list(situation.recordings) if situation else []
        self.setWindowTitle("Installation noise measurement")
        self.setMinimumWidth(780)
        lay = QtWidgets.QVBoxLayout(self)

        form = QtWidgets.QFormLayout()
        self.source = RoomCombo(project, settings, "Installation in room", allow_empty=True)
        self.receiver = RoomCombo(project, settings, "Measured in room")
        self.source.combo.setToolTip("Where the installation is (optional; leave empty when it "
                                     "is not in a room, e.g. a unit on the roof)")
        form.addRow("Measured in room:", self.receiver)
        form.addRow("Installation in room:", self.source)
        self.comment = QtWidgets.QLineEdit(situation.comment if situation else "")
        self.comment.setPlaceholderText("the installation, e.g. heat pump, ventilation position 3")
        form.addRow("Comment:", self.comment)
        self.quantity = QtWidgets.QComboBox()
        for key, text in QUANTITY_TEXT.items():
            self.quantity.addItem(text, key)
        self.method = QtWidgets.QComboBox()
        for key, text in METHOD_TEXT.items():
            self.method.addItem(text, key)
        form.addRow("Quantity:", self.quantity)
        form.addRow("Method:", self.method)
        q = situation.quantity if situation else "laeq"
        self.quantity.setCurrentIndex(max(0, self.quantity.findData(q)))
        self.method.setCurrentIndex(max(0, self.method.findData(
            situation.method if situation else "integrated")))
        self.requirement = RequirementSpin(project, "installation",
                                           situation.requirement if situation else None, q)
        form.addRow("Requirement:", self.requirement)
        lay.addLayout(form)
        self.preview = QtWidgets.QLabel()
        self.preview.setStyleSheet("padding: 4px; background: #f4f6f7; border: 1px solid #d5d8dc;")
        self.preview.setWordWrap(True)
        lay.addWidget(self.preview)

        box = QtWidgets.QGroupBox("Level files and their operating cycle")
        bl = QtWidgets.QVBoxLayout(box)
        self.table = QtWidgets.QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["File", "Time window", "Duration", "LAeq", "LAFmax"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        head = self.table.horizontalHeader()
        head.setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        head.setSectionResizeMode(0, QtWidgets.QHeaderView.Stretch)
        self.table.setMaximumHeight(130)
        self.table.itemSelectionChanged.connect(self.show_selected)
        bl.addWidget(self.table)
        row = QtWidgets.QHBoxLayout()
        for text, slot in (("Add files...", self.add_files), ("Remove", self.remove_file),
                           ("Move up", lambda: self.move(-1)), ("Move down", lambda: self.move(1))):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(lambda _=False, f=slot: f())
            row.addWidget(b)
        row.addStretch(1)
        bl.addLayout(row)
        self.history = LevelHistory()
        self.history.window_changed.connect(self.window_changed)
        bl.addWidget(self.history, 1)
        lay.addWidget(box, 1)

        self.result = QtWidgets.QLabel()
        self.result.setTextFormat(QtCore.Qt.RichText)
        self.result.setWordWrap(True)
        self.result.setStyleSheet("padding: 5px; background: #f4f6f7; border: 1px solid #d5d8dc;")
        lay.addWidget(self.result)
        note = QtWidgets.QLabel("Reverberation time and background come from the room where it "
                                "is measured (and the building). The background is only "
                                "checked (6 dB), never subtracted (ISO 10052).")
        note.setWordWrap(True)
        note.setStyleSheet("color: #666666;")
        lay.addWidget(note)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok |
                                             QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

        if situation:
            self.source.set_value(situation.source_room)
            self.receiver.set_value(situation.receiver_room)
        for combo in (self.source, self.receiver):
            combo.combo.currentIndexChanged.connect(self.update_all)
            combo.new_button.clicked.connect(self.refresh_combos)
        self.comment.textChanged.connect(self.update_preview)
        self.quantity.currentIndexChanged.connect(self.quantity_changed)
        self.method.currentIndexChanged.connect(self.update_result)
        self.fill_table()
        if self.recordings:
            self.table.selectRow(0)
        self.update_all()

    # ---- files ----------------------------------------------------------------------------
    def read(self, path: Path) -> SvlFile | str:
        """The file (read once), or why it cannot be used."""
        if path not in self.files:
            try:
                self.files[path] = read_svl(path)
            except FileNotFoundError:
                self.files[path] = "file not found"
            except (SvlError, OSError) as exc:
                self.files[path] = str(exc)
        return self.files[path]

    def fill_table(self, select: int | None = None):
        self.table.blockSignals(True)
        self.table.setRowCount(len(self.recordings))
        for i, rec in enumerate(self.recordings):
            f = self.read(rec.path)
            cells = [rec.path.name, "", "", "", ""]
            if isinstance(f, str):
                cells[1] = f
            else:
                cells[1] = window_text(rec, f.duration_s)
                try:
                    seconds = len(f.window(rec.start, rec.end))
                    cells[2] = f"{seconds} s"
                    cells[3] = f"{f.laeq(rec.start, rec.end):.1f}"
                    cells[4] = f"{f.lafmax(rec.start, rec.end):.1f}"
                except (ValueError, SvlError) as exc:
                    cells[1] = str(exc)
            for j, text in enumerate(cells):
                item = QtWidgets.QTableWidgetItem(text)
                item.setToolTip(str(rec.path) if j == 0 else text)
                if j:
                    item.setTextAlignment(QtCore.Qt.AlignCenter)
                if isinstance(f, str):
                    item.setForeground(QtGui.QColor("#c0392b"))
                self.table.setItem(i, j, item)
        self.table.blockSignals(False)
        if select is not None and 0 <= select < len(self.recordings):
            self.table.selectRow(select)

    def selected(self) -> int:
        rows = self.table.selectionModel().selectedRows()
        return rows[0].row() if rows else -1

    def show_selected(self):
        i = self.selected()
        if i < 0:
            self.history.show_file(None)
            return
        rec = self.recordings[i]
        f = self.read(rec.path)
        if isinstance(f, str):
            self.history.show_file(None, error=f"{rec.path.name}: {f}")
        else:
            self.history.show_file(f, rec)

    def add_files(self):
        start = self.settings.value("last_dir", "")
        chosen, _ = QtWidgets.QFileDialog.getOpenFileNames(
            self, "Select level file(s) of the installation", start, "Svantek files (*.SVL *.svl)")
        if not chosen:
            return
        self.settings.setValue("last_dir", str(Path(chosen[0]).parent))
        self.recordings += [Recording(Path(p)) for p in chosen]
        self.fill_table(select=len(self.recordings) - len(chosen))
        self.update_result()

    def remove_file(self):
        i = self.selected()
        if i < 0:
            return
        del self.recordings[i]
        self.fill_table(select=min(i, len(self.recordings) - 1))
        if not self.recordings:
            self.history.show_file(None)
        self.update_result()

    def move(self, step: int):
        i = self.selected()
        j = i + step
        if i < 0 or not 0 <= j < len(self.recordings):
            return
        self.recordings[i], self.recordings[j] = self.recordings[j], self.recordings[i]
        self.fill_table(select=j)
        self.update_result()

    def window_changed(self, start: int, end):
        i = self.selected()
        if i < 0:
            return
        self.recordings[i] = replace(self.recordings[i], start=start, end=end)
        self.fill_table()
        self.table.blockSignals(True)
        self.table.selectRow(i)
        self.table.blockSignals(False)
        self.update_result()

    # ---- name and result ------------------------------------------------------------------
    def name(self) -> str:
        return situation_name("installation", self.source.value(), self.receiver.value(),
                              self.comment.text())

    def update_preview(self, *_):
        self.preview.setText(f"Name: <b>{self.name()}</b>")

    def quantity_changed(self):
        self.requirement.set_quantity(self.quantity.currentData())
        self.update_result()

    def update_all(self, *_):
        self.update_preview()
        self.update_result()

    def refresh_combos(self):
        """A room created in one drop-down must show up in the other."""
        for combo in (self.source, self.receiver):
            combo.fill()
        self.update_all()

    def update_result(self, *_):
        """Calculate with the room's reverberation time and background, as the building will."""
        if not self.receiver.value():
            self.result.setText("Choose the room where it is measured to see the result.")
            return
        if not self.recordings:
            self.result.setText("Add the level file(s) to see the result.")
            return
        ev = evaluate_situation(self.project, self.situation())
        if not ev.ok:
            self.result.setText(f"<span style='color:#c0392b'>Not possible yet: {ev.error}</span>")
            return
        r = ev.result
        text = (f"<b>{r.symbol} = {r.value} dB</b> &nbsp; (measured {r.level:.1f} dB, "
                f"k = {r.k:.2f} dB")
        text += ")" if r.background is None else f", background LAeq {r.background:.1f} dB)"
        chk = ev.check
        if chk.status != "none":
            color = {"complies": "#1e8449", "tolerance": "#6b8e23",
                     "fails": "#c0392b"}.get(chk.status, "#b9770e")
            text += (f" &nbsp; <b style='color:{color}'>{chk.text}</b> "
                     f"({LE} {ev.requirement} dB)")
        if ev.notes:
            text += "<br><span style='color:#666666'>" + "; ".join(ev.notes) + "</span>"
        self.result.setText(text)

    # ---- result of the dialog ---------------------------------------------------------------
    def accept(self):
        if not self.receiver.value():
            return _warn(self, "Choose the room where it is measured (create it with "
                               "'New room...').")
        if self.source.value() == self.receiver.value():
            return _warn(self, "The installation room and the measured room are the same: leave "
                               "'Installation in room' empty when the installation is in the "
                               "measured room itself.")
        if not self.recordings:
            return _warn(self, "Add at least one level file.")
        if self.method.currentData() == "positions" and len(self.recordings) != 3:
            return _warn(self, "The position method needs exactly three files: the corner "
                               "position first, then two in the reverberant field. Choose the "
                               "integrated method for another number of files.")
        if self.name() in self.taken:
            return _warn(self, f"There is already a measurement called '{self.name()}'. "
                               "Add a comment to tell them apart (e.g. the installation or its "
                               "setting).")
        super().accept()

    def situation(self) -> InstallationSituation:
        return InstallationSituation(self.receiver.value(), list(self.recordings),
                                     self.source.value(), self.comment.text().strip(),
                                     self.requirement.value(), self.quantity.currentData(),
                                     self.method.currentData())
