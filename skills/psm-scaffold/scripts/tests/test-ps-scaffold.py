#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test ps-scaffold.py — verifikasi kerangka valid & cross-version-safe.

Bukti inti: kerangka hasil generate LOLOS ps-static-scan psm-validate di 3 versi.
Jalankan: uv run scripts/tests/test-ps-scaffold.py
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

# __file__ = .../skills/psm-scaffold/scripts/tests/test-ps-scaffold.py
GEN = Path(__file__).resolve().parent.parent / "ps-scaffold.py"          # skills/psm-scaffold/scripts/ps-scaffold.py
SKILLS_DIR = Path(__file__).resolve().parents[3]                          # skills/
SCAN = SKILLS_DIR / "psm-validate" / "scripts" / "ps-static-scan.py"


def gen(dest, name, *extra):
    p = subprocess.run(["uv", "run", str(GEN), name, "--dest", str(dest), "--author", "Budi", *extra],
                       capture_output=True, text=True)
    return p.returncode, (json.loads(p.stdout) if p.stdout.strip().startswith("{") else None), p.stderr


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    return cond


def main():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        rc, res, err = gen(tmp, "ps_mybanner")
        ok &= check("generate sukses (rc=0)", rc == 0 and res is not None)
        mod = tmp / "ps_mybanner"
        ok &= check("main file ada", (mod / "ps_mybanner.php").is_file())
        ok &= check("composer.json ada", (mod / "composer.json").is_file())

        # index.php di SETIAP folder
        all_dirs = [mod, *[p for p in mod.rglob("*") if p.is_dir()]]
        ok &= check("index.php di tiap folder", all((d / "index.php").is_file() for d in all_dirs))

        # composer: prepend-autoloader false + psr-4
        comp = json.loads((mod / "composer.json").read_text())
        ok &= check("prepend-autoloader=false", comp["config"]["prepend-autoloader"] is False)
        ok &= check("psr-4 -> src/", comp["autoload"]["psr-4"].get("PrestaShop\\Module\\PsMybanner\\") == "src/")
        ok &= check("type prestashop-module", comp.get("type") == "prestashop-module")

        # main file: ps_versions_compliancy ada
        main_src = (mod / "ps_mybanner.php").read_text()
        ok &= check("ps_versions_compliancy = ada", "ps_versions_compliancy =" in main_src)
        ok &= check("guard _PS_VERSION_", "_PS_VERSION_" in main_src)

        # BUKTI INTI: lolos ps-static-scan di 3 versi
        if SCAN.is_file():
            sp = subprocess.run(["uv", "run", str(SCAN), str(mod), "--versions", "1.7.8,8.1,9.0"],
                                capture_output=True, text=True)
            scan = json.loads(sp.stdout)
            ok &= check("LOLOS ps-static-scan 3 versi (0 error)", scan["pass"] and sp.returncode == 0)
            ok &= check("0 warning juga", all(v["warnings"] == 0 for v in scan["versions"].values()))
        else:
            print("  SKIP: ps-static-scan tak ditemukan (jalankan dari layout module psm)")

        # nama tak valid ditolak
        rc2, _, _ = gen(tmp, "Ps-Invalid-Name")
        ok &= check("nama tak valid (huruf besar/dash) ditolak", rc2 == 2)

        # ps-min 8.x -> php >=8.1
        rc3, res3, _ = gen(tmp, "ps_modern", "--ps-min", "8.0.0")
        ok &= check("ps-min 8.x -> php require >=8.1", res3 and res3["php_require"] == ">=8.1")

        # --target-versions -> min/max diturunkan deterministik (bukan oleh model)
        rc4, res4, _ = gen(tmp, "ps_targeted", "--target-versions", "1.7.8,8.1,9.0")
        ok &= check("target-versions -> min 1.7.8.0", res4 and res4["ps_compliancy"]["min"] == "1.7.8.0")
        ok &= check("target-versions -> max 9.99.99", res4 and res4["ps_compliancy"]["max"] == "9.99.99")

        # urutan input acak tetap benar (sort semver, bukan string) + major 10 tak salah urut
        rc5, res5, _ = gen(tmp, "ps_future", "--target-versions", "10.0,8.1,1.7.8")
        ok &= check("target-versions urut acak -> min 1.7.8.0", res5 and res5["ps_compliancy"]["min"] == "1.7.8.0")
        ok &= check("major 10 tak salah urut -> max 10.99.99", res5 and res5["ps_compliancy"]["max"] == "10.99.99")

        # --ps-min override menang atas turunan target-versions
        rc6, res6, _ = gen(tmp, "ps_override", "--target-versions", "1.7.8,9.0", "--ps-min", "8.0.0.0")
        ok &= check("ps-min override menang atas target-versions", res6 and res6["ps_compliancy"]["min"] == "8.0.0.0")

        # dest tak valid (berupa file) -> error bersih rc=2, bukan traceback mentah
        badfile = tmp / "not_a_dir"
        badfile.write_text("x")
        rc7, res7, err7 = gen(badfile, "ps_baddest")
        ok &= check("dest tak valid ditolak bersih (rc=2)", rc7 == 2 and res7 is None)
        ok &= check("dest tak valid tanpa traceback mentah", "Traceback" not in err7 and err7.startswith("error:"))

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
