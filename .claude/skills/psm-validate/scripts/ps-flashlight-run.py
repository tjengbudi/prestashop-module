#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Jalankan validasi module di dalam Docker prestashop-flashlight, per versi.

Lapisan akurasi #2: menguji module terhadap PrestaShop core ASLI tiap versi —
instalasi module + analisis statis (phpstan) di dalam core yang benar-benar boot.
Deterministik per (module, versi, image). Output JSON per versi.

PENTING — flashlight butuh DATABASE. Image `prestashop/prestashop-flashlight`
adalah web-tier saja (nginx + php-fpm), TANPA server MySQL: entrypoint-nya menunggu
host DB bernama `mysql`/sesuai `MYSQL_HOST` selamanya. Karena itu skrip ini TIDAK
menjalankan `docker run` telanjang (yang pasti gagal "no database"), melainkan
membangun DB + flashlight berpasangan:
  - orchestrator `compose` : generate docker-compose ephemeral (mariadb + flashlight,
    di-gate lewat healthcheck DB) lalu `docker compose up -d`.
  - orchestrator `manual`  : `docker network` + dua `docker run` (mariadb lalu
    flashlight) pada network yang sama; hanya butuh CLI `docker`.
  - `auto` (default)       : compose bila tersedia, jika tidak manual.

Env runtime flashlight yang dibaca: MYSQL_HOST/PORT/USER/PASSWORD/DATABASE + PS_DOMAIN
(bukan DB_SERVER/DB_NAME — itu milik image produksi prestashop/prestashop, diabaikan).
Kesiapan diukur dari HEALTHCHECK container flashlight (status `healthy`), bukan port.

Coding-standard: image punya `phpstan` (canonical PrestaShop), BUKAN `phpcs`. Bila
module membawa `phpstan.neon`(.dist) sendiri, hasilnya KONKLUSIF (memblok bila error).
Bila tidak, skrip meng-auto-generate neon yang menyertakan extension resmi PrestaShop
(`ps-module-extension.neon`: stub Module/Tab + bootstrap, akurat; fallback
scanDirectories bila absen). Hasil auto-neon bersifat ADVISORY (errors=0, tak memblok)
— kita tak menjatuhkan rilis atas config buatan sendiri, hanya surface sebagai warning.

Bila Docker/compose tak tersedia, keluar dengan status terstruktur (`skipped` /
`skipped_image`) — bukan crash — supaya pemanggil bisa degrade ke ps-static-scan.
Pemetaan tag default mengikuti tag resmi Docker Hub prestashop/prestashop-flashlight.
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

DEFAULT_TAG_MAP = {"1.7.8": "1.7.8.11", "8.1": "8.1.6-nginx", "9.1": "9.1.4-nginx"}
# Kontrol positif cakupan phpstan. Namanya dipakai DUA sisi — INNER_SH menulis filenya,
# parse_phpstan mengenalinya di laporan — jadi ia disulih ke INNER_SH lewat token di bawah,
# bukan diketik ulang di sana. Mengetiknya ulang membuat komentar ini bohong: rename konstanta
# akan memalsukan error yang memblok (temuan canary tak dikenali lalu dihitung sbg milik module)
# SEKALIGUS memvoidkan cakupan (canary "tak muncul") — dua cacat dari satu refactor yang tampak
# tak berbahaya, persis kelas rename CONTAINER_PREFIX.
CANARY_BASENAME = "psm-coverage-canary.php"
_CANARY_TOKEN = "__PSM_CANARY_BASENAME__"
IMAGE = "prestashop/prestashop-flashlight"
DEFAULT_DB_IMAGE = "mariadb:lts"
DEFAULT_PS_DOMAIN = "localhost:8000"
DEFAULT_STARTUP_TIMEOUT = 180  # detik menunggu container jadi healthy
DEFAULT_ORCHESTRATOR = "auto"   # auto = compose bila ada, else manual
# Kredensial DB — harus cocok di sisi flashlight & DB; nilai internal, bukan setelan.
DB_USER = "prestashop"
DB_PASSWORD = "prestashop"
DB_NAME = "prestashop"

# Awalan SEMUA sentinel fase phpstan (PSM_PHPSTAN_GEN=/_JSON_START/_JSON_END/_ABSENT). Dipakai
# untuk memotong ekor phpstan dari log install; dinamai supaya kopling ke awalannya terlihat,
# dan dikunci test yang memeriksa tiap sentinel fase itu benar-benar berawalan ini.
PHPSTAN_SENTINEL_PREFIX = "PSM_PHPSTAN"

# Blok install yang dijalankan DI DALAM container. Dipakai KEDUA lapis: Lapis 2 (INNER_SH, +
# phpstan) dan Lapis 4 (ps-e2e-run.INSTALL_SH, tanpa phpstan). SATU konstanta, karena sentinel
# di sini berpasangan dengan parse_install di bawah. Seam-nya dulu asimetris — reader dibagi
# lewat impor, writer disalin — jadi rename satu sentinel di satu sisi bikin install dilaporkan
# GAGAL untuk module yang sebenarnya sukses, lalu jatuh jadi tak-konklusif berbentuk infra dan
# `ready` turun tanpa ada yang menyebut sebabnya. $MOD_NAME dari env.
INSTALL_BLOCK_SH = r'''
if ! cp -r /ps-module-src "/var/www/html/modules/$MOD_NAME" 2>&1; then echo PSM_COPY_FAIL; fi
cd /var/www/html || echo PSM_NO_PSROOT
if [ ! -f bin/console ]; then
  echo PSM_NO_CONSOLE
elif php -d memory_limit=-1 bin/console prestashop:module --no-interaction install "$MOD_NAME" 2>&1; then
  echo PSM_INSTALL_OK
else
  echo PSM_INSTALL_FAIL
fi
'''

# Skrip yang dijalankan DI DALAM container flashlight setelah healthy: salin module,
# install via PS console, lalu phpstan (neon module bila ada, else auto-generate).
INNER_SH = INSTALL_BLOCK_SH + r'''
NEON=""
for c in "modules/$MOD_NAME/phpstan.neon" "modules/$MOD_NAME/phpstan.neon.dist"; do
  if [ -f "$c" ]; then NEON="$c"; break; fi
done
GEN=0
if [ -z "$NEON" ]; then
  GEN=1
  NEON=/tmp/psm-phpstan.neon
  EXT=/var/opt/prestashop/coding-standards/phpstan/ps-module-extension.neon
  if [ -f "$EXT" ]; then
    # Extension resmi PrestaShop (stub Module/Tab + bootstrap) -> analisis akurat.
    printf 'includes:\n    - %s\nparameters:\n    level: 2\n    paths:\n        - /var/www/html/modules/%s\n' "$EXT" "$MOD_NAME" > "$NEON"
  else
    # Fallback bila extension resmi tak ada: scanDirectories (best-effort, bisa noisy).
    printf 'parameters:\n    level: 2\n    paths:\n        - /var/www/html/modules/%s\n    scanDirectories:\n        - /var/www/html/classes\n        - /var/www/html/src\n        - /var/www/html/vendor/prestashop\n' "$MOD_NAME" > "$NEON"
  fi
fi
if command -v phpstan >/dev/null 2>&1; then
  echo "PSM_PHPSTAN_GEN=$GEN"
  # CANARY / kontrol positif. Laporan JSON phpstan TAK bisa membedakan "bersih" dari "tak
  # menganalisis apa-apa": map `files` hanya memuat file YANG BER-ERROR, jadi module bersih dan
  # module yang neon-nya mengecualikan dirinya sendiri sama-sama menghasilkan files:{} &
  # file_errors:0 — dan yang kedua dulu diklaim "coding standard bersih, konklusif". File ini
  # dijamin ber-error di level berapa pun (fungsi tak dikenal); kalau ia TAK muncul di laporan,
  # berarti phpstan tak menyentuh pohon module dan vonis CS tak boleh diklaim. Ditulis ke
  # SALINAN dalam container (module di-cp di atas), jadi pohon module di host tak tersentuh.
  printf '<?php\npsm_canary_undefined_fn_xyz();\n' > "modules/$MOD_NAME/__PSM_CANARY_BASENAME__"
  echo PSM_PHPSTAN_JSON_START
  phpstan analyse --no-progress --error-format=json --memory-limit=-1 -c "$NEON" "modules/$MOD_NAME" 2>/dev/null || true
  echo PSM_PHPSTAN_JSON_END
  rm -f "modules/$MOD_NAME/__PSM_CANARY_BASENAME__"
else
  echo PSM_PHPSTAN_ABSENT
fi
'''.replace(_CANARY_TOKEN, CANARY_BASENAME)


def docker_available():
    if not shutil.which("docker"):
        return False
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=20)
        return r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def compose_available():
    """True bila plugin `docker compose` (v2) tersedia."""
    try:
        r = subprocess.run(["docker", "compose", "version"], capture_output=True, timeout=20)
        return r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def image_present(image_ref):
    """True bila image sudah ada lokal (tak perlu pull)."""
    try:
        r = subprocess.run(["docker", "image", "inspect", image_ref],
                           capture_output=True, timeout=20)
        return r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _parse_pairs(raw):
    """'1.7.8=1.7.8.11,8.1=8.1.6-nginx' -> dict. Tanpa pasangan valid -> {}."""
    out = {}
    for pair in (raw or "").split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def parse_tag_map(raw, extra=None):
    """Peta versi->tag. `raw` MENGGANTI peta default; `extra` MENAMBAH di atasnya.

    Dua kanal karena dua maksud berbeda: --tag-map memasang peta lengkap (mis. dari
    config psm_flashlight_tag_map), --extra-tag-map menambal satu-dua versi tanpa
    menjatuhkan sisanya. Dulu hanya ada kanal pengganti, sehingga satu tag tambahan
    membuang tag versi lain -> tag telanjang -> image tak ada -> lapis void diam-diam.
    """
    base = _parse_pairs(raw) or dict(DEFAULT_TAG_MAP)
    base.update(_parse_pairs(extra))
    return base


def resolve_tag(tag_map, full_ver):
    """Tag image untuk satu versi target: cocokkan versi penuh, lalu bentuk yang dipendekkan.

    Satu pemilik untuk aturan ini. Ekspresinya sempat disalin di dua main() (flashlight & e2e),
    dan pra-pass kesegaran butuh jawaban yang SAMA untuk tahu apakah file lapis diproduksi image
    yang sama — implementasi ketiga yang mendrift akan membuat gerbangnya menolak reuse yang sah
    atau, lebih buruk, menerima bukti dari core yang lain.
    """
    return tag_map.get(full_ver) or tag_map.get(full_ver.rsplit(".", 1)[0]) or full_ver


def parse_install(out):
    """Baca penanda hasil install dari output inner-script.

    `no_console`/`no_psroot` = kondisi INFRASTRUKTUR (image tanpa bin/console, PS root
    tak ada): pemanggil memperlakukannya tak konklusif, bukan module gagal install.
    Keduanya benar-benar diemit inner-script — sentinel yang dibaca tapi tak pernah
    ditulis = jalur degrade mati, dan infra jatuh jadi vonis memblok palsu.

    `no_verdict` = installer TAK PERNAH mencapai vonisnya: baik PSM_INSTALL_OK maupun
    PSM_INSTALL_FAIL absen (docker exec mati sesudah healthy / output terpotong / sh gagal).
    Dulu PSM_INSTALL_FAIL DITULIS tapi tak pernah DIBACA — jadi 'exec mati' dan 'installer
    menolak module' jatuh ke ok=False yang sama, dan infra murni dijual sbg vonis memblok
    'modul gagal install di core asli'. Membaca PSM_INSTALL_FAIL memisahkan keduanya: hanya
    ia bukti installer BENAR-BENAR menjalankan lalu menolak (satu-satunya yang boleh memblok).
    """
    if "PSM_COPY_FAIL" in out:
        return {"ok": False, "no_console": False, "no_psroot": False,
                "copy_fail": True, "no_verdict": False}
    ran = ("PSM_INSTALL_OK" in out) or ("PSM_INSTALL_FAIL" in out)
    return {"ok": "PSM_INSTALL_OK" in out, "no_console": "PSM_NO_CONSOLE" in out,
            "no_psroot": "PSM_NO_PSROOT" in out, "copy_fail": False, "no_verdict": not ran}


def parse_phpstan(out):
    """Ambil hitungan error EXACT dari laporan JSON phpstan (bukan tebak substring).

    phpstan --error-format=json -> {"totals":{"file_errors":N,...}, "files":{...}, "errors":[...]}.
    Neon auto-generate (GEN=1) bersifat ADVISORY: errors dipetakan ke warnings agar
    TAK memblok vonis (tanpa bootstrap module, phpstan bisa false-positive). Neon milik
    module (GEN=0) bersifat konklusif: errors tetap errors (memblok).
    """
    if "PSM_PHPSTAN_ABSENT" in out:
        return {"available": False}
    if "PSM_PHPSTAN_JSON_START" not in out or "PSM_PHPSTAN_JSON_END" not in out:
        return {"available": True, "parse_ok": False, "note": "penanda laporan phpstan tak ditemukan"}
    generated = "PSM_PHPSTAN_GEN=1" in out
    raw = out.split("PSM_PHPSTAN_JSON_START", 1)[1].split("PSM_PHPSTAN_JSON_END", 1)[0].strip()
    start = raw.find("{")
    if start == -1:
        return {"available": True, "parse_ok": False, "generated_config": generated,
                "note": "JSON phpstan kosong/tak valid"}
    try:
        report = json.loads(raw[start:])
    except json.JSONDecodeError:
        return {"available": True, "parse_ok": False, "generated_config": generated,
                "note": "gagal parse JSON phpstan"}
    totals = report.get("totals", {}) or {}
    generic = report.get("errors", []) or []  # error non-file (mis. neon/bootstrap)
    files = report.get("files", {}) or {}
    messages = []
    canary_hits = 0
    for path, fdata in files.items():
        msgs = fdata.get("messages", []) or []
        # Temuan canary BUKAN temuan module: ia cuma membuktikan phpstan benar-benar menyentuh
        # pohon module. Disaring dari vonis lalu dikurangkan dari hitungan supaya kontrol positif
        # ini tak pernah bocor jadi error yang memblok.
        if CANARY_BASENAME in str(path):
            canary_hits += len(msgs)
            continue
        for m in msgs:
            messages.append({"line": m.get("line"), "source": "phpstan",
                             "message": (m.get("message") or "")[:160], "file": path})
    for g in generic:
        messages.append({"line": 0, "source": "phpstan", "message": str(g)[:160]})
    count = totals.get("file_errors", 0) - canary_hits + len(generic)
    # Canary tak muncul = phpstan tak menganalisis satu file pun dari module (mis. neon module
    # meng-excludePaths dirinya sendiri). 0 error di situ bukan "bersih" — itu "tak diukur".
    coverage_ok = canary_hits > 0
    if generated:
        return {"available": True, "parse_ok": True, "generated_config": True,
                "coverage_ok": coverage_ok, "errors": 0, "warnings": count,
                "error_messages": messages[:50],
                "note": "phpstan pakai neon auto-generate (advisory — tak memblok)"}
    return {"available": True, "parse_ok": True, "generated_config": False,
            "coverage_ok": coverage_ok, "errors": count, "warnings": 0,
            "error_messages": messages[:50]}


def _health_status(container):
    """Status health container: 'healthy'|'unhealthy'|'starting'|'nohealth'|'gone'."""
    r = subprocess.run(
        ["docker", "inspect", "--format",
         "{{if .State.Health}}{{.State.Health.Status}}{{else}}nohealth{{end}}", container],
        capture_output=True, text=True)
    if r.returncode != 0:
        return "gone"
    return (r.stdout or "").strip() or "unknown"


def wait_healthy(container, timeout, poll=3.0):
    """Poll status health sampai 'healthy' / 'unhealthy' / timeout. Return (ok, status)."""
    deadline = time.monotonic() + timeout
    last = "unknown"
    while time.monotonic() < deadline:
        last = _health_status(container)
        if last == "healthy":
            return True, "healthy"
        if last in ("unhealthy", "gone"):
            return False, last
        time.sleep(poll)
    return False, f"timeout ({last})"


def _logs(container):
    r = subprocess.run(["docker", "logs", container], capture_output=True, text=True)
    return (r.stdout or "") + (r.stderr or "")


def _compose_file_text(db_image, image_ref, ps_domain, module_dir, publish=None):
    """docker-compose ephemeral: mariadb (healthcheck) + flashlight (depends_on healthy).

    `publish` (opsional, mis. '8000:80') memetakan port HTTP flashlight ke host —
    dipakai pemanggil yang perlu menjangkau PS dari luar container (mis. Lapis 4
    browser E2E lewat Playwright). Default None = tak ada port terpublish (perilaku
    lama; uji phpstan cukup lewat `docker exec`).
    """
    return (
        "services:\n"
        "  db:\n"
        f"    image: {db_image}\n"
        "    healthcheck:\n"
        '      test: ["CMD", "healthcheck.sh", "--connect"]\n'
        "      interval: 5s\n"
        "      timeout: 10s\n"
        "      retries: 20\n"
        "    environment:\n"
        f"      MYSQL_USER: {DB_USER}\n"
        f"      MYSQL_PASSWORD: {DB_PASSWORD}\n"
        f"      MYSQL_ROOT_PASSWORD: {DB_PASSWORD}\n"
        f"      MYSQL_DATABASE: {DB_NAME}\n"
        "  ps:\n"
        f"    image: {image_ref}\n"
        "    depends_on:\n"
        "      db:\n"
        "        condition: service_healthy\n"
        "    environment:\n"
        f"      PS_DOMAIN: {ps_domain}\n"
        "      MYSQL_HOST: db\n"
        '      MYSQL_PORT: "3306"\n'
        f"      MYSQL_USER: {DB_USER}\n"
        f"      MYSQL_PASSWORD: {DB_PASSWORD}\n"
        f"      MYSQL_DATABASE: {DB_NAME}\n"
        + (f'    ports:\n      - "{publish}"\n' if publish else "")
        + "    volumes:\n"
        f"      - {module_dir}:/ps-module-src:ro\n"
    )


CONTAINER_PREFIX = "psm-fl"  # SATU prefix untuk KEDUA orkestrator — lihat _project_name


def _project_name(full_ver):
    """Nama project compose — ber-prefix sama dgn jalur manual (CONTAINER_PREFIX).

    Dulu compose memakai `psmfl<ver><uid>` sementara jalur manual memakai `psm-fl-ps-<uid>`:
    dua konvensi untuk satu pertanyaan ("container mana milik skrip ini"). Akibatnya perintah
    pembersihan port-bocor `--filter name=psmfl` TIDAK cocok dgn container jalur manual —
    justru jalur yang dipakai saat `docker compose` absen, dan yang memegang port host. Satu
    prefix = satu filter (`--filter name=psm-fl`) menangkap keduanya.
    """
    v = re.sub(r"[^a-z0-9]", "", full_ver.lower())
    return f"{CONTAINER_PREFIX}-{v}-{uuid.uuid4().hex[:8]}"


def _bring_up_compose(module_dir, full_ver, image_ref, db_image, ps_domain, op_timeout, publish=None):
    proj = _project_name(full_ver)
    tmpdir = tempfile.mkdtemp(prefix="psm-fl-")
    compose_path = Path(tmpdir) / "docker-compose.yml"
    compose_path.write_text(_compose_file_text(db_image, image_ref, ps_domain, module_dir, publish),
                            encoding="utf-8")
    session = {"mode": "compose", "project": proj, "compose_file": str(compose_path),
               "tmpdir": tmpdir, "ps_container": None}
    up = subprocess.run(["docker", "compose", "-f", str(compose_path), "-p", proj, "up", "-d"],
                        capture_output=True, text=True, timeout=op_timeout)
    if up.returncode != 0:
        return session, f"docker compose up gagal: {up.stderr.strip()[-300:]}"
    q = subprocess.run(["docker", "compose", "-f", str(compose_path), "-p", proj, "ps", "-q", "ps"],
                       capture_output=True, text=True)
    cid = [c for c in (q.stdout or "").strip().splitlines() if c]
    if not cid:
        return session, "tak bisa resolve container flashlight dari compose"
    session["ps_container"] = cid[0]
    return session, None


def _bring_up_manual(module_dir, image_ref, db_image, ps_domain, startup_timeout, publish=None):
    uid = uuid.uuid4().hex[:8]
    session = {"mode": "manual", "network": f"{CONTAINER_PREFIX}-net-{uid}",
               "db": f"{CONTAINER_PREFIX}-db-{uid}", "ps_container": f"{CONTAINER_PREFIX}-ps-{uid}"}
    n = subprocess.run(["docker", "network", "create", session["network"]], capture_output=True, text=True)
    if n.returncode != 0:
        return session, f"gagal buat network: {n.stderr.strip()[-200:]}"
    db = subprocess.run(
        ["docker", "run", "-d", "--name", session["db"], "--network", session["network"],
         "--network-alias", "db",
         "-e", f"MYSQL_USER={DB_USER}", "-e", f"MYSQL_PASSWORD={DB_PASSWORD}",
         "-e", f"MYSQL_ROOT_PASSWORD={DB_PASSWORD}", "-e", f"MYSQL_DATABASE={DB_NAME}",
         "--health-cmd", "healthcheck.sh --connect", "--health-interval", "5s",
         "--health-timeout", "10s", "--health-retries", "20", db_image],
        capture_output=True, text=True)
    if db.returncode != 0:
        return session, f"gagal start DB: {db.stderr.strip()[-200:]}"
    ok, status = wait_healthy(session["db"], startup_timeout)
    if not ok:
        return session, f"DB tak jadi healthy ({status})"
    ps = subprocess.run(
        ["docker", "run", "-d", "--name", session["ps_container"], "--network", session["network"],
         "-e", f"PS_DOMAIN={ps_domain}", "-e", "MYSQL_HOST=db", "-e", "MYSQL_PORT=3306",
         "-e", f"MYSQL_USER={DB_USER}", "-e", f"MYSQL_PASSWORD={DB_PASSWORD}",
         "-e", f"MYSQL_DATABASE={DB_NAME}",
         *(["-p", publish] if publish else []),
         "-v", f"{module_dir}:/ps-module-src:ro", image_ref],
        capture_output=True, text=True)
    if ps.returncode != 0:
        return session, f"gagal start flashlight: {ps.stderr.strip()[-200:]}"
    return session, None


def _exec(session, env, inner, timeout):
    env_args = []
    for k, v in env.items():
        env_args += ["-e", f"{k}={v}"]
    if session["mode"] == "compose":
        cmd = ["docker", "compose", "-f", session["compose_file"], "-p", session["project"],
               "exec", "-T", *env_args, "ps", "sh", "-c", inner]
    else:
        cmd = ["docker", "exec", *env_args, session["ps_container"], "sh", "-c", inner]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _teardown(session):
    if not session:
        return
    if session.get("mode") == "compose":
        if session.get("compose_file"):
            subprocess.run(["docker", "compose", "-f", session["compose_file"],
                            "-p", session["project"], "down", "-v"], capture_output=True, text=True)
        if session.get("tmpdir"):
            shutil.rmtree(session["tmpdir"], ignore_errors=True)
    else:
        for c in (session.get("ps_container"), session.get("db")):
            if c:
                subprocess.run(["docker", "rm", "-f", c], capture_output=True, text=True)
        if session.get("network"):
            subprocess.run(["docker", "network", "rm", session["network"]], capture_output=True, text=True)


def run_one_version(module_dir, mod_name, full_ver, tag, *, orchestrator, db_image,
                    ps_domain, startup_timeout, op_timeout, allow_pull):
    """Bangun DB+flashlight untuk satu versi, install module, jalankan phpstan.

    Kegagalan infrastruktur (image absen tanpa izin pull, compose/DB/boot gagal,
    timeout) → degrade jujur lewat `errors`/`skipped_image` (tak konklusif, tak
    memblok). Install ditolak / phpstan-error (neon module) → sinyal konklusif.
    """
    image_ref = f"{IMAGE}:{tag}"
    res = {"version": full_ver, "tag": tag, "image": image_ref, "orchestrator": None,
           "db_image": db_image, "install": None, "coding_standard": None,
           "errors": [], "pass": False}

    mode = orchestrator
    if mode == "auto":
        mode = "compose" if compose_available() else "manual"
    elif mode == "compose" and not compose_available():
        res["errors"].append("orchestrator=compose diminta tapi 'docker compose' tak tersedia")
        return res
    res["orchestrator"] = mode

    # Gerbang unduh image (flashlight multi-GB + DB) — degrade jujur bila tak diizinkan.
    missing = [i for i in (image_ref, db_image) if not image_present(i)]
    if missing:
        if not allow_pull:
            res["skipped_image"] = True
            res["errors"].append(
                f"image belum ada lokal & pull tak diizinkan: {', '.join(missing)} — lewati versi ini")
            return res
        for i in missing:
            try:
                p = subprocess.run(["docker", "pull", i], capture_output=True, text=True, timeout=op_timeout)
            except subprocess.TimeoutExpired:
                res["errors"].append(f"timeout pull {i}")
                return res
            if p.returncode != 0:
                res["errors"].append(f"gagal pull {i}: {p.stderr.strip()[-300:]}")
                return res

    if mode == "compose":
        session, err = _bring_up_compose(module_dir, full_ver, image_ref, db_image, ps_domain, op_timeout)
    else:
        session, err = _bring_up_manual(module_dir, image_ref, db_image, ps_domain, startup_timeout)
    if err:
        res["errors"].append(err)
        _teardown(session)
        return res

    try:
        ok, status = wait_healthy(session["ps_container"], startup_timeout)
        if not ok:
            res["errors"].append(
                f"flashlight tak jadi 'healthy' ({status}) — DB/boot gagal, degrade jujur")
            res["boot_log"] = _logs(session["ps_container"])[-2000:]
            return res
        try:
            cp = _exec(session, {"MOD_NAME": mod_name}, INNER_SH, op_timeout)
        except subprocess.TimeoutExpired:
            res["errors"].append(f"timeout menjalankan uji di container ({image_ref})")
            return res
        out = (cp.stdout or "") + (cp.stderr or "")
        inst = parse_install(out)
        if inst.get("copy_fail"):
            res["errors"].append("gagal menyalin module ke dalam container")
            return res
        res["install"] = {"ok": inst["ok"], "no_console": inst.get("no_console", False),
                          "no_psroot": inst.get("no_psroot", False),
                          "no_verdict": inst.get("no_verdict", False),
                          "log": out.split(PHPSTAN_SENTINEL_PREFIX, 1)[0][-2000:]}
        res["coding_standard"] = parse_phpstan(out)
        cs = res["coding_standard"]
        res["pass"] = bool(res["install"]["ok"]) and \
            (not cs.get("available") or cs.get("parse_ok") is False or cs.get("errors", 0) == 0)
        return res
    finally:
        _teardown(session)


def main():
    ap = argparse.ArgumentParser(
        description="Validasi module PrestaShop di Docker flashlight (DB-backed), per versi.",
        epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("module_path", help="Path folder module PrestaShop")
    ap.add_argument("--versions", default="1.7.8,8.1,9.1", help="Versi target dipisah koma")
    ap.add_argument("--tag-map", default="", help="Peta LENGKAP versi=tag dipisah koma (MENGGANTI default), "
                                                  "mis. '1.7.8=1.7.8.11,8.1=8.1.6-nginx,9.1=9.1.4-nginx'")
    ap.add_argument("--extra-tag-map", default="", help="Tag TAMBAHAN versi=tag (MENAMBAH di atas peta), "
                                                        "mis. '9.2=9.2.0-nginx' — versi lain tak terpengaruh")
    ap.add_argument("--orchestrator", choices=["auto", "compose", "manual"], default=DEFAULT_ORCHESTRATOR,
                    help="Cara menghidupkan DB+flashlight (default: auto = compose bila ada, else manual)")
    ap.add_argument("--db-image", default=DEFAULT_DB_IMAGE, help=f"Image server DB (default: {DEFAULT_DB_IMAGE})")
    ap.add_argument("--ps-domain", default=DEFAULT_PS_DOMAIN, help=f"PS_DOMAIN flashlight (default: {DEFAULT_PS_DOMAIN})")
    ap.add_argument("--startup-timeout", type=int, default=DEFAULT_STARTUP_TIMEOUT,
                    help=f"Maks detik menunggu container healthy (default: {DEFAULT_STARTUP_TIMEOUT})")
    ap.add_argument("--allow-image-pull", action="store_true",
                    help="Izinkan unduh image bila belum ada lokal (default: lewati versi itu, degrade jujur). "
                         "Wajib utk pemanggil non-interaktif yang memang mau menarik image.")
    ap.add_argument("--timeout", type=int, default=600, help="Timeout operasi per versi (detik): pull/up/exec")
    ap.add_argument("-o", "--output", help="File output JSON (default: stdout)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    module_dir = Path(args.module_path).resolve()
    if not module_dir.is_dir():
        print(f"error: bukan folder: {module_dir}", file=sys.stderr)
        return 2
    mod_name = module_dir.name

    if not docker_available():
        result = {"module": mod_name, "docker_available": False, "status": "skipped",
                  "reason": "Docker tidak tersedia — lewati uji flashlight, andalkan ps-static-scan.",
                  "versions": {}}
        out = json.dumps(result, indent=2, ensure_ascii=False)
        (Path(args.output).write_text(out, encoding="utf-8") if args.output else print(out))
        return 0  # bukan error: degrade terkontrol

    tag_map = parse_tag_map(args.tag_map, args.extra_tag_map)
    result = {"module": mod_name, "docker_available": True, "status": "ran",
              "orchestrator": args.orchestrator, "versions": {}}
    overall_pass = True
    for full_ver in [v.strip() for v in args.versions.split(",")]:
        tag = resolve_tag(tag_map, full_ver)
        if args.verbose:
            print(f"versi {full_ver} -> {IMAGE}:{tag}", file=sys.stderr)
        r = run_one_version(module_dir, mod_name, full_ver, tag,
                            orchestrator=args.orchestrator, db_image=args.db_image,
                            ps_domain=args.ps_domain, startup_timeout=args.startup_timeout,
                            op_timeout=args.timeout, allow_pull=args.allow_image_pull)
        result["versions"][full_ver] = r
        overall_pass = overall_pass and r["pass"]
    result["pass"] = overall_pass

    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"ditulis: {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
