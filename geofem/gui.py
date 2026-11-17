"""Antarmuka PySide6 GeoFEM 3D (seluruh label dalam Bahasa Indonesia).

Tata letak: bilah tab tahapan di atas, Model Explorer + Selection Explorer di kiri,
viewport 3D (PyVista) di tengah, kurva beban-penurunan dan ringkasan di kanan.
"""
from __future__ import annotations

import json
import sys
import time

import numpy as np
import pyvista as pv
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import QObject, QPoint, QRect, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QIcon, QImage, QPainter
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QHeaderView, QLabel, QMainWindow,
                               QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QSpinBox,
                               QSplitter, QStyle, QTableWidget, QTableWidgetItem, QTabWidget, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)
from pyvistaqt import QtInteractor

from . import APP_NAME, fem
from .material import voigt_to_tensor
from .mesher import generate_mesh
from .project import MODELS, Layer, Material, Project, default_project
from .solver import Cancelled, run_analysis

PALETTE = ["#e2c27a", "#9c7b5b", "#b9a37e", "#7f8f6a", "#c98f6b", "#8a8fa0"]
COLS = ["Nama", "Model", "Puncak (m)", "Dasar (m)", "γunsat (kN/m³)", "γsat (kN/m³)", "E (kPa)", "ν",
        "c (kPa)", "φ (°)", "ψ (°)", "E50ref (kPa)", "Eoedref (kPa)", "Eurref (kPa)", "m",
        "pref (kPa)", "νur", "Rf"]
MAT_KEYS = ["gamma_unsat", "gamma_sat", "E", "nu", "c", "phi", "psi",
            "E50ref", "Eoedref", "Eurref", "m", "pref", "nu_ur", "Rf"]
NUM0 = 2   # first numeric column
COL_TIPS = {"E (kPa)": "Mohr-Coulomb saja", "ν": "Mohr-Coulomb saja",
            "E50ref (kPa)": "Hardening Soil: modulus sekan uji triaksial pada pref",
            "Eoedref (kPa)": "Hardening Soil: modulus oedometer pada pref (cap belum dipakai)",
            "Eurref (kPa)": "Hardening Soil: modulus bongkar-muat pada pref",
            "m": "Hardening Soil: pangkat ketergantungan tegangan",
            "pref (kPa)": "Hardening Soil: tegangan acuan", "νur": "Hardening Soil: Poisson bongkar-muat",
            "Rf": "Hardening Soil: rasio keruntuhan qf/qa"}
QUANTITIES = ["Perpindahan total utot (mm)", "Perpindahan vertikal uz (mm)",
              "Tegangan vertikal efektif σ'zz (kPa)", "Tegangan vertikal total σzz (kPa)",
              "Titik plastis", "Perpindahan horizontal ux (mm)",
              "Tegangan rata-rata efektif p' (kPa)", "Tegangan deviator q (kPa)",
              "Perpindahan inkremental fase |Δu| (mm)"]
CUTS = ["Tanpa potongan", "Potongan x-z (melalui pusat fondasi)", "Potongan y-z (melalui pusat fondasi)"]
PHASE_NAMES = {"Initial": "Fase 0 - Tegangan awal (K0)", "Load": "Fase 1 - Beban fondasi (plastis)",
               "Safety": "Fase 2 - Angka keamanan (reduksi φ-c)"}
STYLE = """
QMainWindow, QWidget { background: #f4f6f8; color: #1f2a33; font-size: 9pt; }
QTabWidget::pane { border: 1px solid #c9d2da; background: #ffffff; }
QTabBar::tab { background: #dfe6ec; padding: 6px 14px; border: 1px solid #c9d2da; border-bottom: none; }
QTabBar::tab:selected { background: #ffffff; color: #0d6e6e; font-weight: bold; }
QPushButton { background: #0d6e6e; color: white; border: none; padding: 5px 12px; border-radius: 3px; }
QPushButton:hover { background: #128585; }
QPushButton:disabled { background: #9fb3b3; }
QTreeWidget, QTableWidget, QPlainTextEdit { background: #ffffff; border: 1px solid #c9d2da; }
QHeaderView::section { background: #e8edf1; border: 1px solid #c9d2da; padding: 3px; }
QLabel#title { font-weight: bold; color: #0d6e6e; }
"""


def _vtk_text(s):
    """The VTK font has no Greek letters: spell them out in the 3D view."""
    for a, b in (("φ", "phi"), ("σ", "sigma "), ("Δ", "d"), ("Σ", "sum "), ("ν", "nu"), ("γ", "gamma")):
        s = s.replace(a, b)
    return s


def dspin(lo, hi, val, dec=2, step=0.1, suffix=""):
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(dec)
    w.setSingleStep(step)
    w.setValue(val)
    if suffix:
        w.setSuffix(" " + suffix)
    return w


def titled(text):
    lab = QLabel(text)
    lab.setObjectName("title")
    return lab


# ======================================================================== worker thread
class Worker(QObject):
    progress = Signal(float, str)
    log = Signal(str)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, project, mesh):
        super().__init__()
        self.project, self.mesh, self.stop = project, mesh, False

    def run(self):
        try:
            res = run_analysis(self.project, self.mesh, progress=self.progress.emit,
                               log=self.log.emit, cancel=lambda: self.stop)
            self.done.emit(res)
        except Cancelled:
            self.failed.emit("Perhitungan dibatalkan.")
        except Exception as exc:  # report every solver error in the GUI, never crash silently
            self.failed.emit(f"Perhitungan gagal: {exc}")


# ======================================================================== main window
class MainWindow(QMainWindow):
    def __init__(self, project: Project | None = None):
        super().__init__()
        self.project = project or default_project()
        self.path = None
        self.mesh = None
        self.results = None
        self.thread = None
        self._loading = False
        self.setWindowTitle(APP_NAME)
        self.resize(1440, 900)
        self.setStyleSheet(STYLE)
        self._build_menu()
        self._build_ui()
        self.populate()
        self.statusBar().showMessage("Siap. Atur tanah, struktur, lalu buat jaring dan hitung.")

    # ------------------------------------------------------------------ layout
    def _build_menu(self):
        m = self.menuBar().addMenu("&Berkas")
        for text, slot, key in (("Proyek baru", self.new_project, "Ctrl+N"),
                                ("Buka proyek...", self.open_project, "Ctrl+O"),
                                ("Simpan", self.save_project, "Ctrl+S"),
                                ("Simpan sebagai...", self.save_project_as, "Ctrl+Shift+S"),
                                ("Keluar", self.close, "Ctrl+Q")):
            a = QAction(text, self)
            a.setShortcut(key)
            a.triggered.connect(slot)
            m.addAction(a)
        v = self.menuBar().addMenu("&Tampilan")
        for text, slot in (("Isometrik", lambda: self.set_view("iso")), ("Dari atas", lambda: self.set_view("xy")),
                           ("Dari depan", lambda: self.set_view("xz")), ("Dari samping", lambda: self.set_view("yz"))):
            a = QAction(text, self)
            a.triggered.connect(slot)
            v.addAction(a)
        e = self.menuBar().addMenu("&Ekspor")
        for text, slot in (("Simpan gambar tampilan...", self.export_picture),
                           ("Ekspor hasil titik nodal (CSV)...", self.export_csv),
                           ("Ekspor kurva (CSV)...", self.export_curve)):
            a = QAction(text, self)
            a.triggered.connect(slot)
            e.addAction(a)
        self._build_toolbar()
        h = self.menuBar().addMenu("&Bantuan")
        a = QAction("Tentang GeoFEM 3D", self)
        a.triggered.connect(lambda: QMessageBox.information(
            self, "Tentang", "GeoFEM 3D - analisis elemen hingga geoteknik 3D\n"
            "Mohr-Coulomb dan Hardening Soil, prosedur K0, beban plastis, reduksi φ-c.\n"
            "Python, NumPy/SciPy, gmsh, PyVista."))
        h.addAction(a)

    def _build_toolbar(self):
        tb = self.addToolBar("Utama")
        tb.setMovable(False)
        tb.setIconSize(QSize(20, 20))
        tb.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        sp = QStyle.StandardPixmap
        items = [("Baru", sp.SP_FileIcon, self.new_project), ("Buka", sp.SP_DialogOpenButton, self.open_project),
                 ("Simpan", sp.SP_DialogSaveButton, self.save_project), None,
                 ("Buat jaring", sp.SP_FileDialogDetailedView, self.on_mesh),
                 ("Hitung", sp.SP_MediaPlay, self.on_calc), ("Batal", sp.SP_MediaStop, self.on_stop), None,
                 ("Isometrik", sp.SP_DesktopIcon, lambda: self.set_view("iso")),
                 ("Atas", sp.SP_ArrowDown, lambda: self.set_view("xy")),
                 ("Depan", sp.SP_ArrowForward, lambda: self.set_view("xz")), None,
                 ("Gambar", sp.SP_DialogApplyButton, self.export_picture)]
        for it in items:
            if it is None:
                tb.addSeparator()
                continue
            text, icon, slot = it
            a = QAction(self.style().standardIcon(icon), text, self)
            a.triggered.connect(lambda _=False, s=slot: s())
            tb.addAction(a)

    def set_view(self, which):
        pl = self.plotter
        {"iso": pl.view_isometric, "xy": pl.view_xy, "xz": pl.view_xz, "yz": pl.view_yz}[which]()
        pl.render()

    def _build_ui(self):
        self.tabs = QTabWidget()
        self.tabs.setMaximumHeight(270)
        self.tabs.addTab(self._tab_soil(), "Tanah")
        self.tabs.addTab(self._tab_structure(), "Struktur")
        self.tabs.addTab(self._tab_mesh(), "Jaring")
        self.tabs.addTab(self._tab_flow(), "Kondisi Aliran")
        self.tabs.addTab(self._tab_phases(), "Tahapan Konstruksi")
        self.tabs.addTab(self._tab_output(), "Hasil")
        self.tabs.currentChanged.connect(lambda _: self.refresh_view())

        # left: explorers
        left = QSplitter(Qt.Vertical)
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(titled("Model Explorer"))
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.currentItemChanged.connect(self.on_select)
        lay.addWidget(self.tree)
        left.addWidget(box)
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(4, 4, 4, 4)
        lay.addWidget(titled("Selection Explorer"))
        self.props = QTableWidget(0, 2)
        self.props.setHorizontalHeaderLabels(["Properti", "Nilai"])
        self.props.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.props.verticalHeader().setVisible(False)
        self.props.setEditTriggers(QTableWidget.NoEditTriggers)
        lay.addWidget(self.props)
        left.addWidget(box)

        # centre: 3D viewport
        self.plotter = QtInteractor(self)
        self.plotter.set_background("#fbfcfd", top="#d9e3ea")

        # right: curve + summary
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(4, 4, 4, 4)
        self.curve_title = titled("Kurva beban - penurunan")
        rl.addWidget(self.curve_title)
        self.fig = Figure(figsize=(3.6, 3.0), tight_layout=True)
        self.canvas = FigureCanvasQTAgg(self.fig)
        self.ax = self.fig.add_subplot(111)
        rl.addWidget(self.canvas, 2)
        rl.addWidget(titled("Ringkasan"))
        self.summary = QLabel("Belum ada hasil perhitungan.")
        self.summary.setWordWrap(True)
        self.summary.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self.summary.setTextInteractionFlags(Qt.TextSelectableByMouse)
        rl.addWidget(self.summary, 1)

        main = QSplitter(Qt.Horizontal)
        main.addWidget(left)
        main.addWidget(self.plotter)
        main.addWidget(right)
        main.setSizes([260, 860, 320])
        main.setStretchFactor(1, 1)

        central = QWidget()
        cl = QVBoxLayout(central)
        cl.setContentsMargins(4, 4, 4, 4)
        cl.addWidget(self.tabs)
        cl.addWidget(main, 1)
        self.setCentralWidget(central)
        self._draw_curve()

    def _tab_soil(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        col = QVBoxLayout()
        col.addWidget(titled("Bor log - lapisan tanah horizontal (Mohr-Coulomb / Hardening Soil, terdrainase)"))
        self.table = QTableWidget(0, len(COLS))
        self.table.setHorizontalHeaderLabels(COLS)
        for c, name in enumerate(COLS):
            if name in COL_TIPS:
                self.table.horizontalHeaderItem(c).setToolTip(COL_TIPS[name])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.itemChanged.connect(self.changed)
        col.addWidget(self.table)
        lay.addLayout(col, 1)
        btns = QVBoxLayout()
        for text, slot in (("+ Lapisan", self.add_layer), ("- Lapisan", self.remove_layer)):
            b = QPushButton(text)
            b.clicked.connect(slot)
            btns.addWidget(b)
        form = QFormLayout()
        self.Lx = dspin(1, 1000, 20, step=1, suffix="m")
        self.Ly = dspin(1, 1000, 20, step=1, suffix="m")
        self.sym = QCheckBox("Simetri seperempat")
        self.sym.setToolTip("Hitung seperempat model (x ≥ 0, y ≥ 0) dengan dua bidang simetri")
        form.addRow("Lebar domain x", self.Lx)
        form.addRow("Lebar domain y", self.Ly)
        form.addRow(self.sym)
        btns.addLayout(form)
        btns.addStretch()
        lay.addLayout(btns)
        for s in (self.Lx, self.Ly):
            s.valueChanged.connect(self.changed)
        self.sym.toggled.connect(self.changed)
        return w

    def _tab_structure(self):
        w = QWidget()
        form = QFormLayout(w)
        form.addRow(titled("Fondasi persegi panjang di permukaan tanah (beban merata)"))
        self.fB = dspin(0.1, 500, 2, step=0.1, suffix="m")
        self.fL = dspin(0.1, 500, 2, step=0.1, suffix="m")
        self.fq = dspin(0, 1e5, 150, dec=1, step=10, suffix="kPa")
        self.fkind = QComboBox()
        self.fkind.addItems(["Fleksibel (tekanan merata)", "Kaku (penurunan seragam, kasar)"])
        form.addRow("Lebar B (arah x)", self.fB)
        form.addRow("Panjang L (arah y)", self.fL)
        form.addRow("Beban q", self.fq)
        form.addRow("Jenis fondasi", self.fkind)
        for s in (self.fB, self.fL, self.fq):
            s.valueChanged.connect(self.changed)
        self.fkind.currentIndexChanged.connect(self.changed)
        return w

    def _tab_mesh(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        form = QFormLayout()
        form.addRow(titled("Jaring tetrahedral 10 titik (gmsh)"))
        self.mc = dspin(0.1, 100, 3.0, step=0.25, suffix="m")
        self.mf = dspin(0.05, 50, 0.45, step=0.05, suffix="m")
        self.md = dspin(0.1, 20, 2.0, step=0.25, suffix="× B")
        self.mm = dspin(0.0, 20, 0.75, step=0.25, suffix="× B")
        form.addRow("Ukuran elemen global", self.mc)
        form.addRow("Ukuran elemen di bawah fondasi", self.mf)
        form.addRow("Kedalaman zona halus", self.md)
        form.addRow("Lebar tepi zona halus", self.mm)
        lay.addLayout(form)
        col = QVBoxLayout()
        self.btn_mesh = QPushButton("Buat jaring")
        self.btn_mesh.clicked.connect(self.on_mesh)
        col.addWidget(self.btn_mesh)
        col.addWidget(QLabel("Tumpuan: dasar dijepit (ux = uy = uz = 0);\n"
                             "sisi vertikal dijepit arah normal (rol)."))
        self.mesh_info = QLabel("Jaring belum dibuat.")
        col.addWidget(self.mesh_info)
        col.addStretch()
        lay.addLayout(col)
        lay.addStretch()
        for s in (self.mc, self.mf, self.md, self.mm):
            s.valueChanged.connect(self.changed)
        return w

    def _tab_flow(self):
        w = QWidget()
        form = QFormLayout(w)
        form.addRow(titled("Muka air tanah (tekanan pori hidrostatis, analisis terdrainase)"))
        self.wl = dspin(-1000, 1000, -2, step=0.5, suffix="m")
        self.gw = dspin(1, 20, 10, step=0.1, suffix="kN/m³")
        form.addRow("Elevasi muka air tanah", self.wl)
        form.addRow("Berat isi air γw", self.gw)
        for s in (self.wl, self.gw):
            s.valueChanged.connect(self.changed)
        return w

    def _tab_phases(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        col = QVBoxLayout()
        col.addWidget(titled("Daftar fase"))
        self.phase_list = QTreeWidget()
        self.phase_list.setHeaderLabels(["Fase", "Jenis perhitungan"])
        for name, kind in (("Fase 0 - Tegangan awal", "Prosedur K0 (K0 = 1 - sin φ)"),
                           ("Fase 1 - Beban fondasi", "Plastis, inkremental-iteratif"),
                           ("Fase 2 - Angka keamanan", "Reduksi φ-c")):
            QTreeWidgetItem(self.phase_list, [name, kind])
        self.phase_list.header().setSectionResizeMode(QHeaderView.ResizeToContents)
        col.addWidget(self.phase_list)
        lay.addLayout(col, 1)
        form = QFormLayout()
        self.pm = QComboBox()
        self.pm.addItems(["Newton termodifikasi (kekakuan elastis)", "Newton penuh (tangen, lambat)"])
        self.ptol = dspin(1e-4, 0.2, 0.01, dec=4, step=0.005)
        self.pit = QSpinBox()
        self.pit.setRange(5, 1000)
        self.pst = QSpinBox()
        self.pst.setRange(1, 200)
        self.psf = QCheckBox("Hitung angka keamanan (Fase 2)")
        self.pdm = dspin(0.01, 1, 0.1, dec=3, step=0.05)
        form.addRow("Metode iterasi", self.pm)
        form.addRow("Toleransi galat", self.ptol)
        form.addRow("Iterasi maksimum", self.pit)
        form.addRow("Jumlah langkah awal", self.pst)
        form.addRow("Kenaikan awal ΣMsf", self.pdm)
        form.addRow(self.psf)
        lay.addLayout(form)
        col = QVBoxLayout()
        row = QHBoxLayout()
        self.btn_calc = QPushButton("Hitung")
        self.btn_calc.clicked.connect(self.on_calc)
        self.btn_stop = QPushButton("Batal")
        self.btn_stop.setEnabled(False)
        self.btn_stop.clicked.connect(self.on_stop)
        row.addWidget(self.btn_calc)
        row.addWidget(self.btn_stop)
        col.addLayout(row)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        col.addWidget(self.bar)
        self.logbox = QPlainTextEdit()
        self.logbox.setReadOnly(True)
        col.addWidget(self.logbox)
        lay.addLayout(col, 2)
        for s in (self.ptol, self.pit, self.pst, self.pdm):
            s.valueChanged.connect(self.changed)
        self.pm.currentIndexChanged.connect(self.changed)
        self.psf.toggled.connect(self.changed)
        return w

    def _tab_output(self):
        w = QWidget()
        form = QFormLayout(w)
        form.addRow(titled("Tampilan hasil"))
        self.oph = QComboBox()
        self.oq = QComboBox()
        self.oq.addItems(QUANTITIES)
        self.oscale = dspin(0, 1e5, 0, dec=1, step=10)
        self.oscale.setToolTip("0 = otomatis")
        self.oedges = QCheckBox("Tampilkan garis jaring")
        self.ocut = QComboBox()
        self.ocut.addItems(CUTS)
        form.addRow("Fase", self.oph)
        form.addRow("Besaran", self.oq)
        form.addRow("Potongan", self.ocut)
        form.addRow("Skala deformasi (0 = otomatis)", self.oscale)
        form.addRow(self.oedges)
        self.oph.currentIndexChanged.connect(lambda _: (self.refresh_view(), self._draw_curve()))
        self.oq.currentIndexChanged.connect(lambda _: self.refresh_view())
        self.ocut.currentIndexChanged.connect(lambda _: self.refresh_view())
        self.oscale.valueChanged.connect(lambda _: self.refresh_view())
        self.oedges.toggled.connect(lambda _: self.refresh_view())
        return w

    # ------------------------------------------------------------------ project <-> forms
    def populate(self):
        p = self.project
        self._loading = True
        self.table.setRowCount(0)
        for l in p.borehole.layers:
            m = p.material(l.material)
            self._append_row([m.name, m.model, l.top, l.bottom] + [getattr(m, k) for k in MAT_KEYS])
        self.Lx.setValue(p.domain.Lx)
        self.Ly.setValue(p.domain.Ly)
        self.sym.setChecked(p.domain.symmetry)
        self.fB.setValue(p.footing.B)
        self.fL.setValue(p.footing.L)
        self.fq.setValue(p.footing.q)
        self.fkind.setCurrentIndex(1 if p.footing.kind == "rigid" else 0)
        self.mc.setValue(p.mesh.coarse)
        self.mf.setValue(p.mesh.fine)
        self.md.setValue(p.mesh.refine_depth)
        self.mm.setValue(p.mesh.refine_margin)
        self.wl.setValue(p.borehole.water_level)
        self.gw.setValue(p.gamma_w)
        ps = p.phases
        self.pm.setCurrentIndex(1 if ps.method == "newton" else 0)
        self.ptol.setValue(ps.tolerance)
        self.pit.setValue(ps.max_iterations)
        self.pst.setValue(ps.initial_steps)
        self.pdm.setValue(ps.sf_increment)
        self.psf.setChecked(ps.run_safety)
        self._loading = False
        self.mesh = self.results = None
        self._mark_phases()
        self.update_tree()
        self.refresh_view()
        self._draw_curve()

    def _append_row(self, vals):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(vals[0]))
        box = QComboBox()
        box.addItems(list(MODELS))
        box.setCurrentText(vals[1])
        box.currentIndexChanged.connect(self.changed)
        self.table.setCellWidget(r, 1, box)
        for c, v in enumerate(vals[NUM0:], NUM0):
            self.table.setItem(r, c, QTableWidgetItem(f"{float(v):g}"))

    def collect(self) -> Project:
        """Read every form into self.project; raise ValueError with an Indonesian message."""
        p = self.project
        old = {m.name: m for m in p.materials}
        mats, layers = [], []
        for r in range(self.table.rowCount()):
            cells = [(self.table.item(r, c).text().strip() if self.table.item(r, c) else "")
                     for c in range(len(COLS))]
            name = cells[0] or f"Lapisan {r + 1}"
            try:
                vals = [float(s.replace(",", ".")) for s in cells[NUM0:]]
            except ValueError:
                raise ValueError(f"Baris {r + 1}: semua kolom angka harus berisi bilangan.")
            color = old[name].color if name in old else PALETTE[r % len(PALETTE)]
            model = self.table.cellWidget(r, 1).currentText()
            mats.append(Material(name=name, color=color, model=model, **dict(zip(MAT_KEYS, vals[2:]))))
            layers.append(Layer(vals[0], vals[1], name))
        p.materials, p.borehole.layers = mats, layers
        p.borehole.water_level = self.wl.value()
        p.gamma_w = self.gw.value()
        p.domain.Lx, p.domain.Ly, p.domain.symmetry = self.Lx.value(), self.Ly.value(), self.sym.isChecked()
        p.footing.B, p.footing.L, p.footing.q = self.fB.value(), self.fL.value(), self.fq.value()
        p.footing.kind = "rigid" if self.fkind.currentIndex() == 1 else "flexible"
        p.mesh.coarse, p.mesh.fine = self.mc.value(), self.mf.value()
        p.mesh.refine_depth, p.mesh.refine_margin = self.md.value(), self.mm.value()
        ps = p.phases
        ps.method = "newton" if self.pm.currentIndex() == 1 else "modified_newton"
        ps.tolerance, ps.max_iterations = self.ptol.value(), self.pit.value()
        ps.initial_steps, ps.sf_increment = self.pst.value(), self.pdm.value()
        ps.run_safety = self.psf.isChecked()
        err = p.validate()
        if err:
            raise ValueError("\n".join(err))
        return p

    def changed(self, *_):
        if self._loading:
            return
        try:
            self.collect()
        except ValueError as exc:
            self.statusBar().showMessage("Input belum valid: " + str(exc).split("\n")[0])
            return
        if self.mesh is not None or self.results is not None:
            self.statusBar().showMessage("Input berubah: jaring dan hasil lama dihapus.")
        self.mesh = self.results = None
        self._mark_phases()
        self.mesh_info.setText("Jaring belum dibuat.")
        self.update_tree()
        self.refresh_view()
        self._draw_curve()

    def add_layer(self):
        n = self.table.rowCount()
        top = float(self.table.item(n - 1, 2).text()) if n else 0.0
        self._loading = True
        self._append_row([f"Tanah {n + 1}", MODELS[0], top, top - 5, 17, 19, 20000, 0.3, 5, 28, 0,
                          20000, 20000, 60000, 0.5, 100, 0.2, 0.9])
        self._loading = False
        self.changed()

    def remove_layer(self):
        if self.table.rowCount() > 1:
            self.table.removeRow(self.table.currentRow() if self.table.currentRow() >= 0
                                 else self.table.rowCount() - 1)
            self.changed()

    # ------------------------------------------------------------------ explorers
    def update_tree(self):
        p = self.project
        self.tree.clear()
        root = QTreeWidgetItem(self.tree, [p.name])
        soil = QTreeWidgetItem(root, ["Tanah (bor log)"])
        for i, l in enumerate(p.borehole.layers):
            it = QTreeWidgetItem(soil, [f"{l.material}  [{l.top:g} … {l.bottom:g} m]"])
            it.setData(0, Qt.UserRole, ("layer", i))
        QTreeWidgetItem(soil, [f"Muka air tanah  {p.borehole.water_level:g} m"]).setData(0, Qt.UserRole, ("water", 0))
        st = QTreeWidgetItem(root, ["Struktur"])
        QTreeWidgetItem(st, [f"Fondasi {p.footing.B:g} × {p.footing.L:g} m"]).setData(0, Qt.UserRole, ("footing", 0))
        QTreeWidgetItem(root, ["Jaring"]).setData(0, Qt.UserRole, ("mesh", 0))
        ph = QTreeWidgetItem(root, ["Tahapan"])
        for k, name in enumerate(PHASE_NAMES.values()):
            QTreeWidgetItem(ph, [name]).setData(0, Qt.UserRole, ("phase", k))
        self.tree.expandAll()

    def on_select(self, item, _prev=None):
        rows = []
        p = self.project
        kind = item.data(0, Qt.UserRole) if item else None
        if kind:
            k, i = kind
            if k == "layer" and i < len(p.borehole.layers):
                l = p.borehole.layers[i]
                m = p.material(l.material)
                rows = [("Material", m.name), ("Puncak", f"{l.top:g} m"), ("Dasar", f"{l.bottom:g} m"),
                        ("Model", f"{m.model}, terdrainase"), ("γunsat", f"{m.gamma_unsat:g} kN/m³"),
                        ("γsat", f"{m.gamma_sat:g} kN/m³")]
                if m.model == "Hardening Soil":
                    rows += [("E50ref", f"{m.E50ref:g} kPa"), ("Eoedref", f"{m.Eoedref:g} kPa (cap belum dipakai)"),
                             ("Eurref", f"{m.Eurref:g} kPa"), ("m", f"{m.m:g}"), ("pref", f"{m.pref:g} kPa"),
                             ("νur", f"{m.nu_ur:g}"), ("Rf", f"{m.Rf:g}")]
                else:
                    rows += [("E", f"{m.E:g} kPa"), ("ν", f"{m.nu:g}")]
                rows += [("c", f"{m.c:g} kPa"), ("φ", f"{m.phi:g}°"), ("ψ", f"{m.psi:g}°"),
                         ("K0 = 1 - sin φ", f"{1 - np.sin(np.radians(m.phi)):.3f}")]
            elif k == "water":
                rows = [("Elevasi", f"{p.borehole.water_level:g} m"), ("γw", f"{p.gamma_w:g} kN/m³")]
            elif k == "footing":
                f = p.footing
                rows = [("B", f"{f.B:g} m"), ("L", f"{f.L:g} m"), ("q", f"{f.q:g} kPa"),
                        ("Jenis", "kaku" if f.kind == "rigid" else "fleksibel"),
                        ("Gaya total", f"{f.q * f.B * f.L:.1f} kN")]
            elif k == "mesh":
                rows = [("Ukuran global", f"{p.mesh.coarse:g} m"), ("Ukuran halus", f"{p.mesh.fine:g} m")]
                if self.mesh is not None:
                    rows += [("Titik nodal", str(self.mesh.n_nodes)), ("Elemen", str(self.mesh.n_elems))]
            elif k == "phase" and self.results is not None and i < len(self.results.phases):
                ph = self.results.phases[i]
                rows = [("Status", "OK" if ph.ok else "gagal"), ("Pesan", ph.message),
                        ("Langkah", str(ph.steps)), ("Iterasi", str(ph.iterations))]
        self.props.setRowCount(len(rows))
        for r, (a, b) in enumerate(rows):
            self.props.setItem(r, 0, QTableWidgetItem(a))
            self.props.setItem(r, 1, QTableWidgetItem(b))

    # ------------------------------------------------------------------ actions
    def on_mesh(self):
        try:
            p = self.collect()
        except ValueError as exc:
            QMessageBox.warning(self, "Input tidak valid", str(exc))
            return False
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            t = time.perf_counter()
            self.mesh = generate_mesh(p)
            self.results = None
            self.mesh_info.setText(f"{self.mesh.n_nodes} titik nodal, {self.mesh.n_elems} elemen "
                                   f"({time.perf_counter() - t:.1f} detik)")
            self.statusBar().showMessage("Jaring selesai dibuat.")
        except Exception as exc:
            QMessageBox.critical(self, "Pembuatan jaring gagal", str(exc))
            return False
        finally:
            QApplication.restoreOverrideCursor()
        self.update_tree()
        self.refresh_view()
        self._draw_curve()
        return True

    def on_calc(self, sync=False):
        try:
            self.collect()
        except ValueError as exc:
            QMessageBox.warning(self, "Input tidak valid", str(exc))
            return
        if self.mesh is None and not self.on_mesh():
            return
        self.logbox.clear()
        self.bar.setValue(0)
        self.btn_calc.setEnabled(False)
        self.btn_stop.setEnabled(True)
        self.worker = Worker(self.project, self.mesh)
        self.worker.progress.connect(self._on_progress)
        self.worker.log.connect(self.logbox.appendPlainText)
        self.worker.done.connect(self._on_done)
        self.worker.failed.connect(self._on_failed)
        if sync:
            self.worker.run()
            return
        self.thread = QThread()
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.done.connect(self.thread.quit)
        self.worker.failed.connect(self.thread.quit)
        self.thread.start()

    def on_stop(self):
        if getattr(self, "worker", None):
            self.worker.stop = True

    def _on_progress(self, frac, text):
        self.bar.setValue(int(frac * 1000))
        self.statusBar().showMessage(text)

    def _on_failed(self, msg):
        self.btn_calc.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.logbox.appendPlainText(msg)
        self.statusBar().showMessage(msg)

    def _on_done(self, res):
        self.btn_calc.setEnabled(True)
        self.btn_stop.setEnabled(False)
        self.results = res
        self.oph.blockSignals(True)
        self.oph.clear()
        self.oph.addItems([PHASE_NAMES.get(ph.name, ph.name) for ph in res.phases])
        self.oph.setCurrentIndex(1 if len(res.phases) > 1 else 0)
        self.oph.blockSignals(False)
        self._mark_phases()
        self._draw_curve()
        self.tabs.setCurrentIndex(5)
        self.refresh_view()
        self.statusBar().showMessage("Perhitungan selesai.")

    # ------------------------------------------------------------------ project files
    def new_project(self):
        self.project, self.path = default_project(), None
        self.populate()

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Buka proyek", "", "Proyek GeoFEM (*.json)")
        if not path:
            return
        try:
            p = Project.load(path)
            err = p.validate()
            if err:
                raise ValueError("\n".join(err))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
            QMessageBox.critical(self, "Gagal membuka", f"Berkas tidak dapat dibaca:\n{exc}")
            return
        self.project, self.path = p, path
        self.populate()
        self.setWindowTitle(f"{APP_NAME} - {path}")

    def save_project(self):
        if not self.path:
            return self.save_project_as()
        try:
            self.collect().save(self.path)
            self.statusBar().showMessage(f"Proyek disimpan: {self.path}")
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Gagal menyimpan", str(exc))

    def save_project_as(self):
        path, _ = QFileDialog.getSaveFileName(self, "Simpan proyek", "proyek.json", "Proyek GeoFEM (*.json)")
        if path:
            self.path = path
            self.setWindowTitle(f"{APP_NAME} - {path}")
            self.save_project()

    # ------------------------------------------------------------------ export
    def _selected_phase(self):
        if self.results is None:
            QMessageBox.information(self, "Belum ada hasil", "Hitung model terlebih dahulu.")
            return None
        k = min(max(self.oph.currentIndex(), 0), len(self.results.phases) - 1)
        return self.results.phases[k]

    def export_picture(self):
        path, _ = QFileDialog.getSaveFileName(self, "Simpan gambar", "geofem3d.png", "Gambar PNG (*.png)")
        if path:
            self.plotter.screenshot(path)
            self.statusBar().showMessage(f"Gambar disimpan: {path}")

    def export_csv(self):
        ph = self._selected_phase()
        if ph is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Ekspor hasil titik nodal", f"hasil_{ph.name}.csv",
                                              "CSV (*.csv)")
        if not path:
            return
        n, U = self.mesh.nodes, ph.u * 1000
        data = np.column_stack([np.arange(len(n)), n, U, np.linalg.norm(U, axis=1)])
        np.savetxt(path, data, delimiter=",", fmt=["%d"] + ["%.6g"] * 7, comments="",
                   header="node,x_m,y_m,z_m,ux_mm,uy_mm,uz_mm,utot_mm")
        self.statusBar().showMessage(f"Hasil disimpan: {path}")

    def export_curve(self):
        ph = self._selected_phase()
        if ph is None:
            return
        ph = ph if ph.name == "Safety" else self.results.phase("Load")
        if ph is None or not ph.curve:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Ekspor kurva", f"kurva_{ph.name}.csv", "CSV (*.csv)")
        if path:
            head = "SumMsf,du_maks_m" if ph.name == "Safety" else "q_kPa,penurunan_m"
            np.savetxt(path, np.array(ph.curve), delimiter=",", fmt="%.6g", comments="", header=head)
            self.statusBar().showMessage(f"Kurva disimpan: {path}")

    def _mark_phases(self):
        """Green tick / red cross on the phase list after a calculation."""
        ok_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogApplyButton)
        bad_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton)
        res = self.results
        for i in range(self.phase_list.topLevelItemCount()):
            it = self.phase_list.topLevelItem(i)
            if res is not None and i < len(res.phases):
                it.setIcon(0, ok_icon if res.phases[i].ok else bad_icon)
                it.setToolTip(0, res.phases[i].message)
            else:
                it.setIcon(0, QIcon())

    # ------------------------------------------------------------------ 3D view
    def _grid(self, U=None, scale=0.0):
        m = self.mesh
        pts = m.nodes + (scale * U if U is not None else 0.0)
        return pv.UnstructuredGrid({pv.CellType.QUADRATIC_TETRA: m.elems[:, fem.GMSH_TO_VTK_TET10]}, pts)

    def _mirror(self, g):
        if not self.project.domain.symmetry:
            return g
        g = g.merge(g.reflect((1, 0, 0), point=(0, 0, 0)))
        return g.merge(g.reflect((0, 1, 0), point=(0, 0, 0)))

    def refresh_view(self):
        pl = self.plotter
        pl.clear()
        try:
            if self.results is not None and self.tabs.currentIndex() in (4, 5):
                self._show_results()
            elif self.mesh is not None and self.tabs.currentIndex() >= 2:
                self._show_mesh()
            else:
                self._show_geometry()
        except Exception as exc:  # a drawing problem must not take the window down
            self.statusBar().showMessage(f"Gagal menggambar: {exc}")
        pl.add_axes()
        pl.render()

    def _show_geometry(self):
        p, pl = self.project, self.plotter
        hx, hy = p.domain.Lx / 2, p.domain.Ly / 2
        for l in p.borehole.layers:
            m = p.material(l.material)
            box = pv.Box((-hx, hx, -hy, hy, l.bottom, l.top))
            pl.add_mesh(box, color=m.color, opacity=0.55, show_edges=True, edge_color="#6b5a45",
                        label=m.name)
        zt, zb = p.ground_level, p.bottom_level
        if zb < p.borehole.water_level < zt:
            pl.add_mesh(pv.Plane(center=(0, 0, p.borehole.water_level), direction=(0, 0, 1),
                                 i_size=2 * hx, j_size=2 * hy),
                        color="#3a7bd5", opacity=0.35)
        f = p.footing
        t = 0.02 * max(p.domain.Lx, p.domain.Ly)
        pl.add_mesh(pv.Box((-f.B / 2, f.B / 2, -f.L / 2, f.L / 2, zt, zt + t)), color="#5c6770")
        arrows = pv.Arrow(start=(0, 0, zt + 6 * t), direction=(0, 0, -1), scale=5 * t)
        pl.add_mesh(arrows, color="#c0392b")
        pl.add_text("Geometri model", font_size=10, color="#1f2a33")
        pl.view_isometric()

    def _show_mesh(self):
        g = self._grid()
        g.cell_data["lapisan"] = self.mesh.elem_layer
        g = self._mirror(g)
        cols = [self.project.material(l.material).color for l in self.project.borehole.layers]
        self.plotter.add_mesh(g, scalars="lapisan", cmap=cols, show_edges=True, edge_color="#40474d",
                              show_scalar_bar=False, n_colors=len(cols),
                              clim=(-0.5, len(cols) - 0.5))
        self.plotter.add_text(f"Jaring: {self.mesh.n_elems} elemen tet-10", font_size=10, color="#1f2a33")
        self.plotter.view_isometric()

    def _show_results(self):
        res = self.results
        k = max(self.oph.currentIndex(), 0)
        ph = res.phases[min(k, len(res.phases) - 1)]
        q = self.oq.currentIndex()
        U = ph.u
        umax = float(np.abs(U).max())
        size = max(self.project.domain.Lx, self.project.domain.Ly)
        scale = self.oscale.value() or (0.08 * size / umax if umax > 0 else 0.0)
        g = self._grid(U, scale)
        sig = ph.sig
        if q == 0:
            g.point_data["v"] = np.linalg.norm(U, axis=1) * 1000
        elif q == 1:
            g.point_data["v"] = U[:, 2] * 1000
        elif q == 2:
            g.cell_data["v"] = sig[..., 2].mean(1)
        elif q == 3:
            g.cell_data["v"] = (sig[..., 2] - res.pw).mean(1)
        elif q == 5:
            g.point_data["v"] = U[:, 0] * 1000
        elif q == 6:
            g.cell_data["v"] = (-sig[..., :3].sum(-1) / 3.0).mean(1)
        elif q == 7:
            p_ = np.linalg.eigvalsh(voigt_to_tensor(sig.reshape(-1, 6)))
            g.cell_data["v"] = (p_[:, 2] - p_[:, 0]).reshape(sig.shape[:2]).mean(1)
        elif q == 8:
            g.point_data["v"] = np.linalg.norm(ph.du, axis=1) * 1000
        else:
            g.cell_data["v"] = ph.plastic.mean(1)
        g = self._mirror(g)
        cut = self.ocut.currentIndex()
        if cut:
            g = g.clip(normal="y" if cut == 1 else "x", origin=(0.0, 0.0, 0.0), invert=False)
        title = QUANTITIES[q]
        if q == 4:
            self.plotter.add_mesh(g, color="#d7dde2", opacity=0.25, show_edges=self.oedges.isChecked())
            pts = res.model.kin.xgp[ph.plastic]
            if len(pts):
                if self.project.domain.symmetry:
                    pts = np.vstack([pts * s for s in ([1, 1, 1], [-1, 1, 1], [1, -1, 1], [-1, -1, 1])])
                self.plotter.add_points(pts, color="#d62728", point_size=6, render_points_as_spheres=True)
        else:
            self.plotter.add_mesh(g, scalars="v", cmap="turbo", show_edges=self.oedges.isChecked(),
                                  scalar_bar_args={"title": _vtk_text(title.split(" (")[0]) + "\n"
                                                   + title[title.find("("):],
                                                   "vertical": True, "position_x": 0.80, "width": 0.07,
                                                   "title_font_size": 14, "label_font_size": 12,
                                                   "color": "#1f2a33", "fmt": "%.3g"})
        self.plotter.add_text(_vtk_text(f"{PHASE_NAMES.get(ph.name, ph.name)}\n{title}\n"
                                        f"skala deformasi {scale:.0f}x"),
                              font_size=9, color="#1f2a33")
        self.plotter.view_isometric()

    # ------------------------------------------------------------------ curve + summary
    def _draw_curve(self):
        ax = self.ax
        ax.clear()
        ax.grid(True, alpha=0.3)
        res = self.results
        ph_sel = None
        if res is not None and self.oph.currentIndex() >= 0 and self.oph.currentIndex() < len(res.phases):
            ph_sel = res.phases[self.oph.currentIndex()]
        if ph_sel is not None and ph_sel.name == "Safety" and len(ph_sel.curve) > 1:
            c = np.array(ph_sel.curve)
            ax.plot(c[:, 1] * 1000, c[:, 0], "o-", color="#b5532a", ms=3)
            ax.set_xlabel("|Δu| maks. (mm)")
            ax.set_ylabel("ΣMsf")
            self.curve_title.setText("Kurva reduksi φ-c (ΣMsf)")
        else:
            ax.set_xlabel("Penurunan fondasi (mm)")
            ax.set_ylabel("Beban q (kPa)")
            self.curve_title.setText("Kurva beban - penurunan")
        if res is not None and res.phase("Load") is not None:
            if not (ph_sel is not None and ph_sel.name == "Safety"):
                c = np.array(res.phase("Load").curve)
                ax.plot(c[:, 1] * 1000, c[:, 0], "o-", color="#0d6e6e", ms=3)
            s = [f"<b>Penurunan fondasi:</b> {res.footing_settlement * 1000:.2f} mm",
                 f"<b>Penurunan maksimum:</b> {res.max_settlement * 1000:.2f} mm",
                 f"<b>Beban tercapai:</b> {res.phase('Load').load_fraction * self.project.footing.q:.1f} kPa"
                 f" dari {self.project.footing.q:.1f} kPa",
                 f"<b>Titik plastis:</b> {int(res.phase('Load').plastic.sum())}"]
            sf = res.safety_factor
            s.append(f"<b>Angka keamanan SF:</b> {sf:.3f}" if sf is not None else
                     "<b>Angka keamanan SF:</b> tidak dihitung")
            s.append(f"<b>Waktu hitung:</b> {res.run_time:.1f} detik")
            self.summary.setText("<br>".join(s))
        else:
            ax.text(0.5, 0.5, "belum ada hasil", ha="center", va="center", transform=ax.transAxes,
                    color="#888")
            self.summary.setText("Belum ada hasil perhitungan.")
        self.canvas.draw_idle()

    # ------------------------------------------------------------------ picture of the window
    def save_picture(self, path):
        img = self.grab().toImage()
        arr = np.ascontiguousarray(self.plotter.screenshot(return_img=True)[..., :3])
        h, w = arr.shape[:2]
        qimg = QImage(arr.data, w, h, 3 * w, QImage.Format_RGB888).copy()
        pos = self.plotter.mapTo(self, QPoint(0, 0))
        painter = QPainter(img)
        painter.drawImage(QRect(pos, self.plotter.size()), qimg)
        painter.end()
        return img.save(path)

    def closeEvent(self, ev):
        self.on_stop()
        if self.thread is not None:
            self.thread.quit()
            self.thread.wait(3000)
        self.plotter.close()
        super().closeEvent(ev)


# ======================================================================== entry point
def _quiet_show(win):
    """Show without taking focus; on Windows also put the window behind the others."""
    win.setAttribute(Qt.WA_ShowWithoutActivating, True)
    win.show()
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.user32.SetWindowPos(int(win.winId()), 1, 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010)


def _self_test(win, out):
    steps = []
    t0 = time.perf_counter()
    # scripted input, like a user would do: smaller mesh, set load, mesh, calculate
    win.mc.setValue(4.0)
    win.mf.setValue(0.8)
    win.fq.setValue(150.0)
    meshed = win.on_mesh()
    win.on_calc(sync=True)
    QApplication.processEvents()
    res = win.results
    s = res.footing_settlement * 1000 if res else 0.0
    steps.append({"step": "move", "passed": bool(meshed and res is not None and s > 0),
                  "detail": f"footing settled {s:.2f} mm under q = {win.fq.value():.0f} kPa "
                            f"({win.mesh.n_elems if win.mesh else 0} elements)"})
    sf = res.safety_factor if res else None
    load = res.phase("Load") if res else None
    ok = bool(load is not None and load.ok and sf is not None and sf > 1.0)
    steps.append({"step": "act", "passed": ok,
                  "detail": f"phases run: {[p.name for p in res.phases] if res else []}, "
                            f"load fraction {load.load_fraction if load else 0:.2f}, SF = {sf}"})
    win.tabs.setCurrentIndex(5)
    win.refresh_view()
    QApplication.processEvents()
    text = win.summary.text()
    nline = len(win.ax.lines[0].get_xdata()) if win.ax.lines else 0
    nact = len(win.plotter.renderer.actors)
    hud = "Penurunan fondasi" in text and "SF" in text and nline > 2 and nact > 0
    steps.append({"step": "hud", "passed": bool(hud),
                  "detail": f"summary shows settlement and SF, load-settlement curve has {nline} points, "
                            f"3D view has {nact} actors"})
    # cross-section of the deviatoric stress and the phi-c reduction curve
    win.ocut.setCurrentIndex(1)
    win.oq.setCurrentIndex(7)
    win.oph.setCurrentIndex(len(res.phases) - 1)
    QApplication.processEvents()
    ok_cut = len(win.plotter.renderer.actors) > 0 and win.ax.get_ylabel() == "ΣMsf"
    steps.append({"step": "cut", "passed": bool(ok_cut),
                  "detail": f"cut view actors {len(win.plotter.renderer.actors)}, curve y-label {win.ax.get_ylabel()}"})
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "steps": steps, "seconds": round(time.perf_counter() - t0, 1)}, fh, indent=2)


def run(args) -> int:
    app = QApplication.instance() or QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    project = None
    if args.project:
        project = Project.load(args.project)
    win = MainWindow(project)
    if args.screenshot or args.self_test:
        _quiet_show(win)
        state = {"frames": 0}

        def tick():
            state["frames"] += 1
            win.plotter.render()
            if state["frames"] < 120:
                return
            timer.stop()
            if args.self_test:
                _self_test(win, args.self_test)
            if args.screenshot:
                win.save_picture(args.screenshot)
            win.close()
            app.quit()

        timer = QTimer()
        timer.timeout.connect(tick)
        timer.start(16)
    else:
        win.show()
    return app.exec()
