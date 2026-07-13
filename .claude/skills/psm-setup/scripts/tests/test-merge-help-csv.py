#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Unit test untuk merge-help-csv.py — extract codes, anti-zombie filter, roundtrip.

Jalankan: uv run scripts/tests/test-merge-help-csv.py
Exit 0 = semua lolos, 1 = ada yang gagal.
"""
import contextlib
import importlib.util
import io
import sys
import tempfile
from pathlib import Path

MOD_PATH = Path(__file__).resolve().parent.parent / "merge-help-csv.py"
spec = importlib.util.spec_from_file_location("merge_help_csv", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

_fail = []


def check(name, cond):
    print(f"  {'ok' if cond else 'FAIL'}: {name}")
    if not cond:
        _fail.append(name)


def expect_exit(fn, code=1):
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            fn()
        return False
    except SystemExit as e:
        return e.code == code


def test_extract_module_codes():
    rows = [["psm", "psm-validate"], ["psm", "psm-setup"], ["bmb", "x"], ["", "kosong"], []]
    codes = mod.extract_module_codes(rows)
    check("kode unik terkumpul", codes == {"psm", "bmb"})
    check("baris kosong/tanpa kode diabaikan", "" not in codes)


def test_filter_rows_anti_zombie():
    rows = [["psm", "a"], ["bmb", "b"], ["psm", "c"], ["core", "d"]]
    kept = mod.filter_rows(rows, "psm")
    check("semua baris kode target dibuang", all(r[0] != "psm" for r in kept if r))
    check("baris kode lain dipertahankan", ["bmb", "b"] in kept and ["core", "d"] in kept)
    check("jumlah tersisa benar (2 psm dibuang)", len(kept) == 2)


def test_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        p = str(Path(td) / "module-help.csv")
        header = list(mod.HEADER)
        rows = [["psm", "psm-validate", "Validasi", "PV", "desc,berkoma", "", "", "anytime", "", "", "false", "", ""]]
        mod.write_csv(p, header, rows)
        h2, r2 = mod.read_csv_rows(p)
        check("roundtrip header utuh", h2 == header)
        check("roundtrip baris utuh (koma dalam field aman)", r2 == rows)
        # file tak ada -> header & rows kosong
        h3, r3 = mod.read_csv_rows(str(Path(td) / "tak-ada.csv"))
        check("file tak ada -> kosong", h3 == [] and r3 == [])


def test_merge_composition():
    # anti-zombie + append: target lama punya psm basi + bmb; source psm baru
    target_rows = [["psm", "old-a"], ["bmb", "keep"], ["psm", "old-b"]]
    source_rows = [["psm", "new-a"], ["psm", "new-b"]]
    filtered = target_rows
    for code in mod.extract_module_codes(source_rows):
        filtered = mod.filter_rows(filtered, code)
    merged = filtered + source_rows
    check("baris psm lama hilang", all(not (r[0] == "psm" and "old" in r[1]) for r in merged))
    check("baris modul lain tetap", ["bmb", "keep"] in merged)
    check("baris psm baru ditambah", ["psm", "new-a"] in merged and ["psm", "new-b"] in merged)


def test_reject_unresolved_paths():
    check("{project-root} di path arg -> exit 1",
          expect_exit(lambda: mod.reject_unresolved_paths([("--target", "{project-root}/x.csv")]), 1))
    ok = True
    try:
        mod.reject_unresolved_paths([("--target", "/abs/x.csv"), ("--legacy-dir", None)])
    except SystemExit:
        ok = False
    check("path teresolusi/None -> tak exit", ok)


def main():
    for t in (test_extract_module_codes, test_filter_rows_anti_zombie, test_roundtrip,
              test_merge_composition, test_reject_unresolved_paths):
        print(f"{t.__name__}:")
        t()
    print("\n" + (f"{len(_fail)} GAGAL" if _fail else "SEMUA TEST LOLOS"))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
