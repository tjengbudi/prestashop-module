#!/usr/bin/env python3
"""Tests for skill_files.py — the one definition of skill content vs build artifact.

Covers the dot-component rule, the paths that must stay INSIDE the scan (so the fix cannot
silently blind the scanner), the out-of-tree guard, and the two scanners that consume it —
scan-path-standards and prepass-prompt-metrics — driven end-to-end over a fixture skill that
carries the artifacts this exists to exclude. Run: python3 test_skill_files.py
"""
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
SCRIPT = SCRIPTS / "skill_files.py"

_failures = []


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    if not cond:
        _failures.append(name)
    return cond


def _load():
    spec = importlib.util.spec_from_file_location("skill_files", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fixture(root):
    """A skill carrying exactly the artifacts that made the scanner read its own output."""
    (root / "references").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "assets").mkdir()
    (root / "SKILL.md").write_text("---\nname: fix\ndescription: d\n---\n\n# fix\n")
    (root / "references" / "lens.md").write_text("# lens\n")
    (root / "assets" / "rules.json").write_text("{}")
    (root / "scripts" / "tool.py").write_text("#!/usr/bin/env python3\n")
    # build artifacts — the things being excluded
    (root / ".memlog.md").write_text("- (note) build history\n")
    run = root / ".analysis" / "2026-07-17-1024"
    run.mkdir(parents=True)
    (run / "findings.json").write_text(json.dumps({"findings": []}))
    (run / "skill-analysis-report.md").write_text("# report\n")
    (run / "lint-paths.json").write_text(json.dumps({"findings": []}))
    return root


def main():
    mod = _load()

    with tempfile.TemporaryDirectory() as td:
        root = _fixture(Path(td) / "myskill")

        # The rule: any dot-prefixed component, relative to the skill root.
        check("`.memlog.md` at root is a build artifact",
              mod.is_build_artifact(root / ".memlog.md", root) is True)
        check("anything under `.analysis/` is a build artifact",
              mod.is_build_artifact(root / ".analysis" / "2026-07-17-1024" / "findings.json", root) is True)
        check("a dated run folder itself is a build artifact",
              mod.is_build_artifact(root / ".analysis" / "2026-07-17-1024", root) is True)

        # Just as important: the fix must not blind the scanner to real content.
        for keep in ("SKILL.md", "references/lens.md", "assets/rules.json", "scripts/tool.py"):
            check(f"`{keep}` is skill content, not an artifact",
                  mod.is_build_artifact(root / keep, root) is False)

        # A path outside the skill is not this skill's artifact — say so, do not guess.
        check("path outside the skill root -> not an artifact (no guessing)",
              mod.is_build_artifact(Path(td) / "elsewhere" / ".analysis" / "x.json", root) is False)

        files = mod.skill_files(root, ("*.md", "*.json"))
        names = sorted(str(p.relative_to(root)) for p in files)
        check("skill_files returns content only, artifacts dropped",
              names == ["SKILL.md", "assets/rules.json", "references/lens.md"])
        check("skill_files finds no .analysis or .memlog entry",
              not any(".analysis" in n or ".memlog" in n for n in names))

        # --- consumers, end-to-end: the scanners must actually stop reading themselves ---
        r = subprocess.run(["uv", "run", str(SCRIPTS / "scan-path-standards.py"), str(root)],
                           capture_output=True, text=True)
        out = json.loads(r.stdout)
        scanned = out.get("files_scanned", [])
        check("scan-path-standards scans content only",
              sorted(scanned) == ["SKILL.md", "assets/rules.json", "references/lens.md"])
        check("scan-path-standards reports no findings from its own prior reports",
              not any(f["file"].startswith(".analysis") for f in out["findings"]))
        # `.memlog.md` must live at the root; telling every round to move it to references/
        # was advice that would break resume.
        check("`.memlog.md` at root is not reported as a misplaced prompt file",
              not any(f["file"] == ".memlog.md" for f in out["findings"]))

        r = subprocess.run(["uv", "run", str(SCRIPTS / "prepass-prompt-metrics.py"), str(root)],
                           capture_output=True, text=True)
        met = json.loads(r.stdout)
        check("prepass-prompt-metrics measures SKILL.md, not the build history beside it",
              [f["file"] for f in met["files"]] == ["SKILL.md"])

    print("\n" + ("SEMUA TEST LOLOS" if not _failures else f"GAGAL: {_failures}"))
    return 0 if not _failures else 1


if __name__ == "__main__":
    sys.exit(main())
