"""Pemetaan material GeoFEM -> properti PLAXIS (tanpa perlu PLAXIS berjalan)."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "validasi"))

import plaxis_run  # noqa: E402


def _pairs(path, name):
    p = json.loads((ROOT / "contoh" / path).read_text(encoding="utf-8"))
    m = next(m for m in p["materials"] if m["name"] == name)
    pairs = plaxis_run.material_pairs(m)
    return dict(zip(pairs[0::2], pairs[1::2]))


def test_mohr_coulomb_mapping():
    d = _pairs("pondasi_pasir_lempung.json", "Pasir")
    assert d["SoilModel"] == 2 and d["Eref"] == 30000.0 and d["phi"] == 32.0
    assert "E50ref" not in d


def test_hardening_soil_mapping():
    d = _pairs("pondasi_hardening_soil.json", "Pasir")
    assert d["SoilModel"] == 3
    assert d["E50ref"] == 30000.0 and d["EurRef"] == 90000.0 and d["powerm"] == 0.5
    assert "Eref" not in d
