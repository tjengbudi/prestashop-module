#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test untuk ps-aggregate.py — verifikasi vonis dihitung native & degrade jujur.

Fokus kontrak: pass per-versi & keseluruhan dihitung dari temuan error lapis
konklusif; lapis flashlight tak konklusif (skipped/pull-fail/timeout/no-console)
TAK PERNAH memblok. Jalankan: uv run scripts/tests/test-ps-aggregate.py
"""
import importlib.util
import sys
from pathlib import Path

MOD_PATH = Path(__file__).resolve().parent.parent / "ps-aggregate.py"
spec = importlib.util.spec_from_file_location("ps_aggregate", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    return cond


def static_result(versions):
    """versions: {full_ver: [(id, severity)]} -> bentuk output ps-static-scan."""
    out = {"module": "m", "versions": {}}
    for ver, finds in versions.items():
        errs = sum(1 for _, sev in finds if sev == "error")
        out["versions"][ver] = {
            "major": ver.split(".")[0], "errors": errs,
            "warnings": len(finds) - errs, "pass": errs == 0,
            "findings": [{"id": i, "severity": s, "kind": "x", "message": i,
                          "fix": "", "occurrences": [{"file": "a.php", "line": 1}], "count": 1}
                         for i, s in finds],
        }
    out["pass"] = all(v["pass"] for v in out["versions"].values())
    return out


def main():
    ok = True
    TV = ["1.7.8", "8.1", "9.0"]

    # 1. Static bersih, tanpa flashlight/adversarial -> lolos, tapi flashlight tak konklusif
    static = static_result({v: [] for v in TV})
    r = mod.merge_version("8.1", static, None, None, TV)
    ok &= check("static bersih -> versi lolos", r["pass"])
    ok &= check("tanpa flashlight -> flashlight_conclusive False", not r["flashlight_conclusive"])
    ok &= check("static selalu memberi vonis dasar konklusif", r["conclusive"])

    # 2. Static punya error -> versi gagal (dihitung native, bukan model)
    static_bad = static_result({"8.1": [("cls-attribute", "error")], "9.0": [], "1.7.8": []})
    r = mod.merge_version("8.1", static_bad, None, None, TV)
    ok &= check("static error -> versi gagal", not r["pass"] and len(r["blocking"]) == 1)
    r90 = mod.merge_version("9.0", static_bad, None, None, TV)
    ok &= check("versi lain tanpa error tetap lolos", r90["pass"])

    # 3. Flashlight skipped (Docker absen) -> TAK memblok versi yang static-nya bersih
    flash_skipped = {"module": "m", "docker_available": False, "status": "skipped",
                     "reason": "Docker absen", "versions": {}}
    r = mod.merge_version("8.1", static, flash_skipped, None, TV)
    ok &= check("flashlight skipped tak memblok versi bersih", r["pass"])
    ok &= check("flashlight skipped -> state skipped, tak konklusif",
                r["layers"]["flashlight"]["state"] == "skipped" and not r["flashlight_conclusive"])

    # 4. Flashlight gagal infra (timeout) -> TAK memblok (degrade jujur), tak diklaim gagal
    flash_infra = {"module": "m", "docker_available": True, "status": "ran",
                   "versions": {"8.1": {"version": "8.1", "image": "img", "install": None,
                                        "coding_standard": None,
                                        "errors": ["timeout menjalankan container img"], "pass": False}}}
    r = mod.merge_version("8.1", static, flash_infra, None, TV)
    ok &= check("flashlight timeout tak memblok (enhancement-2)", r["pass"])
    ok &= check("flashlight timeout -> not_conclusive",
                r["layers"]["flashlight"]["state"] == "not_conclusive")

    # 4b. Flashlight skipped_image (image absen, pull tak diizinkan) -> tak memblok (enhancement-1)
    flash_noimg = {"module": "m", "docker_available": True, "status": "ran",
                   "versions": {"8.1": {"version": "8.1", "image": "img", "install": None,
                                        "coding_standard": None, "skipped_image": True,
                                        "errors": ["image img belum ada lokal & pull tak diizinkan"],
                                        "pass": False}}}
    r = mod.merge_version("8.1", static, flash_noimg, None, TV)
    ok &= check("flashlight skipped_image tak memblok (enhancement-1)", r["pass"])
    ok &= check("flashlight skipped_image -> not_conclusive",
                r["layers"]["flashlight"]["state"] == "not_conclusive" and not r["flashlight_conclusive"])

    # 5. Flashlight no_console -> tak konklusif, tak memblok
    flash_nocon = {"module": "m", "docker_available": True, "status": "ran",
                   "versions": {"8.1": {"version": "8.1", "image": "img",
                                        "install": {"ok": False, "no_console": True, "log": ""},
                                        "coding_standard": {"available": False},
                                        "errors": [], "pass": False}}}
    r = mod.merge_version("8.1", static, flash_nocon, None, TV)
    ok &= check("flashlight no_console tak memblok", r["pass"] and not r["flashlight_conclusive"])

    # 6. Flashlight KONKLUSIF + install ditolak -> MEMBLOK (uji nyata gagal)
    flash_fail = {"module": "m", "docker_available": True, "status": "ran",
                  "versions": {"8.1": {"version": "8.1", "image": "img",
                                       "install": {"ok": False, "no_console": False, "log": "boom"},
                                       "coding_standard": {"available": False},
                                       "errors": [], "pass": False}}}
    r = mod.merge_version("8.1", static, flash_fail, None, TV)
    ok &= check("install ditolak (konklusif) -> memblok", not r["pass"] and r["flashlight_conclusive"])

    # 7. Flashlight konklusif + phpcs error -> memblok dengan lokasi
    flash_cs = {"module": "m", "docker_available": True, "status": "ran",
                "versions": {"8.1": {"version": "8.1", "image": "img",
                                     "install": {"ok": True, "no_console": False, "log": ""},
                                     "coding_standard": {"available": True, "parse_ok": True, "errors": 2,
                                                         "error_messages": [{"line": 3, "source": "X", "message": "bad"},
                                                                            {"line": 9, "source": "Y", "message": "worse"}]},
                                     "errors": [], "pass": False}}}
    r = mod.merge_version("8.1", static, flash_cs, None, TV)
    ok &= check("phpcs 2 error -> 2 temuan memblok", not r["pass"] and len(r["blocking"]) == 2)

    # 8. Adversarial error -> memblok; adversarial warning -> tak memblok
    adv = {"findings": [{"id": "adv-sqli", "severity": "error", "message": "SQL injection",
                         "versions": ["8.1"], "location": "x.php:5"},
                        {"id": "adv-perf", "severity": "warning", "message": "query in loop",
                         "versions": ["8.1"]}]}
    r = mod.merge_version("8.1", static, None, adv, TV)
    ok &= check("adversarial error memblok", not r["pass"])
    ok &= check("adversarial error terkumpul 1 blocking (warning tak)", len(r["blocking"]) == 1)
    # adversarial tanpa versi -> berlaku semua versi target
    adv_all = {"findings": [{"id": "adv-x", "severity": "error", "message": "global"}]}
    r97 = mod.merge_version("9.0", static, None, adv_all, TV)
    ok &= check("adversarial tanpa versi -> berlaku semua target", not r97["pass"])
    # regression architecture-1: versions major-form ('8') harus match full-form target ('8.1')
    adv_major = {"findings": [{"id": "adv-m", "severity": "error", "message": "major-form",
                               "versions": ["8"]}]}
    r_m = mod.merge_version("8.1", static, None, adv_major, TV)
    ok &= check("adversarial major-form '8' match target '8.1' (tak diam-diam drop)", not r_m["pass"])
    r_m90 = mod.merge_version("9.0", static, None, adv_major, TV)
    ok &= check("major-form '8' TAK bocor ke versi lain (9.0 tetap lolos)", r_m90["pass"])
    # full-form tetap match apa adanya
    adv_full = {"findings": [{"id": "adv-f", "severity": "error", "message": "full-form",
                              "versions": ["1.7.8"]}]}
    r_f = mod.merge_version("1.7.8", static, None, adv_full, TV)
    ok &= check("adversarial full-form '1.7.8' tetap match", not r_f["pass"])

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
