#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test untuk ps-merge-versions.py — verifikasi penggabungan file lapis per-versi.

Fokus kontrak: union `versions` lintas file; top-level direkonsiliasi deterministik
(pass=AND, list di-union, status "ran" bila ada yang jalan, screenshot_dir first-present);
versi bertumpuk dengan isi BEDA = konflik (exit 2); file salah-bentuk = exit 2; output
kanonik dikonsumsi ps-aggregate tanpa keluhan. Jalankan: uv run scripts/tests/test-ps-merge-versions.py
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
MOD_PATH = SCRIPTS / "ps-merge-versions.py"
spec = importlib.util.spec_from_file_location("ps_merge_versions", MOD_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    return cond


def _write(tmp, name, obj):
    p = Path(tmp) / name
    p.write_text(json.dumps(obj), encoding="utf-8")
    return str(p)


def _run(inputs, layer=None, output=None):
    """Jalankan skrip sbg subprocess -> (returncode, stdout, stderr)."""
    cmd = ["uv", "run", str(MOD_PATH), "--inputs", *inputs]
    if layer:
        cmd += ["--layer", layer]
    if output:
        cmd += ["-o", output]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout, r.stderr


def test_pure():
    """Fungsi murni: merge_versions_field & merge_toplevel tanpa subprocess."""
    ok = True
    a = {"e2e_available": True, "status": "ran", "pass": True, "browsers": ["chromium"],
         "scenario_notes": ["a"], "screenshot_dir": None,
         "versions": {"9.1": {"pass": True, "findings": []}}}
    b = {"e2e_available": True, "status": "ran", "pass": False, "browsers": ["firefox"],
         "scenario_notes": ["b"], "screenshot_dir": "/shots/run-x",
         "versions": {"8.1": {"pass": False, "findings": []}}}
    c = {"e2e_available": False, "status": "skipped", "pass": True, "browsers": ["chromium"],
         "scenario_notes": [], "versions": {}}  # skipped: tak menyumbang versi

    mv = mod.merge_versions_field([a, b, c])
    ok &= check("union 3 file -> versi 9.1 & 8.1 (skipped tak menyumbang)",
                set(mv.keys()) == {"9.1", "8.1"})
    ok &= check("urutan versi mengikuti kemunculan --inputs", list(mv.keys()) == ["9.1", "8.1"])

    top = mod.merge_toplevel([a, b, c], mv)
    ok &= check("pass = AND semua (True & False & True -> False)", top["pass"] is False)
    ok &= check("status 'ran' bila ada yang jalan", top["status"] == "ran")
    ok &= check("e2e_available OR (True bila ada satu pun)", top["e2e_available"] is True)
    ok &= check("browsers di-union urut-stabil", top["browsers"] == ["chromium", "firefox"])
    ok &= check("scenario_notes di-union", top["scenario_notes"] == ["a", "b"])
    ok &= check("screenshot_dir first-present (lewati None)", top["screenshot_dir"] == "/shots/run-x")
    ok &= check("versions ikut di top hasil merge", set(top["versions"].keys()) == {"9.1", "8.1"})

    # Duplikat IDENTIK sah (mis. reuse) — tak raise, pertahankan.
    mv2 = mod.merge_versions_field([a, a])
    ok &= check("duplikat versi identik -> sah, satu entri", list(mv2.keys()) == ["9.1"])

    # Konflik: versi sama, isi beda -> raise ValueError.
    conflict = {"versions": {"9.1": {"pass": False, "findings": []}}}
    try:
        mod.merge_versions_field([a, conflict])
        ok &= check("versi bertumpuk isi beda -> raise", False)
    except ValueError:
        ok &= check("versi bertumpuk isi beda -> raise ValueError", True)
    return ok


def test_cli():
    """Jalur CLI: exit code & output kanonik lewat subprocess."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        f91 = _write(tmp, "m-e2e-9.1.json",
                     {"module": "m", "e2e_available": True, "status": "ran", "pass": True,
                      "scenario_notes": ["x"], "versions": {"9.1": {"pass": True, "findings": []}}})
        f81 = _write(tmp, "m-e2e-8.1.json",
                     {"module": "m", "e2e_available": True, "status": "ran", "pass": False,
                      "scenario_notes": ["y"], "versions": {"8.1": {"pass": False, "findings": []}}})
        out = str(Path(tmp) / "m-e2e.json")
        rc, _, _ = _run([f91, f81], layer="e2e", output=out)
        ok &= check("merge dua versi -> exit 0", rc == 0)
        merged = json.loads(Path(out).read_text(encoding="utf-8"))
        ok &= check("output kanonik memuat kedua versi",
                    set(merged["versions"].keys()) == {"9.1", "8.1"})
        ok &= check("output kanonik pass=AND (False)", merged["pass"] is False)
        ok &= check("output kanonik notes ter-union", merged["scenario_notes"] == ["x", "y"])

        # Merged file harus dikonsumsi ps-aggregate tanpa gerbang-bentuk menolaknya.
        static = _write(tmp, "static.json",
                        {"module": "m", "main_file_found": True, "pass": True,
                         "versions": {"9.1": {"errors": 0, "warnings": 0, "findings": [],
                                              "rules_evaluated": 5},
                                      "8.1": {"errors": 0, "warnings": 0, "findings": [],
                                              "rules_evaluated": 5}}})
        agg = subprocess.run(
            ["uv", "run", str(SCRIPTS / "ps-aggregate.py"), "--static", static,
             "--e2e", out, "--versions", "9.1,8.1"], capture_output=True, text=True)
        ok &= check("ps-aggregate menerima output merge (exit 0/1, bukan 2 salah-bentuk)",
                    agg.returncode in (0, 1))

        # Konflik versi -> exit 2.
        conflict = _write(tmp, "m-e2e-9.1-b.json",
                          {"versions": {"9.1": {"pass": False, "findings": []}}})
        rc_c, _, err_c = _run([f91, conflict])
        ok &= check("konflik versi (isi beda) -> exit 2", rc_c == 2)
        ok &= check("pesan konflik menyebut versi", "9.1" in err_c and "BERBEDA" in err_c)

        # Salah-bentuk (versions list) -> exit 2.
        bad = _write(tmp, "bad.json", {"versions": [1, 2]})
        rc_b, _, _ = _run([bad])
        ok &= check("versions bertipe list -> exit 2 (gerbang bentuk)", rc_b == 2)

        # File tak terbaca -> exit 2.
        rc_m, _, _ = _run([str(Path(tmp) / "tak-ada.json")])
        ok &= check("file input tak ada -> exit 2", rc_m == 2)
    return ok


def main():
    ok = True
    print("test_pure:")
    ok &= test_pure()
    print("test_cli:")
    ok &= test_cli()
    print()
    print("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
