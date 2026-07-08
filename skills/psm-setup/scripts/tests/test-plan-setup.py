#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Unit tests for plan-setup.py"""
import importlib.util
import sys
import tempfile
import types
import unittest
from pathlib import Path

import yaml

_spec = importlib.util.spec_from_file_location(
    "plan_setup", Path(__file__).parent.parent / "plan-setup.py"
)
assert _spec is not None and _spec.loader is not None
ps: types.ModuleType = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)  # type: ignore[union-attr]

MODULE_YAML = {
    "code": "psm",
    "name": "PSM",
    "psm_target_versions": {"prompt": "Versions?", "default": "1.7.8,8.1,9.0"},
    "psm_modules_dir": {"prompt": "Modules dir?", "default": "{project-root}/modules"},
    "directories": ["{project-root}/_bmad/psm/memory/tech"],
}


class TestClassifyState(unittest.TestCase):
    def test_fresh(self):
        assert ps.classify_state(False, False) == "fresh"

    def test_fresh_consolidate(self):
        assert ps.classify_state(False, True) == "fresh_consolidate"

    def test_update(self):
        assert ps.classify_state(True, False) == "update"

    def test_legacy_migration(self):
        assert ps.classify_state(True, True) == "legacy_migration"


class TestDefaults(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.module_yaml_path = self.root / "module.yaml"
        self.module_yaml_path.write_text(yaml.dump(MODULE_YAML), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, config=None, legacy=None):
        """Invoke plan-setup's main() by monkeypatching argv, capturing JSON."""
        import io
        import json

        config_path = self.root / "config.yaml"
        if config is not None:
            config_path.write_text(yaml.dump(config), encoding="utf-8")

        argv = [
            "plan-setup.py",
            "--config-path", str(config_path),
            "--module-yaml", str(self.module_yaml_path),
        ]
        if legacy is not None:
            argv += ["--legacy-dir", str(legacy)]

        old_argv, old_stdout = sys.argv, sys.stdout
        sys.argv = argv
        sys.stdout = io.StringIO()
        try:
            ps.main()
            out = sys.stdout.getvalue()
        finally:
            sys.argv, sys.stdout = old_argv, old_stdout
        return json.loads(out)

    def test_fresh_install_reports_core_and_module_defaults(self):
        r = self._run()
        assert r["module_code"] == "psm"
        assert r["install_state"] == "fresh"
        assert r["core_needed"] is True
        core_keys = {d["key"] for d in r["defaults"]["core"]}
        assert core_keys == {"user_name", "communication_language",
                             "document_output_language", "output_folder"}
        module_keys = {d["key"] for d in r["defaults"]["module"]}
        assert module_keys == {"psm_target_versions", "psm_modules_dir"}
        vers = next(d for d in r["defaults"]["module"] if d["key"] == "psm_target_versions")
        assert vers["default"] == "1.7.8,8.1,9.0"

    def test_existing_module_section_is_update(self):
        r = self._run(config={"psm": {"psm_target_versions": "9.0"}, "output_folder": "x"})
        assert r["install_state"] == "update"
        assert r["module_section_present"] is True
        assert r["core_needed"] is False  # core already present

    def test_legacy_value_overrides_module_default(self):
        legacy = self.root / "_bmad"
        (legacy / "psm").mkdir(parents=True)
        (legacy / "psm" / "config.yaml").write_text(
            yaml.dump({"psm_target_versions": "1.7.8"}), encoding="utf-8"
        )
        r = self._run(legacy=legacy)
        assert r["install_state"] == "fresh_consolidate"
        assert r["legacy_configs_found"]
        vers = next(d for d in r["defaults"]["module"] if d["key"] == "psm_target_versions")
        assert vers["default"] == "1.7.8", "legacy value should win over module.yaml default"

    def test_user_setting_target_marked_on_core(self):
        r = self._run()
        by_key = {d["key"]: d for d in r["defaults"]["core"]}
        assert by_key["user_name"]["target"] == "config.user.yaml"
        assert by_key["communication_language"]["target"] == "config.user.yaml"
        assert by_key["output_folder"]["target"] == "config.yaml"


if __name__ == "__main__":
    unittest.main()
