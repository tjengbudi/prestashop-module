#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Unit tests for merge-help-csv.py"""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import importlib.util
import types

_spec = importlib.util.spec_from_file_location("merge_help_csv", Path(__file__).parent.parent / "merge-help-csv.py")
assert _spec is not None and _spec.loader is not None
mhc: types.ModuleType = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mhc)  # type: ignore[union-attr]

HEADER = ["module", "skill", "display-name", "menu-code", "description",
          "action", "args", "phase", "after", "before", "required", "output-location", "outputs"]

SOURCE_ROWS = [
    ["psm", "psm-scaffold", "Scaffold Module", "SC", "Create new PS module", "", "", "anytime", "", "", "false", "", ""],
    ["psm", "psm-validate", "Validate Module", "VA", "Validate PS module", "", "", "anytime", "", "", "false", "", ""],
]


def _write_csv(path: Path, header, rows):
    import csv
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        for row in rows:
            w.writerow(row)


class TestMergeHelpCsv(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.source = self.root / "source.csv"
        self.target = self.root / "module-help.csv"
        _write_csv(self.source, HEADER, SOURCE_ROWS)

    def tearDown(self):
        self.tmp.cleanup()

    def test_fresh_merge_adds_rows(self):
        mhc.write_csv(str(self.target), HEADER,
                      mhc.filter_rows([], "psm") + SOURCE_ROWS)
        _, rows = mhc.read_csv_rows(str(self.target))
        assert len(rows) == 2

    def test_rerun_replaces_rows_anti_zombie(self):
        # First merge
        mhc.write_csv(str(self.target), HEADER, SOURCE_ROWS)
        # Add an unrelated row
        other_row = ["other", "other-skill", "Other", "OT", "", "", "", "anytime", "", "", "false", "", ""]
        _, existing_rows = mhc.read_csv_rows(str(self.target))
        mhc.write_csv(str(self.target), HEADER, existing_rows + [other_row])
        # Second merge (anti-zombie should remove psm rows, re-add fresh)
        _, current_rows = mhc.read_csv_rows(str(self.target))
        filtered = mhc.filter_rows(current_rows, "psm")
        merged = filtered + SOURCE_ROWS
        mhc.write_csv(str(self.target), HEADER, merged)
        _, final_rows = mhc.read_csv_rows(str(self.target))
        psm_rows = [r for r in final_rows if r and r[0] == "psm"]
        other_rows = [r for r in final_rows if r and r[0] == "other"]
        assert len(psm_rows) == 2, "Should have exactly the fresh psm rows"
        assert len(other_rows) == 1, "Other module rows should be preserved"

    def test_legacy_csv_deleted_after_merge(self):
        legacy_dir = self.root / "_bmad"
        (legacy_dir / "psm").mkdir(parents=True)
        (legacy_dir / "core").mkdir(parents=True)
        legacy_psm = legacy_dir / "psm" / "module-help.csv"
        legacy_core = legacy_dir / "core" / "module-help.csv"
        _write_csv(legacy_psm, HEADER, SOURCE_ROWS)
        _write_csv(legacy_core, HEADER, [])
        deleted = mhc.cleanup_legacy_csvs(str(legacy_dir), "psm")
        assert not legacy_psm.exists()
        assert not legacy_core.exists()
        assert len(deleted) == 2

    def test_unresolved_token_rejected(self):
        with self.assertRaises(SystemExit) as ctx:
            mhc.reject_unresolved_paths([("--target", "{project-root}/_bmad/module-help.csv")])
        assert ctx.exception.code == 1


if __name__ == "__main__":
    unittest.main()
