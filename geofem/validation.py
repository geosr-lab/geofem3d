"""Otomatisasi dan validasi tanpa GUI.

    python -m geofem.validation run proyek.json hasil.json
    python -m geofem.validation compare hasil.json referensi.json [--tol 0.10]

Berkas referensi (JSON) dibuat sendiri oleh pengguna, misalnya dari hasil program lain yang
diambil lewat API/skrip resmi program tersebut:
    {"footing_settlement_mm": 14.0, "SF": 1.2, "curve": [[q_kPa, settlement_mm], ...]}
Semua kunci opsional; hanya kunci yang ada yang dibandingkan.
"""
from __future__ import annotations

import argparse
import json
import sys

import numpy as np


def run_project(project_path, out_path=None, log=print):
    from .mesher import generate_mesh
    from .project import Project
    from .solver import run_analysis

    p = Project.load(project_path)
    err = p.validate()
    if err:
        raise ValueError("\n".join(err))
    res = run_analysis(p, generate_mesh(p), log=log)
    load = res.phase("Load")
    out = {"project": p.name, "footing_settlement_mm": res.footing_settlement * 1000,
           "max_settlement_mm": res.max_settlement * 1000, "SF": res.safety_factor,
           "load_fraction": load.load_fraction,
           "curve": [[q, s * 1000] for q, s in load.curve]}
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            json.dump(out, fh, indent=2)
    return out


def compare(ours: dict, ref: dict, tol=0.10):
    """Relative differences per quantity; returns list of (name, ours, ref, rel_diff, ok)."""
    rows = []
    for key in ("footing_settlement_mm", "max_settlement_mm", "SF"):
        if ref.get(key) is not None and ours.get(key) is not None:
            d = abs(ours[key] - ref[key]) / max(abs(ref[key]), 1e-12)
            rows.append((key, ours[key], ref[key], d, d <= tol))
    if ref.get("curve") and ours.get("curve"):
        c = np.array(ours["curve"], float)
        for q, s_ref in ref["curve"]:
            if c[0, 0] <= q <= c[-1, 0]:
                s = float(np.interp(q, c[:, 0], c[:, 1]))
                d = abs(s - s_ref) / max(abs(s_ref), 1e-12)
                rows.append((f"penurunan @ q={q:g} kPa", s, s_ref, d, d <= tol))
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser(description="GeoFEM 3D - otomatisasi dan validasi")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="hitung proyek tanpa GUI")
    r.add_argument("project")
    r.add_argument("out")
    c = sub.add_parser("compare", help="bandingkan hasil dengan referensi")
    c.add_argument("ours")
    c.add_argument("ref")
    c.add_argument("--tol", type=float, default=0.10)
    a = ap.parse_args(argv)
    if a.cmd == "run":
        run_project(a.project, a.out)
        return 0
    with open(a.ours, encoding="utf-8") as fh:
        ours = json.load(fh)
    with open(a.ref, encoding="utf-8") as fh:
        ref = json.load(fh)
    rows = compare(ours, ref, a.tol)
    for name, o, rf, d, ok in rows:
        print(f"{name:32s} GeoFEM={o:10.4g}  referensi={rf:10.4g}  selisih={d * 100:6.1f} %  "
              f"{'OK' if ok else 'BEDA'}")
    return 0 if rows and all(r[4] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
