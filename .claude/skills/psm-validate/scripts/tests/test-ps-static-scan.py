#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test untuk ps-static-scan.py — verifikasi akurasi ruleset lintas versi.

Jalankan: uv run scripts/tests/test_ps_static_scan.py
Exit 0 = semua lolos, 1 = ada yang gagal.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCAN = Path(__file__).resolve().parent.parent / "ps-static-scan.py"

GOOD_MAIN = '''<?php
class GoodMod extends Module {
    public function __construct() {
        $this->name = 'goodmod';
        $this->ps_versions_compliancy = ['min' => '1.7.0.0', 'max' => _PS_VERSION_];
    }
}
'''
BAD_MAIN = '''<?php
class BadMod extends Module {
    public function __construct() { $this->name = 'badmod'; }
    public function hookActionAdminLoginControllerBefore($p) {
        $x = Tools::jsonEncode($p);
        $a = new Attribute(1);
        return $x . $a;
    }
}
'''


def make_module(tmp, name, main_src, with_index=True, tpl=None):
    d = tmp / name
    d.mkdir()
    (d / f"{name}.php").write_text(main_src)
    if with_index:
        (d / "index.php").write_text("<?php")
    if tpl is not None:
        sub = d / "views"
        sub.mkdir()
        if with_index:
            (sub / "index.php").write_text("<?php")
        (sub / "x.tpl").write_text(tpl)
    return d


def run_scan(module_dir, versions):
    p = subprocess.run(
        ["uv", "run", str(SCAN), str(module_dir), "--versions", versions],
        capture_output=True, text=True,
    )
    return json.loads(p.stdout), p.returncode


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    return cond


def main():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)

        # 1. Module bersih + compliancy -> lolos semua versi
        good = make_module(tmp, "goodmod", GOOD_MAIN, tpl="<div>{$x|escape:'html'}</div>")
        res, rc = run_scan(good, "1.7.8,8.1,9.1")
        ok &= check("module bersih lolos semua versi", res["pass"] and rc == 0)
        ok &= check("compliancy ada -> tak ada struct-compliancy", all(
            "struct-compliancy" not in [f["id"] for f in v["findings"]] for v in res["versions"].values()))

        # 2. Module buruk: Attribute & jsonEncode -> error di 8/9, bukan 1.7
        bad = make_module(tmp, "badmod", BAD_MAIN)
        res, rc = run_scan(bad, "1.7.8,8.1,9.1")
        v87 = [f["id"] for f in res["versions"]["1.7.8"]["findings"]]
        v81 = [f["id"] for f in res["versions"]["8.1"]["findings"]]
        v91 = [f["id"] for f in res["versions"]["9.1"]["findings"]]
        ok &= check("Attribute kena di 8.1 & 9.1", "cls-attribute" in v81 and "cls-attribute" in v91)
        ok &= check("Attribute TIDAK kena di 1.7.8", "cls-attribute" not in v87)
        ok &= check("jsonEncode kena di 8/9", "mth-tools-jsonencode" in v81 and "mth-tools-jsonencode" in v91)
        ok &= check("login hook (method case-insensitive) kena di 9.1", "hook-admin-login" in v91)
        ok &= check("compliancy hilang kena semua versi", all(
            "struct-compliancy" in [f["id"] for f in v["findings"]] for v in res["versions"].values()))
        ok &= check("module buruk -> overall gagal + exit 1", not res["pass"] and rc == 1)

        # 3. compliancy hanya dalam komentar -> tetap dianggap hilang (pattern butuh '=')
        commented = make_module(tmp, "commod", '<?php\nclass C extends Module {\n// ps_versions_compliancy diatur di tempat lain\n}\n')
        res, _ = run_scan(commented, "8.1")
        ok &= check("compliancy dalam komentar tak dihitung ada",
                    "struct-compliancy" in [f["id"] for f in res["versions"]["8.1"]["findings"]])

        # 4. index.php hilang -> warning struct-index-php
        noindex = make_module(tmp, "noidx", GOOD_MAIN, with_index=False)
        res, _ = run_scan(noindex, "8.1")
        ok &= check("index.php hilang -> struct-index-php",
                    "struct-index-php" in [f["id"] for f in res["versions"]["8.1"]["findings"]])

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
