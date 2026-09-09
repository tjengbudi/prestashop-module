#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Lapis 5 — jalankan SKENARIO KONDISI-RUSAK module di flashlight -> JSON temuan.

Empat lapis lain menguji module dari keadaan BERSIH: pindai source, install di core asli,
review konteks-bersih, dan drive browser. Tak satu pun bisa melahirkan keadaan RUSAK —
baris config yang membayangi, OrderState duplikat yang keduanya memegang order, template
core yang tertimpa, file yang tak bisa ditulis. Padahal justru di sanalah cacat kelas berat
bersembunyi: upgrade dari build cacat, tombol Reset, multistore, uninstall separuh jalan.

Sampai lapis ini ada, kondisi itu dirakit ulang dengan tangan oleh peninjau adversarial tiap
ronde — puluhan sampai ratusan langkah, berbeda-beda tiap kali, dan hilang begitu ronde
selesai. Lapis ini membuatnya DEKLARATIF dan DAPAT DIULANG: module menuliskannya sekali,
mesin menjalankannya tiap run.

Bentuk skenario (`<module>/tests/scenarios/*.json`):

  {
    "name": "duplicate-order-states-both-with-orders",
    "description": "kenapa kondisi ini mungkin terjadi di toko nyata",
    "given": ["UPDATE `{prefix}configuration` SET ...",        # SQL, atau
              {"sh": "chmod 0555 /var/www/html/mails/en"}],    # perintah shell
    "when":  "upgrade",                                        # install|upgrade|uninstall|reset|none
    "then":  [{"query": "SELECT COUNT(*) FROM `{prefix}order_state` WHERE ...",
               "expect": "1"}]
  }

`{prefix}` disubstitusi dari `database_prefix` instalasi — skenario tak boleh mengetik `ps_`,
karena toko nyata sering memakai prefix lain dan skenario yang mengetiknya akan hijau palsu
(query menunjuk tabel yang tak ada -> error -> tertangkap, tapi hanya kalau kita menggerbang;
lebih baik tak punya permukaannya).

ISOLASI: DB di-snapshot SEKALI sesudah install, lalu DIPULIHKAN sebelum tiap skenario. Tanpa
itu skenario jadi urut-bergantung — yang satu meninggalkan jejak untuk berikutnya — dan
"deterministik" tinggal klaim. Snapshot/restore memakai mysqldump/mysql yang ada di image.

Exit: 0 = jalan (atau degrade jujur: Docker/image absen), 1 = ada skenario gagal,
2 = error input (skenario cacat bentuk, module bukan folder, versi tak dikenal).

Pemakaian:
  uv run scripts/ps-scenario-run.py <module-path> --versions 9.1 --reports-dir <dir>
"""
import argparse
import importlib.util
import json
import re
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent


def load_sibling(path, name):
    """Muat skrip sibling by-path. Gagal = exit 2 berpesan, bukan traceback telanjang."""
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if not (spec and spec.loader):
            raise ImportError(f"spec tak terbentuk untuk {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except (OSError, ImportError, SyntaxError) as e:
        print(f"error: skrip sibling tak bisa dimuat: {Path(path).name} ({e})", file=sys.stderr)
        print("skrip psm-validate saling bergantung — salin folder scripts/ utuh", file=sys.stderr)
        sys.exit(2)


fl = load_sibling(_HERE / "ps-flashlight-run.py", "ps_flashlight_run")

SCENARIO_DIR = "tests/scenarios"
WHEN_ACTIONS = ("none", "install", "upgrade", "uninstall", "reset")
BASELINE_PATH = "/tmp/psm-scenario-baseline.sql"
SQL_TIMEOUT = 120

# Prelude shell: baca kredensial DB dari parameters.php (seragam di 1.7.8/8.1/9.1) lalu
# ekspor sebagai variabel. Host bisa berbentuk "host:port" — dipisah di sini, bukan di tiap
# pemanggil, supaya satu tempat saja yang tahu bentuknya.
DB_PRELUDE = r'''
eval "$(php -r '
$p = include "/var/www/html/app/config/parameters.php";
$d = $p["parameters"];
$h = $d["database_host"]; $port = "3306";
if (strpos($h, ":") !== false) { list($h, $port) = explode(":", $h, 2); }
printf("DBH=%s; DBPORT=%s; DBU=%s; DBPW=%s; DBN=%s; DBX=%s;",
    escapeshellarg($h), escapeshellarg($port), escapeshellarg($d["database_user"]),
    escapeshellarg($d["database_password"]), escapeshellarg($d["database_name"]),
    escapeshellarg($d["database_prefix"]));
')"
# `mysql`/`mysqldump` di image MariaDB adalah alias usang yang mencetak peringatan
# deprecation ke stderr. Peringatan itu pernah tercampur ke nilai query dan membuat setiap
# assertion gagal dengan alasan palsu — pilih binary bernama benar bila ada.
MYSQL_BIN=$(command -v mariadb || command -v mysql)
MYSQLDUMP_BIN=$(command -v mariadb-dump || command -v mysqldump)
MYSQL="$MYSQL_BIN -h $DBH -P $DBPORT -u $DBU -p$DBPW $DBN"
MYSQLDUMP="$MYSQLDUMP_BIN -h $DBH -P $DBPORT -u $DBU -p$DBPW $DBN"
'''


# ---------------------------------------------------------------------------
# Fungsi murni (teruji tanpa Docker)
# ---------------------------------------------------------------------------
def discover_scenarios(module_dir):
    """Baca `<module>/tests/scenarios/*.json`. Return (scenarios, notes).

    Spec cacat bentuk DILEWATI dengan catatan, tidak menggagalkan run: satu file rusak tak
    boleh membuat seluruh lapis tak konklusif, tapi ia juga tak boleh hilang senyap —
    catatannya naik ke output dan operator melihat apa yang tak dinilai.
    """
    scen_dir = Path(module_dir) / SCENARIO_DIR
    scenarios, notes = [], []
    if not scen_dir.is_dir():
        return scenarios, notes

    for path in sorted(scen_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            notes.append(f"{path.name}: JSON tak terbaca ({e}) — dilewati")
            continue
        problem = validate_scenario(data)
        if problem:
            notes.append(f"{path.name}: {problem} — dilewati")
            continue
        data["source"] = path.name
        scenarios.append(data)
    return scenarios, notes


def validate_scenario(data):
    """Return None bila bentuknya sah, atau alasan satu baris kenapa tidak."""
    if not isinstance(data, dict):
        return "bukan objek JSON"
    if not data.get("name"):
        return "tanpa `name`"
    when = data.get("when", "none")
    if when not in WHEN_ACTIONS:
        return f"`when` tak dikenal: {when!r} — sah: {'|'.join(WHEN_ACTIONS)}"
    for g in data.get("given", []):
        if isinstance(g, dict):
            if "sh" not in g:
                return "entri `given` objek tanpa kunci `sh`"
        elif not isinstance(g, str):
            return "entri `given` harus string SQL atau {\"sh\": ...}"
    then = data.get("then", [])
    if not isinstance(then, list) or not then:
        return "`then` kosong — skenario tanpa assertion tak membuktikan apa pun"
    for a in then:
        if not isinstance(a, dict) or "query" not in a or "expect" not in a:
            return "entri `then` harus {\"query\": ..., \"expect\": ...}"
    return None


def substitute_prefix(sql, prefix):
    """Ganti `{prefix}` dengan prefix tabel instalasi."""
    return (sql or "").replace("{prefix}", prefix)


def compare_expect(actual, expected):
    """Bandingkan hasil query dengan yang diharapkan — string, dinormalkan spasi.

    Sengaja perbandingan STRING, bukan numerik: `expect` ditulis operator sebagai teks, dan
    memaksa cast akan diam-diam menyamakan "0" dengan "" (query tanpa baris) — dua keadaan
    yang berbeda arti.
    """
    return re.sub(r"\s+", " ", str(actual)).strip() == re.sub(r"\s+", " ", str(expected)).strip()


# ---------------------------------------------------------------------------
# Eksekusi di container
# ---------------------------------------------------------------------------
def _sh(session, inner, timeout=SQL_TIMEOUT):
    """Jalankan blok shell di container PS, dengan prelude kredensial DB terpasang."""
    return fl._exec(session, {}, DB_PRELUDE + "\n" + inner, timeout)


def read_db_prefix(session):
    """Prefix tabel instalasi. '' bila tak terbaca — pemanggil menandainya tak konklusif."""
    cp = _sh(session, 'printf "%s" "$DBX"')
    return (cp.stdout or "").strip() if cp.returncode == 0 else ""


def snapshot_db(session):
    """Dump DB sekali sesudah install. Return (ok, pesan)."""
    cp = _sh(session, f'$MYSQLDUMP --single-transaction --routines > {BASELINE_PATH} 2>/dev/null')
    if cp.returncode != 0:
        return False, f"mysqldump gagal (rc={cp.returncode}): {(cp.stderr or '').strip()[-200:]}"
    return True, ""


def restore_db(session):
    """Pulihkan DB ke snapshot. Inilah yang membuat skenario tak urut-bergantung."""
    cp = _sh(session, f'$MYSQL < {BASELINE_PATH} 2>/dev/null')
    if cp.returncode != 0:
        return False, f"restore snapshot gagal (rc={cp.returncode})"
    return True, ""


def run_sql(session, sql):
    """Jalankan satu pernyataan SQL. Return (ok, stderr-terpotong)."""
    payload = sql.replace("'", "'\\''")
    cp = _sh(session, f"$MYSQL -e '{payload}' 2>&1")
    return cp.returncode == 0, (cp.stdout or "").strip()[-200:]


def query_scalar(session, sql):
    """Jalankan query & kembalikan skalar pertama sebagai string. (ok, nilai|error)."""
    payload = sql.replace("'", "'\\''")
    # stderr sengaja TIDAK digabung ke stdout: kanal nilai harus murni. Peringatan klien
    # (mis. alias usang) yang bocor ke sini terbaca sebagai hasil query dan menggagalkan
    # assertion dengan alasan yang bukan miliknya.
    cp = _sh(session, f"$MYSQL -N -B -e '{payload}'")
    out = (cp.stdout or "").strip()
    if cp.returncode != 0:
        return False, ((cp.stderr or "") + " " + out).strip()[-200:]
    # -N -B: tanpa header, dipisah tab. Ambil sel pertama baris pertama.
    first = out.splitlines()[0] if out.splitlines() else ""
    return True, first.split("\t")[0] if first else ""


def module_action(session, mod_name, action, timeout):
    """Jalankan aksi siklus-hidup module lewat bin/console. Return (ok, output-terpotong)."""
    if action == "none":
        return True, ""
    cmd = (f'cd /var/www/html && php -d memory_limit=-1 bin/console prestashop:module '
           f'--no-interaction {action} {mod_name} 2>&1')
    cp = fl._exec(session, {}, cmd, timeout)
    return cp.returncode == 0, (cp.stdout or "").strip()[-400:]


def run_scenario(session, scenario, mod_name, prefix, timeout):
    """Terapkan given -> jalankan when -> nilai then. Return dict hasil satu skenario."""
    out = {"name": scenario["name"], "source": scenario.get("source", ""),
           "ok": True, "conclusive": True, "steps": [], "note": ""}

    ok, err = restore_db(session)
    if not ok:
        out.update(ok=False, conclusive=False, note=err)
        return out

    for g in scenario.get("given", []):
        if isinstance(g, dict):
            cp = fl._exec(session, {}, g["sh"], timeout)
            good, detail = cp.returncode == 0, (cp.stdout or cp.stderr or "").strip()[-200:]
            label = f"sh: {g['sh'][:60]}"
        else:
            good, detail = run_sql(session, substitute_prefix(g, prefix))
            label = f"sql: {g[:60]}"
        out["steps"].append({"phase": "given", "step": label, "ok": good, "detail": detail})
        if not good:
            # `given` yang gagal berarti kondisi rusaknya TAK TERBENTUK. Menilai `then` di
            # atasnya akan melaporkan lolos/gagal atas keadaan yang bukan yang dimaksud —
            # jadi ini tak konklusif, bukan gagal.
            out.update(ok=False, conclusive=False, note="given gagal — kondisi tak terbentuk")
            return out

    when = scenario.get("when", "none")
    good, detail = module_action(session, mod_name, when, timeout)
    out["steps"].append({"phase": "when", "step": when, "ok": good, "detail": detail})
    # `when` yang gagal BUKAN otomatis tak konklusif: "upgrade menolak jalan di kondisi ini"
    # bisa jadi persis yang diuji. Biarkan `then` yang memutuskan.

    for a in scenario.get("then", []):
        good, actual = query_scalar(session, substitute_prefix(a["query"], prefix))
        if not good:
            out["steps"].append({"phase": "then", "step": a["query"][:60], "ok": False,
                                 "detail": f"query error: {actual}"})
            out.update(ok=False, conclusive=False, note="query `then` error — assertion tak dinilai")
            return out
        match = compare_expect(actual, a["expect"])
        out["steps"].append({"phase": "then", "step": a["query"][:60], "ok": match,
                             "detail": f"dapat={actual!r} harap={a['expect']!r}"})
        if not match:
            out["ok"] = False

    return out


# ---------------------------------------------------------------------------
# Orkestrasi per versi
# ---------------------------------------------------------------------------
def install_module(session, mod_name, timeout):
    """Salin + install module via PS console di container. Return (info, err_or_None)."""
    import subprocess as _sp
    try:
        cp = fl._exec(session, {"MOD_NAME": mod_name}, fl.INSTALL_BLOCK_SH, timeout)
    except _sp.TimeoutExpired:
        return {"ok": False}, "timeout menjalankan install di container"
    out = (cp.stdout or "") + (cp.stderr or "")
    inst = fl.parse_install(out)
    if inst.get("copy_fail"):
        return {"ok": False}, "gagal menyalin module ke dalam container"
    return {"ok": inst["ok"], "no_console": inst.get("no_console", False)}, None


def run_one_version(module_dir, mod_name, full_ver, tag, scenarios, *, orchestrator, db_image,
                    ps_domain, startup_timeout, op_timeout, allow_pull):
    """Boot flashlight, install module, snapshot DB, jalankan tiap skenario terisolasi."""
    import subprocess as _sp

    image_ref = f"{fl.IMAGE}:{tag}"
    res = {"version": full_ver, "tag": tag, "image": image_ref, "install": {"ok": False},
           "scenarios": [], "errors": [], "inconclusive": [], "pass": True, "conclusive": False}

    if not scenarios:
        # Nol skenario BUKAN lolos: tak ada yang dibuktikan. Konklusivitas tetap False supaya
        # agregat tak menghitungnya sebagai lapis yang menegakkan sesuatu.
        res["errors"].append("module tak punya tests/scenarios/*.json — lapis tak menilai apa pun")
        return res

    mode = orchestrator
    if mode == "auto":
        mode = "compose" if fl.compose_available() else "manual"
    elif mode == "compose" and not fl.compose_available():
        res["errors"].append("orchestrator=compose diminta tapi 'docker compose' tak tersedia")
        return res
    res["orchestrator"] = mode

    missing = [i for i in (image_ref, db_image) if not fl.image_present(i)]
    if missing:
        if not allow_pull:
            res["skipped_image"] = True
            res["errors"].append(
                f"image belum ada lokal & pull tak diizinkan: {', '.join(missing)} — lewati versi ini")
            return res
        for i in missing:
            try:
                p = _sp.run(["docker", "pull", i], capture_output=True, text=True, timeout=op_timeout)
            except _sp.TimeoutExpired:
                res["errors"].append(f"timeout pull {i}")
                return res
            if p.returncode != 0:
                res["errors"].append(f"gagal pull {i}: {p.stderr.strip()[-200:]}")
                return res

    if mode == "compose":
        session, err = fl._bring_up_compose(module_dir, full_ver, image_ref, db_image,
                                            ps_domain, op_timeout)
    else:
        session, err = fl._bring_up_manual(module_dir, image_ref, db_image, ps_domain,
                                           startup_timeout)
    if err:
        res["errors"].append(err)
        fl._teardown(session)
        return res

    try:
        ok, status = fl.wait_healthy(session["ps_container"], startup_timeout)
        if not ok:
            res["errors"].append(f"flashlight tak jadi 'healthy' ({status}) — degrade jujur")
            return res

        install, ierr = install_module(session, mod_name, op_timeout)
        res["install"] = install
        if ierr or not install["ok"]:
            res["errors"].append(ierr or "install module gagal — skenario tak bisa dinilai")
            return res

        prefix = read_db_prefix(session)
        if not prefix:
            res["errors"].append("prefix tabel tak terbaca dari parameters.php")
            return res
        res["db_prefix"] = prefix

        snap_ok, snap_err = snapshot_db(session)
        if not snap_ok:
            # Tanpa snapshot tak ada isolasi, dan skenario urut-bergantung adalah persis
            # yang lapis ini ada untuk dihindari. Lebih baik tak menilai daripada menilai
            # keadaan yang tak diketahui.
            res["errors"].append(snap_err + " — tanpa snapshot skenario tak terisolasi")
            return res

        for scenario in scenarios:
            out = run_scenario(session, scenario, mod_name, prefix, op_timeout)
            res["scenarios"].append(out)
            if not out["conclusive"]:
                res["inconclusive"].append({"scenario": out["name"], "note": out["note"]})
            elif not out["ok"]:
                res["pass"] = False

        # Konklusif bila ADA skenario yang benar-benar dinilai.
        res["conclusive"] = any(s["conclusive"] for s in res["scenarios"])
    finally:
        fl._teardown(session)

    return res


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser(
        description="Lapis 5 — jalankan skenario kondisi-rusak module di flashlight.",
        epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("module_path", help="Path folder module PrestaShop")
    ap.add_argument("--versions", default="1.7.8,8.1,9.1", help="Versi target dipisah koma")
    ap.add_argument("--config", help="JSON hasil resolve-psm-config.py — setelan keluarga diisi "
                                     "dari sini untuk argumen yang tak diberikan eksplisit.")
    ap.add_argument("--tag-map", default="", help="Peta LENGKAP versi=tag dipisah koma (MENGGANTI default)")
    ap.add_argument("--extra-tag-map", default="", help="Peta TAMBAHAN versi=tag (menambal default)")
    ap.add_argument("--orchestrator", choices=["auto", "compose", "manual"],
                    default=fl.DEFAULT_ORCHESTRATOR)
    ap.add_argument("--db-image", default=fl.DEFAULT_DB_IMAGE)
    ap.add_argument("--ps-domain", default=fl.DEFAULT_PS_DOMAIN)
    ap.add_argument("--startup-timeout", type=int, default=fl.DEFAULT_STARTUP_TIMEOUT)
    ap.add_argument("--timeout", type=int, default=600,
                    help="Batas detik tiap operasi docker/console (default 600)")
    ap.add_argument("--allow-image-pull", action="store_true",
                    help="Izinkan tarik image (multi-GB). Tanpa ini, image absen = degrade jujur.")
    ap.add_argument("-o", "--output", help="File output JSON (default: stdout)")
    args = ap.parse_args()

    if args.config:
        fl.apply_config_file(args, ap, args.config)

    module_dir = Path(args.module_path).resolve()
    if not module_dir.is_dir():
        print(f"error: bukan folder: {module_dir}", file=sys.stderr)
        return 2

    scenarios, notes = discover_scenarios(module_dir)

    result = {"module": module_dir.name, "layer": "scenario",
              "docker_available": fl.docker_available(), "status": "skipped",
              "scenario_sources": [s.get("source", "") for s in scenarios],
              "scenario_notes": notes, "pass": True, "versions": {}}

    if not result["docker_available"]:
        # Runner tanpa Docker bukan module yang gagal — degrade jujur, exit 0.
        result["reason"] = "Docker tidak tersedia"
        _emit(result, args.output)
        return 0

    tag_map = fl.parse_tag_map(args.tag_map, args.extra_tag_map)
    result["status"] = "ran"

    for full_ver in [v.strip() for v in args.versions.split(",") if v.strip()]:
        tag = fl.resolve_tag(tag_map, full_ver)
        if not tag:
            print(f"error: versi tak dikenal di tag map: {full_ver}", file=sys.stderr)
            return 2
        res = run_one_version(module_dir, module_dir.name, full_ver, tag, scenarios,
                              orchestrator=args.orchestrator, db_image=args.db_image,
                              ps_domain=args.ps_domain, startup_timeout=args.startup_timeout,
                              op_timeout=args.timeout, allow_pull=args.allow_image_pull)
        result["versions"][full_ver] = res
        if not res["pass"]:
            result["pass"] = False

    _emit(result, args.output)
    return 0 if result["pass"] else 1


def _emit(result, output):
    out = json.dumps(result, indent=2, ensure_ascii=False)
    if output:
        Path(output).write_text(out, encoding="utf-8")
        print(f"ditulis: {output}", file=sys.stderr)
    else:
        print(out)


if __name__ == "__main__":
    sys.exit(main())
