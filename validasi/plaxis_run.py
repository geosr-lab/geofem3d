"""Bangun dan hitung model GeoFEM 3D yang sama di PLAXIS 3D lewat Python Remote Scripting resmi.

Dijalankan dengan Python bawaan PLAXIS (Python 3.7, berisi paket plxscripting), bukan .venv:

    "C:\\Program Files\\Bentley\\Geotechnical\\PLAXIS 3D CONNECT Edition V20\\python\\python.exe" ^
        validasi\\plaxis_run.py proyek.json referensi_plaxis.json

Biasanya tidak dijalankan langsung, tetapi lewat validasi\\bandingkan_plaxis.py.

Syarat: PLAXIS 3D Input terbuka dengan server scripting aktif (menu Expert > Configure remote
scripting server). Port dan kata sandi dibaca dari variabel lingkungan:
    PLAXIS_INPUT_PORT   (bawaan 10000)
    PLAXIS_OUTPUT_PORT  (bawaan 10001)
    PLAXIS_PASSWORD     (wajib; tidak pernah disimpan di berkas)

Hanya API resmi yang dipakai. Nama properti material ada di PROP_MC / PROP_HS di bawah; bila
PLAXIS menolak sebuah nama, cocokkan dengan jendela material PLAXIS (arahkan kursor ke kolom
untuk melihat nama properti) lalu ubah di sini.
"""
import json
import os
import sys

PROP_COMMON = {"name": "MaterialName", "model": "SoilModel", "drainage": "DrainageType",
               "gamma_unsat": "gammaUnsat", "gamma_sat": "gammaSat",
               "c": "cref", "phi": "phi", "psi": "psi"}
PROP_MC = {"E": "Eref", "nu": "nu"}
PROP_HS = {"E50ref": "E50ref", "Eoedref": "EoedRef", "Eurref": "EurRef", "m": "powerm",
           "pref": "pRef", "nu_ur": "nu", "Rf": "Rf"}
SOIL_MODEL_ID = {"Mohr-Coulomb": 2, "Hardening Soil": 3}
DRAINED = 0


def fail(msg):
    sys.stderr.write("GAGAL: " + msg + "\n")
    sys.exit(2)


def connect():
    try:
        from plxscripting.easy import new_server
    except ImportError:
        fail("paket plxscripting tidak ditemukan. Jalankan skrip ini dengan python.exe bawaan PLAXIS.")
    pw = os.environ.get("PLAXIS_PASSWORD")
    if not pw:
        fail("variabel lingkungan PLAXIS_PASSWORD belum diisi.")
    pin = int(os.environ.get("PLAXIS_INPUT_PORT", "10000"))
    pout = int(os.environ.get("PLAXIS_OUTPUT_PORT", "10001"))
    try:
        s_i, g_i = new_server("localhost", pin, password=pw)
    except Exception as exc:
        fail("tidak bisa terhubung ke PLAXIS Input di port %d (%s). Pastikan PLAXIS 3D Input terbuka "
             "dan server scripting aktif." % (pin, exc))
    return s_i, g_i, pin, pout, pw


def material_pairs(m):
    pairs = [PROP_COMMON["name"], m["name"], PROP_COMMON["model"], SOIL_MODEL_ID[m.get("model", "Mohr-Coulomb")],
             PROP_COMMON["drainage"], DRAINED,
             PROP_COMMON["gamma_unsat"], m["gamma_unsat"], PROP_COMMON["gamma_sat"], m["gamma_sat"],
             PROP_COMMON["c"], m["c"], PROP_COMMON["phi"], m["phi"], PROP_COMMON["psi"], m["psi"]]
    extra = PROP_HS if m.get("model") == "Hardening Soil" else PROP_MC
    for key, prop in extra.items():
        pairs += [prop, m[key]]
    return pairs


def build_and_run(p, g_i):
    d, f = p["domain"], p["footing"]
    layers, bh = p["borehole"]["layers"], p["borehole"]
    # full model (PLAXIS needs no symmetry here); footing centred at (0, 0)
    g_i.SoilContour.initializerectangular(-d["Lx"] / 2, -d["Ly"] / 2, d["Lx"] / 2, d["Ly"] / 2)
    borehole = g_i.borehole(0, 0)
    borehole.Head = bh["water_level"]
    for lay in layers:
        g_i.soillayer(lay["top"] - lay["bottom"])
    mats = {}
    for m in p["materials"]:
        mats[m["name"]] = g_i.soilmat(*material_pairs(m))
    for i, lay in enumerate(layers):
        sl = g_i.Soillayers[i]
        sl.Zones[0].Top = lay["top"]
        sl.Zones[0].Bottom = lay["bottom"]
        sl.Soil.Material = mats[lay["material"]]

    g_i.gotostructures()
    x0, x1, y0, y1, z = -f["B"] / 2, f["B"] / 2, -f["L"] / 2, f["L"] / 2, layers[0]["top"]
    load = g_i.surfload((x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z))
    surf_load = load[-1] if isinstance(load, (list, tuple)) else load

    g_i.gotomesh()
    g_i.mesh(0.05)

    g_i.gotostages()
    ph0 = g_i.InitialPhase                               # K0 procedure is the default
    ph1 = g_i.phase(ph0)
    ph1.Identification = "GeoFEM - beban fondasi"
    g_i.activate(surf_load, ph1)
    surf_load.sigz[ph1] = -f["q"]
    phases = [ph0, ph1]
    if p["phases"].get("run_safety", True):
        ph2 = g_i.phase(ph1)
        ph2.Identification = "GeoFEM - reduksi phi-c"
        ph2.DeformCalcType = "Safety"
        phases.append(ph2)
    g_i.calculate()
    return phases


def read_results(g_i, phases, pout, pw, z_top):
    from plxscripting.easy import new_server
    g_i.view(phases[1])
    try:
        s_o, g_o = new_server("localhost", pout, password=pw)
    except Exception as exc:
        fail("tidak bisa terhubung ke PLAXIS Output di port %d (%s)." % (pout, exc))
    ph_o = g_o.Phases[1]
    xs = g_o.getresults(ph_o, g_o.ResultTypes.Soil.X, "node")
    ys = g_o.getresults(ph_o, g_o.ResultTypes.Soil.Y, "node")
    zs = g_o.getresults(ph_o, g_o.ResultTypes.Soil.Z, "node")
    uz = g_o.getresults(ph_o, g_o.ResultTypes.Soil.Uz, "node")
    best, centre_uz, min_uz = None, 0.0, 0.0
    for x, y, zz, u in zip(xs, ys, zs, uz):
        min_uz = min(min_uz, u)
        dist = x * x + y * y + (zz - z_top) ** 2
        if best is None or dist < best:
            best, centre_uz = dist, u
    out = {"sumber": "PLAXIS 3D (Python Remote Scripting)",
           "footing_settlement_mm": -centre_uz * 1000.0,
           "max_settlement_mm": -min_uz * 1000.0,
           "SF": None}
    if len(phases) > 2:
        out["SF"] = float(phases[2].Reached.SumMsf.value)
    return out


def main():
    if len(sys.argv) != 3:
        fail("pemakaian: plaxis_run.py proyek.json referensi_plaxis.json")
    with open(sys.argv[1], encoding="utf-8") as fh:
        p = json.load(fh)
    s_i, g_i, pin, pout, pw = connect()
    s_i.new()
    phases = build_and_run(p, g_i)
    for ph in phases[1:]:
        if ph.CalculationResult.value != 1:                 # 1 = calculation OK
            sys.stderr.write("Peringatan: fase %s tidak selesai dengan baik di PLAXIS.\n" % ph.Identification.value)
    out = read_results(g_i, phases, pout, pw, p["borehole"]["layers"][0]["top"])
    with open(sys.argv[2], "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2)
    print("Hasil PLAXIS disimpan ke %s" % sys.argv[2])


if __name__ == "__main__":
    main()
