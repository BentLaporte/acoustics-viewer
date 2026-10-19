"""Dialogs to add and edit rooms and measurements of a building."""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from PySide6 import QtCore, QtGui, QtWidgets

from calc.building import (AIRBORNE_BASES, IMPACT_BASES, INSTALLATION_QUANTITIES,
                           AirborneSituation, ImpactSituation, Photo, Project, ReportInfo, Room,
                           situation_name)

from export.report_options import GROUPS, TOGGLES, ReportOptions

from .thumbs import IMAGE_FILTER, thumbnail
from .widgets import FileRow


def _warn(parent, text):
    QtWidgets.QMessageBox.warning(parent, "Check the input", text)


class RoomDialog(QtWidgets.QDialog):
    """Name, reverberation time files and an optional own background of a room."""

    def __init__(self, settings, taken_names, room: Room | None = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Room" if room is None else f"Room {room.name}")
        self.setMinimumWidth(650)
        self.setMinimumHeight(560)
        self.taken = set(taken_names)
        lay = QtWidgets.QVBoxLayout(self)
        form = QtWidgets.QFormLayout()
        self.name = QtWidgets.QLineEdit(room.name if room else "")
        self.name.setPlaceholderText("e.g. Living room 2.01")
        form.addRow("Name:", self.name)
        # volume and bedroom decide the NBN S 01-400 in-situ tolerance (calc/nbn.py)
        self.volume = QtWidgets.QDoubleSpinBox()
        self.volume.setRange(0, 100000)
        self.volume.setDecimals(1)
        self.volume.setSuffix(" m\u00b3")
        self.volume.setSpecialValueText("unknown")          # 0 shows as 'unknown'
        self.volume.setValue(room.volume if room and room.volume else 0)
        self.bedroom = QtWidgets.QCheckBox("Bedroom")
        self.bedroom.setChecked(bool(room and room.bedroom))
        vrow = QtWidgets.QHBoxLayout()
        vrow.addWidget(self.volume)
        vrow.addWidget(self.bedroom)
        vrow.addStretch(1)
        form.addRow("Volume:", vrow)
        hint = QtWidgets.QLabel("Receiving rooms under 25 m\u00b3 that are not bedrooms get the "
                                "larger NBN tolerance (4 dB instead of 2 dB; installation noise "
                                "3 dB instead of 1 dB). Unknown volume: the normal tolerance.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666666;")
        form.addRow("", hint)
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

        box = QtWidgets.QGroupBox("Photos (they appear in the report)")
        bl = QtWidgets.QVBoxLayout(box)
        self.settings = settings
        self.photos = QtWidgets.QListWidget()
        self.photos.setIconSize(QtCore.QSize(96, 72))
        self.photos.setMinimumHeight(180)
        self.photos.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.photos.itemDoubleClicked.connect(lambda _item: self.edit_caption())
        bl.addWidget(self.photos)
        row = QtWidgets.QHBoxLayout()
        for text, slot in (("Add photos...", self.add_photos), ("Caption...", self.edit_caption),
                           ("Move up", lambda: self.move_photo(-1)),
                           ("Move down", lambda: self.move_photo(1)),
                           ("Remove", self.remove_photo)):
            b = QtWidgets.QPushButton(text)
            b.clicked.connect(lambda _=False, f=slot: f())
            row.addWidget(b)
        row.addStretch(1)
        bl.addLayout(row)
        hint = QtWidgets.QLabel("The first photo is the main picture of the room. Double-click "
                                "a photo to give it a caption.")
        hint.setStyleSheet("color: #666666;")
        bl.addWidget(hint)
        lay.addWidget(box)
        for ph in (room.photos if room else []):
            self.add_item(ph.path, ph.caption)

        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok |
                                             QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    # ---- photos -----------------------------------------------------------------------
    def add_item(self, path: str, caption: str = "") -> QtWidgets.QListWidgetItem:
        item = QtWidgets.QListWidgetItem()
        item.setData(QtCore.Qt.UserRole, path)
        item.setData(QtCore.Qt.UserRole + 1, caption)
        pix = thumbnail(path)
        if pix is not None:
            item.setIcon(QtGui.QIcon(pix))
        self.photos.addItem(item)
        self.refresh_item(item)
        return item

    @staticmethod
    def refresh_item(item):
        path, caption = item.data(QtCore.Qt.UserRole), item.data(QtCore.Qt.UserRole + 1)
        item.setText(caption or Path(path).name)
        item.setToolTip(path)
        missing = not Path(path).exists()
        item.setForeground(QtGui.QColor("#c0392b" if missing else
                                        "#1b2631" if caption else "#7f8c8d"))
        if missing:
            item.setToolTip(f"File not found: {path}")

    def add_photos(self):
        start = self.settings.value("photo_dir", "")
        chosen, _ = QtWidgets.QFileDialog.getOpenFileNames(self, "Add photos", start, IMAGE_FILTER)
        if not chosen:
            return
        self.settings.setValue("photo_dir", str(Path(chosen[0]).parent))
        have = {self.photos.item(i).data(QtCore.Qt.UserRole) for i in range(self.photos.count())}
        unreadable = []
        for path in chosen:
            if path in have:
                continue
            if thumbnail(path) is None:
                unreadable.append(Path(path).name)
                continue
            self.add_item(path)
            have.add(path)
        if unreadable:
            _warn(self, "These files could not be read as pictures (supported: JPEG, PNG, BMP, "
                        "TIFF, WebP):\n" + "\n".join(unreadable))

    def edit_caption(self):
        item = self.photos.currentItem()
        if item is None:
            return
        text, ok = QtWidgets.QInputDialog.getText(
            self, "Caption", "Caption of the photo (empty = none):",
            text=item.data(QtCore.Qt.UserRole + 1))
        if ok:
            item.setData(QtCore.Qt.UserRole + 1, text.strip())
            self.refresh_item(item)

    def move_photo(self, step: int):
        row = self.photos.currentRow()
        new = row + step
        if row < 0 or not 0 <= new < self.photos.count():
            return
        item = self.photos.takeItem(row)
        self.photos.insertItem(new, item)
        self.photos.setCurrentRow(new)

    def remove_photo(self):
        row = self.photos.currentRow()
        if row >= 0:
            self.photos.takeItem(row)

    def accept(self):
        name = self.name.text().strip()
        if not name:
            return _warn(self, "Give the room a name.")
        if name in self.taken:
            return _warn(self, f"There is already a room called '{name}'.")
        super().accept()

    def room(self) -> Room:
        photos = [Photo(self.photos.item(i).data(QtCore.Qt.UserRole),
                        self.photos.item(i).data(QtCore.Qt.UserRole + 1))
                  for i in range(self.photos.count())]
        return Room(self.name.text().strip(), self.rt.paths(),
                    self.bg.paths() if self.own_bg.isChecked() else [], photos,
                    self.volume.value() or None, self.bedroom.isChecked())


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
    """'DnT,w >= [ 54 ] dB' - 0 means: no requirement.

    Installation noise: the quantity is chosen per measurement ('laeq' / 'lafmax', None = both
    when several measurements get the same requirement); set_quantity() updates the label."""

    def __init__(self, project: Project, kind: str, value: int | None = None,
                 quantity: str | None = None):
        super().__init__()
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        if kind == "airborne":
            text, sym = AIRBORNE_BASES[project.airborne_basis], "\u2265"
        elif kind == "impact":
            text, sym = IMPACT_BASES[project.impact_basis], "\u2264"
        else:
            text, sym = self.quantity_text(quantity), "\u2264"
        self.label = QtWidgets.QLabel(f"{text} {sym}")
        lay.addWidget(self.label)
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

    @staticmethod
    def quantity_text(quantity: str | None) -> str:
        return INSTALLATION_QUANTITIES[quantity] if quantity else \
            " / ".join(INSTALLATION_QUANTITIES.values())

    def set_quantity(self, quantity: str):
        self.label.setText(f"{self.quantity_text(quantity)} \u2264")


class RequirementsDialog(QtWidgets.QDialog):
    """Set the requirement of several measurements at once."""

    def __init__(self, project: Project, n_airborne: int, n_impact: int, n_installation: int = 0,
                 parent=None):
        super().__init__(parent)
        self.setWindowTitle("Set requirement")
        self.setMinimumWidth(460)
        lay = QtWidgets.QVBoxLayout(self)
        lay.addWidget(QtWidgets.QLabel("Give the selected measurements the same requirement "
                                       "(0 = remove the requirement)."))
        self.rows = {}
        for kind, n in (("airborne", n_airborne), ("impact", n_impact),
                        ("installation", n_installation)):
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


class ReportDialog(QtWidgets.QDialog):
    """Information for the first page of the PDF report and what to put in it.

    The switches come from export.report_options.TOGGLES (one checkbox each, grouped); their
    values are remembered in the project. To add a switch to the report, add it there."""

    def __init__(self, project: Project, n_included: int, n_left_out: int, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Export PDF report")
        self.setMinimumWidth(560)
        lay = QtWidgets.QVBoxLayout(self)
        info = project.report
        form = QtWidgets.QFormLayout()
        self.client = QtWidgets.QLineEdit(info.client)
        self.location = QtWidgets.QLineEdit(info.location)
        self.author = QtWidgets.QLineEdit(info.author)
        self.date = QtWidgets.QDateEdit(QtCore.QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("d MMMM yyyy")
        self.remarks = QtWidgets.QPlainTextEdit(info.remarks)
        self.remarks.setPlaceholderText("Optional: conditions during the measurements, "
                                        "measurement method, remarks for the reader...")
        self.remarks.setFixedHeight(90)
        self.equipment = QtWidgets.QPlainTextEdit(info.equipment)
        self.equipment.setPlaceholderText("Optional, one per line: calibrator, loudspeaker, "
                                          "tapping machine... (the sound level meters are "
                                          "listed automatically from the files)")
        self.equipment.setFixedHeight(70)
        form.addRow("Client:", self.client)
        form.addRow("Location:", self.location)
        form.addRow("Prepared by:", self.author)
        form.addRow("Report date:", self.date)
        form.addRow("Remarks:", self.remarks)
        form.addRow("Other equipment:", self.equipment)
        lay.addLayout(form)

        # one checkbox per switch of the report, in groups; the saved values of this project
        self.stored = ReportOptions.from_dict(project.report_options)
        n_photos = sum(len(r.photos) for r in project.rooms)
        self.toggles: dict[str, QtWidgets.QCheckBox] = {}
        for group in GROUPS:
            box = QtWidgets.QGroupBox(group)
            column = QtWidgets.QVBoxLayout(box)
            for toggle in (t for t in TOGGLES if t.group == group):
                check = QtWidgets.QCheckBox(toggle.label)
                check.setChecked(getattr(self.stored, toggle.key))
                check.setToolTip(toggle.tip)
                self.toggles[toggle.key] = check
                column.addWidget(check)
            lay.addWidget(box)
        photos = self.toggles["room_photos"]                  # only possible with photos
        photos.setText(f"Room photos ({n_photos} available): a photo page and small photos "
                       "per measurement")
        photos.setEnabled(n_photos > 0)
        photos.setChecked(n_photos > 0 and self.stored.room_photos)
        # names used by the older code and tests
        self.pages = self.toggles["per_measurement_pages"]
        self.bands = self.toggles["per_band_tables"]
        self.photos = photos
        self.dates = self.toggles["file_dates"]

        self.open_after = QtWidgets.QCheckBox("Open the PDF when it is ready")
        self.open_after.setChecked(True)
        lay.addWidget(self.open_after)
        text = f"{n_included} measurement(s) will be included."
        if n_left_out:
            text += (f" {n_left_out} measurement(s) that are unticked ('Show') in the overview "
                     "are left out.")
        label = QtWidgets.QLabel(text)
        label.setWordWrap(True)
        label.setStyleSheet("color: #666666;")
        lay.addWidget(label)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok |
                                             QtWidgets.QDialogButtonBox.Cancel)
        buttons.button(QtWidgets.QDialogButtonBox.Ok).setText("Choose file...")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)

    def info(self) -> ReportInfo:
        return ReportInfo(self.client.text().strip(), self.location.text().strip(),
                          self.author.text().strip(), self.remarks.toPlainText().strip(),
                          self.equipment.toPlainText().strip())

    def report_date(self) -> dt.date:
        d = self.date.date()
        return dt.date(d.year(), d.month(), d.day())

    def report_options(self) -> ReportOptions:
        """The chosen switches (a disabled box keeps its saved value) and the report date."""
        values = {key: (box.isChecked() if box.isEnabled() else getattr(self.stored, key))
                  for key, box in self.toggles.items()}
        return ReportOptions(**values, date=self.report_date())
