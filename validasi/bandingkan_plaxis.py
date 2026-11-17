"""Validasi otomatis GeoFEM 3D terhadap PLAXIS 3D.

    .venv\\Scripts\\python.exe validasi\\bandingkan_plaxis.py proyek.json [--keluar folder] [--tol 0.10]

Langkah:
1. Hitung proyek dengan GeoFEM 3D.
2. Bangun dan hitung model yang sama di PLAXIS 3D lewat Python Remote Scripting resmi
   (validasi\\plaxis_run.py dijalankan dengan python.exe bawaan PLAXIS).
3. Tulis tabel perbandingan (CSV dan Markdown) beserta selisih dalam persen.

PLAXIS tidak wajib untuk aplikasi maupun test; skrip ini hanya untuk validasi.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

PLAXIS_PY = os.environ.get(
    "PLAXIS_PYTHON",
    r"C:\Program Files\Bentley\Geotechnical\PLAXIS 3D CONNECT Edition V20\python\python.exe")
NAMES = {"footing_settlement_mm": "Penurunan pusat fondasi (mm)",
         "max_settlement_mm": "Penurunan maksimum (mm)", "SF": "Angka keamanan SF"}


def main(argv=None):
    from geofem.validation import compare, run_project

    ap = argparse.ArgumentParser(description="Bandingkan hasil GeoFEM 3D dengan PLAXIS 3D")
    ap.add_argument("project", help="berkas proyek GeoFEM (.json)")
    ap.add_argument("--keluar", default="hasil_validasi", help="folder hasil (bawaan: hasil_validasi)")
    ap.add_argument("--tol", type=float, default=0.10, help="toleransi selisih relatif (bawaan 0,10)")
    a = ap.parse_args(argv)

    out = Path(a.keluar)
    out.mkdir(parents=True, exist_ok=True)
    ours_path, ref_path = out / "hasil_geofem.json", out / "referensi_plaxis.json"

    print("1/3 Menghitung dengan GeoFEM 3D ...")
    ours = run_project(a.project, ours_path, log=lambda s: None)

    print("2/3 Menghitung model yang sama di PLAXIS 3D ...")
    if not Path(PLAXIS_PY).exists():
        print(f"GAGAL: python PLAXIS tidak ditemukan di {PLAXIS_PY}. Atur variabel PLAXIS_PYTHON.")
        return 2
    run = subprocess.run([PLAXIS_PY, str(Path(__file__).with_name("plaxis_run.py")), a.project, str(ref_path)],
                         capture_output=True, text=True)
    sys.stdout.write(run.stdout)
    if run.returncode != 0:
        sys.stderr.write(run.stderr)
        return run.returncode
    ref = json.loads(ref_path.read_text(encoding="utf-8"))

    print("3/3 Membandingkan ...")
    rows = compare(ours, ref, a.tol)
    with open(out / "perbandingan.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["besaran", "GeoFEM 3D", "PLAXIS 3D", "selisih (%)", "status"])
        for name, o, rf, d, ok in rows:
            w.writerow([NAMES.get(name, name), f"{o:.4g}", f"{rf:.4g}", f"{d * 100:.1f}", "OK" if ok else "BEDA"])
    md = ["| Besaran | GeoFEM 3D | PLAXIS 3D | Selisih | Status |", "|---|---:|---:|---:|---|"]
    md += [f"| {NAMES.get(n, n)} | {o:.4g} | {rf:.4g} | {d * 100:.1f} % | {'OK' if ok else 'BEDA'} |"
           for n, o, rf, d, ok in rows]
    (out / "perbandingan.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    print("\n".join(md))
    print(f"\nTabel tersimpan di {out / 'perbandingan.csv'} dan {out / 'perbandingan.md'}")
    return 0 if rows and all(r[4] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
