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

        # 5. compliancy range: min 9.0 -> gagal di 1.7.8 saja
        ranged = make_module(tmp, "rangemod", GOOD_MAIN.replace("'min' => '1.7.0.0'", "'min' => '9.0'"))
        res, _ = run_scan(ranged, "1.7.8,9.1")
        ok &= check("min 9.0 -> struct-compliancy-range kena di 1.7.8",
                    "struct-compliancy-range" in [f["id"] for f in res["versions"]["1.7.8"]["findings"]])
        ok &= check("min 9.0 -> range TIDAK kena di 9.1",
                    "struct-compliancy-range" not in [f["id"] for f in res["versions"]["9.1"]["findings"]])

        # 6. max literal terlalu rendah -> gagal di 9.1; max _PS_VERSION_ aman semua versi
        maxed = make_module(tmp, "maxmod", GOOD_MAIN.replace("'max' => _PS_VERSION_", "'max' => '8.99'"))
        res, _ = run_scan(maxed, "9.1")
        ok &= check("max 8.99 -> struct-compliancy-range kena di 9.1",
                    "struct-compliancy-range" in [f["id"] for f in res["versions"]["9.1"]["findings"]])
        res, _ = run_scan(good, "1.7.8,8.1,9.1")
        ok &= check("max _PS_VERSION_ -> range aman semua versi", all(
            "struct-compliancy-range" not in [f["id"] for f in v["findings"]] for v in res["versions"].values()))
        ok &= check("tanpa composer.json -> tak ada struct-composer-prepend", all(
            "struct-composer-prepend" not in [f["id"] for f in v["findings"]] for v in res["versions"].values()))

        # 7. composer.json tanpa prepend-autoloader=false -> error; dengan -> aman
        comp = make_module(tmp, "compmod", GOOD_MAIN)
        (comp / "composer.json").write_text('{"name": "x/compmod"}')
        res, _ = run_scan(comp, "8.1")
        ok &= check("composer tanpa prepend-autoloader=false -> struct-composer-prepend",
                    "struct-composer-prepend" in [f["id"] for f in res["versions"]["8.1"]["findings"]])
        (comp / "composer.json").write_text('{"config": {"prepend-autoloader": false}}')
        res, _ = run_scan(comp, "8.1")
        ok &= check("prepend-autoloader false -> tak ada struct-composer-prepend",
                    "struct-composer-prepend" not in [f["id"] for f in res["versions"]["8.1"]["findings"]])

    # 8. Kontrak authoring ruleset: pattern/expect konsisten dgn kind (rule salah-tulis
    #    ketahuan di test, bukan KeyError saat scan)
    EXPECTS = {"present", "index_php_each_dir", "composer_prepend_autoloader_false", "compliancy_covers_target"}
    rules_doc = json.loads((SCAN.parent.parent / "assets" / "ps-rules.json").read_text(encoding="utf-8"))
    bad_rules = []
    for grp, items in rules_doc.items():
        if grp == "_meta":
            continue
        for r in items:
            structural = r.get("kind") in ("structure", "compliancy")
            if not all(k in r for k in ("id", "severity", "affects", "kind", "message")):
                bad_rules.append(f"{grp}:{r.get('id', '?')} field wajib hilang")
            elif structural and (r.get("expect") not in EXPECTS or (r["expect"] == "present" and "pattern" not in r)):
                bad_rules.append(f"{r['id']}: expect tak valid utk rule struktural")
            elif not structural and "pattern" not in r:
                bad_rules.append(f"{r['id']}: rule non-struktural tanpa pattern (KeyError saat scan)")
    ok &= check(f"kontrak ruleset: pattern/expect konsisten dgn kind ({bad_rules or 'bersih'})", not bad_rules)

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
