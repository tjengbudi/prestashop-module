#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Unit tests for merge-config.py"""
import sys
import tempfile
import unittest
from pathlib import Path

# Add scripts/ to path
sys.path.insert(0, str(Path(__file__).parent.parent))
import importlib.util
import types

_spec = importlib.util.spec_from_file_location("merge_config", Path(__file__).parent.parent / "merge-config.py")
assert _spec is not None and _spec.loader is not None
mc: types.ModuleType = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mc)  # type: ignore[union-attr]

MINIMAL_MODULE_YAML = {
    "code": "psm",
    "name": "PSM",
    "psm_target_versions": {"prompt": "Versions?", "default": "1.7.8,8.1,9.0"},
}


class TestMergeConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.config_path = self.root / "config.yaml"
        self.user_config_path = self.root / "config.user.yaml"

    def tearDown(self):
        self.tmp.cleanup()

    def _answers(self, core=None, module=None):
        a = {}
        if core:
            a["core"] = core
        if module:
            a["module"] = module
        return a

    def test_fresh_install_writes_both_files(self):
        answers = self._answers(
            core={"user_name": "Budi", "communication_language": "indonesian",
                  "document_output_language": "English", "output_folder": "{project-root}/_bmad-output"},
            module={"psm_target_versions": "1.7.8,8.1,9.0"},
        )
        updated = mc.merge_config({}, MINIMAL_MODULE_YAML, answers)
        mc.write_config(updated, str(self.config_path))
        user_settings = mc.extract_user_settings(MINIMAL_MODULE_YAML, answers)
        mc.write_config(user_settings, str(self.user_config_path))

        assert self.config_path.exists(), "config.yaml should be created"
        assert self.user_config_path.exists(), "config.user.yaml should be created"

    def test_update_preserves_other_module_sections(self):
        existing = {"other_module": {"key": "value"}, "output_folder": "{project-root}/_bmad-output"}
        answers = self._answers(module={"psm_target_versions": "1.7.8,8.1,9.0"})
        updated = mc.merge_config(existing, MINIMAL_MODULE_YAML, answers)
        assert "other_module" in updated, "Other module section should be preserved"
        assert "psm" in updated, "New module section should be written"

    def test_anti_zombie_removes_stale_section(self):
        existing = {"psm": {"psm_target_versions": "old_value", "stale_key": "stale"}}
        answers = self._answers(module={"psm_target_versions": "1.7.8,8.1,9.0"})
        updated = mc.merge_config(existing, MINIMAL_MODULE_YAML, answers)
        assert "stale_key" not in updated.get("psm", {}), "Stale keys should be removed by anti-zombie"
        assert updated["psm"]["psm_target_versions"] == "1.7.8,8.1,9.0"

    def test_user_keys_go_to_user_config_only(self):
        answers = self._answers(
            core={"user_name": "Budi", "communication_language": "indonesian",
                  "output_folder": "{project-root}/_bmad-output"},
        )
        updated = mc.merge_config({}, MINIMAL_MODULE_YAML, answers)
        assert "user_name" not in updated, "user_name must not appear in config.yaml"
        assert "communication_language" not in updated, "communication_language must not appear in config.yaml"
        user_settings = mc.extract_user_settings(MINIMAL_MODULE_YAML, answers)
        assert "user_name" in user_settings
        assert "communication_language" in user_settings

    def test_legacy_defaults_applied_then_deletable(self):
        legacy_dir = self.root / "_bmad_legacy"
        (legacy_dir / "core").mkdir(parents=True)
        (legacy_dir / "psm").mkdir(parents=True)
        import yaml
        (legacy_dir / "core" / "config.yaml").write_text(
            yaml.dump({"output_folder": "{project-root}/old-output"}), encoding="utf-8"
        )
        (legacy_dir / "psm" / "config.yaml").write_text(
            yaml.dump({"psm_target_versions": "1.7.8,8.1"}), encoding="utf-8"
        )
        legacy_core, legacy_module, _ = mc.load_legacy_values(
            str(legacy_dir), "psm", MINIMAL_MODULE_YAML
        )
        assert legacy_core.get("output_folder") == "{project-root}/old-output"
        assert legacy_module.get("psm_target_versions") == "1.7.8,8.1"
        deleted = mc.cleanup_legacy_configs(str(legacy_dir), "psm")
        assert len(deleted) == 2
        assert not (legacy_dir / "psm" / "config.yaml").exists()
        assert not (legacy_dir / "core" / "config.yaml").exists()

    def test_unresolved_token_rejected(self):
        with self.assertRaises(SystemExit) as ctx:
            mc.reject_unresolved_paths([("--config-path", "{project-root}/_bmad/config.yaml")])
        assert ctx.exception.code == 1

    def test_collect_output_dirs_gathers_path_values(self):
        module_yaml = {
            "code": "psm",
            "directories": ["{project-root}/_bmad/psm/memory/tech"],
        }
        config = {
            "output_folder": "{project-root}/_bmad-output",
            "document_output_language": "English",  # non-path, ignored
            "psm": {
                "psm_modules_dir": "{project-root}/modules",
                "psm_target_versions": "1.7.8,8.1",  # non-path, ignored
            },
        }
        dirs = mc.collect_output_dirs(config, "psm", module_yaml)
        assert "{project-root}/_bmad-output" in dirs
        assert "{project-root}/modules" in dirs
        assert "{project-root}/_bmad/psm/memory/tech" in dirs
        assert "1.7.8,8.1" not in dirs
        assert "English" not in dirs
        assert len(dirs) == len(set(dirs)), "dirs should be deduped"

    def test_create_output_dirs_resolves_and_makes(self):
        dirs = ["{project-root}/_bmad-output", "{project-root}/modules"]
        created = mc.create_output_dirs(dirs, str(self.root))
        assert (self.root / "_bmad-output").is_dir()
        assert (self.root / "modules").is_dir()
        assert str(self.root / "_bmad-output") in created
        # Idempotent: running again does not raise
        mc.create_output_dirs(dirs, str(self.root))


if __name__ == "__main__":
    unittest.main()
