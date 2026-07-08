#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Unit test untuk resolve-psm-config.py — verifikasi resolve/overlay/default.

Jalankan: uv run scripts/tests/test-resolve-psm-config.py
Exit 0 = semua lolos, 1 = ada yang gagal.
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

RESOLVER = Path(__file__).resolve().parent.parent / "resolve-psm-config.py"

FULL_CONFIG = """\
document_output_language: English
psm:
  name: PrestaShop Module Builder
  psm_target_versions: 1.7.8,8.1,9.0
  psm_flashlight_tag_map: 1.7.8=1.7.8.11,8.1=8.1.6-nginx,9.0=nightly
  psm_modules_dir: '{project-root}/modules'
  psm_reports_dir: '{project-root}/_bmad-output/psm-validate'
"""
# config.yaml tanpa key psm apa pun (memicu default kanonik)
BARE_CONFIG = """\
document_output_language: English
psm:
  name: PrestaShop Module Builder
"""
USER_CONFIG = """\
user_name: Budi
communication_language: Indonesia
"""

_failures = []


def make_project(config_yaml: str, user_yaml: str | None = None) -> Path:
    """Bikin tmpdir dengan _bmad/config.yaml (+ optional config.user.yaml)."""
    tmp = Path(tempfile.mkdtemp())
    bmad = tmp / "_bmad"
    bmad.mkdir()
    (bmad / "config.yaml").write_text(config_yaml, encoding="utf-8")
    if user_yaml is not None:
        (bmad / "config.user.yaml").write_text(user_yaml, encoding="utf-8")
    return tmp


def run(project_root: Path, *extra) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["uv", "run", str(RESOLVER), "--project-root", str(project_root), *extra],
        capture_output=True,
        text=True,
    )


def check(name: str, cond: bool, detail: str = ""):
    if cond:
        print(f"  ok: {name}")
    else:
        _failures.append(f"{name} — {detail}")
        print(f"  FAIL: {name} — {detail}")


def test_full_config_all_keys():
    proj = make_project(FULL_CONFIG, USER_CONFIG)
    res = run(proj)
    check("full: exit 0", res.returncode == 0, res.stderr)
    data = json.loads(res.stdout)
    check("full: target versions", data["psm_target_versions"] == "1.7.8,8.1,9.0", res.stdout)
    check("full: tag map", data["psm_flashlight_tag_map"] == "1.7.8=1.7.8.11,8.1=8.1.6-nginx,9.0=nightly", res.stdout)
    check("full: modules_dir", data["psm_modules_dir"] == "{project-root}/modules", res.stdout)
    check("full: reports_dir", data["psm_reports_dir"] == "{project-root}/_bmad-output/psm-validate", res.stdout)


def test_missing_psm_keys_get_defaults():
    proj = make_project(BARE_CONFIG)  # tak ada key psm, tak ada user.yaml
    res = run(proj)
    check("default: exit 0", res.returncode == 0, res.stderr)
    data = json.loads(res.stdout)
    check("default: target versions kanonik", data["psm_target_versions"] == "1.7.8,8.1,9.0", res.stdout)
    check("default: tag map kanonik", data["psm_flashlight_tag_map"] == "1.7.8=1.7.8.11,8.1=8.1.6-nginx,9.0=nightly", res.stdout)
    check("default: reports_dir kanonik", data["psm_reports_dir"] == "{project-root}/_bmad-output/psm-validate", res.stdout)
    check("default: communication_language kanonik", data["communication_language"] == "Indonesia", res.stdout)


def test_user_overlay_wins():
    user = "user_name: Budi\ncommunication_language: English\n"
    proj = make_project(FULL_CONFIG, user)
    res = run(proj)
    data = json.loads(res.stdout)
    check("overlay: user comm_lang menang", data["communication_language"] == "English", res.stdout)
    check("overlay: user_name terisi", data["user_name"] == "Budi", res.stdout)


def test_single_key():
    proj = make_project(FULL_CONFIG, USER_CONFIG)
    res = run(proj, "--key", "psm_target_versions")
    check("key: exit 0", res.returncode == 0, res.stderr)
    check("key: nilai tunggal", res.stdout.strip() == "1.7.8,8.1,9.0", res.stdout)


def test_unknown_key_errors():
    proj = make_project(FULL_CONFIG)
    res = run(proj, "--key", "nonexistent")
    check("key: unknown -> exit 1", res.returncode == 1, res.stdout)


def test_missing_config_errors():
    tmp = Path(tempfile.mkdtemp())  # tak ada _bmad/ sama sekali
    res = run(tmp)
    check("missing: exit non-zero", res.returncode != 0, res.stdout)
    check("missing: pesan ke stderr", "config" in res.stderr.lower(), res.stderr)


def test_graceful_missing_config():
    tmp = Path(tempfile.mkdtemp())  # tak ada _bmad/ sama sekali
    res = run(tmp, "--graceful")
    check("graceful: exit 0", res.returncode == 0, res.stderr)
    data = json.loads(res.stdout)
    check("graceful: config_missing true", data.get("config_missing") is True, res.stdout)
    check("graceful: default kanonik terisi", data["psm_target_versions"] == "1.7.8,8.1,9.0", res.stdout)
    check("graceful: comm_lang default", data["communication_language"] == "Indonesia", res.stdout)


def test_graceful_present_config():
    proj = make_project(FULL_CONFIG, USER_CONFIG)
    res = run(proj, "--graceful")
    check("graceful+present: exit 0", res.returncode == 0, res.stderr)
    data = json.loads(res.stdout)
    check("graceful+present: config_missing false", data.get("config_missing") is False, res.stdout)


def main():
    for test in (
        test_full_config_all_keys,
        test_missing_psm_keys_get_defaults,
        test_user_overlay_wins,
        test_single_key,
        test_unknown_key_errors,
        test_missing_config_errors,
        test_graceful_missing_config,
        test_graceful_present_config,
    ):
        print(f"{test.__name__}:")
        test()
    print()
    if _failures:
        print(f"{len(_failures)} gagal:")
        for f in _failures:
            print(f"  - {f}")
        sys.exit(1)
    print("semua lolos")
    sys.exit(0)


if __name__ == "__main__":
    main()
