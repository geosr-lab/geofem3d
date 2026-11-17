"""GeoFEM 3D - titik masuk program.

    python main.py [proyek.json]
    python main.py --screenshot shots/now.png     (simpan gambar jendela lalu keluar)
    python main.py --self-test hasil.json         (uji otomatis alur kerja lalu keluar)
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser(description="GeoFEM 3D - analisis elemen hingga geoteknik 3D")
    ap.add_argument("project", nargs="?", help="berkas proyek .json untuk dibuka")
    ap.add_argument("--screenshot", metavar="FILE.png", help="simpan gambar jendela lalu keluar")
    ap.add_argument("--self-test", metavar="FILE.json", help="jalankan uji alur kerja lalu keluar")
    args = ap.parse_args()
    from geofem.gui import run
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
