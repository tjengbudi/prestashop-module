#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test untuk ps-scenario-run.py — Lapis 5, skenario kondisi-rusak.

Fokus kontrak: (1) bentuk skenario digerbang SEBELUM dijalankan, dan yang cacat DILEWATI
dengan catatan alih-alih menggagalkan lapis; (2) tiga kanal hasil dibedakan — `given` gagal
= TAK KONKLUSIF (kondisi rusaknya tak terbentuk, jadi apa pun sesudahnya bicara tentang
keadaan lain), `then` meleset = GAGAL, query error = TAK KONKLUSIF; (3) `when` yang gagal
TIDAK otomatis menggagalkan — "upgrade menolak jalan di kondisi ini" bisa jadi yang diuji;
(4) restore snapshot terjadi SEBELUM `given`, karena itu satu-satunya yang membuat skenario
tak urut-bergantung; (5) perbandingan `expect` string, bukan numerik.

Lapisan container dipalsukan lewat injeksi `_sh`/`_exec` — logika diuji tanpa Docker.
Jalankan: uv run scripts/tests/test-ps-scenario-run.py
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

MOD_PATH = Path(__file__).resolve().parent.parent / "ps-scenario-run.py"
spec = importlib.util.spec_from_file_location("ps_scenario_run", MOD_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    return cond


class _CP:
    def __init__(self, rc=0, out="", err=""):
        self.returncode, self.stdout, self.stderr = rc, out, err


def _install_fakes(script):
    """Ganti lapisan container dengan skrip jawaban. Return (calls, restore_fn)."""
    calls = []
    orig_sh, orig_exec = mod._sh, mod.fl._exec

    def fake_sh(session, inner, timeout=None):
        calls.append(("sh", inner))
        for pat, cp in script:
            if pat in inner:
                return cp
        return _CP(0, "")

    def fake_exec(session, env, inner, timeout):
        calls.append(("exec", inner))
        for pat, cp in script:
            if pat in inner:
                return cp
        return _CP(0, "")

    mod._sh, mod.fl._exec = fake_sh, fake_exec

    def restore():
        mod._sh, mod.fl._exec = orig_sh, orig_exec
    return calls, restore


def _scen(**kw):
    base = {"name": "s", "given": [], "when": "none",
            "then": [{"query": "SELECT 1", "expect": "1"}]}
    base.update(kw)
    return base


def main():
    ok = True

    # --- validate_scenario: bentuk digerbang sebelum dijalankan ---
    ok &= check("bentuk sah -> None", mod.validate_scenario(_scen()) is None)
    ok &= check("bukan objek -> ditolak", mod.validate_scenario([1]) is not None)
    ok &= check("tanpa name -> ditolak", mod.validate_scenario(_scen(name="")) is not None)
    ok &= check("when tak dikenal -> ditolak & menyebut yang sah",
                "sah:" in (mod.validate_scenario(_scen(when="teleport")) or ""))
    ok &= check("then kosong -> ditolak (skenario tanpa assertion tak membuktikan apa pun)",
                mod.validate_scenario(_scen(then=[])) is not None)
    ok &= check("entri then tanpa expect -> ditolak",
                mod.validate_scenario(_scen(then=[{"query": "q"}])) is not None)
    ok &= check("entri given objek tanpa `sh` -> ditolak",
                mod.validate_scenario(_scen(given=[{"x": 1}])) is not None)
    ok &= check("entri given {sh:...} -> diterima",
                mod.validate_scenario(_scen(given=[{"sh": "chmod 0555 /x"}])) is None)

    # --- discover_scenarios: cacat DILEWATI dgn catatan, tak menggagalkan lapis ---
    with tempfile.TemporaryDirectory() as td:
        sd = Path(td) / mod.SCENARIO_DIR
        sd.mkdir(parents=True)
        (sd / "good.json").write_text(json.dumps(_scen(name="good")), encoding="utf-8")
        (sd / "broken.json").write_text("{ bukan json", encoding="utf-8")
        (sd / "noassert.json").write_text(json.dumps(_scen(name="na", then=[])), encoding="utf-8")
        found, notes = mod.discover_scenarios(Path(td))
        ok &= check("skenario sah terkumpul; yang cacat dilewati",
                    [s["name"] for s in found] == ["good"])
        ok &= check("tiap yang dilewati punya catatan (tak hilang senyap)", len(notes) == 2)
        ok &= check("catatan menyebut nama filenya",
                    any("broken.json" in n for n in notes) and any("noassert.json" in n for n in notes))
        ok &= check("source dicatat utk telusur balik", found[0]["source"] == "good.json")
    ok &= check("folder scenarios tak ada -> nol skenario, nol catatan (bukan error)",
                mod.discover_scenarios("/tmp/tak-ada-folder-psm") == ([], []))

    # --- substitute_prefix & compare_expect ---
    ok &= check("prefix disubstitusi", mod.substitute_prefix("FROM `{prefix}orders`", "shop7_")
                == "FROM `shop7_orders`")
    ok &= check("compare_expect normalisasi spasi", mod.compare_expect(" 2 \n", "2"))
    ok &= check("compare_expect '0' BUKAN '' (nol baris beda arti dari nilai nol)",
                not mod.compare_expect("", "0"))
    ok &= check("compare_expect beda -> False", not mod.compare_expect("2", "1"))

    # --- run_scenario: tiga kanal hasil dibedakan ---
    calls, restore = _install_fakes([])
    r = mod.run_scenario({}, _scen(then=[{"query": "SELECT 1", "expect": ""}]), "m", "ps_", 10)
    restore()
    ok &= check("restore snapshot dipanggil SEBELUM given (isolasi, bukan urut-bergantung)",
                calls and mod.BASELINE_PATH in calls[0][1])

    calls, restore = _install_fakes([("UPDATE gagal", _CP(1, "err"))])
    r = mod.run_scenario({}, _scen(given=["UPDATE gagal"]), "m", "ps_", 10)
    restore()
    ok &= check("given gagal -> TAK KONKLUSIF (kondisi rusaknya tak terbentuk)",
                r["ok"] is False and r["conclusive"] is False and "given" in r["note"])

    calls, restore = _install_fakes([("-N -B", _CP(0, "2"))])
    r = mod.run_scenario({}, _scen(then=[{"query": "SELECT c", "expect": "1"}]), "m", "ps_", 10)
    restore()
    ok &= check("then meleset -> GAGAL tapi KONKLUSIF (bukti ada, hasilnya salah)",
                r["ok"] is False and r["conclusive"] is True)
    ok &= check("detail then menyebut dapat & harap (bukan pesan hampa)",
                any("dapat=" in s["detail"] and "harap=" in s["detail"]
                    for s in r["steps"] if s["phase"] == "then"))

    calls, restore = _install_fakes([("-N -B", _CP(1, "", "table tak ada"))])
    r = mod.run_scenario({}, _scen(), "m", "ps_", 10)
    restore()
    ok &= check("query then error -> TAK KONKLUSIF (assertion tak dinilai, bukan gagal)",
                r["ok"] is False and r["conclusive"] is False)

    calls, restore = _install_fakes([("prestashop:module", _CP(1, "upgrade ditolak")),
                                     ("-N -B", _CP(0, "1"))])
    r = mod.run_scenario({}, _scen(when="upgrade"), "m", "ps_", 10)
    restore()
    ok &= check("when gagal TIDAK otomatis menggagalkan — then yang memutuskan",
                r["ok"] is True and r["conclusive"] is True)
    ok &= check("kegagalan when tetap tercatat di langkah (tak disembunyikan)",
                any(s["phase"] == "when" and s["ok"] is False for s in r["steps"]))

    calls, restore = _install_fakes([(mod.BASELINE_PATH, _CP(1, "restore gagal"))])
    r = mod.run_scenario({}, _scen(), "m", "ps_", 10)
    restore()
    ok &= check("restore gagal -> TAK KONKLUSIF & given tak dijalankan",
                r["conclusive"] is False and not any(s["phase"] == "given" for s in r["steps"]))

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
