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

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
