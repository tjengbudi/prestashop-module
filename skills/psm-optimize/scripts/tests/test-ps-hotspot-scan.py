#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test ps-hotspot-scan.py. Jalankan: uv run scripts/tests/test-ps-hotspot-scan.py"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCAN = Path(__file__).resolve().parent.parent / "ps-hotspot-scan.py"

MOD = """<?php
class Hotmod extends Module {
    public function hookDisplayHeader($params) {
        $ids = array(1,2,3);
        foreach ($ids as $id) {
            $row = Db::getInstance()->getRow('SELECT * FROM ps_product WHERE id='.$id);
            $p = new Product($id);
        }
        $single = Db::getInstance()->executeS('SELECT 1');
    }
    public function hookActionTiny($p) { return 1; }
}
"""


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    return cond


def main():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        mod = Path(td) / "hotmod"
        (mod / "vendor").mkdir(parents=True)
        (mod / "hotmod.php").write_text(MOD)
        (mod / "vendor" / "junk.php").write_text("<?php foreach($x as $y){ Db::getInstance()->executeS('q'); }\n")

        p = subprocess.run(["uv", "run", str(SCAN), str(mod)], capture_output=True, text=True)
        d = json.loads(p.stdout)
        ok &= check("rc=0", p.returncode == 0)
        ok &= check("2 kandidat N+1 dalam loop", d["query_in_loop_count"] == 2)
        lines = {h["line"] for h in d["query_in_loop_candidates"]}
        ok &= check("Db getRow dalam loop terdeteksi (line 6)", 6 in lines)
        ok &= check("new Product dalam loop terdeteksi (line 7)", 7 in lines)
        ok &= check("query di luar loop (line 9) TIDAK dihitung", 9 not in lines)
        ok &= check("vendor/ diabaikan", all("vendor" not in h["file"] for h in d["query_in_loop_candidates"]))
        ok &= check("2 hook discan", d["all_hooks_scanned"] == 2)
        # ambang heavy-hook kecil -> hook terdeteksi berat
        p2 = subprocess.run(["uv", "run", str(SCAN), str(mod), "--heavy-hook-lines", "3"], capture_output=True, text=True)
        d2 = json.loads(p2.stdout)
        ok &= check("ambang rendah -> ada heavy hook", len(d2["heavy_hook_candidates"]) >= 1)

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
