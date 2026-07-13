#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Unit test untuk merge-config.py — anti-zombie, template result, split user config.

Jalankan: uv run scripts/tests/test-merge-config.py
Exit 0 = semua lolos, 1 = ada yang gagal.
"""
import contextlib
import importlib.util
import io
import sys
from pathlib import Path

MOD_PATH = Path(__file__).resolve().parent.parent / "merge-config.py"
spec = importlib.util.spec_from_file_location("merge_config", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

_fail = []


def check(name, cond):
    print(f"  {'ok' if cond else 'FAIL'}: {name}")
    if not cond:
        _fail.append(name)


def expect_exit(fn, code=1):
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            fn()
        return False
    except SystemExit as e:
        return e.code == code


MODYAML = {
    "code": "psm", "name": "PSM", "description": "desc", "module_version": "2.0",
    "default_selected": False,
    "psm_target_versions": {"prompt": "?", "default": "x", "result": "{value}"},
    "psm_modules_dir": {"prompt": "?", "default": "d", "result": "{project-root}/{value}"},
    "secret_key": {"prompt": "?", "user_setting": True},
}


def test_apply_result_templates():
    t = mod.apply_result_templates(MODYAML, {"psm_target_versions": "1.7.8,9.1"})
    check("template {value} diterapkan", t["psm_target_versions"] == "1.7.8,9.1")
    # anti-double-prefix: value sudah punya {project-root} -> template dilewati
    t2 = mod.apply_result_templates(MODYAML, {"psm_modules_dir": "{project-root}/modules"})
    check("value ber-{project-root} tak digandakan", t2["psm_modules_dir"] == "{project-root}/modules")
    # tanpa result field -> passthrough
    t3 = mod.apply_result_templates({"v": {"prompt": "?"}}, {"v": "raw"})
    check("tanpa result -> nilai apa adanya", t3["v"] == "raw")


def test_merge_anti_zombie_and_core():
    answers = {"core": {"user_name": "Budi", "communication_language": "Indonesia",
                        "document_output_language": "English"},
               "module": {"psm_target_versions": "9.1"}}
    # existing punya section psm basi + legacy 'core' section
    existing = {"core": {"output_folder": "{project-root}/out"},
                "psm": {"name": "OLD", "stale_key": "zombie"}}
    cfg = mod.merge_config(existing, MODYAML, answers)
    check("anti-zombie: key basi section module hilang", "stale_key" not in cfg["psm"])
    check("metadata module segar ditulis", cfg["psm"]["name"] == "PSM" and cfg["psm"]["version"] == "2.0")
    check("nilai module ditulis", cfg["psm"]["psm_target_versions"] == "9.1")
    check("legacy 'core' section dimigrasi ke root", "core" not in cfg and cfg["output_folder"] == "{project-root}/out")
    check("core non-user ditulis di root", cfg["document_output_language"] == "English")
    check("user-only key TAK bocor ke config root",
          "user_name" not in cfg and "communication_language" not in cfg)


def test_merge_requires_code():
    check("module.yaml tanpa 'code' -> exit 1", expect_exit(lambda: mod.merge_config({}, {"name": "x"}, {}), 1))


def test_extract_user_settings():
    answers = {"core": {"user_name": "Budi", "communication_language": "Indonesia",
                        "document_output_language": "English"},
               "module": {"secret_key": "s3cr3t", "psm_target_versions": "9.1"}}
    us = mod.extract_user_settings(MODYAML, answers)
    check("user_name masuk user config", us.get("user_name") == "Budi")
    check("comm_lang masuk user config", us.get("communication_language") == "Indonesia")
    check("var user_setting:true masuk user config", us.get("secret_key") == "s3cr3t")
    check("var biasa TAK masuk user config", "psm_target_versions" not in us)
    check("core non-user TAK masuk user config", "document_output_language" not in us)


def test_apply_legacy_defaults():
    answers = {"core": {"user_name": "New"}, "module": {"a": "ans"}}
    m = mod.apply_legacy_defaults(answers, {"user_name": "Old", "document_output_language": "English"},
                                  {"a": "legacy", "b": "legacyB"})
    check("legacy: jawaban menang atas legacy (core)", m["core"]["user_name"] == "New")
    check("legacy: mengisi gap core", m["core"]["document_output_language"] == "English")
    check("legacy: jawaban menang atas legacy (module)", m["module"]["a"] == "ans")
    check("legacy: mengisi gap module", m["module"]["b"] == "legacyB")


def test_extract_module_metadata():
    meta = mod.extract_module_metadata(MODYAML)
    check("metadata: name/description/version/default_selected",
          meta["name"] == "PSM" and meta["description"] == "desc"
          and meta["version"] == "2.0" and meta["default_selected"] is False)


def test_reject_unresolved_paths():
    check("{project-root} di path arg -> exit 1",
          expect_exit(lambda: mod.reject_unresolved_paths([("--x", "{project-root}/foo")]), 1))
    ok = True
    try:
        mod.reject_unresolved_paths([("--x", "/abs/path"), ("--y", None)])
    except SystemExit:
        ok = False
    check("path teresolusi/None -> tak exit", ok)


def main():
    for t in (test_apply_result_templates, test_merge_anti_zombie_and_core, test_merge_requires_code,
              test_extract_user_settings, test_apply_legacy_defaults, test_extract_module_metadata,
              test_reject_unresolved_paths):
        print(f"{t.__name__}:")
        t()
    print("\n" + (f"{len(_fail)} GAGAL" if _fail else "SEMUA TEST LOLOS"))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
