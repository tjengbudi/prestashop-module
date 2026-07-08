#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Test check-env.py: degrade jujur saat Docker absent, output JSON valid, exit 0."""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "check-env.py"


def main():
    # Force docker-absent: PATH points at an empty dir so shutil.which('docker')
    # fails, while we invoke the script via the absolute interpreter path (no
    # PATH lookup needed to launch it).
    with tempfile.TemporaryDirectory() as empty:
        env = dict(os.environ)
        env["PATH"] = empty
        r = subprocess.run(
            [sys.executable, str(SCRIPT)],
            capture_output=True,
            text=True,
            env=env,
        )

    # Exit 0 even when Docker absent — absence is a reported state, not an error.
    assert r.returncode == 0, f"exit {r.returncode}: {r.stderr}"

    out = json.loads(r.stdout)
    assert out["ready"] is False, out
    assert out["docker"]["available"] is False, out
    assert out["flashlight_image"]["present"] is False, out
    assert out["flashlight_image"]["name"] == "prestashop/prestashop-flashlight"
    assert "docker belum siap" in out["action_hint"], out

    print("PASS test-check-env")
    return 0


if __name__ == "__main__":
    sys.exit(main())
