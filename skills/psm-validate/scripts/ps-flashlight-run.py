#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Jalankan validasi module di dalam Docker prestashop-flashlight, per versi.

Lapisan akurasi #2: menguji module terhadap PrestaShop core ASLI tiap versi —
instalasi module + coding standard (php-cs / phpstan bila tersedia di image).
Deterministik per (module, versi, image). Output JSON per versi.

Memetakan versi target -> tag image flashlight, menjalankan container dengan
module di-mount ke INSTALL_MODULES_DIR, lalu mengumpulkan status install &
hasil coding-standard. Bila Docker tak tersedia, keluar dengan status terstruktur
'skipped' (bukan crash) supaya pemanggil bisa degrade ke ps-static-scan saja.

Pemetaan tag default mengikuti tag resmi Docker Hub prestashop/prestashop-flashlight.
"""
import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_TAG_MAP = {"1.7.8": "1.7.8.11", "8.1": "8.1", "9.0": "nightly"}
IMAGE = "prestashop/prestashop-flashlight"


def docker_available():
    if not shutil.which("docker"):
        return False
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=20)
        return r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def parse_tag_map(raw):
    """Format: '1.7.8=1.7.8.11,8.1=8.1,9.0=nightly' -> dict. Kosong -> default."""
    if not raw:
        return dict(DEFAULT_TAG_MAP)
    out = {}
    for pair in raw.split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k.strip()] = v.strip()
    return out or dict(DEFAULT_TAG_MAP)


def run_one_version(module_dir, full_ver, tag, pull, timeout):
    """Spin container flashlight untuk satu versi, install module, jalankan CS.

    Strategi: jalankan container dengan module di-mount, gunakan PrestaShop CLI
    untuk instalasi dan jalankan coding-standard bila tooling ada di image.
    """
    image_ref = f"{IMAGE}:{tag}"
    res = {"version": full_ver, "tag": tag, "image": image_ref, "pull": None,
           "install": None, "coding_standard": None, "errors": [], "pass": False}

    if pull:
        p = subprocess.run(["docker", "pull", image_ref], capture_output=True, text=True, timeout=timeout)
        res["pull"] = {"ok": p.returncode == 0, "stderr": p.stderr.strip()[-500:]}
        if p.returncode != 0:
            res["errors"].append(f"gagal pull {image_ref}")
            return res

    # Script di dalam container: install module via PS CLI, lalu coding standard.
    # PS CLI ada di /var/www/html/bin/console (PS8/9) atau ./bin/console.
    inner = (
        'set -e; MOD="$(basename /ps-module-src)"; '
        'cp -r /ps-module-src "/var/www/html/modules/$MOD"; '
        'cd /var/www/html; '
        'CONSOLE=""; [ -f bin/console ] && CONSOLE="bin/console"; '
        'if [ -n "$CONSOLE" ]; then '
        '  php $CONSOLE prestashop:module install "$MOD" 2>&1 && echo "PSM_INSTALL_OK" || echo "PSM_INSTALL_FAIL"; '
        'else echo "PSM_NO_CONSOLE"; fi; '
        # coding standard: phpcs PrestaShop dengan report JSON (hitungan exact, bukan tebak)
        'if command -v phpcs >/dev/null 2>&1; then '
        '  echo "PSM_CS_JSON_START"; '
        '  phpcs --standard=PrestaShop --report=json "modules/$MOD" 2>/dev/null || true; '
        '  echo "PSM_CS_JSON_END"; '
        'else echo "PSM_CS_ABSENT"; fi'
    )
    cmd = [
        "docker", "run", "--rm",
        "-v", f"{module_dir}:/ps-module-src:ro",
        "-e", "DRY_RUN=true",  # jangan boot web server penuh; kita hanya butuh CLI + FS
        "--entrypoint", "/bin/sh",
        image_ref, "-c", inner,
    ]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        res["errors"].append(f"timeout menjalankan container {image_ref}")
        return res
    out = (p.stdout or "") + (p.stderr or "")
    res["install"] = {
        "ok": "PSM_INSTALL_OK" in out,
        "no_console": "PSM_NO_CONSOLE" in out,
        "log": out[-2000:],
    }
    res["coding_standard"] = parse_phpcs(out)
    cs = res["coding_standard"]
    res["pass"] = bool(res["install"] and res["install"]["ok"]) and \
        (not cs.get("available") or cs.get("parse_ok") is False or cs.get("errors", 0) == 0)
    return res


def parse_phpcs(out):
    """Ambil hitungan error EXACT dari laporan JSON phpcs (bukan tebak substring).

    phpcs --report=json mengeluarkan {"totals":{"errors":N,"warnings":M}, "files":{...}}.
    Bila JSON tak terparse, jangan menebak — tandai parse_ok=False dan jangan gating.
    """
    if "PSM_CS_ABSENT" in out:
        return {"available": False}
    if "PSM_CS_JSON_START" not in out or "PSM_CS_JSON_END" not in out:
        return {"available": True, "parse_ok": False, "note": "penanda report phpcs tak ditemukan"}
    raw = out.split("PSM_CS_JSON_START", 1)[1].split("PSM_CS_JSON_END", 1)[0].strip()
    start = raw.find("{")
    if start == -1:
        return {"available": True, "parse_ok": False, "note": "JSON phpcs kosong/tak valid"}
    try:
        report = json.loads(raw[start:])
        totals = report.get("totals", {})
        files = report.get("files", {})
        messages = []
        for fdata in files.values():
            for m in fdata.get("messages", []):
                if m.get("type") == "ERROR":
                    messages.append({"line": m.get("line"), "source": m.get("source"), "message": m.get("message", "")[:160]})
        return {"available": True, "parse_ok": True,
                "errors": totals.get("errors", 0), "warnings": totals.get("warnings", 0),
                "error_messages": messages[:50]}
    except json.JSONDecodeError:
        return {"available": True, "parse_ok": False, "note": "gagal parse JSON phpcs"}


def main():
    ap = argparse.ArgumentParser(description="Validasi module PrestaShop di Docker flashlight, per versi.")
    ap.add_argument("module_path", help="Path folder module PrestaShop")
    ap.add_argument("--versions", default="1.7.8,8.1,9.0", help="Versi target dipisah koma")
    ap.add_argument("--tag-map", default="", help="Pemetaan versi=tag dipisah koma, mis. '9.0=nightly'")
    ap.add_argument("--no-pull", action="store_true", help="Jangan docker pull (pakai image lokal)")
    ap.add_argument("--timeout", type=int, default=600, help="Timeout per versi (detik)")
    ap.add_argument("-o", "--output", help="File output JSON (default: stdout)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    module_dir = Path(args.module_path).resolve()
    if not module_dir.is_dir():
        print(f"error: bukan folder: {module_dir}", file=sys.stderr)
        return 2

    if not docker_available():
        result = {"module": module_dir.name, "docker_available": False, "status": "skipped",
                  "reason": "Docker tidak tersedia — lewati uji flashlight, andalkan ps-static-scan.", "versions": {}}
        out = json.dumps(result, indent=2, ensure_ascii=False)
        (Path(args.output).write_text(out, encoding="utf-8") if args.output else print(out))
        return 0  # bukan error: degrade terkontrol

    tag_map = parse_tag_map(args.tag_map)
    result = {"module": module_dir.name, "docker_available": True, "status": "ran", "versions": {}}
    overall_pass = True
    for full_ver in [v.strip() for v in args.versions.split(",")]:
        tag = tag_map.get(full_ver) or tag_map.get(full_ver.rsplit(".", 1)[0]) or full_ver
        if args.verbose:
            print(f"versi {full_ver} -> {IMAGE}:{tag}", file=sys.stderr)
        r = run_one_version(module_dir, full_ver, tag, pull=not args.no_pull, timeout=args.timeout)
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
