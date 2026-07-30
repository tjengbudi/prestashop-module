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
import os
import re
import socket
import sys
from pathlib import Path


def _literal_const(path, name):
    """Baca konstanta literal top-level dari file Python TANPA mengimpornya."""
    for node in ast.parse(Path(path).read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == name for t in node.targets):
            return ast.literal_eval(node.value)
    raise AssertionError(f"konstanta {name} tak ditemukan di {path}")


def _argparse_default(path, flag):
    """Nilai `default=` sebuah add_argument, dibaca lewat AST TANPA mengimpor skripnya.

    Dibandingkan per-NILAI, bukan per-teks: default boleh ditulis literal telanjang
    ATAU lewat konstanta top-level (ps-static-scan memakai DEFAULT_TARGETS karena
    test lain perlu merujuk daftar target yang benar-benar dipakai CLI). Pencocokan
    string mentah dulu menganggap konstanta-bernama sebagai drift — persis kebalikan
    dari yang dijaga: satu sumber kebenaran.
    """
    src = Path(path).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "add_argument"):
            continue
        if not any(isinstance(a, ast.Constant) and a.value == flag for a in node.args):
            continue
        for kw in node.keywords:
            if kw.arg != "default":
                continue
            if isinstance(kw.value, ast.Constant):
                return kw.value.value
            if isinstance(kw.value, ast.Name):
                return _literal_const(path, kw.value.id)
            return None
    return None


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

    # --- enh-3 (ronde-6): PSM_INSTALL_FAIL DIBACA (dulu ditulis, nol pembaca). Membedakan
    #     "installer menjalankan lalu MENOLAK module" (no_verdict False, boleh memblok) dari
    #     "installer tak pernah mencapai vonisnya: exec mati / output terpotong" (no_verdict
    #     True, infra). Dulu keduanya jatuh ke ok=False -> infra murni dijual sbg vonis memblok.
    ok &= check("PSM_INSTALL_FAIL -> ok False & no_verdict False (installer memvonis: ditolak)",
                mod.parse_install("...PSM_INSTALL_FAIL...")["no_verdict"] is False)
    ok &= check("PSM_INSTALL_OK -> no_verdict False (installer memvonis: diterima)",
                mod.parse_install("...PSM_INSTALL_OK...")["no_verdict"] is False)
    ok &= check("output tanpa sentinel vonis (exec mati) -> no_verdict True (bukan module ditolak)",
                mod.parse_install("Error response from daemon: Container is not running")["no_verdict"] is True)
    ok &= check("output kosong -> no_verdict True", mod.parse_install("")["no_verdict"] is True)
    # Writer: PSM_INSTALL_FAIL benar-benar diemit blok install (produsen==konsumen). Mutasi
    # 'echo PSM_INSTALL_FAIL' -> 'echo PSM_BANANA' dulu bikin SEMUA suite tetap hijau (assert
    # lama lolos krn PSM_INSTALL_OK absen, bukan krn PSM_INSTALL_FAIL ada) — kini merah.
    ok &= check("INSTALL_BLOCK_SH benar-benar mengemit PSM_INSTALL_FAIL (writer utk no_verdict)",
                "PSM_INSTALL_FAIL" in mod.INSTALL_BLOCK_SH)

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
                    for s in ("PSM_COPY_FAIL", "PSM_NO_PSROOT", "PSM_NO_CONSOLE",
                              "PSM_INSTALL_OK", "PSM_INSTALL_FAIL")))
    # (Gerbang prosa pembersih dulu berdiri DUA kali: sekali di sini utk SKILL.md saja, sekali
    # di bawah utk kedua dokumen. Yang di sini dilebur ke bawah — satu aturan satu pemilik —
    # karena keduanya kini menjaga kontrak yang sama & yang bawah mencakupnya penuh.)

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
    # Perintah cleanup hidup di PROSA (SKILL.md gotcha Lapis 2 + quickstart) sementara
    # mekanismenya hidup di KODE. Gerbang ini DIGANTI SECARA SADAR (arch-9): dulu ia mengunci
    # prosa ke sapuan berbasis NAMA (`--filter name=psm-fl` + `docker rm -f`) dan hanya menuntut
    # sapuan itu lengkap. Tapi perintah itu memilih korban dari NAMA, jadi ia memang membunuh
    # container Lapis 2/4 milik sesi lain yang sedang jalan — caveat prosa "pastikan tak ada run
    # lain" tak bisa menegakkan apa pun. Kontrak baru: prosa WAJIB merutekan ke mode pembersih
    # yang memvonis lewat label, dan sapuan berbasis nama DILARANG muncul lagi di dokumen mana pun.
    skill_root = MOD_PATH.parent.parent
    # Dua arah penulisan, bukan satu: `--filter … | xargs docker rm` DAN
    # `docker rm $(docker ps --filter …)`. Gerbang versi pertama hanya menangkap arah pertama
    # pada SATU baris — reviewer membuktikan bentuk `$(...)` dan yang dipatahkan `\` lolos,
    # jadi larangannya bisa dihindari tanpa mengubah maknanya sedikit pun.
    def _has_sweep(text):
        flat = re.sub(r"\s+", " ", text.replace("\\\n", " "))
        pat = rf"--filter name={re.escape(mod.CONTAINER_PREFIX)}"
        rm = r"docker (?:rm|network rm)"
        return bool(re.search(rf"{pat}.*?{rm}", flat) or re.search(rf"{rm}.*?{pat}", flat))

    # Larangan yang tak bisa menyala = izin diam-diam. Kontrol positif: perintah lama yang
    # PERSIS ter-ship dulu HARUS terdeteksi, begitu pula tiap penulisan-ulang yang setara.
    for _bad in (f"docker ps -aq --filter name={mod.CONTAINER_PREFIX} | xargs -r docker rm -f",
                 f"docker network ls --filter name={mod.CONTAINER_PREFIX} -q | xargs -r docker network rm",
                 f"docker rm -f $(docker ps -aq --filter name={mod.CONTAINER_PREFIX})",
                 f"docker network rm $(docker network ls -q --filter name={mod.CONTAINER_PREFIX})",
                 f"docker ps -aq --filter name={mod.CONTAINER_PREFIX} \\\n  | xargs -r docker rm -f"):
        ok &= check("gerbang sapuan tak vakum: bentuk sapuan terdeteksi terlarang",
                    _has_sweep(_bad))
    ok &= check("gerbang sapuan tak over-fire: prosa pembersih yang berlaku lolos",
                not _has_sweep((skill_root / "SKILL.md").read_text(encoding="utf-8")))
    # Dokumen operator DIKUMPULKAN, bukan didaftar tangan: doc referensi baru yang mengapalkan
    # sapuan itu takkan terjaring oleh tuple tetap. (.memlog.md & .analysis/ dikecualikan sadar —
    # keduanya CATATAN SEJARAH yang memang mengutip perintah lama sebagai bukti.)
    docs = [skill_root / "SKILL.md"] + sorted((skill_root / "references").glob("*.md"))
    ok &= check(f"gerbang prosa punya subjek ({len(docs)} dokumen operator)", len(docs) >= 2)
    for doc in docs:
        rel = doc.relative_to(skill_root)
        dtext = doc.read_text(encoding="utf-8")
        ok &= check(f"{rel} TAK memuat sapuan berbasis nama (perintah yang membunuh run sesi lain)",
                    not _has_sweep(dtext))
    for doc in ("SKILL.md", "references/e2e-quickstart.md"):
        dtext = (skill_root / doc).read_text(encoding="utf-8")
        ok &= check(f"{doc} merutekan cleanup ke mode berbasis label ({mod.CLEANUP_FLAG})",
                    mod.CLEANUP_FLAG in dtext)
        ok &= check(f"{doc} menyebut label pemilik yang benar-benar dipakai skrip",
                    mod.LABEL_OWNER_PID in dtext)
        # Pin prosa->konstanta yang SEMPAT KUHAPUS saat melebur dua gerbang: dokumen masih
        # menyebut `psm-fl` sebagai literal ketikan, jadi rename CONTAINER_PREFIX membuat
        # operator meng-grep nama yang tak ada lagi, dgn seluruh suite tetap hijau.
        ok &= check(f"{doc} menyebut prefix container yang berlaku (pin ke konstanta)",
                    f"`{mod.CONTAINER_PREFIX}`" in dtext)

    # --- Kepemilikan run: label + keputusan pembersihan (arch-9) ---
    labels = mod.owner_labels()
    _core = {mod.LABEL_RUN, mod.LABEL_OWNER_PID, mod.LABEL_OWNER_HOST}
    _ctx = {k for k, v in ((mod.LABEL_OWNER_BOOT, mod.OWNER_BOOT), (mod.LABEL_OWNER_NS, mod.OWNER_NS)) if v}
    ok &= check("owner_labels memakai key konstanta (inti + konteks yang platform ini bisa tulis)",
                set(labels) == _core | _ctx and all(labels.values()))
    ok &= check("owner_labels: pid = proses ini, host = host ini",
                labels[mod.LABEL_OWNER_PID] == str(os.getpid())
                and labels[mod.LABEL_OWNER_HOST] == socket.gethostname())
    # Artefak yang lolos tanpa label TAK bisa dibuktikan mati, jadi pembersih menolak
    # menyentuhnya selamanya: satu situs yang tercecer = kebocoran permanen, bukan bug kecil.
    yml_lab = mod._compose_file_text("mariadb:lts", "img:9.1", "localhost:8000", "/x/mod")
    ok &= check("compose mencap db, ps, DAN network default (3 blok label)",
                yml_lab.count(f'{mod.LABEL_RUN}: "{mod.RUN_ID}"') == 3
                and "networks:\n  default:\n" in yml_lab)
    # Hitungan situs adalah SENSUS, bukan invarian: tambah satu `docker run` berlabel sambil
    # menjatuhkan label dari yang lain menjaga angkanya tetap 3. Yang dijaga: TIAP pemanggilan
    # yang membuat artefak membawa label, berapa pun jumlah situsnya.
    _creators = [m for m in re.finditer(r'\["docker", "(?:run|network", "create)"', fl_src)]
    ok &= check(f"tiap pemanggilan docker yang MEMBUAT artefak membawa label ({len(_creators)} situs)",
                len(_creators) >= 3
                and all("_label_flags()" in fl_src[m.start():m.start() + 400] for m in _creators))
    ok &= check("_label_flags menurunkan --label dari owner_labels (bukan literal terpisah)",
                mod._label_flags() == [x for k, v in labels.items()
                                       for x in ("--label", f"{k}={v}")])

    # Tabel keputusan — invarian keamanan arch-9: HANYA vonis "pemilik pasti sudah mati" yang
    # menghapus. Tiap cabang lain menamai apa yang TAK terbukti, dan wajib menolak. Arah gagalnya
    # sengaja: melewatkan sampah itu murah, menebak "mati" membunuh run yang sedang jalan.
    orig_alive = mod._pid_alive
    try:
        mod._pid_alive = lambda pid: pid == 4242
        base = dict(mod.owner_labels())
        live = {**base, mod.LABEL_OWNER_PID: "4242"}
        dead = {**base, mod.LABEL_RUN: "r2", mod.LABEL_OWNER_PID: "4243"}
        cases = [
            ("run sesi lain masih hidup -> owner-alive", live, (False, "owner-alive")),
            ("pemilik mati -> owner-dead (menghapus)", dead, (True, "owner-dead")),
            ("tanpa label -> no-owner-label", {}, (False, "no-owner-label")),
            ("host lain -> foreign-host", {**dead, mod.LABEL_OWNER_HOST: "host-lain"},
             (False, "foreign-host")),
            ("pid tak terbaca -> bad-owner-pid", {**dead, mod.LABEL_OWNER_PID: "x1"},
             (False, "bad-owner-pid")),
            # "²".isdigit() True tapi int("²") ValueError: penjaga yang salah bikin fungsi
            # pengklasifikasi label rusak justru MATI oleh label rusak.
            ("digit Unicode non-desimal -> bad-owner-pid (bukan crash)",
             {**dead, mod.LABEL_OWNER_PID: "\u00b2"}, (False, "bad-owner-pid")),
            # os.kill(0, 0) menyasar process group PEMANGGIL & selalu sukses -> "0" akan
            # dibaca owner-alive selamanya dengan alasan yang bohong.
            ("pid 0 -> bad-owner-pid (bukan owner-alive palsu)",
             {**dead, mod.LABEL_OWNER_PID: "0"}, (False, "bad-owner-pid")),
        ]
        if mod.OWNER_BOOT:
            cases += [
                # Beda boot: seluruh proses boot itu sudah lenyap, jadi PID-nya MUSTAHIL hidup —
                # dan PID yang sama kini bisa milik proses lain (sumber "owner-alive" abadi).
                ("boot lain -> owner-boot-gone (direklaim, bukan tersangkut selamanya)",
                 {**live, mod.LABEL_OWNER_BOOT: "boot-lama"}, (True, "owner-boot-gone")),
                ("label boot hilang padahal platform menulisnya -> incomplete-owner-labels",
                 {k: v for k, v in dead.items() if k != mod.LABEL_OWNER_BOOT},
                 (False, "incomplete-owner-labels")),
            ]
        if mod.OWNER_NS:
            cases += [
                # Inti temuan reviewer: dua distro WSL2 berbagi hostname + daemon Docker tapi
                # PID namespace-nya terpisah. Tanpa cabang ini, run HIDUP sesi lain terbaca mati.
                ("PID namespace lain -> foreign-pid-ns (run hidup sesi lain TAK dibunuh)",
                 {**dead, mod.LABEL_OWNER_NS: "9999999"}, (False, "foreign-pid-ns")),
                ("label ns hilang padahal platform menulisnya -> incomplete-owner-labels",
                 {k: v for k, v in dead.items() if k != mod.LABEL_OWNER_NS},
                 (False, "incomplete-owner-labels")),
            ]
        for case, lab, want in cases:
            ok &= check(f"cleanup_decision: {case}", mod.cleanup_decision(lab) == want)
        # PID di luar jangkauan C melempar OverflowError — BUKAN OSError, jadi ia dulu menembus
        # sampai memutus sweep di tengah, sesudah sebagian artefak terlanjur dihapus. Diuji ke
        # probe ASLI (yang di dalam blok ini sedang di-monkeypatch), sebab di situ letak penjaganya.
        try:
            ok &= check("pid di luar jangkauan C -> probe tak crash & membaca 'hidup' (aman)",
                        orig_alive(10 ** 25) is True)
        except Exception as e:
            ok &= check(f"pid di luar jangkauan C -> probe tak crash (dapat {type(e).__name__})", False)

        calls = []
        orig_list, orig_rm, orig_docker = mod._list_artifacts, mod._remove_artifact, mod.docker_available
        try:
            mod.docker_available = lambda: True
            inv = {"container": [{"name": "psm-fl-ps-live", "labels": live},
                                 {"name": "psm-fl-ps-dead", "labels": dead},
                                 {"name": "psm-fl-ps-legacy", "labels": {}}],
                   "network": [{"name": "psm-fl-net-dead", "labels": dead}]}
            mod._list_artifacts = lambda kind: (inv[kind], None)
            mod._remove_artifact = lambda kind, name: (calls.append((kind, name)), ("removed", None))[1]
            rep = mod.cleanup_orphans()
            ok &= check("cleanup_orphans menghapus HANYA jejak pemilik mati",
                        calls == [("container", "psm-fl-ps-dead"), ("network", "psm-fl-net-dead")])
            ok &= check("container run hidup DILEWATI (dilaporkan, tak dibunuh)",
                        any(s["name"] == "psm-fl-ps-live" and s["reason"] == "owner-alive"
                            for s in rep["skipped"]))
            # Menyodorkan perintah bunuh untuk run yang SEDANG JALAN adalah persis tindakan yang
            # mode ini ada untuk mencegah — alasan lain boleh, yang ini tidak.
            ok &= check("owner-alive TAK diberi manual_command (jangan tawarkan pembunuhan)",
                        all("manual_command" not in s for s in rep["skipped"]
                            if s["reason"] == "owner-alive"))
            ok &= check("artefak lama tanpa label dilewati + diberi perintah manual per-nama",
                        any(s["name"] == "psm-fl-ps-legacy"
                            and s.get("manual_command") == "docker rm -f -v psm-fl-ps-legacy"
                            for s in rep["skipped"]))
            ok &= check("container dibongkar SEBELUM network (network tak lepas selagi dipakai)",
                        [k for k, _ in calls] == ["container", "network"])
            ok &= check("sweep bersih -> status ran", rep["status"] == "ran")

            # Balapan normal: pemilik membongkar sendiri antara listing & penghapusan. Itu bukan
            # kegagalan — kalau mendarat di `errors`, run yang sehat tampak rusak.
            mod._remove_artifact = lambda kind, name: ("already-gone", None)
            rep_gone = mod.cleanup_orphans()
            ok &= check("artefak lenyap saat balapan -> skipped 'already-gone', bukan error",
                        rep_gone["errors"] == [] and rep_gone["removed"] == []
                        and any(s["reason"] == "already-gone" for s in rep_gone["skipped"]))

            # Gagal nyata TETAP exit 0 (kontrak yang disetujui), tapi status harus membedakan
            # "bersih" dari "ada yang tak tergarap" — kalau tidak, wrapper membaca sukses.
            mod._remove_artifact = lambda kind, name: ("error", "daemon menolak")
            rep_err = mod.cleanup_orphans()
            ok &= check("penghapusan gagal -> status 'partial' (bukan 'ran' yang menyesatkan)",
                        rep_err["status"] == "partial" and bool(rep_err["errors"]))

            # Satu record aneh tak boleh membatalkan sisa sweep: tanpa penjaga, artefak yang
            # sudah dihapus tak pernah dilaporkan dan network tak pernah diproses sama sekali.
            orig_dec = mod.cleanup_decision
            try:
                def _boom(labels):
                    if labels.get(mod.LABEL_RUN) == "r2":
                        raise RuntimeError("label mustahil")
                    return orig_dec(labels)
                mod.cleanup_decision = _boom
                mod._remove_artifact = lambda kind, name: ("removed", None)
                rep_boom = mod.cleanup_orphans()
                ok &= check("record yang meledak -> dicatat 'undecidable', sweep TETAP lanjut",
                            any(e.get("reason") == "undecidable" for e in rep_boom["errors"])
                            and len(rep_boom["skipped"]) + len(rep_boom["errors"]) == 4)
            finally:
                mod.cleanup_decision = orig_dec

            mod.docker_available = lambda: False
            rep2 = mod.cleanup_orphans()
            ok &= check("docker absen -> status skipped + alasan jujur, tak menyentuh apa pun",
                        rep2["status"] == "skipped" and bool(rep2.get("reason"))
                        and rep2["removed"] == [])
        finally:
            mod._list_artifacts, mod._remove_artifact, mod.docker_available = \
                orig_list, orig_rm, orig_docker
    finally:
        mod._pid_alive = orig_alive

    # Inventaris diuji lewat PERILAKU perintah yang benar-benar dibangun, bukan sensus teks:
    # cek teks tak bisa membedakan kode dari komentar yang menjelaskannya, dan tetap hijau
    # saat perintahnya sendiri berubah.
    _cap = {}

    class _FakeRun:
        returncode = 0
        stderr = ""
        # 3 baris: milik kita, milik pihak ketiga yang namanya cuma MEMUAT prefix, dan tanpa label
        stdout = ("psm-fl-91-abc-ps-1\trun1\t123\thostx\tboot1\tns1\n"
                  "my-psm-fl-notes\t\t\t\t\t\n"
                  "psm-fl-lama\t\t\t\t\t\n")

    _orig_run = mod.subprocess.run
    try:
        def _fake(cmd, **kw):
            _cap["cmd"] = cmd
            return _FakeRun()
        mod.subprocess.run = _fake
        items, lerr = mod._list_artifacts("container")
        fmt = _cap["cmd"][_cap["cmd"].index("--format") + 1]
        # Label diambil per-key; mem-parse {{.Labels}} yang dipisah koma membuat nilai ber-koma
        # (warisan image) memecah diri jadi pasangan palsu — dan pasangan `psm.*` palsu berarti
        # kepemilikan bisa dikarang, lalu artefak milik run HIDUP terhapus.
        ok &= check("perintah listing meminta tiap label per-key, bukan {{.Labels}} gabungan",
                    all(f'.Label "{k}"' in fmt for k in mod.OWNER_LABEL_KEYS)
                    and "{{.Labels}}" not in fmt)
        # `--filter name=` docker adalah pencocokan SUBSTRING: container pihak ketiga bernama
        # `my-psm-fl-notes` ikut terjaring. Ia takkan dihapus (tak berlabel), tapi tanpa saringan
        # ini laporan menganjurkan operator menghapus milik orang lain.
        names = [i["name"] for i in items]
        ok &= check("artefak yang namanya cuma MEMUAT prefix dibuang dari inventaris",
                    lerr is None and names == ["psm-fl-91-abc-ps-1", "psm-fl-lama"])
        ok &= check("label ter-zip ke key yang benar (nilai kosong tak jadi label palsu)",
                    items[0]["labels"][mod.LABEL_RUN] == "run1"
                    and items[0]["labels"][mod.LABEL_OWNER_HOST] == "hostx"
                    and items[1]["labels"] == {})
    finally:
        mod.subprocess.run = _orig_run

    # _remove_artifact diuji LANGSUNG: test cabang 'already-gone' di atas me-monkeypatch fungsi
    # ini, jadi deteksi "no such" di dalamnya tak pernah ikut terjalankan di sana (kubuktikan:
    # mencabut deteksinya lolos senyap) — kelas "jalur tanpa cakupan".
    class _RmRun:
        def __init__(self, rc, err=""):
            self.returncode, self.stderr, self.stdout = rc, err, ""

    _orig_run2 = mod.subprocess.run
    try:
        mod.subprocess.run = lambda cmd, **kw: _RmRun(0)
        ok &= check("_remove_artifact sukses -> ('removed', None)",
                    mod._remove_artifact("container", "x") == ("removed", None))
        # Balapan normal: pemilik membongkar sendiri antara listing & penghapusan. Kalau ini
        # dibaca 'error', run yang SEHAT tampak rusak & status jatuh ke partial tanpa sebab.
        mod.subprocess.run = lambda cmd, **kw: _RmRun(1, "Error: No such container: x")
        ok &= check("_remove_artifact 'No such container' -> already-gone, bukan error",
                    mod._remove_artifact("container", "x") == ("already-gone", None))
        mod.subprocess.run = lambda cmd, **kw: _RmRun(1, "permission denied")
        st, err = mod._remove_artifact("container", "x")
        ok &= check("_remove_artifact gagal nyata -> ('error', pesan)",
                    st == "error" and "permission denied" in (err or ""))
    finally:
        mod.subprocess.run = _orig_run2

    # Container DB membawa volume anonim; tanpa -v tiap orphan meninggalkan volume ratusan MB
    # yang tak berlabel & tak bisa direklaim pembersih ini lagi (compose down -v mereklaimnya).
    ok &= check("penghapusan container memakai -v (volume anonim ikut direklaim)",
                mod._rm_command("container", "x") == ["docker", "rm", "-f", "-v", "x"])
    # Mode ini eksklusif: digabung module_path validasi diam-diam tak jalan (exit 0), digabung
    # -o laporan pembersih MENIMPA file bukti lapis lalu agregat mengarang sebab "Docker absen".
    ok &= check("--cleanup-orphans menolak module_path & -o (tak menimpa bukti lapis)",
                "if args.module_path or args.output:" in fl_src)
    # Diteruskan lewat passthrough ps-run-layer, TIAP anak menjalankan pembersihan destruktif
    # alih-alih memvalidasi lalu keluar 0; operator cuma diberi tahu "versi tak berbukti".
    _rl = (MOD_PATH.parent / "ps-run-layer.py").read_text(encoding="utf-8")
    ok &= check("ps-run-layer menolak --cleanup-orphans di passthrough (flag destruktif)",
                f'"{mod.CLEANUP_FLAG}"' in _rl.split("RESERVED_PASSTHROUGH = ", 1)[1].split(")", 1)[0])

    # customization-4: salinan KEEMPAT tag map hidup di PROSA e2e-quickstart (perintah
    # `docker pull` operator + baris "Verified vs flashlight"). Tiga salinan lain dijaga;
    # yang keempat tidak -> tag stale = image yang ditarik BUKAN yang diuji Lapis 2/4. Gerbang
    # doc-vs-konstanta yang sama, kini diterapkan ke NILAI tag: tiap tag kanonik WAJIB muncul,
    # dan tak boleh ada tag <ver>-nginx / 1.7.x.y di luar himpunan yang tercecer (drift ter-ship
    # sekali: 9.0=nightly & 8.1 usang, ditemukan user bukan CI).
    qs_text = (skill_root / "references" / "e2e-quickstart.md").read_text(encoding="utf-8")
    canonical_tags = set(mod.DEFAULT_TAG_MAP.values())
    for tag in canonical_tags:
        ok &= check(f"tag kanonik {tag} muncul di e2e-quickstart (docker pull operator tak stale)",
                    tag in qs_text)
    # PENARIKAN: tiap tag di loop `docker pull` (for t in <tags>; do) WAJIB kanonik — ini yang
    # menentukan image mana ditarik operator. Regex `-nginx` lama meloloskan `nightly`/`-fpm`/
    # `-apache` (verifier ronde-6; `nightly` justru contoh drift historis 9.0=nightly). Parse
    # daftar langsung menangkap SEMBARANG token stale, bukan cuma pola -nginx.
    pull_tags = [t for lst in re.findall(r"for t in (.+?);\s*do", qs_text) for t in lst.split()]
    ok &= check(f"loop docker pull quickstart tak kosong (guard punya subjek): {pull_tags}",
                pull_tags != [])
    stray_pull = [t for t in pull_tags if t not in canonical_tags]
    ok &= check(f"tiap tag di loop docker pull kanonik ({stray_pull or 'bersih'} — nightly/-fpm/-apache tertangkap)",
                stray_pull == [])
    # Literal prestashop-flashlight:<tag> (bukan variabel $t) juga wajib kanonik.
    stray_ref = [t for t in re.findall(r"prestashop-flashlight:([A-Za-z0-9._-]+)", qs_text)
                 if t not in canonical_tags]
    ok &= check(f"tiap image ref prestashop-flashlight:<tag> kanonik ({stray_ref or 'bersih'})",
                stray_ref == [])

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

        # ENUMERASI, bukan daftar hardcode (customization-1): tiap key psm_flashlight_* di
        # PSM_DEFAULTS WAJIB punya konstanta DEFAULT_<SUFFIX> padanan di ps-flashlight-run &
        # nilainya cocok. Dulu per-key hardcode -> psm_flashlight_orchestrator (dan key ke-N
        # mana pun) lahir tanpa penjaga: nilainya literal telanjang default="auto" yang bisa
        # mendrift dari resolver diam-diam. tag_map bentuknya dict vs string, jadi dicek via
        # parse_tag_map; sisanya str()== (startup_timeout int vs "180", dll).
        for k in [k for k in D if k.startswith("psm_flashlight_")]:
            cname = "DEFAULT_" + k[len("psm_flashlight_"):].upper()
            has = hasattr(mod, cname)
            ok &= check(f"drift: {k} punya konstanta {cname} di skrip (key baru tak boleh tak berpenjaga)", has)
            if not has:
                continue
            cval = getattr(mod, cname)
            match = (mod.parse_tag_map("") == mod.parse_tag_map(D[k])
                     if k == "psm_flashlight_tag_map" else str(cval) == str(D[k]))
            ok &= check(f"drift: {cname} == {k} ({cval!r} vs {D[k]!r})", match)
        ok &= check("drift: DEFAULT_BROWSERS ps-e2e-run == psm_e2e_browsers",
                    e2e_browsers == D["psm_e2e_browsers"])
        # customization-2: psm_reports_dir dulu required=True tanpa default kanonik skrip,
        # jadi janji SKILL "resolver absen -> default skrip" tak bisa ditepati. Default skrip
        # bentuk TANPA token; resolver ber-token {project-root}/... -> bandingkan sesudah strip.
        reports_default = _literal_const(
            Path(__file__).resolve().parent.parent / "ps-plan-layers.py", "DEFAULT_REPORTS_DIR")
        ok &= check("drift: DEFAULT_REPORTS_DIR ps-plan-layers == psm_reports_dir (tanpa {project-root}/)",
                    reports_default == D["psm_reports_dir"].replace("{project-root}/", ""))
        # --versions default: satu sumber kebenaran, empat salinan literal di argparse.
        scripts_dir = Path(__file__).resolve().parent.parent
        drifted = [name for name in ("ps-flashlight-run.py", "ps-e2e-run.py",
                                     "ps-static-scan.py", "ps-plan-layers.py")
                   if _argparse_default(scripts_dir / name, "--versions")
                   != D["psm_target_versions"]]
        ok &= check(f"drift: --versions default tiap skrip == psm_target_versions ({drifted or 'selaras'})",
                    drifted == [])

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
