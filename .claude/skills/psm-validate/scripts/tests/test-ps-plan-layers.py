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

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
