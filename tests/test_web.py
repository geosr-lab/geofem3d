"""Versi web: jaring terstruktur dan keluaran JSON (tanpa gmsh)."""
import json

import numpy as np

from geofem import mesh_terstruktur, web
from geofem.project import default_project
from geofem.solver import run_analysis


def test_structured_mesh_hits_footing_edges_and_layers():
    p = default_project()
    m = mesh_terstruktur.generate(p, "kasar")
    x, y, z = m.nodes.T
    assert np.any(np.isclose(x, p.footing.B / 2)) and np.any(np.isclose(y, p.footing.L / 2))
    for l in p.borehole.layers:
        assert np.any(np.isclose(z, l.bottom))
    assert np.any(np.isclose(z, p.borehole.water_level))
    assert np.isclose(fem_volume(m), (p.domain.Lx / 2) * (p.domain.Ly / 2) * (p.ground_level - p.bottom_level))


def fem_volume(m):
    from geofem.fem import Kinematics
    return Kinematics(m.nodes, m.elems).volume


def test_web_output_matches_gmsh_order_of_magnitude():
    p = default_project()
    p.phases.run_safety = False
    out = json.loads(web.hitung(json.dumps(p.to_dict()), "kasar"))
    s = out["ringkasan"]["penurunan_pondasi_mm"]
    assert 10.0 < s < 20.0                     # jaring gmsh halus: 14,2 mm
    n = len(out["titik"]) // 3
    assert max(out["segitiga"]) < n and len(out["segitiga"]) % 3 == 0
    assert len(out["fase"][1]["u"]) == 3 * n
    assert len(out["fase"][1]["szz"]) == len(out["segitiga"]) // 3
    # potongan di bidang y = 0 hanya memakai dua salinan cermin pertama
    assert max(out["segitiga_potong"]) < 2 * n // 4
    assert len(out["fase"][1]["szz_p"]) == len(out["segitiga_potong"]) // 3


def test_web_reports_invalid_input():
    p = default_project()
    p.footing.B = -1
    out = json.loads(web.hitung(json.dumps(p.to_dict())))
    assert out["galat"]
