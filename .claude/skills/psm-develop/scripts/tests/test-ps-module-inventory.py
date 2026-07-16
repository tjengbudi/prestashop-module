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
ADMIN_SF = """<?php
namespace Inv\\Controller;
class InvmodConfigController extends FrameworkBundleAdminController {}
class InvmodStatsController extends PrestaShopAdminController {}
"""
MULTI_ENTITY = """<?php
class Coupon extends ObjectModel {
    public static $definition = ['table' => 'invmod_coupon', 'primary' => 'id_coupon'];
}
class Points extends ObjectModel {
    public static $definition = ['table' => 'invmod_points', 'primary' => 'id_points'];
}
"""


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
        (mod / "src" / "Entity" / "Rewards.php").write_text(MULTI_ENTITY)
        (mod / "controllers" / "front" / "display.php").write_text(FRONT)
        (mod / "src" / "Controller" / "Admin.php").parent.mkdir(parents=True, exist_ok=True)
        (mod / "src" / "Controller" / "Admin.php").write_text(ADMIN_SF)
        # file di vendor harus diabaikan
        (mod / "vendor" / "junk.php").write_text("<?php class X extends ObjectModel {}\n")

        p = subprocess.run(["uv", "run", str(INV), str(mod)], capture_output=True, text=True)
        d = json.loads(p.stdout)
        ok &= check("rc=0", p.returncode == 0)
        ok &= check("versi module terbaca", d["module_version"] == "1.2.0")
        ok &= check("registered hooks lengkap", set(d["registered_hooks"]) == {"displayHeader", "actionValidateOrder"})
        ok &= check("implemented hooks lengkap", set(d["implemented_hooks"]) == {"hookDisplayHeader", "hookActionValidateOrder"})
        ok &= check("ObjectModel + tabel terdeteksi", {(o["class"], o["table"]) for o in d["object_models"]}
                    == {("Banner", "invmod_banner"), ("Coupon", "invmod_coupon"), ("Points", "invmod_points")})
        ok &= check("tabel di-scope per body class (file multi-class tak menular)",
                    next(o["table"] for o in d["object_models"] if o["class"] == "Points") == "invmod_points")
        ok &= check("front controller terdeteksi", any(c["type"] == "front" and c["class"] == "InvmodDisplayModuleFrontController" for c in d["controllers"]))
        ok &= check("admin controller Symfony terdeteksi (FrameworkBundle + PrestaShopAdmin)",
                    {c["class"] for c in d["controllers"] if c["type"] == "admin"}
                    >= {"InvmodConfigController", "InvmodStatsController"})
        ok &= check("upgrade dir terdeteksi", d["has_upgrade_dir"] is True)
        ok &= check("vendor/ diabaikan (tak ada class X)", all("vendor" not in o["file"] for o in d["object_models"]))
        ok &= check("looks_like_module true untuk module berisi", d["looks_like_module"] is True)
        ok &= check("detection flag direct-parent-only", d["detection"] == "direct-parent-only")

        # --- gerbang target: folder ber-.php tanpa sinyal struktur -> looks_like_module False ---
        with tempfile.TemporaryDirectory() as td0:
            empty = Path(td0) / "kosong"
            empty.mkdir()
            (empty / "readme.php").write_text("<?php // bukan module\n")
            pe = subprocess.run(["uv", "run", str(INV), str(empty)], capture_output=True, text=True)
            de = json.loads(pe.stdout)
            ok &= check("looks_like_module false tanpa sinyal struktur", de["looks_like_module"] is False)

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

        # --- pair-check: pasangan sinkron -> ok, rc=0 ---
        (mod / ".psm-develop-plan.md").write_text(
            "# Rencana invmod\n\n## wishlist\nStatus: direncanakan\nDetail naratif.\n\n"
            "## loyalty\n- **Status:** diterapkan\nDetail lain.\n")
        (mod / ".psm-develop-plan.json").write_text(json.dumps({"items": [
            {"function": "wishlist", "status": "direncanakan"},
            {"function": "loyalty", "status": "diterapkan"}]}))
        pc = subprocess.run(["uv", "run", str(INV), str(mod), "--pair-check"],
                            capture_output=True, text=True)
        pcj = json.loads(pc.stdout)
        ok &= check("pair-check sinkron rc=0 (marker polos & bullet-bold)",
                    pc.returncode == 0 and pcj["ok"] is True and pcj["pair_drift"] == [])

        # --- pair-check: status beda + item hilang di tiap sisi -> drift, rc=1 ---
        (mod / ".psm-develop-plan.json").write_text(json.dumps({"items": [
            {"function": "wishlist", "status": "diterapkan"},     # .md bilang direncanakan
            {"function": "seo", "status": "direncanakan"}]}))      # tak ada di .md
        pd = subprocess.run(["uv", "run", str(INV), str(mod), "--pair-check"],
                            capture_output=True, text=True)
        pdj = json.loads(pd.stdout)
        pkinds = {i["kind"] for i in pdj["pair_drift"]}
        ok &= check("pair-check drift rc=1", pd.returncode == 1)
        ok &= check("pair-check status_mismatch + missing di dua arah",
                    pkinds == {"status_mismatch", "missing_in_json", "missing_in_md"})

        # --- pair-check: .md tanpa marker (format lama) -> no_markers ---
        (mod / ".psm-develop-plan.md").write_text("# Rencana lama\n\n## wishlist\nTanpa baris status.\n")
        pn = subprocess.run(["uv", "run", str(INV), str(mod), "--pair-check"],
                            capture_output=True, text=True)
        pnj = json.loads(pn.stdout)
        ok &= check("pair-check no_markers untuk .md format lama",
                    pn.returncode == 1 and [i["kind"] for i in pnj["pair_drift"]] == ["no_markers"])

        # --- pair-check: .json hilang -> json_missing; tanpa pasangan sama sekali -> rc=2 ---
        (mod / ".psm-develop-plan.json").unlink()
        pj = subprocess.run(["uv", "run", str(INV), str(mod), "--pair-check"],
                            capture_output=True, text=True)
        pjj = json.loads(pj.stdout)
        ok &= check("pair-check json_missing",
                    pj.returncode == 1 and [i["kind"] for i in pjj["pair_drift"]] == ["json_missing"])
        (mod / ".psm-develop-plan.md").unlink()
        p0 = subprocess.run(["uv", "run", str(INV), str(mod), "--pair-check"],
                            capture_output=True, text=True)
        ok &= check("pair-check tanpa pasangan rc=2", p0.returncode == 2)

        # --- anchor skema: --help memuat skema kanonik + marker pair-check ---
        ph = subprocess.run(["uv", "run", str(INV), "--help"], capture_output=True, text=True)
        ok &= check("--help memuat skema items[] kanonik",
                    "add_hooks" in ph.stdout and "changes_objectmodel" in ph.stdout)
        ok &= check("--help memuat kontrak marker Status:",
                    "Status: <status>" in ph.stdout)

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
