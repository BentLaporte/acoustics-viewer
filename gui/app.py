"""Viewer for building acoustics measurements (PySide6 + pyqtgraph).

Run from the project folder:
    python -m gui
    python -m gui --project my_building.json
    python -m gui --source samples/A_L2.SVL --receiver samples/B_L2.SVL \
                  --tapping samples/B_L4.SVL --background samples/C_L20.SVL \
                  --rt samples/B_L11.SVL
"""
from __future__ import annotations

import argparse
import sys

from PySide6 import QtCore, QtWidgets

from .airborne_page import AirbornePage
from .building_page import BuildingPage
from .impact_page import ImpactPage

SHARED = ("background", "rt")     # same receiving room in both measurements


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Acoustics viewer")
        self.resize(1500, 950)
        settings = QtCore.QSettings("acoustics-viewer", "viewer")
        self.building = BuildingPage(settings)
        self.airborne = AirbornePage(settings)
        self.impact = ImpactPage(settings)
        self.tabs = QtWidgets.QTabWidget()
        self.tabs.addTab(self.building, "Building")
        self.tabs.addTab(self.airborne, "Single airborne  (DnT,w)")
        self.tabs.addTab(self.impact, "Single impact  (L'nT,w)")
        self.setCentralWidget(self.tabs)
        self.status = self.statusBar()
        self.status.showMessage("Select the measurement files.")
        self.messages = {}
        for page in (self.building, self.airborne, self.impact):
            page.message.connect(lambda text, pg=page: self.on_message(pg, text))
        self.building.title_changed.connect(
            lambda t: self.setWindowTitle(f"Acoustics viewer - {t}"))
        self.building.details_requested.connect(self.show_details)
        self.tabs.currentChanged.connect(self.show_current_message)
        # background and reverberation time usually belong to the same receiving room:
        # a file chosen on one page is offered to the other page if that is still empty
        for key in SHARED:
            self.airborne.rows[key].changed.connect(lambda k=key: self.share(k, self.airborne, self.impact))
            self.impact.rows[key].changed.connect(lambda k=key: self.share(k, self.impact, self.airborne))

    def show_details(self, kind, files, rt_kind):
        """Open one measurement of the building on its single-measurement page."""
        page = self.airborne if kind == "airborne" else self.impact
        page.rt_kind.blockSignals(True)
        page.rt_kind.setCurrentIndex(max(0, page.rt_kind.findData(rt_kind)))
        page.rt_kind.blockSignals(False)
        page.load(files)
        self.tabs.setCurrentWidget(page)

    def closeEvent(self, event):
        if self.building.maybe_save():
            event.accept()
        else:
            event.ignore()

    def on_message(self, page, text):
        self.messages[page] = text
        if self.tabs.currentWidget() is page:
            self.status.showMessage(text)

    def show_current_message(self, _index=None):
        self.status.showMessage(self.messages.get(self.tabs.currentWidget(),
                                                   "Select the measurement files."))

    @staticmethod
    def share(key, src, dst):
        paths = src.rows[key].paths()
        if paths and not dst.rows[key].paths():
            dst.rows[key].set_paths(paths)

    def load(self, paths: dict):
        self.airborne.load(paths)
        self.impact.load(paths)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Building acoustics viewer")
    for key in ("source", "receiver", "tapping", "background", "rt"):
        ap.add_argument(f"--{key}", nargs="+", help=f"{key} file(s) (.SVL), several = averaged")
    ap.add_argument("--project", help="building project file (.json) to open")
    ap.add_argument("--tab", choices=["building", "airborne", "impact"], default="building")
    ap.add_argument("--screenshot", help="save a screenshot to this PNG file and exit")
    args = ap.parse_args(argv)

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv[:1])
    win = MainWindow()
    win.load({k: getattr(args, k) for k in
              ("source", "receiver", "tapping", "background", "rt")})
    if args.project:
        win.building.open_path(args.project)
    win.tabs.setCurrentIndex({"building": 0, "airborne": 1, "impact": 2}[args.tab])
    win.show()
    if args.screenshot:
        QtCore.QTimer.singleShot(400, lambda: (win.grab().save(args.screenshot), app.quit()))
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
