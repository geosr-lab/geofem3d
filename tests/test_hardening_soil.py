"""Hardening Soil: drained triaxial compression on one material point."""
import numpy as np

from geofem.hardening_soil import hs_update, initial_gamma_p, ur_moduli
from geofem.material import triaxial_failure_stress


def triaxial(prm, s3=100.0, eps_max=0.05, n=400):
    """Strain controlled axial compression, constant cell pressure s3 (compression positive).
    Returns axial strain (compression positive) and deviator q."""
    P = {k: np.array([v], float) for k, v in prm.items()}
    sig = np.array([[-s3, -s3, -s3, 0, 0, 0]], float)
    gp = initial_gamma_p(sig, P)
    de = eps_max / n
    ea, qs = [0.0], [0.0]
    eps_tot = 0.0
    for _ in range(n):
        K, G = ur_moduli(sig, P)
        lat = 0.0
        for _ in range(60):          # lateral strain keeps the cell pressure constant
            d = np.array([[lat, lat, -de, 0, 0, 0]])
            s, g, _, _ = hs_update(sig, gp, d, P, K, G)
            err = s[0, 0] + s3
            if abs(err) < 1e-8 * s3:
                break
            lat -= err / (2.0 * (K[0] + G[0] / 3.0))
        sig, gp = s, g
        eps_tot += de
        ea.append(eps_tot)
        qs.append(-(sig[0, 2] - sig[0, 0]))
    return np.array(ea), np.array(qs)


PRM = dict(E50ref=20000.0, Eurref=60000.0, m=0.5, pref=100.0, Rf=0.9,
           c=0.0, phi=np.radians(32.0), psi=0.0, nu_ur=0.2)


def test_secant_modulus_at_half_failure_equals_E50():
    ea, q = triaxial(PRM, s3=100.0)
    qf = triaxial_failure_stress(100.0, 0.0, 32.0) - 100.0
    e50 = np.interp(0.5 * qf, q, ea)
    assert abs((0.5 * qf / e50) / PRM["E50ref"] - 1.0) < 0.03


def test_failure_reaches_mohr_coulomb_line():
    ea, q = triaxial(PRM, s3=100.0, eps_max=0.2, n=800)
    qf = triaxial_failure_stress(100.0, 0.0, 32.0) - 100.0
    assert abs(q.max() / qf - 1.0) < 0.01


def test_stiffness_depends_on_confining_pressure():
    _, q1 = triaxial(PRM, s3=100.0, eps_max=0.001, n=100)
    _, q4 = triaxial(PRM, s3=400.0, eps_max=0.001, n=100)
    # m = 0.5, c = 0: stiffness ratio sqrt(4) = 2 at the same small strain
    assert abs(q4[10] / q1[10] - 2.0) < 0.05
