#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Ringkas output mentah profiler (cachegrind Xdebug / JSON Blackfire) -> JSON kompak.

Deterministik: ekstraksi metrik baseline & ukur-ulang harus semetode agar
perbandingan before/after di gerbang performa psm-optimize sah. Yang diekstrak:
- wall_time_ms : total waktu (summary cachegrind, atau wt Blackfire dalam µs)
- memory_kb    : memori (summary cachegrind, atau pmu/mu Blackfire dalam byte)
- sql_count    : jumlah call method query Db* (calls= cachegrind; key sql Blackfire), null bila tak terlacak

Untuk JSON, metrik hanya dibaca dari lokasi dikenal (top-level dan `envelope`;
sql juga `metrics`) — subtree lain (callgraph dsb.) diabaikan. Nilai berbeda di
lebih dari satu lokasi dikenal = ambigu -> exit 2 dengan daftar kandidat, bukan
tebakan diam.

Model tetap memutuskan apakah metrik "membaik" dan trade-off-nya — itu judgment.
Skrip hanya membaca angka.
"""
import argparse
import json
import re
import sys
from pathlib import Path

SQL_NAME_RE = re.compile(r"\bDb\w*(->|::)(executeS?|getRow|getValue|query|insert|update|delete)\b")
FN_RE = re.compile(r"^(c?fn)=\((\d+)\)(?:\s+(.*))?$")
TIME_MS_PER_UNIT = {"10ns": 1e-5, "ns": 1e-6, "us": 1e-3, "µs": 1e-3, "ms": 1.0, "s": 1000.0}


def parse_cachegrind(text):
    """Baca summary: (total per kolom events:) + akumulasi calls= ke method query Db*."""
    events, summary, names = [], None, {}
    sql_calls, pending_callee = 0, None
    for line in text.splitlines():
        if line.startswith("events:"):
            events = line.split(":", 1)[1].split()
        elif line.startswith("summary:"):
            vals = [int(v) for v in line.split(":", 1)[1].split()]
            summary = vals if summary is None else [a + b for a, b in zip(summary, vals)]
        elif line.startswith("calls=") and pending_callee is not None:
            n = int(line.split("=", 1)[1].split()[0])
            if SQL_NAME_RE.search(pending_callee):
                sql_calls += n
            pending_callee = None
        else:
            m = FN_RE.match(line)
            if m:
                kind, fid, name = m.groups()
                if name:
                    names[fid] = name
                if kind == "cfn":
                    pending_callee = names.get(fid, "")
    if summary is None:
        raise ValueError("cachegrind tanpa baris summary:")

    def col(prefix):
        for i, ev in enumerate(events):
            if ev.lower().startswith(prefix):
                return i, ev
        return None, None

    ti, tev = col("time")
    mi, _ = col("memory")
    unit_m = re.search(r"\(([^)]+)\)", tev or "")
    factor = TIME_MS_PER_UNIT.get((unit_m.group(1) if unit_m else "10ns").lower(), 1e-5)
    return {
        "profiler": "xdebug-cachegrind",
        "wall_time_ms": round(summary[ti] * factor, 3) if ti is not None and ti < len(summary) else None,
        "memory_kb": round(summary[mi] / 1024, 1) if mi is not None and mi < len(summary) else None,
        "sql_count": sql_calls if names else None,
    }


def _num_leaves(obj, path=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else str(k)
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                yield p, str(k), v
            else:
                yield from _num_leaves(v, p)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _num_leaves(v, f"{path}[{i}]")


def _known_locations(data):
    """Lokasi metrik yang dikenal: top-level dan envelope. Subtree lain diabaikan."""
    spots = [("", data)]
    env = data.get("envelope")
    if isinstance(env, dict):
        spots.append(("envelope.", env))
    return spots


def _pick(data, key):
    """Ambil key dari lokasi dikenal. >1 nilai berbeda = ambigu -> error, bukan tebakan."""
    cands = [(prefix + key, obj.get(key)) for prefix, obj in _known_locations(data)
             if isinstance(obj.get(key), (int, float)) and not isinstance(obj.get(key), bool)]
    if len({v for _, v in cands}) > 1:
        raise ValueError(f"metrik '{key}' ambigu: " + ", ".join(f"{p}={v}" for p, v in cands))
    return cands[0][1] if cands else None


def parse_blackfire(data):
    """Baca metrik Blackfire dari lokasi dikenal: wt (µs), pmu/mu (byte), *sql*count* di envelope/metrics."""
    if not isinstance(data, dict):
        raise ValueError("JSON bukan objek metrik")
    wall = _pick(data, "wall_time_ms")  # passthrough bila sudah ternormalisasi
    if wall is None:
        wt = _pick(data, "wt")
        wall = round(wt / 1000, 3) if wt is not None else None
    mem = _pick(data, "memory_kb")
    if mem is None:
        b = _pick(data, "pmu")
        b = _pick(data, "mu") if b is None else b
        mem = round(b / 1024, 1) if b is not None else None
    sql = _pick(data, "sql_count")
    if sql is None:
        roots = [("metrics", data.get("metrics"))] + [(p + "metrics", o.get("metrics")) for p, o in _known_locations(data) if p]
        sql_cands = [(path, val) for name, root in roots if isinstance(root, (dict, list))
                     for path, key, val in _num_leaves(root, name)
                     if "sql" in path.lower() and ("count" in key.lower() or "queries" in key.lower())]
        if len({v for _, v in sql_cands}) > 1:
            raise ValueError("sql_count ambigu: " + ", ".join(f"{p}={v}" for p, v in sql_cands))
        sql = sql_cands[0][1] if sql_cands else None
    if wall is None and mem is None:
        raise ValueError("tak ada metrik dikenal di top-level/envelope (wt/pmu/mu atau wall_time_ms/memory_kb)")
    return {
        "profiler": "blackfire-json",
        "wall_time_ms": wall,
        "memory_kb": mem,
        "sql_count": int(sql) if sql is not None else None,
    }


def main():
    ap = argparse.ArgumentParser(description="Ringkas output mentah profiler jadi JSON kompak {wall_time_ms, memory_kb, sql_count} untuk blok baseline / ukur-ulang psm-optimize.")
    ap.add_argument("profile_file", help="File output profiler: cachegrind Xdebug atau JSON Blackfire")
    ap.add_argument("--flow", help="Label alur yang diprofil (mis. 'front home', 'hookDisplayHeader')")
    ap.add_argument("-o", "--output", help="Tulis JSON ke file (default stdout)")
    args = ap.parse_args()

    src = Path(args.profile_file)
    try:
        text = src.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        print(f"error: tak terbaca: {e}", file=sys.stderr)
        return 2

    try:
        stripped = text.lstrip()
        if stripped.startswith(("{", "[")):
            result = parse_blackfire(json.loads(stripped))
        elif "events:" in text and ("fn=" in text or "fl=" in text):
            result = parse_cachegrind(text)
        else:
            raise ValueError("format tak dikenali (bukan cachegrind, bukan JSON)")
    except (ValueError, json.JSONDecodeError) as e:
        print(f"error: {src.name}: {e}", file=sys.stderr)
        return 2

    result = {"source": src.name, "flow": args.flow, **result,
              "note": "Angka, bukan vonis. Model memutuskan membaik/tidaknya & trade-off."}
    out = json.dumps(result, indent=2, ensure_ascii=False)
    (Path(args.output).write_text(out, encoding="utf-8") if args.output else print(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
