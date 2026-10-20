"""A time window on background files, to leave out a disturbance (a door, voices).

The window is stored with the file as 'file.SVL@start-end' (calc.measurements.as_recordings), so
the building evaluation, the single-measurement pages and the project file all use it without
extra fields. BackgroundRow is a FileRow with a 'Time window...' button; the dialog shows the
level history of each file, as the installation noise dialog does for its recordings.
"""
from __future__ import annotations

from dataclasses import replace

from PySide6 import QtCore, QtWidgets

from calc.measurements import Recording
from svl.parser import SvlError, SvlFile, read_svl

from .level_history import LevelHistory, window_text
from .widgets import FileRow


class BackgroundWindowDialog(QtWidgets.QDialog):
    """Per background file the seconds that are used."""

    def __init__(self, specs: list[str], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Background: time window")
        self.setMinimumSize(820, 420)
        self.recs = [Recording.parse(s) for s in specs]
        self.files: dict[str, SvlFile | str] = {}      # path -> file, or the reading error
        lay = QtWidgets.QVBoxLayout(self)
        hint = QtWidgets.QLabel(
            "Leave out seconds disturbed by something that is not the usual background (a door, "
            "voices). The report names the part of the file that is used. Keep the window long "
            "enough: the standards ask for a minimum averaging time.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #666666;")
        lay.addWidget(hint)
        row = QtWidgets.QHBoxLayout()
        self.list = QtWidgets.QListWidget()
        self.list.setFixedWidth(230)
        self.list.currentRowChanged.connect(self.show_selected)
        row.addWidget(self.list)
        right = QtWidgets.QVBoxLayout()
        self.history = LevelHistory("drag the shaded region over the undisturbed seconds")
        self.history.window_changed.connect(self.window_changed)
        right.addWidget(self.history, 1)
        self.result = QtWidgets.QLabel()
        right.addWidget(self.result)
        row.addLayout(right, 1)
        lay.addLayout(row, 1)
        buttons = QtWidgets.QDialogButtonBox(QtWidgets.QDialogButtonBox.Ok |
                                             QtWidgets.QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.fill_list()
        if self.recs:
            self.list.setCurrentRow(0)

    def read(self, rec: Recording) -> SvlFile | str:
        key = str(rec.path)
        if key not in self.files:
            try:
                self.files[key] = read_svl(rec.path)
            except (OSError, SvlError) as exc:
                self.files[key] = str(exc)
        return self.files[key]

    def fill_list(self):
        current = self.list.currentRow()
        self.list.blockSignals(True)
        self.list.clear()
        for rec in self.recs:
            f = self.read(rec)
            duration = f.duration_s if isinstance(f, SvlFile) else None
            self.list.addItem(f"{rec.path.name}   {window_text(rec, duration)}")
        self.list.setCurrentRow(current)
        self.list.blockSignals(False)

    def show_selected(self, i: int):
        if not 0 <= i < len(self.recs):
            self.history.show_file(None)
            self.result.setText("")
            return
        f = self.read(self.recs[i])
        if isinstance(f, str):
            self.history.show_file(None, error=f)
            self.result.setText("")
            return
        self.history.show_file(f, self.recs[i])
        self.update_result()

    def window_changed(self, start: int, end):
        i = self.list.currentRow()
        if 0 <= i < len(self.recs):
            self.recs[i] = replace(self.recs[i], start=start, end=end)
            self.fill_list()
            self.update_result()

    def update_result(self):
        """LAeq of the window next to the whole file: shows what leaving seconds out does."""
        i = self.list.currentRow()
        f = self.read(self.recs[i])
        try:
            part, whole = f.laeq(self.recs[i].start, self.recs[i].end), f.laeq()
        except SvlError as exc:
            self.result.setText(str(exc))
            return
        self.result.setText(f"LAeq of the window: <b>{part:.1f} dB(A)</b> &nbsp; "
                            f"(whole file {whole:.1f} dB(A))")

    def specs(self) -> list[str]:
        return [r.spec for r in self.recs]


class BackgroundRow(FileRow):
    """Background files with an optional time window each ('Time window...')."""

    def __init__(self, label: str, settings: QtCore.QSettings):
        super().__init__(label, settings)
        self.window_button = QtWidgets.QPushButton("Window...")
        self.window_button.setToolTip("Leave out disturbed seconds of the background files")
        self.window_button.clicked.connect(self.edit_windows)
        lay = self.layout()
        lay.insertWidget(lay.indexOf(self.clear_button), self.window_button)
        self.window_button.setEnabled(False)

    def set_paths(self, paths, notify: bool = True):
        super().set_paths(paths, notify)
        recs = [Recording.parse(p) for p in self._paths]
        if any(r.windowed for r in recs):               # names + windows: the field is narrow
            self.edit.setText(", ".join(f"{r.path.name} ({r.window_text})" if r.windowed
                                        else r.path.name for r in recs))
        if hasattr(self, "window_button"):              # FileRow.__init__ calls nothing, but
            self.window_button.setEnabled(bool(self._paths))   # stay safe if that changes

    set_path = set_paths

    def edit_windows(self):
        dlg = BackgroundWindowDialog(self.paths(), self)
        if dlg.exec() == QtWidgets.QDialog.Accepted:
            self.set_paths(dlg.specs())
