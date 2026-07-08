#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test untuk ps-flashlight-run.py — fokus parsing & degrade (tanpa Docker pull).

Menguji fungsi murni (parse_tag_map) dan kontrak output saat Docker tak ada.
Tidak menjalankan container nyata (image besar). Jalankan:
  uv run scripts/tests/test_ps_flashlight_run.py
"""
import importlib.util
import sys
from pathlib import Path

MOD_PATH = Path(__file__).resolve().parent.parent / "ps-flashlight-run.py"
spec = importlib.util.spec_from_file_location("ps_flashlight_run", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    return cond


def main():
    ok = True

    # parse_tag_map: kosong -> default
    ok &= check("tag-map kosong -> default", mod.parse_tag_map("") == mod.DEFAULT_TAG_MAP)
    # parse_tag_map: custom
    tm = mod.parse_tag_map("9.0=nightly,8.1=8.1")
    ok &= check("tag-map custom diparse", tm.get("9.0") == "nightly" and tm.get("8.1") == "8.1")
    # parse_tag_map: entri tanpa '=' diabaikan, sisanya tetap
    tm2 = mod.parse_tag_map("9.0=nightly,rusak")
    ok &= check("entri tanpa '=' diabaikan", tm2 == {"9.0": "nightly"})
    # tag map default punya 3 versi inti
    ok &= check("default tag-map punya 1.7.8/8.1/9.0",
                all(k in mod.DEFAULT_TAG_MAP for k in ("1.7.8", "8.1", "9.0")))

    # parse_phpcs: report JSON valid -> hitungan exact
    good_out = 'PSM_INSTALL_OK PSM_CS_JSON_START {"totals":{"errors":2,"warnings":1},"files":{"a.php":{"messages":[{"type":"ERROR","line":3,"source":"X","message":"bad"},{"type":"WARNING","line":5}]}}} PSM_CS_JSON_END'
    cs = mod.parse_phpcs(good_out)
    ok &= check("phpcs JSON valid -> errors exact 2", cs.get("available") and cs.get("parse_ok") and cs.get("errors") == 2)
    ok &= check("phpcs JSON valid -> kumpulkan error message", len(cs.get("error_messages", [])) == 1)
    ok &= check("phpcs absent -> available False", mod.parse_phpcs("PSM_CS_ABSENT").get("available") is False)
    bad = mod.parse_phpcs("PSM_CS_JSON_START tidak-ada-json PSM_CS_JSON_END")
    ok &= check("phpcs JSON rusak -> parse_ok False (tak menebak)", bad.get("parse_ok") is False)
    # regression determinism-1: baris liar ber-ERROR tak menggelembungkan hitungan
    noisy = mod.parse_phpcs('PSM_CS_JSON_START {"totals":{"errors":0,"warnings":0},"files":{}} PSM_CS_JSON_END echo "FOUND 9 ERRORS"')
    ok &= check("baris liar ber-ERROR tak menggelembungkan (errors=0)", noisy.get("errors") == 0)

    # enhancement-1: image belum ada lokal + allow_pull False -> skipped_image, tak menarik & tak crash
    orig_present = mod.image_present
    mod.image_present = lambda ref: False  # simulasikan image absen tanpa Docker
    try:
        r = mod.run_one_version(Path("/tmp/x"), "8.1", "8.1", pull=True, timeout=1, allow_pull=False)
        ok &= check("image absen + allow_pull False -> skipped_image", r.get("skipped_image") is True)
        ok &= check("image absen + allow_pull False -> tak pass, tak konklusif (errors terisi)",
                    r["pass"] is False and len(r["errors"]) == 1 and r["install"] is None)
    finally:
        mod.image_present = orig_present

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
