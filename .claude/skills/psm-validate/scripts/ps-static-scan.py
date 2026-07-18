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
# Folder yang bukan source module. Satu definisi, dipakai-ulang ps-plan-layers.py.
SKIP_DIRS = {"vendor", "node_modules", ".git"}


def is_skipped(path, module_dir):
    """True bila `path` ada DI DALAM folder yang dilewati, RELATIF ke module.

    Komponen relatif, bukan substring & bukan path absolut: substring membuang
    `myvendor/thing.php` (tak pernah dipindai, diam-diam), sedangkan mencocokkan
    path absolut membuang SELURUH module yang kebetulan berada di bawah ancestor
    bernama vendor/ — dua-duanya gagal ke arah yang tak aman.
    """
    try:
        parts = set(Path(path).relative_to(module_dir).parts)
    except ValueError:
        return False
    return bool(SKIP_DIRS & parts)
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


def _extends_module(path):
    """True bila file PHP ini mendeklarasikan class turunan Module."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return re.search(r"extends\s+Module\b", text) is not None


def find_main_file(module_dir):
    """Main module file + alasan bila tak ketemu. Return (path|None, reason|None).

    Konvensi PrestaShop: <namafolder>.php. Bila tak ada, jangan langsung menyerah —
    pilih root .php yang isinya `extends Module`. Penyempitan itu deterministik dan
    menyelesaikan kasus paling lumrah tanpa judgment: folder hasil clone/unzip sering
    bernama mymod-master sementara file utamanya tetap mymod.php.

    Alasannya DIBEDAKAN karena konsumennya beda. `no_php_at_root` = memang bukan module
    PrestaShop; itu satu-satunya yang layak menghentikan run. `ambiguous_main_file` =
    ada kandidat tapi skrip tak bisa memilih — pertanyaan makna, wilayah model. Dulu
    keduanya dilebur jadi `main_file_found: false` yang menghentikan run, jadi module
    nyata yang namanya tak cocok divonis "bukan module PrestaShop".
    """
    cand = module_dir / f"{module_dir.name}.php"
    if cand.is_file():
        return cand, None
    php_root = [p for p in module_dir.glob("*.php") if p.name != "index.php"]
    if not php_root:
        return None, "no_php_at_root"
    if len(php_root) == 1:
        return php_root[0], None
    extends = [p for p in php_root if _extends_module(p)]
    if len(extends) == 1:
        return extends[0], None
    return None, "ambiguous_main_file"


def ruleset_provenance(paths):
    """Jejak ruleset yang MEMPRODUKSI vonis ini: daftar file + mtime termuda.

    Vonis Lapis 1 punya DUA input — source module DAN ruleset — tapi pra-pass kesegaran
    dulu hanya men-stat yang pertama. Akibatnya aturan knowledge-base yang baru ditambahkan
    tak pernah menyala: file lapis lama dinilai "lebih baru dari module" lalu dipakai ulang
    dan melaporkan pass, sementara SKILL.md justru melarang model menilai kesegaran sendiri.
    Dicatat di output supaya reuse diputuskan dari yang DIAKUI file itu, bukan diturunkan
    ulang oleh pembacanya.
    """
    files = sorted(str(Path(p).resolve()) for p in paths if p)
    newest = 0.0
    for f in files:
        try:
            newest = max(newest, Path(f).stat().st_mtime)
        except OSError:
            pass
    return {"files": files, "mtime": newest}


def iter_files(module_dir, glob_filters):
    # Cabang glob (`files: ["*.php"]`, jalur yang dipakai aturan knowledge-base) dulu TAK
    # menyaring sama sekali: satu `eval(` di vendor/ pihak-ketiga memblok module yang
    # source-nya bersih. Skip dipakai di KEDUA cabang — satu definisi, is_skipped.
    if glob_filters and "__MAIN__" not in glob_filters:
        seen = set()
        for g in glob_filters:
            for p in module_dir.rglob(g):
                if p.is_file() and p not in seen and not is_skipped(p, module_dir):
                    seen.add(p)
                    yield p
        return
    for p in module_dir.rglob("*"):
        if p.is_file() and p.suffix.lower() in SCANNED_SUFFIXES and not is_skipped(p, module_dir):
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
        # `"vendor" not in p.parts` (path ABSOLUT, buta node_modules/.git) adalah
        # implementasi KETIGA dari "folder mana yang bukan source module" — is_skipped
        # sudah memilikinya, relatif ke module.
        for d in [module_dir, *[p for p in module_dir.rglob("*")
                                if p.is_dir() and not is_skipped(p, module_dir)]]:
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


STRUCT_EXPECTS = {"present", "index_php_each_dir", "composer_prepend_autoloader_false",
                  "compliancy_covers_target"}
# Domain `affects`: major key yang dihasilkan norm_versions — bukan versi penuh.
# Ditegakkan di sini DAN didokumentasikan di ps-rules.json _meta.schema.
MAJOR_KEYS = ("1.7", "8", "9")


def _check_regex(notes, rid, field, value):
    """Field regex harus string DAN compile. Non-string bikin re.compile lempar
    TypeError (bukan re.error) — kalau tak dijaga, validator sendiri yang meledak."""
    if not isinstance(value, str):
        notes.append(f"{rid}: '{field}' bertipe {type(value).__name__}, harus string")
        return
    try:
        re.compile(value)
    except re.error as e:
        notes.append(f"{rid}: '{field}' bukan regex valid ({e})")


def validate_extra_rules(extra, label="extra-rules"):
    """Validasi ruleset buatan model. Return list pelanggaran (kosong = lolos).

    Dipakai KEDUA kanal ruleset, bukan cuma `--extra-rules`. Dulu hanya kanal MENAMBAH yang
    digerbang sementara `--rules` (MENGGANTI) dimuat mentah — jadi rule yang tak akan pernah
    menyala (affects [9] angka, affects absen/kosong, severity di luar enum) lolos diam-diam
    lewat flag di sebelahnya, dan module ber-eval() dinyatakan `ready` atas ruleset yang tak
    pernah menyentuhnya. Gerbangnya sudah menangkap semua bentuk itu; ia cuma tak dipasang
    di seam yang satunya — bentuk kelalaian yang sama dengan yang dijaga fungsi ini.

    Menjaga TIPE tiap field yang benar-benar disentuh kode pindai — bukan sekadar
    keberadaannya. Tanpa itu aturan tambahan gagal DIAM-DIAM (grup salah-nama -> 0
    rule di-merge, sementara prompt dilarang memindai dengan tangan) atau meledak
    KeyError/TypeError -> exit 1 = kode "module punya error". Pelanggaran = input
    rusak (exit 2), supaya exit 1 tetap berarti satu hal saja: module bermasalah.
    """
    notes = []
    if not isinstance(extra, dict):
        return [f"{label} bukan JSON object — bentuk: {{\"<grup>\": [ {{rule}}, ... ]}}"]
    unknown = [g for g in extra if g not in RULE_GROUPS and g != "_meta"]
    if unknown:
        notes.append(f"grup tak dikenal (rule-nya TAK akan dipakai): {', '.join(sorted(unknown))}"
                     f" — grup sah: {', '.join(RULE_GROUPS)}")
    for grp in RULE_GROUPS:
        items = extra.get(grp, [])
        if not isinstance(items, list):
            notes.append(f"{grp}: bertipe {type(items).__name__}, harus list")
            continue
        for i, r in enumerate(items):
            rid = r.get("id", f"{grp}[{i}]") if isinstance(r, dict) else f"{grp}[{i}]"
            if not isinstance(r, dict):
                notes.append(f"{rid}: bertipe {type(r).__name__}, harus object")
                continue
            missing = [k for k in ("id", "severity", "kind", "message", "affects") if k not in r]
            if missing:
                notes.append(f"{rid}: field wajib hilang: {', '.join(missing)}")
            if r.get("severity") not in ("error", "warning"):
                notes.append(f"{rid}: severity '{r.get('severity')}' di luar enum error|warning")
            # Tipe ELEMEN, bukan cuma container: 'affects': [9] (angka JSON tanpa kutip)
            # lolos cek list lalu rule-nya DIAM-DIAM tak pernah menyala ('9' not in [9]),
            # dan 'files': [123] meledak TypeError di rglob -> exit 1 = kode "module error".
            if "affects" in r:
                if not isinstance(r["affects"], list):
                    notes.append(f"{rid}: 'affects' bertipe {type(r['affects']).__name__}, harus list")
                elif not r["affects"]:
                    # Container KOSONG = seam yang sama dgn elemen salah-tipe: lolos cek
                    # tipe, lalu `major not in []` selalu benar -> rule tak pernah menyala.
                    notes.append(f"{rid}: 'affects' kosong — rule tak akan pernah menyala; "
                                 f"sebut versi terpengaruh ({'|'.join(MAJOR_KEYS)})")
                else:
                    for a in r["affects"]:
                        if not isinstance(a, str):
                            notes.append(f"{rid}: affects {a!r} bukan string — tulis sebagai teks "
                                         f"({'|'.join(MAJOR_KEYS)}); rule tak akan pernah menyala")
                        elif a not in MAJOR_KEYS:
                            notes.append(f"{rid}: affects '{a}' bukan major key — sah: {', '.join(MAJOR_KEYS)}"
                                         " (rule diam-diam tak pernah dipakai)")
            if "files" in r:
                if not isinstance(r["files"], list):
                    notes.append(f"{rid}: 'files' bertipe {type(r['files']).__name__}, harus list")
                else:
                    for fl in r["files"]:
                        if not isinstance(fl, str) or not fl.strip():
                            notes.append(f"{rid}: files {fl!r} harus string tak kosong")
            structural = r.get("kind") in ("structure", "compliancy")
            if structural and r.get("expect") not in STRUCT_EXPECTS:
                notes.append(f"{rid}: expect '{r.get('expect')}' tak dikenal untuk rule struktural"
                             f" — sah: {', '.join(sorted(STRUCT_EXPECTS))}")
            # `pattern` dipakai rule non-struktural DAN rule struktural expect=present.
            if ("pattern" not in r) and (not structural or r.get("expect") == "present"):
                notes.append(f"{rid}: rule ini butuh 'pattern' (kind={r.get('kind')!r}"
                             f"{', expect=present' if structural else ''})")
            if "pattern" in r:
                _check_regex(notes, rid, "pattern", r["pattern"])
            if "negate_pattern" in r:
                _check_regex(notes, rid, "negate_pattern", r["negate_pattern"])
    return notes


def unresolved_path_args(named_paths):
    """Argumen path yang masih memuat token `{project-root}` (mestinya diekspansi pemanggil).

    Token itu hanya bermakna di dalam nilai config; argumen path filesystem harus sudah
    diresolve. Gagal keras mencegah ps-plan-layers exit 0 sambil melihat folder harfiah
    `{project-root}/...` lalu melaporkan 'file lapis belum ada' dengan percaya diri (rerun
    semua lapis mahal). Satu pemilik di ps-static-scan; ps-plan-layers memanggilnya via sibling
    (dulu reject_unresolved_paths ada 3x di psm-setup, 0x di psm-validate — konsumen terberat).
    Mengembalikan daftar (nama, nilai) yang melanggar; pemanggil cetak + return 2 (error input).
    """
    return [(name, val) for name, val in named_paths if val and "{project-root}" in val]


def main():
    ap = argparse.ArgumentParser(description="Pindai module PrestaShop terhadap aturan kompatibilitas lintas versi.",
                                 epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("module_path", help="Path folder module PrestaShop")
    ap.add_argument("--versions", default="1.7.8,8.1,9.1", help="Versi target dipisah koma (default: 1.7.8,8.1,9.1)")
    ap.add_argument("--rules", default=str(DEFAULT_RULES), help="Path ps-rules.json (default: assets/ps-rules.json)")
    ap.add_argument("--extra-rules", help="Path JSON aturan TAMBAHAN (skema sama ps-rules.json) — "
                                          "di-merge ke ruleset; --rules MENGGANTI, ini MENAMBAH. "
                                          "Untuk aturan dari knowledge base tanpa menyalin ruleset inti.")
    ap.add_argument("-o", "--output", help="File output JSON (default: stdout)")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    bad = unresolved_path_args([("--rules", args.rules), ("--extra-rules", args.extra_rules),
                                ("-o", args.output)])
    if bad:
        for name, val in bad:
            print(f"error: token '{{project-root}}' belum diresolve di {name}: {val!r} — resolve "
                  "ke root project dulu; ini path filesystem, bukan nilai config.", file=sys.stderr)
        return 2

    module_dir = Path(args.module_path).resolve()
    if not module_dir.is_dir():
        print(f"error: bukan folder: {module_dir}", file=sys.stderr)
        return 2
    try:
        rules = json.loads(Path(args.rules).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: gagal baca ruleset: {e}", file=sys.stderr)
        return 2
    violations = validate_extra_rules(rules, label="ruleset")
    if violations:
        print("error: ruleset tak lolos validasi skema:", file=sys.stderr)
        for n in violations:
            print(f"  - {n}", file=sys.stderr)
        print("perbaiki ruleset lalu jalankan ulang "
              f"(skema: {DEFAULT_RULES.name} _meta.schema)", file=sys.stderr)
        return 2
    if args.extra_rules:
        try:
            extra = json.loads(Path(args.extra_rules).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"error: gagal baca extra-rules: {e}", file=sys.stderr)
            return 2
        violations = validate_extra_rules(extra)
        if violations:
            print("error: extra-rules tak lolos validasi skema:", file=sys.stderr)
            for n in violations:
                print(f"  - {n}", file=sys.stderr)
            print("perbaiki file aturan tambahan lalu jalankan ulang "
                  f"(skema: {DEFAULT_RULES.name} _meta.schema)", file=sys.stderr)
            return 2
        for grp in RULE_GROUPS:
            rules.setdefault(grp, []).extend(extra.get(grp, []))

    main_file, main_reason = find_main_file(module_dir)
    if args.verbose:
        print(f"module={module_dir.name} main_file={main_file} reason={main_reason}", file=sys.stderr)

    all_rules = []
    for grp in RULE_GROUPS:
        all_rules.extend(rules.get(grp, []))

    versions = norm_versions(args.versions.split(","))

    # Gerbang domain di sisi TARGET — cerminan gerbang `affects` di sisi ATURAN.
    # validate_extra_rules sudah menolak rule ber-affects di luar MAJOR_KEYS dengan alasan
    # "rule tak akan pernah menyala"; versi target yang major-nya di luar domain itu kondisi
    # yang SAMA dilihat dari arah sebaliknya — SETIAP aturan dilewati, hasilnya 0 error, lalu
    # terbaca konklusif lolos. Module ber-eval() pernah dinyatakan siap-rilis di `--versions 1.6`
    # begitu. Ketiadaan aturan bukan bukti, jadi ini kekeliruan pemanggil (exit 2), bukan vonis.
    off_domain = [full for full, major in versions if major not in MAJOR_KEYS]
    if off_domain:
        print(f"error: versi target di luar domain ruleset: {', '.join(off_domain)}", file=sys.stderr)
        print(f"  ruleset ini hanya menilai major: {', '.join(MAJOR_KEYS)}", file=sys.stderr)
        print("nol aturan akan dinilai untuk versi itu — dan 0 error di sana bukan lolos",
              file=sys.stderr)
        return 2

    result = {"module": module_dir.name, "module_path": str(module_dir),
              "main_file_found": main_file is not None,
              "ruleset": ruleset_provenance([args.rules, args.extra_rules]),
              "versions": {}}
    if main_reason:
        result["main_file_reason"] = main_reason
        result["main_file_candidates"] = sorted(
            p.name for p in module_dir.glob("*.php") if p.name != "index.php")
    overall_errors = 0

    for full_ver, major in versions:
        # Berapa aturan yang BENAR-BENAR dinilai di versi ini. Gerbang domain di atas menjaga
        # major yang tak dikenal ruleset bawaan, tapi `--rules` MENGGANTI ruleset: file KB yang
        # cuma menyebut major "9" membuat target 8.1 lolos gerbang lalu dinilai nol aturan.
        # Agregat butuh angkanya untuk membedakan "bersih" dari "tak dinilai".
        applicable = [r for r in all_rules if major in r.get("affects", [])]
        v_findings = []
        for rule in applicable:
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
            "rules_evaluated": len(applicable),
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
