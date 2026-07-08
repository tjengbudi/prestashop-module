#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Test init-kb.py: scaffolding lengkap, idempoten, tak menimpa isi."""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "init-kb.py"


def run(root, *extra):
    r = subprocess.run(
        ["uv", "run", str(SCRIPT), str(root), *extra],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "memory"

        # First run: builds full tree (9 tech + 1 ecommerce), everything needs seed.
        first = run(root)
        assert first["status"] == "ok"
        assert len(first["created_files"]) == 10, first["created_files"]
        assert len(first["needs_seed"]) == 10
        assert (root / "tech" / "hooks.md").exists()
        assert (root / "ecommerce" / "function-catalog.md").exists()
        assert (root / "projects").is_dir()

        # Curator seeds one file with real content that MENTIONS the word STUB —
        # must not be re-flagged (marker-line match, not bare substring).
        seeded = root / "tech" / "hooks.md"
        seeded.write_text("# hooks\n\nactionFrontControllerSetMedia jalan di 1.7/8/9. Hindari STUB kosong.\n")

        # Second run: idempotent — nothing recreated, seeded file preserved.
        second = run(root)
        assert len(second["created_files"]) == 0, second["created_files"]
        assert len(second["existing_files"]) == 10
        assert "tech/hooks.md" not in second["needs_seed"], "seeded file (even mentioning STUB) must not be re-flagged"
        assert seeded.read_text().startswith("# hooks\n\nactionFront"), "content preserved"

        # Dry-run touches nothing new.
        with tempfile.TemporaryDirectory() as tmp2:
            dry = run(Path(tmp2) / "m", "--dry-run")
            assert dry["dry_run"] is True
            assert not (Path(tmp2) / "m").exists(), "dry-run must not write"

    print("PASS test-init-kb")
    return 0


if __name__ == "__main__":
    sys.exit(main())
