#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test untuk ps-flashlight-run.py — fungsi murni & orkestrasi (tanpa Docker).

Menguji parsing (tag-map, install, phpstan), pembuatan compose, gerbang kesiapan,
dan degrade jujur — semua tanpa menjalankan container nyata (image besar). Docker
di-monkeypatch. Jalankan: uv run scripts/tests/test-ps-flashlight-run.py
"""
import ast
import importlib.util
import re
import sys
from pathlib import Path


def _literal_const(path, name):
    """Baca konstanta literal top-level dari file Python TANPA mengimpornya."""
    for node in ast.parse(Path(path).read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"konstanta {name} tak ditemukan di {path}")


MOD_PATH = Path(__file__).resolve().parent.parent / "ps-flashlight-run.py"
spec = importlib.util.spec_from_file_location("ps_flashlight_run", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    return cond


# Laporan phpstan yang REALISTIS: produsen selalu menulis canary ke pohon module, jadi laporan
# yang benar-benar menganalisis module SELALU memuat temuannya. file_errors=3 = 2 milik module
# + 1 canary; yang boleh sampai ke vonis cuma yang 2.
PHPSTAN_JSON = ('{"totals":{"errors":0,"file_errors":3},'
                '"files":{"a.php":{"errors":2,"messages":['
                '{"message":"bad","line":3},{"message":"worse","line":9}]},'
                '"/var/www/html/modules/m/psm-coverage-canary.php":{"errors":1,"messages":['
                '{"message":"Function psm_canary_undefined_fn_xyz not found.","line":2}]}},'
                '"errors":[]}')
# Canary TAK muncul = phpstan tak menyentuh pohon module. Bentuknya identik dgn module bersih —
# itulah sebabnya laporan JSON saja tak pernah cukup.
PHPSTAN_JSON_NOCOVER = '{"totals":{"errors":0,"file_errors":0},"files":{},"errors":[]}'


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

    # --- extra tag-map MENAMBAH (kanal terpisah dari --tag-map yang MENGGANTI) ---
    # Dulu satu-satunya kanal mengganti peta: satu tag "tambahan" menjatuhkan tag versi
    # lain -> tag telanjang -> image tak ada -> SELURUH Lapis 2 void diam-diam.
    ok &= check("extra tag-map: versi baru masuk, default lain UTUH",
                mod.parse_tag_map("", "9.2=9.2.0-nginx") == {**mod.DEFAULT_TAG_MAP, "9.2": "9.2.0-nginx"})
    ok &= check("extra tag-map menimpa base utk versi sama",
                mod.parse_tag_map("9.1=a", "9.1=b") == {"9.1": "b"})
    ok &= check("extra tag-map di atas peta pengganti (base tetap yang diganti)",
                mod.parse_tag_map("9.1=a", "9.2=c") == {"9.1": "a", "9.2": "c"})
    ok &= check("extra kosong -> peta tak berubah", mod.parse_tag_map("", "") == mod.DEFAULT_TAG_MAP)

    # --- parse_install ---
    ok &= check("install OK", mod.parse_install("...PSM_INSTALL_OK...")["ok"] is True)
    ok &= check("install FAIL", mod.parse_install("...PSM_INSTALL_FAIL...")["ok"] is False)
    ci = mod.parse_install("PSM_COPY_FAIL")
    ok &= check("copy fail -> copy_fail True & ok False", ci["copy_fail"] is True and ci["ok"] is False)

    # --- sentinel infra: dibaca aggregate HARUS benar-benar diemit inner-script ---
    # (dulu no_console dibaca tapi tak pernah ditulis -> jalur degrade mati -> image
    #  tanpa bin/console jatuh ke PSM_INSTALL_FAIL = vonis memblok palsu)
    ok &= check("no_console terbaca dari sentinel", mod.parse_install("PSM_NO_CONSOLE")["no_console"] is True)
    ok &= check("no_psroot terbaca dari sentinel", mod.parse_install("PSM_NO_PSROOT")["no_psroot"] is True)
    ok &= check("install OK -> bukan infra", mod.parse_install("PSM_INSTALL_OK")["no_console"] is False)
    ok &= check("INNER_SH benar-benar mengemit PSM_NO_CONSOLE (produsen == konsumen)",
                "echo PSM_NO_CONSOLE" in mod.INNER_SH)
    ok &= check("INNER_SH menggerbang install pada bin/console (bukan install-fail palsu)",
                "[ ! -f bin/console ]" in mod.INNER_SH)

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

    # --- CANARY: kontrol positif cakupan phpstan (keputusan user 2026-07-17, opsi 1) ---
    # Laporan JSON phpstan TAK bisa membedakan "bersih" dari "tak menganalisis apa-apa": map
    # `files` cuma memuat file YANG BER-ERROR, jadi module bersih & module yang neon-nya
    # mengecualikan dirinya sama-sama menghasilkan files:{} + file_errors:0. Tanpa kontrol
    # positif, yang kedua dulu diklaim "coding standard bersih, konklusif".
    ok &= check("canary terdeteksi -> coverage_ok True (phpstan benar-benar menyentuh module)",
                conc.get("coverage_ok") is True and adv.get("coverage_ok") is True)
    ok &= check("temuan canary TAK bocor ke vonis (2 pesan module, bukan 3)",
                conc.get("errors") == 2 and len(conc.get("error_messages", [])) == 2
                and not any("canary" in (m.get("file") or "")
                            for m in conc.get("error_messages", [])))
    nocov = mod.parse_phpstan(
        f"PSM_PHPSTAN_GEN=0\nPSM_PHPSTAN_JSON_START {PHPSTAN_JSON_NOCOVER} PSM_PHPSTAN_JSON_END")
    ok &= check("canary tak muncul -> coverage_ok False (0 error = tak diukur, bukan bersih)",
                nocov.get("parse_ok") is True and nocov.get("errors") == 0
                and nocov.get("coverage_ok") is False)
    # Nama canary dipakai DUA sisi: INNER_SH menulis filenya, parse_phpstan mengenalinya di
    # laporan. Dua string terpisah bisa mendrift diam-diam & mematikan kontrol positifnya
    # tanpa satu test pun merah — sama seperti rename CONTAINER_PREFIX dulu.
    # Assert ke perintah TULIS-nya, bukan sekadar "nama canary muncul di INNER_SH": baris `rm -f`
    # juga memuat nama itu, jadi cek keberadaan saja tetap hijau walau penulisannya dimatikan
    # atau namanya mendrift (kubuktikan: 2 mutasi lolos senyap sebelum assert ini diperketat).
    ok &= check("INNER_SH MENULIS canary dgn nama yang SAMA dgn yang dikenali parse_phpstan",
                f'> "modules/$MOD_NAME/{mod.CANARY_BASENAME}"' in mod.INNER_SH)
    ok &= check("INNER_SH menghapus canary lagi sesudah phpstan",
                f'rm -f "modules/$MOD_NAME/{mod.CANARY_BASENAME}"' in mod.INNER_SH)
    # Nama itu DITURUNKAN dari konstanta, bukan diketik ulang di INNER_SH. Bedanya nyata:
    # diketik ulang -> rename konstanta memalsukan error yang memblok (temuan canary tak
    # dikenali lalu dihitung sbg milik module) SEKALIGUS memvoidkan cakupan. Di-sulih ->
    # drift-nya mustahil, bukan sekadar terjaga test.
    # Hitung nama TELANJANG, bukan yang berkutip: mutasi yang mengetik ulang literalnya dgn
    # kutip tunggal lolos dari hitungan berkutip-ganda (kubuktikan). Tepat SATU kemunculan di
    # seluruh source = definisi konstanta; lebih dari itu berarti ada yang mengetik ulang.
    ok &= check("nama canary disulih dari konstanta (token habis, literal tak diketik ulang)",
                mod._CANARY_TOKEN not in mod.INNER_SH
                and MOD_PATH.read_text().count(mod.CANARY_BASENAME) == 1)
    ok &= check("canary dijamin ber-error di level phpstan berapa pun (fungsi tak dikenal)",
                "psm_canary_undefined_fn_xyz();" in mod.INNER_SH)

    # --- Seam sentinel: WRITER dibagi, bukan cuma reader ---
    # Sentinel install berpasangan dgn parse_install. Reader-nya sudah dibagi lewat impor sejak
    # awal; writer-nya disalin ke INSTALL_SH milik Lapis 4 — jadi rename satu sentinel di satu
    # sisi membuat install dilaporkan GAGAL untuk module yang sukses, lalu jatuh jadi
    # tak-konklusif berbentuk infra & `ready` turun tanpa ada yang menyebut sebabnya.
    _e2e_path = MOD_PATH.parent / "ps-e2e-run.py"
    _spec_e = importlib.util.spec_from_file_location("ps_e2e_run_x", _e2e_path)
    _e2e = importlib.util.module_from_spec(_spec_e)
    _spec_e.loader.exec_module(_e2e)
    # Kesamaan ISI + bukti tak diketik ulang di bawah = derivasi. (Identitas objek tak bisa
    # dipakai: test ini memuat ps-e2e-run segar, yang memuat instance ps-flashlight-run-nya
    # sendiri, jadi objeknya memang beda meski sumbernya satu.)
    ok &= check("Lapis 4 memakai blok install dari PEMILIKNYA (isi sama persis)",
                _e2e.INSTALL_SH == mod.INSTALL_BLOCK_SH)
    ok &= check("INNER_SH (Lapis 2) dibangun dari blok yang sama",
                mod.INNER_SH.startswith(mod.INSTALL_BLOCK_SH))
    ok &= check("blok install tak diketik ulang di ps-e2e-run",
                "PSM_INSTALL_OK" not in _e2e_path.read_text())
    # Tiap sentinel yang dibaca parse_install benar-benar ditulis blok itu — pasangan
    # writer/reader dikunci di sini, bukan dianggap benar.
    ok &= check("tiap sentinel yang dibaca parse_install ditulis blok install",
                all(s in mod.INSTALL_BLOCK_SH
                    for s in ("PSM_COPY_FAIL", "PSM_NO_PSROOT", "PSM_NO_CONSOLE", "PSM_INSTALL_OK")))
    # Perintah pembersih port-leak di SKILL.md menyebut prefix container sebagai LITERAL —
    # tak bisa disatukan lewat konstanta (itu dokumen), jadi dikunci di sini. Rename
    # CONTAINER_PREFIX akan membuat perintah itu diam-diam tak cocok apa pun, dan gunanya
    # justru melepas container pemegang port sesudah run di-kill: ia gagal tepat saat dibutuhkan.
    _skill = (MOD_PATH.parent.parent / "SKILL.md").read_text(encoding="utf-8")
    ok &= check("perintah pembersih di SKILL.md memakai CONTAINER_PREFIX yang berlaku",
                f"name={mod.CONTAINER_PREFIX}" in _skill)

    # Pemotong log kopel ke AWALAN sentinel fase phpstan; kunci awalannya benar-benar awalan
    # SEMUA sentinel itu, kalau tidak split() mengembalikan seluruh output & log install
    # menelan laporan phpstan.
    ok &= check("tiap sentinel fase phpstan berawalan PHPSTAN_SENTINEL_PREFIX",
                all(s.startswith(mod.PHPSTAN_SENTINEL_PREFIX)
                    for s in ("PSM_PHPSTAN_GEN=", "PSM_PHPSTAN_JSON_START",
                              "PSM_PHPSTAN_JSON_END", "PSM_PHPSTAN_ABSENT"))
                and mod.PHPSTAN_SENTINEL_PREFIX in mod.INNER_SH)

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

    # --- Port-leak (verifier adversarial, ronde 2026-07-17-1024): "container mana milik
    # skrip ini" sempat punya DUA konvensi — compose `psmfl<ver><uid>` vs manual
    # `psm-fl-ps-<uid>` — jadi perintah pembersihan `--filter name=psmfl` TAK cocok dgn
    # jalur manual, justru jalur yang dipakai saat compose absen & yang memegang port host.
    proj = mod._project_name("9.1")
    ok &= check("nama project compose ber-prefix CONTAINER_PREFIX (satu konvensi)",
                proj.startswith(mod.CONTAINER_PREFIX + "-") and "9" in proj)
    ok &= check("nama project compose tetap sah utk docker compose (lowercase/angka/hyphen)",
                re.fullmatch(r"[a-z0-9][a-z0-9_-]*", proj) is not None)
    # Jalur manual menamai container di dalam _bring_up_manual (butuh Docker), jadi yang
    # dijaga di sini: namanya DITURUNKAN dari konstanta yang sama, bukan hardcode terpisah.
    fl_src = MOD_PATH.read_text(encoding="utf-8")
    ok &= check("nama container jalur manual diturunkan dari CONTAINER_PREFIX yang sama",
                all(f'f"{{CONTAINER_PREFIX}}-{part}-{{uid}}"' in fl_src
                    for part in ("net", "db", "ps")))
    # Perintah cleanup hidup di PROSA (SKILL.md gotcha Lapis 2 + quickstart) sementara nama
    # container hidup di KODE. Verifier menemukan keduanya sudah berpisah sekali; kunci
    # keduanya ke konstanta yang sama supaya prosa tak bisa mendrift dari kode diam-diam.
    skill_root = MOD_PATH.parent.parent
    cleanup = f"--filter name={mod.CONTAINER_PREFIX}"
    for doc in ("SKILL.md", "references/e2e-quickstart.md"):
        ok &= check(f"perintah cleanup di {doc} memakai prefix yang benar-benar dipakai skrip",
                    cleanup in (skill_root / doc).read_text(encoding="utf-8"))

    # --- customization-2 (analyze 2026-07-17-1024): default kanonik punya DUA salinan —
    # PSM_DEFAULTS di resolver dan konstanta di skrip lapis — dan SKILL.md merestui salinan
    # skrip sbg jalur sah ("resolver absen? lanjut dengan default kanonik skrip"). Jadi
    # keduanya WAJIB identik, tapi tak ada test yang membandingkannya: drift ini pernah
    # ter-ship (tag 9.0=nightly & 8.1=8.1 usang) dan ditemukan user, bukan CI.
    resolver_path = (Path(__file__).resolve().parents[3]
                     / "psm-setup" / "scripts" / "resolve-psm-config.py")
    if not resolver_path.is_file():
        ok &= check(f"resolver ditemukan utk cek drift ({resolver_path})", False)
    else:
        # Konstanta dibaca lewat ast, bukan impor: resolver memikul dep pyyaml dan
        # sys.exit(2) bila absen (mematikan proses test), sedangkan ps-e2e-run memikul
        # playwright. Yang diperiksa cuma literal, jadi jangan seret runtime-nya.
        D = _literal_const(resolver_path, "PSM_DEFAULTS")
        e2e_browsers = _literal_const(
            Path(__file__).resolve().parent.parent / "ps-e2e-run.py", "DEFAULT_BROWSERS")

        ok &= check("drift: DEFAULT_TAG_MAP skrip == psm_flashlight_tag_map resolver",
                    mod.parse_tag_map("") == mod.parse_tag_map(D["psm_flashlight_tag_map"]))
        ok &= check("drift: DEFAULT_DB_IMAGE == psm_flashlight_db_image",
                    mod.DEFAULT_DB_IMAGE == D["psm_flashlight_db_image"])
        ok &= check("drift: DEFAULT_PS_DOMAIN == psm_flashlight_ps_domain",
                    mod.DEFAULT_PS_DOMAIN == D["psm_flashlight_ps_domain"])
        ok &= check("drift: DEFAULT_STARTUP_TIMEOUT == psm_flashlight_startup_timeout",
                    str(mod.DEFAULT_STARTUP_TIMEOUT) == D["psm_flashlight_startup_timeout"])
        ok &= check("drift: DEFAULT_BROWSERS ps-e2e-run == psm_e2e_browsers",
                    e2e_browsers == D["psm_e2e_browsers"])
        # --versions default: satu sumber kebenaran, empat salinan literal di argparse.
        scripts_dir = Path(__file__).resolve().parent.parent
        drifted = [name for name in ("ps-flashlight-run.py", "ps-e2e-run.py",
                                     "ps-static-scan.py", "ps-plan-layers.py")
                   if f'"--versions", default="{D["psm_target_versions"]}"'
                   not in (scripts_dir / name).read_text(encoding="utf-8")]
        ok &= check(f"drift: --versions default tiap skrip == psm_target_versions ({drifted or 'selaras'})",
                    drifted == [])

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
