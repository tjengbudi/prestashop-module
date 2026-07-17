#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test untuk ps-plan-layers.py — keputusan reuse/rerun deterministik.

Kontrak: file lapis dipakai ulang HANYA bila ada + terbaca + lebih baru dari source
module + cakupan versinya memuat yang diminta. Basi/kurang/rusak -> rerun (jangan
pernah memvonis atas bukti basi). Jalankan: uv run scripts/tests/test-ps-plan-layers.py
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

MOD_PATH = Path(__file__).resolve().parent.parent / "ps-plan-layers.py"
spec = importlib.util.spec_from_file_location("ps_plan_layers", MOD_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

TV = ["1.7.8", "8.1", "9.1"]


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    return cond


def _touch(path, mtime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    os.utime(path, (mtime, mtime))


def _layer(path, versions, mtime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"versions": {v: {"pass": True} for v in versions}}), encoding="utf-8")
    os.utime(path, (mtime, mtime))


def main():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mdir = root / "mymod"
        reports = root / "reports"

        # source module: file termuda pada t=1000
        _touch(mdir / "mymod.php", 1000)
        _touch(mdir / "index.php", 900)
        # vendor/ diabaikan walau jauh lebih baru (bukan source yang kita vonis)
        _touch(mdir / "vendor" / "lib" / "big.php", 9000)

        # REGRESI: match path ABSOLUT dulu membuang seluruh module yang kebetulan
        # berada di bawah ancestor bernama vendor/ -> mtime 0.0 -> file lapis 1970
        # dianggap SEGAR = vonis atas bukti basi (bencana yang skrip ini cegah).
        under = root / "vendor" / "acme" / "shop" / "mymod"
        _touch(under / "mymod.php", 1000)
        nm_under, _ = mod.newest_source_mtime(under)
        ok &= check("module di bawah ancestor vendor/ -> mtime NYATA, bukan 0.0", nm_under == 1000)

        newest, where = mod.newest_source_mtime(mdir)
        ok &= check("newest_source_mtime abaikan vendor/ (1000, bukan 9000)", newest == 1000)
        ok &= check("newest_source_mtime sebut file-nya", where is not None and where.name == "mymod.php")

        # lapis LEBIH BARU + cakupan penuh -> reuse
        _layer(reports / "mymod-static.json", TV, 2000)
        p = mod.plan_layer(reports / "mymod-static.json", TV, newest, "mymod.php")
        ok &= check("lapis lebih baru + cakupan cocok -> reuse", p["reuse"] is True)

        # lapis BASI (module berubah setelahnya) -> rerun (anti vonis atas bukti basi)
        _layer(reports / "mymod-flashlight.json", TV, 500)
        p = mod.plan_layer(reports / "mymod-flashlight.json", TV, newest, "mymod.php")
        ok &= check("lapis lebih tua dari module -> rerun", p["reuse"] is False and "lebih baru" in p["reason"])
        ok &= check("alasan basi sebut file source pemicunya", "mymod.php" in p["reason"])

        # cakupan KURANG -> rerun
        _layer(reports / "mymod-e2e.json", ["9.1"], 2000)
        p = mod.plan_layer(reports / "mymod-e2e.json", TV, newest, None)
        ok &= check("cakupan versi kurang -> rerun", p["reuse"] is False and "cakupan kurang" in p["reason"])
        ok &= check("alasan cakupan sebut versi yang hilang", "1.7.8" in p["reason"] and "8.1" in p["reason"])
        # cakupan LEBIH luas tetap boleh (superset memuat yang diminta)
        _layer(reports / "mymod-wide.json", TV + ["9.2"], 2000)
        p = mod.plan_layer(reports / "mymod-wide.json", TV, newest, None)
        ok &= check("cakupan superset -> tetap reuse", p["reuse"] is True)

        # ABSEN / RUSAK -> rerun
        p = mod.plan_layer(reports / "tak-ada.json", TV, newest, None)
        ok &= check("file lapis absen -> rerun", p["reuse"] is False and "belum ada" in p["reason"])
        broken = reports / "mymod-broken.json"
        broken.write_text("{bukan json", encoding="utf-8")
        os.utime(broken, (2000, 2000))
        p = mod.plan_layer(broken, TV, newest, None)
        ok &= check("file lapis rusak -> rerun (tak crash)", p["reuse"] is False and "tak terbaca" in p["reason"])

        # cakupan tak bisa dipastikan (bentuk adversarial) -> rerun, bukan tebakan
        adv = reports / "mymod-adversarial.json"
        adv.write_text(json.dumps({"findings": []}), encoding="utf-8")
        os.utime(adv, (2000, 2000))
        p = mod.plan_layer(adv, TV, newest, None)
        ok &= check("cakupan tak bisa dipastikan -> rerun", p["reuse"] is False and "tak bisa dipastikan" in p["reason"])
        ok &= check("layer_versions bentuk tak dikenal -> None", mod.layer_versions({"x": 1}) is None)
        ok &= check("layer_versions dari dict versions -> set", mod.layer_versions(
            {"versions": {"9.1": {}}}) == {"9.1"})
        # Lapis adversarial menyatakan cakupan yang DITINJAU di top-level `versions`
        ok &= check("layer_versions dari list versions (adversarial) -> set",
                    mod.layer_versions({"versions": ["1.7.8", "8.1"], "findings": []}) == {"1.7.8", "8.1"})
        ok &= check("cakupan TAK diturunkan dari findings (versi terpengaruh != yang ditinjau)",
                    mod.layer_versions({"findings": [{"versions": ["8.1"]}]}) is None)
        adv_fresh = reports / "mymod-adversarial.json"
        adv_fresh.write_text(json.dumps({"versions": TV, "findings": []}), encoding="utf-8")
        os.utime(adv_fresh, (2000, 2000))
        pa = mod.plan_layer(adv_fresh, TV, newest, None)
        ok &= check("lapis adversarial segar + cakupan dinyatakan -> reuse (lapis termahal tak diulang)",
                    pa["reuse"] is True)

    # --- determinism-3 (analyze 2026-07-17-1024): vonis Lapis 1 punya DUA input (module
    # DAN ruleset) tapi kesegaran cuma men-stat yang pertama. Aturan KB yang baru
    # ditambahkan lalu tak pernah menyala: file lapis basi dipakai ulang & melapor pass,
    # sementara SKILL.md melarang model membackstop-nya.
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        mod_dir = t / "mymod"
        mod_dir.mkdir()
        (mod_dir / "mymod.php").write_text("<?php class MyMod extends Module {}")
        rules = t / "ps-rules.json"
        rules.write_text('{"removed_hooks": []}')
        extra = t / "extra.json"
        extra.write_text('{"removed_hooks": []}')
        layer = t / "mymod-static.json"

        def _write_layer(ruleset_files, ruleset_mtime):
            layer.write_text(json.dumps({
                "module": "mymod", "versions": {v: {"pass": True} for v in TV},
                "ruleset": {"files": [str(p.resolve()) for p in ruleset_files],
                            "mtime": ruleset_mtime}}))
            os.utime(layer, (9e9, 9e9))  # jauh lebih baru dari source: isolasi cek ruleset

        base_state = mod.ss.ruleset_provenance([str(rules)])
        _write_layer([rules], base_state["mtime"])
        r = mod.plan_layer(layer, TV, 0.0, None, ruleset=base_state)
        ok &= check("ruleset sama & tak berubah -> reuse", r["reuse"] is True)

        with_extra = mod.ss.ruleset_provenance([str(rules), str(extra)])
        r = mod.plan_layer(layer, TV, 0.0, None, ruleset=with_extra)
        ok &= check("aturan KB BARU ditambahkan -> rerun (dulu: reuse, aturan tak pernah menyala)",
                    r["reuse"] is False and "ruleset berbeda" in r["reason"])

        os.utime(rules, (9e9 + 100, 9e9 + 100))  # ruleset inti disunting sesudah file lapis
        r = mod.plan_layer(layer, TV, 0.0, None, ruleset=mod.ss.ruleset_provenance([str(rules)]))
        ok &= check("ruleset inti lebih baru dari file lapis -> rerun",
                    r["reuse"] is False and "lebih baru" in r["reason"])

        _write_layer([rules], base_state["mtime"])
        stale = json.loads(layer.read_text())
        del stale["ruleset"]
        layer.write_text(json.dumps(stale))
        os.utime(layer, (9e9, 9e9))
        r = mod.plan_layer(layer, TV, 0.0, None, ruleset=base_state)
        ok &= check("file lapis tanpa jejak ruleset -> rerun (tak bisa dipastikan, jangan tebak)",
                    r["reuse"] is False and "tak mencatat ruleset" in r["reason"])
        r = mod.plan_layer(layer, TV, 0.0, None, ruleset=None)
        ok &= check("lapis non-static tak dinilai atas ruleset (ruleset tak memproduksinya)",
                    r["reuse"] is True)

        # --- enhancement-1: spec E2E authored — satu-satunya input tulisan tangan —
        # divalidasi di pra-pass, sebelum satu container pun boot.
        e2e_dir = mod_dir / "tests" / "e2e"
        e2e_dir.mkdir(parents=True)
        (e2e_dir / "ok.json").write_text(json.dumps(
            {"name": "ok", "steps": [{"action": "goto", "area": "fo", "path": "/"}]}))
        (e2e_dir / "typo.json").write_text(json.dumps(
            {"name": "bad", "steps": [{"action": "expect_visable", "selector": "#x"}]}))
        # Jalur CLI: unit test memanggil plan_layer LANGSUNG, jadi wiring main() ->
        # plan_layer(ruleset=...) tak tersentuh — persis mode "jalur CLI tanpa coverage"
        # yang bikin test hijau di atas kode salah. Diuji lewat proses nyata.
        reports = t / "reports"
        reports.mkdir()
        real_static = Path(mod.ss.DEFAULT_RULES)
        subprocess.run(["uv", "run", str(Path(MOD_PATH).parent / "ps-static-scan.py"),
                        str(mod_dir), "--versions", "9.1",
                        "-o", str(reports / "mymod-static.json")],
                       capture_output=True, text=True)

        def _plan_cli(*extra):
            r = subprocess.run(["uv", "run", str(MOD_PATH), str(mod_dir),
                                "--reports-dir", str(reports), "--versions", "9.1", *extra],
                               capture_output=True, text=True)
            return json.loads(r.stdout)

        ok &= check("CLI: ruleset sama -> static boleh reuse",
                    _plan_cli()["layers"]["static"]["reuse"] is True and real_static.is_file())
        ok &= check("CLI: --extra-rules diteruskan -> static rerun (wiring main() teruji)",
                    _plan_cli("--extra-rules", str(extra))["layers"]["static"]["reuse"] is False)

        sources, notes = mod._e2e_scenarios(mod_dir)
        ok &= check("pra-pass menemukan spec authored yang sah", sources == ["ok.json"])
        ok &= check("pra-pass menandai spec rusak SEBELUM container boot",
                    len(notes) == 1 and "typo.json" in notes[0])
        ok &= check("catatan menyebut kosakata yang SAH, bukan cuma yang salah",
                    "expect_visible" in notes[0] and "goto" in notes[0])
        # Emisi main() (verifier adversarial): fungsinya teruji, tapi penulisan kedua field
        # ke JSON dulu NOL coverage — seluruh output pra-pass bisa dihapus tanpa satu test
        # pun merah. Diuji lewat proses nyata, seperti wiring ruleset di main() yang sama.
        plan = _plan_cli()
        ok &= check("CLI: e2e_scenarios sampai ke JSON pra-pass", plan.get("e2e_scenarios") == ["ok.json"])
        ok &= check("CLI: e2e_scenario_notes sampai ke JSON pra-pass",
                    len(plan.get("e2e_scenario_notes") or []) == 1
                    and "typo.json" in plan["e2e_scenario_notes"][0])

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
