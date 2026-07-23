#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test untuk ps-static-scan.py — verifikasi akurasi ruleset lintas versi.

Jalankan: uv run scripts/tests/test_ps_static_scan.py
Exit 0 = semua lolos, 1 = ada yang gagal.
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCAN = Path(__file__).resolve().parent.parent / "ps-static-scan.py"
_spec = importlib.util.spec_from_file_location("ps_static_scan", SCAN)
assert _spec and _spec.loader
_scan_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_scan_mod)
mod_validate = _scan_mod.validate_extra_rules

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


def run_scan(module_dir, versions, extra_args=None):
    p = subprocess.run(
        ["uv", "run", str(SCAN), str(module_dir), "--versions", versions, *(extra_args or [])],
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

        # 7b. --extra-rules MENAMBAH ke ruleset default (determinism-3: aturan knowledge
        # base masuk skrip via merge, bukan hand-scan model / mengganti ruleset inti)
        extra = tmp / "extra-rules.json"
        extra.write_text(json.dumps({"forbidden_functions": [
            {"id": "xtra-marker", "severity": "error", "kind": "function",
             "affects": ["1.7", "8", "9"], "pattern": r"\bpsm_forbidden_marker\s*\(",
             "message": "fungsi terlarang (aturan tambahan)", "fix": "hapus"}]}))
        xmod = make_module(tmp, "xmod", GOOD_MAIN.replace(
            "$this->name = 'goodmod';", "$this->name = 'xmod'; psm_forbidden_marker(1);"))
        res, rc = run_scan(xmod, "8.1", ["--extra-rules", str(extra)])
        ids_x = [f["id"] for f in res["versions"]["8.1"]["findings"]]
        ok &= check("--extra-rules: aturan tambahan kena (xtra-marker) & exit 1",
                    "xtra-marker" in ids_x and rc == 1)
        res, rc = run_scan(xmod, "8.1")
        ok &= check("tanpa --extra-rules: aturan tambahan tak aktif (default utuh)",
                    "xtra-marker" not in [f["id"] for f in res["versions"]["8.1"]["findings"]] and rc == 0)

        # 7c. Gerbang skema --extra-rules: pelanggaran = exit 2 (input rusak), BUKAN
        # exit 1 (kode "module punya error") dan BUKAN drop senyap.
        def run_raw(module_dir, versions, extra_args):
            return subprocess.run(["uv", "run", str(SCAN), str(module_dir), "--versions", versions,
                                   *extra_args], capture_output=True, text=True)

        badgrp = tmp / "bad-group.json"
        badgrp.write_text(json.dumps({"custom_rules": [
            {"id": "x", "severity": "error", "kind": "function", "affects": ["8"],
             "pattern": "x", "message": "m"}]}))
        p = run_raw(xmod, "8.1", ["--extra-rules", str(badgrp)])
        ok &= check("extra-rules grup tak dikenal -> exit 2 & disebut (bukan drop senyap)",
                    p.returncode == 2 and "custom_rules" in p.stderr)
        nopat = tmp / "no-pattern.json"
        nopat.write_text(json.dumps({"forbidden_functions": [
            {"id": "np", "severity": "error", "kind": "function", "affects": ["8"], "message": "m"}]}))
        p = run_raw(xmod, "8.1", ["--extra-rules", str(nopat)])
        ok &= check("extra-rules rule tanpa pattern -> exit 2 (bukan KeyError exit 1)",
                    p.returncode == 2 and "pattern" in p.stderr)
        badre = tmp / "bad-regex.json"
        badre.write_text(json.dumps({"forbidden_functions": [
            {"id": "br", "severity": "error", "kind": "function", "affects": ["8"],
             "pattern": "(unclosed", "message": "m"}]}))
        p = run_raw(xmod, "8.1", ["--extra-rules", str(badre)])
        ok &= check("extra-rules regex tak valid -> exit 2", p.returncode == 2)
        badsev = tmp / "bad-sev.json"
        badsev.write_text(json.dumps({"forbidden_functions": [
            {"id": "bs", "severity": "critical", "kind": "function", "affects": ["8"],
             "pattern": "x", "message": "m"}]}))
        p = run_raw(xmod, "8.1", ["--extra-rules", str(badsev)])
        ok &= check("extra-rules severity di luar enum -> exit 2", p.returncode == 2)
        def _one(rule, grp="forbidden_functions"):
            return mod_validate({grp: [rule]})

        base = {"id": "r", "severity": "error", "kind": "function", "affects": ["8"], "message": "m"}

        ok &= check("extra-rules sehat -> lolos gerbang (tanpa pelanggaran)",
                    mod_validate({"forbidden_functions": [
                        {"id": "good", "severity": "error", "kind": "function", "affects": ["8"],
                         "pattern": r"\bfoo\(", "message": "m"}]}) == [])
        # REGRESI: tipe ELEMEN yang dibaca kode scan, bukan cuma container
        ok &= check("affects [9] angka -> pelanggaran (dulu lolos & rule diam-diam tak menyala)",
                    len(_one({**base, "pattern": "x", "affects": [9]})) == 1)
        ok &= check("affects ['9.1'] versi penuh -> pelanggaran (domain = major key)",
                    len(_one({**base, "pattern": "x", "affects": ["9.1"]})) == 1)
        ok &= check("affects ['9'] major key -> lolos", _one({**base, "pattern": "x", "affects": ["9"]}) == [])
        ok &= check("affects [] KOSONG -> pelanggaran (lolos cek tipe tapi rule tak pernah menyala)",
                    len(_one({**base, "pattern": "x", "affects": []})) == 1)
        ok &= check("files [123] -> pelanggaran (dulu TypeError di rglob -> exit 1)",
                    len(_one({**base, "pattern": "x", "files": [123]})) == 1)
        ok &= check("files [''] kosong -> pelanggaran (dulu diam-diam tak memindai apa pun)",
                    len(_one({**base, "pattern": "x", "files": [""]})) == 1)
        ok &= check("extra-rules struktural: expect tak dikenal -> pelanggaran",
                    len(mod_validate({"structure": [
                        {"id": "s", "severity": "error", "kind": "structure", "affects": ["8"],
                         "expect": "ngawur", "message": "m"}]})) == 1)

        # REGRESI: gerbang harus menjaga TIPE tiap field yang disentuh kode pindai,
        # bukan cuma keberadaannya. Empat bentuk di bawah dulu LOLOS gerbang lalu
        # meledak (KeyError/TypeError/re.error) -> exit 1 = kode "module punya error".
        ok &= check("struktural expect=present TANPA pattern -> pelanggaran (dulu KeyError saat scan)",
                    len(_one({**base, "kind": "compliancy", "expect": "present"}, "structure")) == 1)
        ok &= check("struktural expect non-present tanpa pattern -> LOLOS (pattern memang tak dipakai)",
                    _one({**base, "kind": "structure", "expect": "index_php_each_dir"}, "structure") == [])
        ok &= check("pattern non-string -> pelanggaran (dulu TypeError DI DALAM validator)",
                    len(_one({**base, "pattern": 123})) == 1)
        ok &= check("negate_pattern regex rusak -> pelanggaran (dulu tak divalidasi sama sekali)",
                    len(_one({**base, "pattern": "x", "negate_pattern": "("})) == 1)
        ok &= check("negate_pattern non-string -> pelanggaran",
                    len(_one({**base, "pattern": "x", "negate_pattern": 5})) == 1)
        ok &= check("affects bukan list -> pelanggaran (dulu TypeError di loop scan)",
                    len(_one({**base, "pattern": "x", "affects": 9})) == 1)
        ok &= check("files bukan list -> pelanggaran",
                    len(_one({**base, "pattern": "x", "files": "*.php"})) == 1)

        # ...dan benar-benar tak crash lewat CLI (exit 2, bukan traceback exit 1)
        for name, rule in (("nopattern-struct", {**base, "kind": "compliancy", "expect": "present"}),
                           ("pattern-int", {**base, "pattern": 123}),
                           ("negate-broken", {**base, "pattern": "x", "negate_pattern": "("}),
                           ("affects-int", {**base, "pattern": "x", "affects": 9})):
            f = tmp / f"{name}.json"
            grp = "structure" if "struct" in name else "forbidden_functions"
            f.write_text(json.dumps({grp: [rule]}))
            p = run_raw(xmod, "8.1", ["--extra-rules", str(f)])
            ok &= check(f"CLI {name} -> exit 2 bersih (bukan crash exit 1)",
                        p.returncode == 2 and "Traceback" not in p.stderr)

    # 7d. skip-vendor: komponen RELATIF, bukan substring & bukan path absolut
    with tempfile.TemporaryDirectory() as td2:
        tmp2 = Path(td2)
        # (a) module DI BAWAH ancestor bernama vendor/ -> source-nya TETAP dipindai
        deep = tmp2 / "vendor" / "acme" / "shop" / "modules"
        deep.mkdir(parents=True)
        vmod = make_module(deep, "vmod", GOOD_MAIN.replace(
            "$this->name = 'goodmod';", "$this->name = 'vmod'; eval('1;');"))
        res, _ = run_scan(vmod, "8.1")
        ok &= check("module di bawah ancestor vendor/ -> source TETAP dipindai (fn-eval kena)",
                    "fn-eval" in [f["id"] for f in res["versions"]["8.1"]["findings"]])
        # (b) folder bernama myvendor/ BUKAN vendor -> tetap dipindai (dulu substring membuangnya)
        mv = make_module(tmp2, "mvmod", GOOD_MAIN)
        (mv / "myvendor").mkdir()
        (mv / "myvendor" / "index.php").write_text("<?php")
        (mv / "myvendor" / "thing.php").write_text("<?php eval($a);")
        res, _ = run_scan(mv, "8.1")
        occ = [o["file"] for f in res["versions"]["8.1"]["findings"] if f["id"] == "fn-eval"
               for o in f["occurrences"]]
        ok &= check("folder 'myvendor/' tetap dipindai (bukan vendor/)",
                    any("myvendor" in o for o in occ))
        # (c) vendor/ MILIK module tetap dilewati
        (mv / "vendor").mkdir()
        (mv / "vendor" / "dep.php").write_text("<?php eval($b);")
        res, _ = run_scan(mv, "8.1")
        occ = [o["file"] for f in res["versions"]["8.1"]["findings"] if f["id"] == "fn-eval"
               for o in f["occurrences"]]
        ok &= check("vendor/ milik module tetap dilewati", not any(o.startswith("vendor") for o in occ))

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
    # _meta.schema = satu-satunya spec yang dibaca penulis aturan KB; ia HARUS sepakat
    # dgn validator & scan (dulu menjanjikan severity 'info' & tak menyebut domain affects)
    schema = rules_doc["_meta"]["schema"]
    ok &= check("_meta.schema: severity sepakat dgn validator (error|warning, tanpa info)",
                "error|warning" in schema and "|info" not in schema)
    ok &= check("_meta.schema: domain affects didokumentasikan (major key)",
                "MAJOR KEY" in schema and "1.7 | 8 | 9" in schema)
    ok &= check("ruleset sendiri patuh domain affects & enum severity",
                all(a in ("1.7", "8", "9") and r["severity"] in ("error", "warning")
                    for g, items in rules_doc.items() if g != "_meta"
                    for r in items for a in r["affects"]))

    # --- determinism-2 (analyze 2026-07-17-1024): "folder mana yang BUKAN source module"
    # punya satu pemilik (is_skipped) tapi dulu cuma satu call site. Dua seam lain
    # hand-roll: cabang glob tak menyaring sama sekali, index_php_each_dir mencocokkan
    # "vendor" di path ABSOLUT (buta node_modules/.git, dan membuang module yang kebetulan
    # berada di bawah ancestor bernama vendor/).
    with tempfile.TemporaryDirectory() as td3:
        t3 = Path(td3)
        m = make_module(t3, "skipmod", GOOD_MAIN)
        for third in ("vendor/acme", "node_modules/pkg", ".git"):
            d = m / third
            d.mkdir(parents=True)
            (d / "bad.php").write_text("<?php eval($x);")
            (d / "bad.tpl").write_text("{$x nofilter}")
        res, rc = run_scan(m, "9.1")
        locs = [o["file"] for f in res["versions"]["9.1"]["findings"] for o in f.get("occurrences", [])]
        ok &= check("seam struktural: index.php tak dituntut di vendor/node_modules/.git",
                    not any(k in l for l in locs for k in ("vendor", "node_modules", ".git")))
        extra = t3 / "extra.json"
        extra.write_text(json.dumps({"forbidden_functions": [
            {"id": "kb-no-eval", "severity": "error", "kind": "function", "message": "eval terlarang",
             "fix": "buang eval", "files": ["*.php"], "pattern": r"eval\(", "affects": ["9"]}]}))
        res, rc = run_scan(m, "9.1", ["--extra-rules", str(extra)])
        ok &= check("seam glob (jalur aturan KB): eval di vendor pihak-ketiga TAK memblok module bersih",
                    res["pass"] and rc == 0)
        nest = t3 / "vendor" / "proj"
        nest.mkdir(parents=True)
        m2 = make_module(nest, "nestmod", BAD_MAIN)
        (m2 / "sub").mkdir()
        (m2 / "sub" / "x.php").write_text("<?php")
        res, _ = run_scan(m2, "9.1")
        ids = [f["id"] for f in res["versions"]["9.1"]["findings"]]
        ok &= check("module DI BAWAH ancestor vendor/ tetap dipindai (bukan diam-diam kosong)",
                    "cls-attribute" in ids and "struct-index-php" in ids)

    # --- determinism-3 (sisi produsen): output WAJIB membawa jejak ruleset yang
    # memproduksinya. Ini kontrak lintas-skrip — ps-plan-layers memutuskan reuse dari
    # jejak ini; tanpa jejak, ia tak punya dasar dan (benar) menolak reuse selamanya.
    with tempfile.TemporaryDirectory() as td5:
        t5 = Path(td5)
        m5 = make_module(t5, "provmod", GOOD_MAIN)
        res, _ = run_scan(m5, "9.1")
        prov = res.get("ruleset")
        ok &= check("output static mencatat jejak ruleset (files + mtime)",
                    isinstance(prov, dict) and len(prov.get("files") or []) == 1
                    and isinstance(prov.get("mtime"), float) and prov["mtime"] > 0)
        x5 = t5 / "extra.json"
        x5.write_text(json.dumps({"removed_hooks": []}))
        res, _ = run_scan(m5, "9.1", ["--extra-rules", str(x5)])
        ok &= check("jejak ruleset ikut memuat --extra-rules (aturan KB bagian dari vonis)",
                    len(res["ruleset"]["files"]) == 2
                    and any("extra.json" in f for f in res["ruleset"]["files"]))

    # --- determinism-5: "bukan module PrestaShop" vs "aku tak bisa memilih" adalah dua
    # jawaban berbeda; meleburnya jadi main_file_found:false membuat stop terminal
    # memvonis module nyata yang nama folder-nya tak cocok.
    with tempfile.TemporaryDirectory() as td4:
        t4 = Path(td4)
        conv = make_module(t4, "convmod", GOOD_MAIN)
        f, reason = _scan_mod.find_main_file(conv)
        ok &= check("konvensi <folder>.php -> ketemu, tanpa alasan", f is not None and reason is None)
        mm = t4 / "clonemod-master"
        mm.mkdir()
        (mm / "clonemod.php").write_text(GOOD_MAIN)
        (mm / "autoload.php").write_text("<?php // helper")
        (mm / "index.php").write_text("<?php")
        f, reason = _scan_mod.find_main_file(mm)
        ok &= check("nama folder tak cocok -> dipilih via 'extends Module' (dulu: 'bukan module')",
                    f is not None and f.name == "clonemod.php" and reason is None)
        empty = t4 / "nomod"
        empty.mkdir()
        (empty / "readme.txt").write_text("hi")
        f, reason = _scan_mod.find_main_file(empty)
        ok &= check("tanpa PHP di root -> no_php_at_root (satu-satunya alasan berhenti)",
                    f is None and reason == "no_php_at_root")
        amb = t4 / "ambmod"
        amb.mkdir()
        (amb / "a.php").write_text("<?php class A extends Module {}")
        (amb / "b.php").write_text("<?php class B extends Module {}")
        f, reason = _scan_mod.find_main_file(amb)
        ok &= check("dua kandidat extends Module -> ambiguous_main_file, bukan 'bukan module'",
                    f is None and reason == "ambiguous_main_file")
        (amb / "helper.php").write_text("<?php class Helper {}")  # bukan Module
        res, _ = run_scan(amb, "9.1")
        # det-3 (ronde-6): kandidat memuat extends_module (find_main_file sudah menghitungnya
        # lalu membuangnya). Model membaca fakta, tak meng-grep source ulang; ia membedakan
        # >=2-extends (rename) dari 0-extends (bukan module) dari field ini.
        cands = res.get("main_file_candidates")
        ok &= check("CLI: main_file_reason + kandidat ber-extends_module disurface",
                    res.get("main_file_reason") == "ambiguous_main_file"
                    and cands == [{"file": "a.php", "extends_module": True},
                                  {"file": "b.php", "extends_module": True},
                                  {"file": "helper.php", "extends_module": False}])

    # determinism-1 (analyze ronde-5, CRITICAL): cakupan aturan itu fakta yang DIHITUNG.
    # Dulu versi di luar domain ruleset dilewati SETIAP aturan lalu keluar pass=true, dan
    # agregat membacanya sbg konklusif lolos -> module ber-eval() siap-rilis di --versions 1.6.
    with tempfile.TemporaryDirectory() as td6:
        t6 = Path(td6)
        evil = make_module(t6, "evilmod", GOOD_MAIN + "<?php eval($x); ?>\n")
        rc_p = subprocess.run(["uv", "run", str(SCAN), str(evil), "--versions", "8.1,1.6"],
                              capture_output=True, text=True)
        ok &= check("versi target di luar domain ruleset -> exit 2 (dulu: pass=true konklusif)",
                    rc_p.returncode == 2 and "1.6" in rc_p.stderr
                    and "domain ruleset" in rc_p.stderr and "Traceback" not in rc_p.stderr)
        # Cerminan gerbang `affects` di sisi aturan: sah di satu arah, sah di arah sebaliknya.
        rc_ok = subprocess.run(["uv", "run", str(SCAN), str(evil), "--versions", "1.7.8,8.1,9.1"],
                               capture_output=True, text=True)
        ok &= check("versi target di dalam domain -> jalan normal (gerbang tak kelebihan sapu)",
                    rc_ok.returncode in (0, 1) and "domain ruleset" not in rc_ok.stderr)

        res, _ = run_scan(evil, "1.7.8,8.1,9.1")
        ok &= check("tiap versi mencatat rules_evaluated > 0 supaya agregat bisa membedakan "
                    "'bersih' dari 'tak dinilai'",
                    all(m.get("rules_evaluated", 0) > 0 for m in res["versions"].values()))

        # Seam yang gerbang domain TAK bisa lihat: --rules MENGGANTI ruleset. File KB yang cuma
        # menyebut major lain membuat target sah lolos gerbang lalu dinilai nol aturan — persis
        # kondisi yang sama, satu seam di sebelah. Angkanya yang menangkapnya, bukan gerbangnya.
        only9 = t6 / "only9.json"
        only9.write_text(json.dumps({"forbidden_functions": [
            {"id": "kb-only9", "severity": "error", "kind": "function", "affects": ["9"],
             "pattern": r"\bmysql_query\b", "message": "kb", "fix": "kb"}]}), encoding="utf-8")
        res9, _ = run_scan(evil, "8.1", extra_args=["--rules", str(only9)])
        ok &= check("--rules yang tak menyebut major target -> rules_evaluated 0 (bukan 'lolos')",
                    res9["versions"]["8.1"]["rules_evaluated"] == 0
                    and res9["versions"]["8.1"]["pass"] is True)

        # Refutasi verifier: gerbang skema dipasang HANYA di kanal MENAMBAH (--extra-rules),
        # sementara --rules MENGGANTI dimuat mentah — jadi rule yang tak akan pernah menyala
        # lolos lewat flag di sebelahnya & module ber-eval() dinyatakan lolos konklusif.
        # rules_evaluated tak menangkapnya: satu rule yang selamat menjaga hitungannya positif.
        dead = t6 / "dead.json"
        dead.write_text(json.dumps({"forbidden_functions": [
            {"id": "kb-idx", "severity": "error", "kind": "function", "affects": ["9"],
             "pattern": r"\bnever_matches_xyz\b", "message": "hidup", "fix": "-"},
            {"id": "kb-eval", "severity": "error", "kind": "function", "affects": [9],
             "pattern": r"\beval\s*\(", "message": "mati: affects angka", "fix": "-"}]}),
            encoding="utf-8")
        rc_dead = subprocess.run(["uv", "run", str(SCAN), str(evil), "--versions", "9.1",
                                  "--rules", str(dead)], capture_output=True, text=True)
        ok &= check("--rules ber-rule mati (affects angka) -> exit 2 seperti --extra-rules "
                    "(dulu: eval() lolos, ready=true)",
                    rc_dead.returncode == 2 and "kb-eval" in rc_dead.stderr
                    and "Traceback" not in rc_dead.stderr)
        rc_live = subprocess.run(["uv", "run", str(SCAN), str(evil), "--versions", "9.1",
                                  "--rules", str(only9)], capture_output=True, text=True)
        ok &= check("--rules yang sah tetap jalan (gerbang tak kelebihan sapu)",
                    rc_live.returncode in (0, 1) and "validasi skema" not in rc_live.stderr)
        ok &= check("ruleset bawaan patuh gerbang yang kini dipasang ke --rules",
                    _scan_mod.validate_extra_rules(
                        json.loads(_scan_mod.DEFAULT_RULES.read_text()), label="ruleset") == [])

        # customization-3: token {project-root} tak terekspansi = path filesystem harfiah.
        # unresolved_path_args satu pemilik (dulu reject_unresolved_paths 3x psm-setup, 0x sini).
        ok &= check("unresolved_path_args tangkap token, lewati path bersih & None",
                    _scan_mod.unresolved_path_args(
                        [("-o", "{project-root}/x"), ("--rules", "/abs/ok.json"),
                         ("--extra-rules", None)]) == [("-o", "{project-root}/x")])
        rc_tok = subprocess.run(["uv", "run", str(SCAN), str(evil), "--versions", "9.1",
                                 "-o", "{project-root}/out.json"], capture_output=True, text=True)
        ok &= check("CLI: -o ber-token {project-root} -> exit 2 error input (bukan tulis junk dir)",
                    rc_tok.returncode == 2 and "belum diresolve di -o" in rc_tok.stderr
                    and "Traceback" not in rc_tok.stderr)

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
