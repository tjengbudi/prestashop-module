#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test ps-module-inventory.py. Jalankan: uv run scripts/tests/test-ps-module-inventory.py"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

INV = Path(__file__).resolve().parent.parent / "ps-module-inventory.py"

MAIN = """<?php
class Invmod extends Module {
    public function __construct() { $this->name='invmod'; $this->version='1.2.0'; }
    public function install() {
        return parent::install()
            && $this->registerHook('displayHeader')
            && $this->registerHook('actionValidateOrder');
    }
    public function hookDisplayHeader($p) {}
    public function hookActionValidateOrder($p) {}
}
"""
ENTITY = """<?php
namespace Inv\\Entity;
class Banner extends ObjectModel {
    public static $definition = ['table' => 'invmod_banner', 'primary' => 'id_banner'];
}
"""
FRONT = "<?php\nclass InvmodDisplayModuleFrontController extends ModuleFrontController {}\n"


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    return cond


def main():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        mod = Path(td) / "invmod"
        (mod / "src" / "Entity").mkdir(parents=True)
        (mod / "controllers" / "front").mkdir(parents=True)
        (mod / "upgrade").mkdir()
        (mod / "vendor").mkdir()
        (mod / "invmod.php").write_text(MAIN)
        (mod / "src" / "Entity" / "Banner.php").write_text(ENTITY)
        (mod / "controllers" / "front" / "display.php").write_text(FRONT)
        # file di vendor harus diabaikan
        (mod / "vendor" / "junk.php").write_text("<?php class X extends ObjectModel {}\n")

        p = subprocess.run(["uv", "run", str(INV), str(mod)], capture_output=True, text=True)
        d = json.loads(p.stdout)
        ok &= check("rc=0", p.returncode == 0)
        ok &= check("versi module terbaca", d["module_version"] == "1.2.0")
        ok &= check("registered hooks lengkap", set(d["registered_hooks"]) == {"displayHeader", "actionValidateOrder"})
        ok &= check("implemented hooks lengkap", set(d["implemented_hooks"]) == {"hookDisplayHeader", "hookActionValidateOrder"})
        ok &= check("ObjectModel + tabel terdeteksi", d["object_models"] == [{"class": "Banner", "table": "invmod_banner", "file": "src/Entity/Banner.php"}])
        ok &= check("front controller terdeteksi", any(c["type"] == "front" and c["class"] == "InvmodDisplayModuleFrontController" for c in d["controllers"]))
        ok &= check("upgrade dir terdeteksi", d["has_upgrade_dir"] is True)
        ok &= check("vendor/ diabaikan (tak ada class X)", all("vendor" not in o["file"] for o in d["object_models"]))

        # --- validate-plan: rencana bersih -> ok, rc=0 ---
        clean_plan = {"items": [{"function": "wishlist", "add_hooks": ["displayProductActions"],
                                 "insert_files": ["invmod.php"], "changes_objectmodel": True}]}
        cp = mod / "plan-clean.json"
        cp.write_text(json.dumps(clean_plan))
        r = subprocess.run(["uv", "run", str(INV), str(mod), "--validate-plan", str(cp)],
                           capture_output=True, text=True)
        rj = json.loads(r.stdout)
        ok &= check("plan bersih rc=0", r.returncode == 0)
        ok &= check("plan bersih ok=True tanpa mismatch", rj["ok"] is True and rj["mismatches"] == [])

        # --- validate-plan: rencana konflik -> mismatch, rc=1 ---
        # module tanpa upgrade/ agar objectmodel-change memicu mismatch
        with tempfile.TemporaryDirectory() as td2:
            m2 = Path(td2) / "invmod2"
            m2.mkdir()
            (m2 / "invmod2.php").write_text(MAIN)  # registerHook displayHeader, actionValidateOrder
            bad_plan = {"items": [{"function": "seo",
                                   "add_hooks": ["displayHeader"],          # sudah terdaftar
                                   "insert_files": ["tidak-ada.php"],        # file tak ada
                                   "changes_objectmodel": True}]}            # tanpa upgrade/ dir
            bp = m2 / "plan-bad.json"
            bp.write_text(json.dumps(bad_plan))
            rb = subprocess.run(["uv", "run", str(INV), str(m2), "--validate-plan", str(bp)],
                                capture_output=True, text=True)
            rbj = json.loads(rb.stdout)
            kinds = {m["kind"] for m in rbj["mismatches"]}
            ok &= check("plan konflik rc=1", rb.returncode == 1)
            ok &= check("mismatch hook_already_registered", "hook_already_registered" in kinds)
            ok &= check("mismatch insert_file_missing", "insert_file_missing" in kinds)
            ok &= check("mismatch objectmodel_change_without_upgrade", "objectmodel_change_without_upgrade" in kinds)

            # nama hook case-insensitive: 'displayheader' vs source 'displayHeader' harus tetap konflik
            case_plan = {"items": [{"function": "seo", "add_hooks": ["displayheader"]}]}
            cbp = m2 / "plan-case.json"
            cbp.write_text(json.dumps(case_plan))
            rc2 = subprocess.run(["uv", "run", str(INV), str(m2), "--validate-plan", str(cbp)],
                                 capture_output=True, text=True)
            rc2j = json.loads(rc2.stdout)
            ok &= check("validate-plan hook case-insensitive tetap konflik",
                        rc2.returncode == 1 and any(m["kind"] == "hook_already_registered" for m in rc2j["mismatches"]))

        # --- reconcile: status 'diterapkan' cocok bukti -> ok, rc=0 ---
        rec_ok_plan = {"items": [{"function": "seo", "status": "diterapkan",
                                  "add_hooks": ["displayHeader"], "insert_files": ["invmod.php"],
                                  "add_tables": ["invmod_banner"], "add_classes": ["Banner"]}]}
        rop = mod / "plan-rec-ok.json"
        rop.write_text(json.dumps(rec_ok_plan))
        ro = subprocess.run(["uv", "run", str(INV), str(mod), "--reconcile", str(rop)],
                            capture_output=True, text=True)
        roj = json.loads(ro.stdout)
        ok &= check("reconcile cocok rc=0", ro.returncode == 0 and roj["ok"] is True)

        # --- reconcile: hook yang cuma diimplementasi-sebagai-method (bare vs prefix) tak salah-drift ---
        # actionValidateOrder ada sbg method hookActionValidateOrder -> present via implemented_hooks
        rec_impl_plan = {"items": [{"function": "loyalty", "status": "diterapkan",
                                    "add_hooks": ["actionValidateOrder"]}]}
        rip = mod / "plan-rec-impl.json"
        rip.write_text(json.dumps(rec_impl_plan))
        ri = subprocess.run(["uv", "run", str(INV), str(mod), "--reconcile", str(rip)],
                            capture_output=True, text=True)
        rij = json.loads(ri.stdout)
        ok &= check("reconcile hook via method (bare vs prefix) tak salah-drift",
                    ri.returncode == 0 and rij["ok"] is True)

        # --- reconcile: status 'diterapkan' tapi bukti hilang -> drift, rc=1 ---
        rec_drift_plan = {"items": [
            {"function": "wishlist", "status": "diterapkan",
             "add_hooks": ["displayProductActions"],        # tak terdaftar
             "insert_files": ["hilang.php"],                 # tak ada
             "add_tables": ["invmod_wishlist"],              # tak ada
             "add_classes": ["Wishlist"]},                   # tak ada
            {"function": "belum", "status": "rencana",       # non-diterapkan -> diabaikan
             "add_hooks": ["apapun"]}]}
        rdp = mod / "plan-rec-drift.json"
        rdp.write_text(json.dumps(rec_drift_plan))
        rd = subprocess.run(["uv", "run", str(INV), str(mod), "--reconcile", str(rdp)],
                            capture_output=True, text=True)
        rdj = json.loads(rd.stdout)
        dkinds = {m["kind"] for m in rdj["drift"]}
        ok &= check("reconcile drift rc=1", rd.returncode == 1)
        ok &= check("drift hook/file/table/class terdeteksi",
                    dkinds == {"hook_missing", "file_missing", "table_missing", "class_missing"})
        ok &= check("item non-diterapkan diabaikan reconcile",
                    all(m["function"] != "belum" for m in rdj["drift"]))

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
