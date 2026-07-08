#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Unit tests for cleanup-legacy.py"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import importlib.util
import types

_spec = importlib.util.spec_from_file_location("cleanup_legacy", Path(__file__).parent.parent / "cleanup-legacy.py")
assert _spec is not None and _spec.loader is not None
cl: types.ModuleType = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cl)  # type: ignore[union-attr]


class TestCleanupLegacy(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.bmad = self.root / "_bmad"
        self.skills = self.root / ".claude" / "skills"
        self.bmad.mkdir(parents=True)
        self.skills.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def _make_legacy_skill(self, module_code: str, skill_name: str):
        skill_dir = self.bmad / module_code / skill_name
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\n", encoding="utf-8")
        return skill_dir

    def _install_skill(self, skill_name: str):
        installed = self.skills / skill_name
        installed.mkdir(parents=True)
        (installed / "SKILL.md").write_text("---\nname: test\n---\n", encoding="utf-8")

    def test_safety_pass_when_skills_installed(self):
        self._make_legacy_skill("psm", "psm-validate")
        self._install_skill("psm-validate")
        verified = cl.verify_skills_installed(
            str(self.bmad), ["psm"], str(self.skills)
        )
        assert "psm-validate" in verified

    def test_safety_fail_when_skill_missing(self):
        self._make_legacy_skill("psm", "psm-validate")
        # Do NOT install the skill
        with self.assertRaises(SystemExit) as ctx:
            cl.verify_skills_installed(str(self.bmad), ["psm"], str(self.skills))
        assert ctx.exception.code == 1

    def test_directories_removed(self):
        self._make_legacy_skill("psm", "psm-scaffold")
        self._install_skill("psm-scaffold")
        removed, _, file_count = cl.cleanup_directories(
            str(self.bmad), ["psm"]
        )
        assert "psm" in removed
        assert not (self.bmad / "psm").exists()
        assert file_count >= 1

    def test_idempotent_missing_dirs_not_error(self):
        # psm dir doesn't exist — should be a no-op, not an error
        removed, _, file_count = cl.cleanup_directories(
            str(self.bmad), ["psm"]
        )
        assert "psm" not in removed
        assert file_count == 0

    def test_dir_without_skills_skips_verification(self):
        # _config dir has no SKILL.md — verify_skills_installed should skip it
        config_dir = self.bmad / "_config"
        config_dir.mkdir()
        (config_dir / "some-file.csv").write_text("data", encoding="utf-8")
        verified = cl.verify_skills_installed(
            str(self.bmad), ["_config"], str(self.skills)
        )
        assert verified == []

    def test_unresolved_token_rejected(self):
        with self.assertRaises(SystemExit) as ctx:
            cl.reject_unresolved_paths([("--bmad-dir", "{project-root}/_bmad")])
        assert ctx.exception.code == 1


if __name__ == "__main__":
    unittest.main()
