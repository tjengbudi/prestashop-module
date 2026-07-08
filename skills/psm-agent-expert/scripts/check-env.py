#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Cek keberadaan Docker + image prestashop-flashlight — deterministik.

Menjawab satu pertanyaan yang punya satu jawaban benar: apakah lingkungan uji
flashlight siap? (Docker terpasang & daemon hidup, image flashlight ada lokal.)
Bukan judgment — jadi bukan tugas prompt. Agent memutuskan APA yang dilakukan
atas hasilnya (tawarkan setup, tunda ke psm-validate); skrip hanya melapor.

Output JSON ke stdout. Exit 0 selalu (ketiadaan Docker bukan error skrip).
"""
import argparse
import json
import shutil
import subprocess
import sys

IMAGE = "prestashop/prestashop-flashlight"


def docker_available():
    if not shutil.which("docker"):
        return False, "docker tidak ada di PATH"
    try:
        r = subprocess.run(
            ["docker", "info"], capture_output=True, timeout=20
        )
        if r.returncode == 0:
            return True, "daemon hidup"
        return False, "docker terpasang tapi daemon tak merespons"
    except (subprocess.SubprocessError, OSError) as e:
        return False, f"docker info gagal: {e}"


def flashlight_present():
    """True bila minimal satu tag image flashlight ada lokal."""
    try:
        r = subprocess.run(
            ["docker", "images", "-q", IMAGE],
            capture_output=True,
            text=True,
            timeout=20,
        )
        return bool(r.stdout.strip())
    except (subprocess.SubprocessError, OSError):
        return False


def main():
    ap = argparse.ArgumentParser(
        description="Cek Docker + image flashlight untuk lapisan uji perilaku."
    )
    ap.parse_args()

    docker_ok, docker_detail = docker_available()
    image_ok = flashlight_present() if docker_ok else False

    if docker_ok and image_ok:
        ready, action = True, "siap"
    elif docker_ok:
        ready, action = False, "docker siap tapi image flashlight belum di-pull"
    else:
        ready, action = False, "docker belum siap"

    print(
        json.dumps(
            {
                "ready": ready,
                "docker": {"available": docker_ok, "detail": docker_detail},
                "flashlight_image": {"name": IMAGE, "present": image_ok},
                "action_hint": action,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
