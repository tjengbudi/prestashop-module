#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Resolve shared psm config for the psm-* skill family -> JSON on stdout.

Deterministik: parse `_bmad/config.yaml` (+ overlay `_bmad/config.user.yaml`),
terapkan default kanonik, emit satu objek JSON. Menggantikan parse-YAML manual
yang dulu diulang inline di tiap SKILL.md (psm-scaffold/develop/cross-version/
validate/optimize) — model tinggal baca vonis JSON, tak perlu parse config.

Section `psm` di config.yaml memegang setting keluarga (target versions, tag map,
folder module & laporan). Core keys (communication_language, user_name) hidup di
root config, dengan config.user.yaml sebagai overlay yang menang untuk scalar.
Default di sini adalah satu-satunya sumber kebenaran untuk nilai yang absen.

Pemakaian:
  uv run resolve-psm-config.py --project-root /abs/path/to/project
  uv run resolve-psm-config.py --project-root ... --key psm_target_versions

Exit codes: 0=success, 1=validation error (config.yaml hilang), 2=runtime error.
"""

import argparse
import json
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("Error: pyyaml is required (PEP 723 dependency)", file=sys.stderr)
    sys.exit(2)


# Default kanonik keluarga psm — dipakai bila key absen dari config.
# Satu sumber kebenaran; menggantikan default yang dulu tersebar di lima prompt.
PSM_DEFAULTS = {
    "psm_target_versions": "1.7.8,8.1,9.0",
    "psm_flashlight_tag_map": "1.7.8=1.7.8.11,8.1=8.1.6-nginx,9.0=nightly",
    "psm_modules_dir": "{project-root}/modules",
    "psm_reports_dir": "{project-root}/_bmad-output/psm-validate",
}
CORE_DEFAULTS = {
    "communication_language": "Indonesia",
    "user_name": None,
}

# Key psm yang di-surface (metadata name/description/version section tak relevan bagi skill).
_PSM_KEYS = tuple(PSM_DEFAULTS.keys())
# Core key yang di-surface dari root config (+ overlay user).
_CORE_KEYS = tuple(CORE_DEFAULTS.keys())


def load_yaml_file(path: Path, required: bool = False, graceful: bool = False) -> dict:
    """Load a YAML file. Empty dict if absent (unless required).

    Bila required tapi absen: exit 1 (default), atau — bila graceful — kembalikan
    dict kosong agar pemanggil bisa terapkan default & tandai config hilang.
    """
    if not path.exists():
        if required and not graceful:
            print(f"Error: config tak ditemukan: {path}", file=sys.stderr)
            sys.exit(1)
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = yaml.safe_load(f)
    except yaml.YAMLError as error:
        print(f"Error: gagal parse YAML {path}: {error}", file=sys.stderr)
        sys.exit(2)
    return content if isinstance(content, dict) else {}


def resolve(project_root: Path, graceful: bool = False) -> dict:
    """Baca config.yaml (+ overlay user), terapkan default, kembalikan objek resolved.

    Bila graceful dan config.yaml hilang: emit default kanonik penuh dengan
    `config_missing: true` alih-alih exit 1 — untuk pemanggil yang mau
    degradasi anggun (mis. psm-agent-expert menyarankan bmad-bmb-setup).
    """
    bmad_dir = project_root / "_bmad"
    config_path = bmad_dir / "config.yaml"
    config_missing = graceful and not config_path.exists()
    base = load_yaml_file(config_path, required=True, graceful=graceful)
    user = load_yaml_file(bmad_dir / "config.user.yaml")

    psm_section = base.get("psm") or {}

    resolved: dict = {}
    # psm keys: section value -> default
    for key in _PSM_KEYS:
        value = psm_section.get(key)
        resolved[key] = value if value is not None else PSM_DEFAULTS[key]
    # core keys: user overlay wins -> base root -> default
    for key in _CORE_KEYS:
        if key in user and user[key] is not None:
            resolved[key] = user[key]
        elif key in base and base[key] is not None:
            resolved[key] = base[key]
        else:
            resolved[key] = CORE_DEFAULTS[key]

    if graceful:
        resolved["config_missing"] = config_missing

    return resolved


def main():
    parser = argparse.ArgumentParser(
        description="Resolve shared psm config -> JSON on stdout."
    )
    parser.add_argument(
        "--project-root",
        default=".",
        help="Root direktori project (berisi _bmad/). Default: cwd.",
    )
    parser.add_argument(
        "--key",
        help="Emit satu nilai key ini alih-alih seluruh objek JSON.",
    )
    parser.add_argument(
        "--graceful",
        action="store_true",
        help="Bila config.yaml hilang, emit default penuh + config_missing:true "
        "(exit 0) alih-alih exit 1. Untuk pemanggil dengan degradasi anggun.",
    )
    args = parser.parse_args()

    resolved = resolve(Path(args.project_root).resolve(), graceful=args.graceful)

    if args.key:
        if args.key not in resolved:
            print(
                f"Error: key tak dikenal: {args.key} "
                f"(pilihan: {', '.join(resolved.keys())})",
                file=sys.stderr,
            )
            sys.exit(1)
        value = resolved[args.key]
        print("" if value is None else value)
    else:
        print(json.dumps(resolved, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
