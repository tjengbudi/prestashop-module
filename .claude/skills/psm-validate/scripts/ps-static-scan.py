#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Pindai source module PrestaShop terhadap aturan kompatibilitas lintas versi.

Deterministik: input sama -> output sama. Tidak butuh Docker/PHP. Membaca
ruleset dari assets/ps-rules.json (di-embed), mencocokkan regex tiap rule ke
isi file module yang relevan, dan mengeluarkan temuan JSON per versi target.

Ini lapisan akurasi #1 (aturan yang diketahui pasti). Lapisan #2 (PHPStan +
coding standard terhadap PS core asli) ditangani ps-flashlight-run.py.
"""
import argparse
import json
import re
import sys
from pathlib import Path

DEFAULT_RULES = Path(__file__).resolve().parent.parent / "assets" / "ps-rules.json"
SCANNED_SUFFIXES = {".php", ".tpl", ".json", ".yml", ".yaml", ".js", ".html", ".twig"}
RULE_GROUPS = [
    "forbidden_dependencies_ps9", "removed_classes_methods", "removed_hooks",
    "removed_constants", "forbidden_functions", "structure", "smarty",
]


def norm_versions(targets):
    """Petakan versi penuh (1.7.8.11, 8.1, 9.1) ke major key (1.7, 8, 9)."""
    out = []
    for t in targets:
        t = t.strip()
        if t.startswith("1.7"):
            out.append((t, "1.7"))
        else:
            out.append((t, t.split(".")[0]))
    return out


def find_main_file(module_dir):
    """Main module file = <modulename>.php di root (konvensi PrestaShop)."""
    cand = module_dir / f"{module_dir.name}.php"
    if cand.is_file():
        return cand
    php_root = [p for p in module_dir.glob("*.php") if p.name != "index.php"]
    return php_root[0] if len(php_root) == 1 else None


def iter_files(module_dir, glob_filters):
    if glob_filters and "__MAIN__" not in glob_filters:
        seen = set()
        for g in glob_filters:
            for p in module_dir.rglob(g):
                if p.is_file() and p not in seen:
                    seen.add(p)
                    yield p
        return
    for p in module_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in SCANNED_SUFFIXES and "vendor/" not in str(p.relative_to(module_dir)):
            yield p


def scan_pattern_rule(rule, module_dir, main_file):
    """Rule berbasis regex -> daftar temuan {file, line, snippet}."""
    findings = []
    # Hook muncul dua bentuk: registerHook('actionFoo') & method hookActionFoo() —
    # cocokkan case-insensitive agar keduanya tertangkap.
    flags = re.IGNORECASE if rule["kind"] == "hook" else 0
    pattern = re.compile(rule["pattern"], flags)
    negate = re.compile(rule["negate_pattern"]) if rule.get("negate_pattern") else None
    files = [main_file] if rule.get("files") == ["__MAIN__"] else iter_files(module_dir, rule.get("files"))
    for fpath in files:
        if not fpath:
            continue
        try:
            text = fpath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if pattern.search(line) and not (negate and negate.search(line)):
                findings.append({
                    "file": str(fpath.relative_to(module_dir)),
                    "line": i,
                    "snippet": line.strip()[:160],
                })
    return findings


def scan_structure_rule(rule, module_dir, main_file, target_ver=None):
    """Rule struktural: ps_versions_compliancy ada & mencakup target, index.php tiap folder, composer prepend-autoloader."""
    expect = rule.get("expect")
    if expect == "present":
        if not main_file:
            return [{"file": "(main module file)", "line": 0, "snippet": "main module file tak ditemukan"}]
        text = main_file.read_text(encoding="utf-8", errors="replace")
        if not re.search(rule["pattern"], text):
            return [{"file": str(main_file.relative_to(module_dir)), "line": 0, "snippet": "ps_versions_compliancy tak ditemukan"}]
        return []
    if expect == "index_php_each_dir":
        missing = []
        for d in [module_dir, *[p for p in module_dir.rglob("*") if p.is_dir() and "vendor" not in p.parts]]:
            if not (d / "index.php").is_file():
                missing.append({"file": str(d.relative_to(module_dir)) or ".", "line": 0, "snippet": "index.php tidak ada di folder ini"})
        return missing
    if expect == "composer_prepend_autoloader_false":
        composer = module_dir / "composer.json"
        if not composer.is_file():
            return []  # tanpa composer.json tak ada autoloader yang bisa prepend
        try:
            cfg = json.loads(composer.read_text(encoding="utf-8", errors="replace"))
        except json.JSONDecodeError:
            cfg = None
        if not isinstance(cfg, dict):
            return [{"file": "composer.json", "line": 0, "snippet": "composer.json bukan JSON object valid"}]
        conf = cfg.get("config")
        if not isinstance(conf, dict) or conf.get("prepend-autoloader") is not False:
            return [{"file": "composer.json", "line": 0, "snippet": "config.prepend-autoloader bukan false"}]
        return []
    if expect == "compliancy_covers_target":
        if not main_file or not target_ver:
            return []
        text = main_file.read_text(encoding="utf-8", errors="replace")
        m = re.search(r"ps_versions_compliancy\s*=\s*(?:\[|array\s*\()(.*?)(?:\]|\))", text, re.S)
        if not m:
            return []  # ketiadaan compliancy sudah urusan struct-compliancy
        body = m.group(1)
        mmin = re.search(r"['\"]min['\"]\s*=>\s*['\"]([0-9.]+)['\"]", body)
        mmax = re.search(r"['\"]max['\"]\s*=>\s*(_PS_VERSION_|['\"]([0-9.]+)['\"])", body)

        def vtup(s):
            return tuple(int(x) for x in s.split(".") if x)

        hits = []
        rel = str(main_file.relative_to(module_dir))
        try:
            if mmin and vtup(mmin.group(1)) > vtup(target_ver):
                hits.append({"file": rel, "line": 0, "snippet": f"min {mmin.group(1)} > versi target {target_ver}"})
            if mmax and mmax.group(1) != "_PS_VERSION_" and vtup(mmax.group(2)) < vtup(target_ver):
                hits.append({"file": rel, "line": 0, "snippet": f"max {mmax.group(2)} < versi target {target_ver}"})
        except ValueError:
            hits.append({"file": rel, "line": 0, "snippet": "min/max compliancy tak terbaca (bukan angka)"})
        return hits
    return []


def main():
    ap = argparse.ArgumentParser(description="Pindai module PrestaShop terhadap aturan kompatibilitas lintas versi.")
    ap.add_argument("module_path", help="Path folder module PrestaShop")
    ap.add_argument("--versions", default="1.7.8,8.1,9.1", help="Versi target dipisah koma (default: 1.7.8,8.1,9.1)")
    ap.add_argument("--rules", default=str(DEFAULT_RULES), help="Path ps-rules.json (default: assets/ps-rules.json)")
    ap.add_argument("--extra-rules", help="Path JSON aturan TAMBAHAN (skema sama ps-rules.json) — "
                                          "di-merge ke ruleset; --rules MENGGANTI, ini MENAMBAH. "
                                          "Untuk aturan dari knowledge base tanpa menyalin ruleset inti.")
    ap.add_argument("-o", "--output", help="File output JSON (default: stdout)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    module_dir = Path(args.module_path).resolve()
    if not module_dir.is_dir():
        print(f"error: bukan folder: {module_dir}", file=sys.stderr)
        return 2
    try:
        rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: gagal baca ruleset: {e}", file=sys.stderr)
        return 2
    if args.extra_rules:
        try:
            extra = json.loads(Path(args.extra_rules).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"error: gagal baca extra-rules: {e}", file=sys.stderr)
            return 2
        for grp in RULE_GROUPS:
            rules.setdefault(grp, []).extend(extra.get(grp, []))

    main_file = find_main_file(module_dir)
    if args.verbose:
        print(f"module={module_dir.name} main_file={main_file}", file=sys.stderr)

    all_rules = []
    for grp in RULE_GROUPS:
        all_rules.extend(rules.get(grp, []))

    versions = norm_versions(args.versions.split(","))
    result = {"module": module_dir.name, "module_path": str(module_dir), "main_file_found": main_file is not None, "versions": {}}
    overall_errors = 0

    for full_ver, major in versions:
        v_findings = []
        for rule in all_rules:
            if major not in rule.get("affects", []):
                continue
            if rule["kind"] in ("structure", "compliancy"):
                hits = scan_structure_rule(rule, module_dir, main_file, full_ver)
            else:
                hits = scan_pattern_rule(rule, module_dir, main_file)
            if hits:
                v_findings.append({
                    "id": rule["id"], "severity": rule["severity"], "kind": rule["kind"],
                    "message": rule["message"], "fix": rule.get("fix", ""),
                    "occurrences": hits, "count": len(hits),
                })
        errs = sum(1 for f in v_findings if f["severity"] == "error")
        warns = sum(1 for f in v_findings if f["severity"] == "warning")
        overall_errors += errs
        result["versions"][full_ver] = {
            "major": major, "errors": errs, "warnings": warns,
            "pass": errs == 0, "findings": v_findings,
        }

    result["pass"] = overall_errors == 0
    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"ditulis: {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
