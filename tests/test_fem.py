"""Uji verifikasi GeoFEM 3D: patch test elastis, penurunan lapisan elastis (solusi tertutup),
dan cek leleh Mohr-Coulomb satu elemen."""
import os
import sys

import numpy as np
import pytest
import scipy.sparse.linalg as spla

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from geofem import fem  # noqa: E402
from geofem.material import (apply_elastic, bulk_shear, elastic_D, mc_return, mc_yield,  # noqa: E402
                             triaxial_failure_stress)
from geofem.mesher import generate_mesh, structured_box_mesh  # noqa: E402
from geofem.project import Layer, Material, default_project  # noqa: E402
from geofem.solver import run_analysis  # noqa: E402


def test_elastic_patch_test():
    """A linear displacement field prescribed on the boundary is reproduced exactly inside
    and gives constant stresses at every Gauss point."""
    nodes, elems = structured_box_mesh(2.0, 2.0, 1.0, 2, 2, 2)
    kin = fem.Kinematics(nodes, elems)
    E, nu = 1e4, 0.3
    D = elastic_D(np.full(len(elems), E), np.full(len(elems), nu))
    K = kin.stiffness(D)
    A = np.array([[1e-3, 2e-4, -3e-4], [5e-4, -2e-3, 1e-4], [-1e-4, 3e-4, 1.5e-3]])
    exact = (nodes @ A.T + [1e-3, -2e-3, 5e-4]).ravel()
    lo, hi = nodes.min(0), nodes.max(0)
    bnd = (np.isclose(nodes, lo) | np.isclose(nodes, hi)).any(1)
    assert (~bnd).sum() > 0
    fixed = np.repeat(bnd, 3)
    u = np.where(fixed, exact, 0.0)
    free = ~fixed
    u[free] = spla.spsolve(K[free][:, free].tocsc(), -(K @ u)[free])
    assert np.allclose(u, exact, atol=1e-12)
    eps = np.array([A[0, 0], A[1, 1], A[2, 2], A[0, 1] + A[1, 0], A[1, 2] + A[2, 1], A[0, 2] + A[2, 0]])
    sig = np.einsum("eij,egj->egi", D, kin.strain(u))
    assert np.allclose(sig, elastic_D(E, nu) @ eps, atol=1e-8)


def test_uniform_load_on_elastic_layer_closed_form():
    """Uniform load q over the whole surface of a laterally confined layer:
    settlement s = q H / E_oed with E_oed = E (1 - nu) / ((1 + nu)(1 - 2 nu))."""
    E, nu, H, q = 10000.0, 0.3, 5.0, 100.0
    p = default_project()
    p.materials = [Material("Elastis", 0.0, 0.0, E, nu, 1e6, 0.0, 0.0)]
    p.borehole.layers = [Layer(0.0, -H, "Elastis")]
    p.borehole.water_level = -100.0
    p.domain.Lx = p.domain.Ly = 4.0
    p.footing.B = p.footing.L = 4.0        # load covers the whole top surface
    p.footing.q = q
    p.mesh.coarse = p.mesh.fine = 1.0
    p.phases.run_safety = False
    assert p.validate() == []
    res = run_analysis(p, generate_mesh(p))
    E_oed = E * (1 - nu) / ((1 + nu) * (1 - 2 * nu))
    assert res.footing_settlement == pytest.approx(q * H / E_oed, rel=1e-6)
    assert res.max_settlement == pytest.approx(q * H / E_oed, rel=1e-6)


def test_one_element_mohr_coulomb_yield():
    """One 10-node tetrahedron under homogeneous triaxial compression (strain driven):
    elastic below the strength, and at failure every Gauss point lies on the Mohr-Coulomb
    surface with sigma1 = sigma3 N_phi + 2 c sqrt(N_phi)."""
    nodes = np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]], float)
    mids = [(nodes[a] + nodes[b]) / 2 for a, b in fem.EDGES]
    nodes = np.vstack([nodes, mids])
    elems = fem.fix_orientation(nodes, np.arange(10)[None, :])
    kin = fem.Kinematics(nodes, elems)
    E, nu, c, phi_deg, p0 = 2e4, 0.3, 10.0, 30.0, 100.0
    K, G = bulk_shear(np.full(4, E), np.full(4, nu))
    cc, phi, psi = np.full(4, c), np.full(4, np.radians(phi_deg)), np.zeros(4)
    sig0 = np.tile([-p0, -p0, -p0, 0, 0, 0], (4, 1)).astype(float)

    def stress(ez, ex):
        u = (nodes * [ex, ex, -ez]).ravel()      # homogeneous strain: axial ez, lateral ex
        trial = sig0 + apply_elastic(K, G, kin.strain(u).reshape(-1, 6))
        return mc_return(trial, K, G, cc, phi, psi)

    # small axial strain: still elastic
    s, pl, _ = stress(1e-4, 0.0)
    assert not pl.any()
    # large axial strain with lateral strain that keeps sigma_lateral close to -p0
    s, pl, mode = stress(5e-2, 1.5e-2)
    assert pl.all() and np.allclose(s, s[0])
    f = mc_yield(s, cc, phi)
    assert np.abs(f).max() < 1e-6
    s_ax, s_lat = -s[0, 2], -min(s[0, 0], s[0, 1])
    assert s_ax == pytest.approx(triaxial_failure_stress(s_lat, c, phi_deg), rel=1e-6)


def test_validation_compare():
    from geofem.validation import compare
    ours = {"footing_settlement_mm": 10.0, "SF": 1.5, "curve": [[0, 0], [100, 10.0]]}
    rows = compare(ours, {"footing_settlement_mm": 10.5, "SF": 2.0, "curve": [[50, 5.0]]}, tol=0.1)
    assert [r[4] for r in rows] == [True, False, True]
