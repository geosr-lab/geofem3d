"""Tema tampilan GeoFEM 3D, diselaraskan dengan sistem tampilan GeoSR (DESIGN.md / gaya.css).

Warna diambil dari token GeoSR (kertas lab, lempung gley, laterit, enam warna lapisan) dalam
versi terang dan gelap. Huruf: Archivo untuk judul dan angka, Plus Jakarta Sans untuk teks,
keduanya SIL Open Font License 1.1 (lisensi di aset/font/).
"""
from __future__ import annotations

from pathlib import Path

ASET = Path(__file__).resolve().parent / "aset"

TERANG = {
    "latar": "#f1f2ec", "permukaan": "#fbfbf8", "permukaan2": "#e8eae1", "garis": "#d2d6ca",
    "teks": "#1c2427", "teks2": "#515a5b", "aksen": "#1d6a63", "aksen_tekan": "#14514b",
    "aksen_teks": "#ffffff", "laterit": "#a3401f", "galat": "#a3261f",
    "lapis": ["#d6b25f", "#8fa89b", "#c8b693", "#6f8189", "#b5532e", "#5e4835"],
    "air": "#3b7ea1", "pondasi": "#515a5b", "beban": "#a3401f", "kisi": "#dfe3d6",
}
GELAP = {
    "latar": "#10181a", "permukaan": "#162124", "permukaan2": "#1e2c2f", "garis": "#2d3e41",
    "teks": "#e5e8e1", "teks2": "#a2aca6", "aksen": "#62c7b8", "aksen_tekan": "#4aa799",
    "aksen_teks": "#10181a", "laterit": "#ee966b", "galat": "#ff9a8c",
    "lapis": ["#c19d4c", "#6f9282", "#a8966f", "#7f949d", "#d07148", "#8c6e52"],
    "air": "#6fb3d6", "pondasi": "#a2aca6", "beban": "#ee966b", "kisi": "#22323a",
}

HURUF_TEKS = "Plus Jakarta Sans"
HURUF_JUDUL = "Archivo"


def muat_huruf(app=None):
    """Daftarkan huruf GeoSR ke Qt dan pakai sebagai huruf aplikasi; True bila berhasil."""
    from PySide6.QtGui import QFont, QFontDatabase

    ok = True
    for f in sorted((ASET / "font").glob("*.ttf")):
        ok &= QFontDatabase.addApplicationFont(str(f)) >= 0
    if ok and app is not None:
        f = QFont(HURUF_TEKS)
        f.setPointSizeF(10)
        f.setWordSpacing(1.6)       # spasi bawaan Plus Jakarta Sans (0,17 em) terlalu rapat di layar
        app.setFont(f)
    return ok


def qss(t: dict) -> str:
    return f"""
QMainWindow, QWidget {{ background: {t['latar']}; color: {t['teks']}; }}
QMenuBar {{ background: {t['latar']}; border-bottom: 1px solid {t['garis']}; }}
QMenuBar::item:selected, QMenu::item:selected {{ background: {t['permukaan2']}; color: {t['teks']}; }}
QMenu {{ background: {t['permukaan']}; border: 1px solid {t['garis']}; }}
QToolBar {{ background: {t['latar']}; border: none; border-bottom: 1px solid {t['garis']}; spacing: 4px; padding: 4px; }}
QToolButton {{ border: 1px solid transparent; border-radius: 6px; padding: 4px 8px; }}
QToolButton:hover {{ background: {t['permukaan']}; border-color: {t['garis']}; }}
QToolButton:pressed {{ background: {t['permukaan2']}; }}
QTabWidget::pane {{ border: 1px solid {t['garis']}; border-radius: 8px; background: {t['permukaan']}; top: -1px; }}
QTabBar::tab {{ background: transparent; color: {t['teks2']}; padding: 8px 16px; border: none;
    border-bottom: 3px solid transparent; font-weight: 600; }}
QTabBar::tab:hover {{ color: {t['teks']}; }}
QTabBar::tab:selected {{ color: {t['aksen']}; border-bottom: 3px solid {t['aksen']}; }}
QPushButton {{ background: {t['aksen']}; color: {t['aksen_teks']}; border: none;
    border-bottom: 3px solid {t['aksen_tekan']}; padding: 6px 14px; border-radius: 6px; font-weight: 700; }}
QPushButton:hover {{ background: {t['aksen_tekan']}; }}
QPushButton:pressed {{ border-bottom-width: 1px; margin-top: 2px; }}
QPushButton:disabled {{ background: {t['permukaan2']}; color: {t['teks2']}; border-bottom-color: {t['garis']}; }}
QTreeWidget, QTableWidget, QPlainTextEdit, QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {t['permukaan']}; border: 1px solid {t['garis']}; border-radius: 6px;
    selection-background-color: {t['aksen']}; selection-color: {t['aksen_teks']}; }}
QSpinBox, QDoubleSpinBox, QComboBox {{ padding: 3px 6px; min-height: 22px; }}
QComboBox QAbstractItemView {{ background: {t['permukaan']}; border: 1px solid {t['garis']}; }}
QTableWidget {{ gridline-color: {t['garis']}; }}
QHeaderView::section {{ background: {t['permukaan2']}; color: {t['teks2']}; border: none;
    border-bottom: 1px solid {t['garis']}; padding: 5px 6px; font-weight: 700; }}
QProgressBar {{ background: {t['permukaan2']}; border: 1px solid {t['garis']}; border-radius: 6px;
    text-align: center; height: 14px; }}
QProgressBar::chunk {{ background: {t['aksen']}; border-radius: 5px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border: 1px solid {t['garis']}; border-radius: 4px;
    background: {t['permukaan']}; }}
QCheckBox::indicator:checked {{ background: {t['aksen']}; border-color: {t['aksen']}; }}
QSplitter::handle {{ background: {t['garis']}; }}
QStatusBar {{ background: {t['latar']}; color: {t['teks2']}; border-top: 1px solid {t['garis']}; }}
QLabel#title {{ font-family: "{HURUF_JUDUL}"; font-weight: 800; font-size: 11pt; color: {t['teks']}; }}
QScrollBar:vertical, QScrollBar:horizontal {{ background: {t['latar']}; border: none; width: 10px; height: 10px; }}
QScrollBar::handle {{ background: {t['garis']}; border-radius: 5px; min-height: 24px; min-width: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QToolTip {{ background: {t['permukaan']}; color: {t['teks']}; border: 1px solid {t['garis']}; }}
"""


def gaya_grafik(ax, fig, t: dict):
    """Warnai sumbu Matplotlib dengan token tema (bidang plot seperti kertas milimeter)."""
    fig.set_facecolor(t["permukaan"])
    ax.set_facecolor(t["latar"])
    for s in ax.spines.values():
        s.set_color(t["garis"])
    ax.tick_params(colors=t["teks2"], labelsize=8)
    ax.xaxis.label.set_color(t["teks2"])
    ax.yaxis.label.set_color(t["teks2"])
    ax.grid(True, which="major", color=t["kisi"], linewidth=0.8)
    ax.minorticks_on()
    ax.grid(True, which="minor", color=t["kisi"], linewidth=0.3)
