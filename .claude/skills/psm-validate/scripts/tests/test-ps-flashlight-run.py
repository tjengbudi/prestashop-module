#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test untuk ps-flashlight-run.py — fungsi murni & orkestrasi (tanpa Docker).

Menguji parsing (tag-map, install, phpstan), pembuatan compose, gerbang kesiapan,
dan degrade jujur — semua tanpa menjalankan container nyata (image besar). Docker
di-monkeypatch. Jalankan: uv run scripts/tests/test-ps-flashlight-run.py
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


PHPSTAN_JSON = ('{"totals":{"errors":0,"file_errors":2},'
                '"files":{"a.php":{"errors":2,"messages":['
                '{"message":"bad","line":3},{"message":"worse","line":9}]}},"errors":[]}')


def main():
    ok = True

    # --- parse_tag_map ---
    ok &= check("tag-map kosong -> default", mod.parse_tag_map("") == mod.DEFAULT_TAG_MAP)
    tm = mod.parse_tag_map("9.1=9.1.4-nginx,8.1=8.1.6-nginx")
    ok &= check("tag-map custom diparse", tm.get("9.1") == "9.1.4-nginx" and tm.get("8.1") == "8.1.6-nginx")
    tm2 = mod.parse_tag_map("9.1=9.1.4-nginx,rusak")
    ok &= check("entri tanpa '=' diabaikan", tm2 == {"9.1": "9.1.4-nginx"})
    ok &= check("default tag-map punya 1.7.8/8.1/9.1",
                all(k in mod.DEFAULT_TAG_MAP for k in ("1.7.8", "8.1", "9.1")))

    # --- parse_install ---
    ok &= check("install OK", mod.parse_install("...PSM_INSTALL_OK...")["ok"] is True)
    ok &= check("install FAIL", mod.parse_install("...PSM_INSTALL_FAIL...")["ok"] is False)
    ci = mod.parse_install("PSM_COPY_FAIL")
    ok &= check("copy fail -> copy_fail True & ok False", ci["copy_fail"] is True and ci["ok"] is False)

    # --- parse_phpstan: neon MILIK MODULE (GEN=0) -> konklusif (errors nyata) ---
    conc = mod.parse_phpstan(f"PSM_PHPSTAN_GEN=0\nPSM_PHPSTAN_JSON_START {PHPSTAN_JSON} PSM_PHPSTAN_JSON_END")
    ok &= check("phpstan module-neon -> errors exact 2", conc.get("parse_ok") and conc.get("errors") == 2)
    ok &= check("phpstan module-neon -> generated_config False & 2 pesan",
                conc.get("generated_config") is False and len(conc.get("error_messages", [])) == 2)

    # --- parse_phpstan: neon AUTO-GENERATE (GEN=1) -> ADVISORY (errors=0, warnings) ---
    adv = mod.parse_phpstan(f"PSM_PHPSTAN_GEN=1\nPSM_PHPSTAN_JSON_START {PHPSTAN_JSON} PSM_PHPSTAN_JSON_END")
    ok &= check("phpstan auto-neon -> advisory: errors=0 (tak memblok)", adv.get("errors") == 0)
    ok &= check("phpstan auto-neon -> temuan jadi warnings & generated_config True",
                adv.get("warnings") == 2 and adv.get("generated_config") is True)

    # --- parse_phpstan: degrade jujur ---
    ok &= check("phpstan absent -> available False", mod.parse_phpstan("PSM_PHPSTAN_ABSENT").get("available") is False)
    ok &= check("phpstan tanpa penanda -> parse_ok False",
                mod.parse_phpstan("PSM_PHPSTAN_GEN=0 tak-ada-marker").get("parse_ok") is False)
    broken = mod.parse_phpstan("PSM_PHPSTAN_JSON_START bukan-json PSM_PHPSTAN_JSON_END")
    ok &= check("phpstan JSON rusak -> parse_ok False (tak menebak)", broken.get("parse_ok") is False)
    # error non-file (mis. bootstrap/neon) tetap terhitung
    generic = mod.parse_phpstan('PSM_PHPSTAN_GEN=0\nPSM_PHPSTAN_JSON_START {"totals":{"file_errors":0},"files":{},"errors":["neon rusak"]} PSM_PHPSTAN_JSON_END')
    ok &= check("phpstan error non-file terhitung (count=1)", generic.get("errors") == 1)

    # --- _compose_file_text: DB + flashlight berpasangan, env benar ---
    yml = mod._compose_file_text("mariadb:lts", "prestashop/prestashop-flashlight:9.1.4-nginx",
                                 "localhost:8000", "/x/mod")
    for needle in ("image: mariadb:lts", "image: prestashop/prestashop-flashlight:9.1.4-nginx",
                   "MYSQL_HOST: db", "condition: service_healthy", "healthcheck.sh",
                   "/x/mod:/ps-module-src:ro", "PS_DOMAIN: localhost:8000"):
        ok &= check(f"compose berisi '{needle}'", needle in yml)
    # backward-compat: tanpa publish -> TAK ada port terpublish (perilaku lama utuh)
    ok &= check("compose default tanpa 'ports:' (backward-compat)", "ports:" not in yml)
    # publish opsional (dipakai Lapis 4 E2E): port HTTP flashlight terpublish ke host
    yml_pub = mod._compose_file_text("mariadb:lts", "prestashop/prestashop-flashlight:9.1.4-nginx",
                                     "localhost:8000", "/x/mod", publish="8000:80")
    ok &= check("compose publish -> ada 'ports:' & '8000:80'",
                "ports:" in yml_pub and '- "8000:80"' in yml_pub)

    # --- wait_healthy: sinyal kesiapan dari HEALTH container (monkeypatch) ---
    orig_health = mod._health_status
    try:
        mod._health_status = lambda c: "healthy"
        ok &= check("health 'healthy' -> (True, healthy)", mod.wait_healthy("x", 1) == (True, "healthy"))
        mod._health_status = lambda c: "unhealthy"
        okc, st = mod.wait_healthy("x", 1)
        ok &= check("health 'unhealthy' -> (False, unhealthy)", okc is False and st == "unhealthy")
        mod._health_status = lambda c: "starting"
        okc, st = mod.wait_healthy("x", 0.05, poll=0.01)
        ok &= check("health 'starting' terus -> timeout (False)", okc is False and st.startswith("timeout"))
    finally:
        mod._health_status = orig_health

    # --- run_one_version: image absen + pull tak diizinkan -> skipped_image (degrade jujur) ---
    orig_present, orig_compose = mod.image_present, mod.compose_available
    try:
        mod.image_present = lambda ref: False   # simulasikan image absen tanpa Docker
        mod.compose_available = lambda: True
        r = mod.run_one_version(Path("/tmp"), "testmod", "9.1", "9.1.4-nginx",
                                orchestrator="auto", db_image="mariadb:lts", ps_domain="localhost:8000",
                                startup_timeout=1, op_timeout=1, allow_pull=False)
        ok &= check("image absen + allow_pull False -> skipped_image", r.get("skipped_image") is True)
        ok &= check("image absen -> orchestrator terpilih 'compose', tak pass, install None",
                    r["orchestrator"] == "compose" and r["pass"] is False and r["install"] is None)
    finally:
        mod.image_present, mod.compose_available = orig_present, orig_compose

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
