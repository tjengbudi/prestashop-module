#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test ps-profile-summary.py. Jalankan: uv run scripts/tests/test-ps-profile-summary.py"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SUMMARY = Path(__file__).resolve().parent.parent / "ps-profile-summary.py"

CACHEGRIND = """version: 1
creator: xdebug 3.2.0
cmd: /var/www/html/index.php
part: 1
positions: line

events: Time_(10ns) Memory_(bytes)

fl=(1) /var/www/html/classes/db/Db.php
fn=(1) DbPDOCore::executeS
123 5000 1024

fl=(2) /var/www/html/modules/hotmod/hotmod.php
fn=(2) Hotmod->hookDisplayHeader
45 200000 4096
cfl=(1)
cfn=(1)
calls=12 123
45 60000 0

fn=(3) {main}
1 100 0
cfl=(2)
cfn=(2)
calls=1 45
1 900000 0

summary: 150000000 8388608
"""

BLACKFIRE = '{"envelope": {"wt": 250000, "pmu": 4194304, "metrics": {"sql": {"queries_count": 7}}}}'

# callgraph berisi wt/mu per-node — harus DIABAIKAN, envelope yang dibaca
BLACKFIRE_GRAPH = ('{"graph": {"main()": {"wt": 12, "mu": 512}, "Db::executeS": {"wt": 8}},'
                   ' "envelope": {"wt": 250000, "pmu": 4194304}}')

# nilai wt berbeda di dua lokasi dikenal — ambigu, harus error bukan menebak
BLACKFIRE_CONFLICT = '{"wt": 999, "envelope": {"wt": 250000, "pmu": 4194304}}'


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    return cond


def run(*argv):
    return subprocess.run(["uv", "run", str(SUMMARY), *argv], capture_output=True, text=True)


def main():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        cg = Path(td) / "cachegrind.out.1"
        cg.write_text(CACHEGRIND)
        bf = Path(td) / "blackfire.json"
        bf.write_text(BLACKFIRE)
        junk = Path(td) / "junk.txt"
        junk.write_text("bukan output profiler\n")

        p = run(str(cg), "--flow", "front home")
        d = json.loads(p.stdout)
        ok &= check("cachegrind rc=0", p.returncode == 0)
        ok &= check("cachegrind terdeteksi", d["profiler"] == "xdebug-cachegrind")
        ok &= check("wall_time 150000000*10ns = 1500ms", d["wall_time_ms"] == 1500.0)
        ok &= check("memory 8388608B = 8192kb", d["memory_kb"] == 8192.0)
        ok &= check("sql_count dari calls= (12), cfn tanpa nama ikut", d["sql_count"] == 12)
        ok &= check("label --flow diteruskan", d["flow"] == "front home")

        p2 = run(str(bf))
        d2 = json.loads(p2.stdout)
        ok &= check("blackfire rc=0", p2.returncode == 0)
        ok &= check("blackfire terdeteksi", d2["profiler"] == "blackfire-json")
        ok &= check("wt 250000us = 250ms", d2["wall_time_ms"] == 250.0)
        ok &= check("pmu 4194304B = 4096kb", d2["memory_kb"] == 4096.0)
        ok &= check("sql queries_count = 7", d2["sql_count"] == 7)

        gr = Path(td) / "blackfire-graph.json"
        gr.write_text(BLACKFIRE_GRAPH)
        pg = run(str(gr))
        dg = json.loads(pg.stdout)
        ok &= check("callgraph diabaikan, envelope dibaca (250ms)", pg.returncode == 0 and dg["wall_time_ms"] == 250.0)
        ok &= check("callgraph: sql_count null (tak dihitung dari graph)", dg["sql_count"] is None)

        cf = Path(td) / "blackfire-conflict.json"
        cf.write_text(BLACKFIRE_CONFLICT)
        pc = run(str(cf))
        ok &= check("wt konflik dua lokasi -> rc=2 ambigu", pc.returncode == 2 and "ambigu" in pc.stderr)

        p3 = run(str(junk))
        ok &= check("format tak dikenali -> rc=2", p3.returncode == 2)
        ok &= check("error ke stderr, stdout kosong", "error" in p3.stderr and not p3.stdout.strip())

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
