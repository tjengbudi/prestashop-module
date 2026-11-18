#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Rawat konteks per-module PrestaShop (lapis tak-terderivasi) -> satu file .md.

Pasangan ps-module-inventory.py: inventaris memegang fakta TERDERIVASI (hook,
ObjectModel, file — segar tiap run, memang dibuang tiap run); skrip ini memegang
yang TAK BISA diturunkan dari kode — kenapa keputusan diambil, tabel mana yang
hidup di produksi, konvensi khusus module ini, riwayat validasi.

Artefaknya `<memory-dir>/projects/<module>.md`, satu file tanpa sidecar JSON:
pasangan .md/.json butuh --pair-check justru karena dua file bisa drift. Klaim
mesin hidup sebagai marker di dalam .md, di-parse seperti parse_md_statuses.

Dua disiplin tulis, karena append-only murni tak cukup: bila tabel dihapus,
meng-append "tabel hilang" membiarkan klaim live lama berdiri dan reconcile
drift selamanya.
- seksi jurnal (psm:jurnal) — append-only (note), semantik memlog.
- seksi fakta (psm:fakta) — upsert by (kind,key) (claim/drop).
Keduanya tata bahasa tertutup: drift datang dari kebebasan prosa, bukan mutasi.

Lima mode:
- init:      buat artefak berkerangka (rc=2 bila sudah ada).
- note:      tambah satu entri Jurnal di akhir.
- claim:     upsert satu Fakta by (kind,key) — terbaru menang.
- drop:      hapus satu Fakta by (kind,key).
- reconcile: cocokkan Fakta dengan JSON inventaris (rc=1 bila drift).

reconcile menerima JSON inventaris sebagai INPUT, tak memanggil
ps-module-inventory.py sendiri: <skills-dir> adalah token yang di-resolve model
dan tak bisa dihitung skrip, dan tiap workflow yang merekonsiliasi sudah
memegang inventaris di fase yang sama — memanggil ulang = scan dua kali pohon
yang sama dalam satu turn.

note/claim AUTO-INIT bila artefak absen (menyimpang sadar dari memlog, yang
error): di sini ada enam pemanggil, dan mengulang "init dulu" enam kali di
SKILL.md ber-budget adalah biaya prosa sekaligus mode gagal hidup.

Kontrak marker kanonik ada di MARKER_SCHEMA / epilog --help; SKILL.md pemanggil
hanya menunjuk ke sini.
"""
import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

# Empat hal yang reconcile bisa BUKTIKAN dari inventaris — himpunan tertutup.
# 'class' = ObjectModel saja (identik reconcile_plan); controller lewat kind=file.
# Konvensi/keputusan sengaja TAK di sini: kalau tak bisa dibuktikan, ia tak boleh
# jadi Fakta, supaya reconcile tak pernah memunculkan drift yang tak punya cara
# diselesaikan. Tempatnya seksi '## Konvensi module' / '## Keputusan'.
KINDS = ("hook", "table", "class", "file")
STATUSES = ("live", "retired", "planned")

# Seksi dikenali lewat ID STABIL, bukan judulnya: judul ditulis dalam bahasa dokumen
# (document_output_language) dan boleh diterjemahkan tangan, jadi parser tak boleh
# bergantung padanya. ID hidup sebagai komentar HTML di baris judul — tak terlihat
# saat dirender: `## Module conventions <!-- psm:konvensi -->`. Artefak lama tanpa
# penanda tetap dikenali lewat judul bawaan (TITLES) dan diberi penanda saat ditulis.
SEC_KONVENSI = "konvensi"
SEC_KEPUTUSAN = "keputusan"
SEC_FAKTA = "fakta"
SEC_JURNAL = "jurnal"
SEC_RINGKASAN = "ringkasan"
SECTIONS = (SEC_KONVENSI, SEC_KEPUTUSAN, SEC_FAKTA, SEC_JURNAL, SEC_RINGKASAN)

# Teks kerangka per bahasa dokumen. Bahasa lain jatuh ke 'en'; model menerjemahkan
# judul & petunjuk sendiri — penanda ID yang membuat itu aman.
TEXTS = {
    "id": {
        "titles": {SEC_KONVENSI: "Konvensi module", SEC_KEPUTUSAN: "Keputusan",
                   SEC_FAKTA: "Fakta terkonsiliasi", SEC_JURNAL: "Jurnal",
                   SEC_RINGKASAN: "Ringkasan"},
        "h1": "Konteks module {module}",
        "seeded": "Diseed {date} dari {src}.",
        "updated": "Diperbarui {date} oleh {who}.",
        "default_src": "inventaris ps-module-inventory + sesi workflow psm",
        "hints": {
            SEC_KONVENSI: "_Konvensi khusus module ini: namespace, layout service, prefix tabel, kesepakatan tim._\n"
                          "_Yang benar untuk PrestaShop umum TIDAK ditulis di sini — rujuk `[[cross-version-patterns]]`,\n"
                          "`[[persistence]]`, `[[services-di]]` di `tech/`._",
            SEC_KEPUTUSAN: "_Butir bertanggal: keputusan yang diambil dan alasannya._",
            SEC_FAKTA: "_Milik `ps-module-context.py` (claim/drop). Jangan sunting tangan._",
            SEC_JURNAL: "_Milik `ps-module-context.py` (note), append-only. Jangan sunting tangan._",
            SEC_RINGKASAN: "_Opsional, dikurasi psm-agent-expert. Tak dibaca workflow._",
        },
        "footer": "Sumber: sesi workflow psm + inventaris ps-module-inventory.py; "
                  "pengetahuan PrestaShop umum di `tech/`.",
    },
    "en": {
        "titles": {SEC_KONVENSI: "Module conventions", SEC_KEPUTUSAN: "Decisions",
                   SEC_FAKTA: "Reconciled facts", SEC_JURNAL: "Journal",
                   SEC_RINGKASAN: "Summary"},
        "h1": "Module context {module}",
        "seeded": "Seeded {date} from {src}.",
        "updated": "Updated {date} by {who}.",
        "default_src": "ps-module-inventory inventory + psm workflow session",
        "hints": {
            SEC_KONVENSI: "_Conventions specific to this module: namespace, service layout, table prefix, team agreements._\n"
                          "_What holds for PrestaShop in general is NOT written here — link `[[cross-version-patterns]]`,\n"
                          "`[[persistence]]`, `[[services-di]]` in `tech/`._",
            SEC_KEPUTUSAN: "_Dated bullets: the decision taken and its reason._",
            SEC_FAKTA: "_Owned by `ps-module-context.py` (claim/drop). Do not edit by hand._",
            SEC_JURNAL: "_Owned by `ps-module-context.py` (note), append-only. Do not edit by hand._",
            SEC_RINGKASAN: "_Optional, curated by psm-agent-expert. Not read by workflows._",
        },
        "footer": "Source: psm workflow sessions + ps-module-inventory.py inventory; "
                  "general PrestaShop knowledge in `tech/`.",
    },
}

MARKER_SCHEMA = """\
Marker kanonik di seksi fakta (psm:fakta) (kontrak bersama workflow psm):
  - Fakta: kind=<hook|table|class|file> key=<ident> status=<live|retired|planned>
           sejak=<YYYY-MM-DD> oleh=<skill> [catatan=<bebas, sampai akhir baris>]

Identity = (kind, key); claim meng-upsert, terbaru menang. 'catatan' wajib
field terakhir agar boleh berspasi tanpa kutip. Parsing toleran bullet/bold.

status=live     -> fakta harus ADA di inventaris; hilang = drift live_but_missing
status=retired  -> fakta sengaja ABSEN; muncul lagi = drift retired_but_present
status=planned  -> diabaikan reconcile (belum diterapkan)

Zona artefak <memory-dir>/projects/<module>.md — seksi dikenali lewat ID di
penanda judul `## <judul> <!-- psm:<id> -->`, BUKAN lewat judulnya:
  psm:konvensi, psm:keputusan, psm:ringkasan -> prosa terkurasi, disunting
    TANGAN (psm-module-context / psm-agent-expert).
  psm:fakta, psm:jurnal -> milik skrip ini saja; jangan disunting tangan.
Bahasa: judul, petunjuk kerangka, H1, dan baris provenance ditulis dalam bahasa
dokumen (--lang, else document_output_language di _bmad/config.yaml, else
English; bawaan Indonesia & English, bahasa lain memakai English). Judul boleh
diterjemahkan tangan asal penanda <!-- psm:<id> --> tetap di baris judul.
Artefak lama tanpa penanda dikenali dari judul bawaan dan diberi penanda saat
ditulis. Token marker (Fakta:, kind=, status=, sejak=, oleh=, catatan=) adalah
kontrak mesin — jangan diterjemahkan.
Tiap write hanya menyentuh satu seksi; isi seksi lain disalin byte-for-byte.
"""

FAKTA_RE = re.compile(r"^\s*(?:[-*]\s+)?Fakta\s*:\s*(.+?)\s*$", re.IGNORECASE)
FIELD_RE = re.compile(r"\b(kind|key|status|sejak|oleh|catatan)=")
H2_RE = re.compile(r"^##\s+(.+?)\s*$")
SEC_ID_RE = re.compile(r"\s*<!--\s*psm:([a-z_]+)\s*-->\s*$")
DOC_LANG_RE = re.compile(r"^document_output_language\s*:\s*['\"]?([^'\"#\n]+?)['\"]?\s*(?:#.*)?$", re.M)
# Judul bawaan semua bahasa -> ID, untuk artefak yang belum berpenanda.
TITLE_TO_ID = {t.lower(): sid for txt in TEXTS.values() for sid, t in txt["titles"].items()}


def today() -> str:
    return date.today().strftime("%Y-%m-%d")


def write_atomic(path: Path, text: str) -> None:
    """Temp + flush + fsync + rename atomik, supaya crash tak pernah menulis separuh.

    Disalin dari _bmad/scripts/memlog.py (bukan di-import): _bmad/scripts/ adalah
    data runtime project, bukan data instal skill — skill yang pecah saat data
    project absen tak bisa dikirim.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def resolve(args) -> Path:
    """Artefak, dari salah satu mode addressing: <memory-dir>/projects/<module>.md atau --path."""
    if args.path:
        return Path(args.path)
    return Path(args.memory_dir) / "projects" / f"{args.module}.md"


def module_name(args, path: Path) -> str:
    return args.module if args.module else path.stem


def normalize_lang(value) -> str:
    """Nama bahasa bebas (config/flag) -> kunci TEXTS. Tak dikenal -> 'en'."""
    v = (value or "").strip().lower()
    if v in ("id", "ind") or v.startswith(("indo", "bahasa")):
        return "id"
    return "en"


def doc_lang(args, path: Path) -> str:
    """Bahasa dokumen: --lang menang; else document_output_language dari
    `_bmad/config.yaml` terdekat di atas artefak; else 'en' (default psm-setup)."""
    if getattr(args, "lang", None):
        return normalize_lang(args.lang)
    for parent in path.resolve().parents:
        cfg = parent / "_bmad" / "config.yaml"
        if cfg.is_file():
            m = DOC_LANG_RE.search(cfg.read_text(encoding="utf-8", errors="replace"))
            return normalize_lang(m.group(1) if m else None)
    return "en"


# --- struktur artefak -------------------------------------------------------

def section_key(heading):
    """Baris judul H2 (tanpa '## ') -> (kunci, judul tampil).

    Kunci = ID penanda bila ada, else ID judul bawaan (artefak lama), else judul
    mentah (seksi tak dikenal — dibawa apa adanya)."""
    m = SEC_ID_RE.search(heading)
    if m:
        return m.group(1), heading[:m.start()].strip()
    return TITLE_TO_ID.get(heading.strip().lower(), heading), heading


def split_sections(text):
    """Pecah jadi (head, {kunci: [baris]}, {kunci: judul}) per batas H2.

    head = semua sebelum H2 pertama (H1 + baris provenance). Dict judul juga
    memegang urutan. Seksi tak dikenal ikut terbawa apa adanya — skrip ini tak
    pernah membuang apa yang tak dimilikinya.
    """
    lines = text.splitlines()
    head, sections, order = [], {}, {}
    current = None
    for line in lines:
        h = H2_RE.match(line)
        if h:
            current, title = section_key(h.group(1))
            if current not in sections:
                sections[current] = []
                order[current] = title
            continue
        (sections[current] if current is not None else head).append(line)
    return head, sections, order


def render_doc(head, sections, order) -> str:
    """Seksi milik kontrak selalu ditulis berpenanda ID; seksi asing apa adanya."""
    parts = ["\n".join(head).rstrip("\n")]
    for key, title in order.items():
        heading = f"{title} <!-- psm:{key} -->" if key in SECTIONS else title
        body = "\n".join(sections[key]).strip("\n")
        parts.append(f"## {heading}\n{body}" if body else f"## {heading}")
    return "\n\n".join(parts).rstrip("\n") + "\n"


SEEDED_PREFIXES = ("Diseed ", "Seeded ")
UPDATED_RE = re.compile(r"\s*(?:Diperbarui|Updated) .*$")


def stamp_updated(head, by, lang="en"):
    """Perbarui klausa 'Updated/Diperbarui' di baris provenance (baris-3 gaya rumah KB)."""
    who = by or "workflow psm"
    clause = TEXTS[lang]["updated"].format(date=today(), who=who)
    for i, line in enumerate(head):
        if line.startswith(SEEDED_PREFIXES):
            base = UPDATED_RE.sub("", line).rstrip()
            head[i] = f"{base} {clause}"
            return
    # tak ada baris provenance (artefak disunting tangan sampai hilang) — jangan
    # memaksa; skrip tak memiliki head.


def skeleton(module, source, lang="en") -> str:
    t = TEXTS[lang]
    src = source or t["default_src"]
    out = f"# {t['h1'].format(module=module)}\n\n{t['seeded'].format(date=today(), src=src)}\n\n"
    for sid in SECTIONS:
        out += f"## {t['titles'][sid]} <!-- psm:{sid} -->\n{t['hints'][sid]}\n\n"
    return out + t["footer"] + "\n"


def load_doc(path: Path, args, autoinit_by=None):
    """Baca artefak; auto-init bila absen dan diizinkan. -> (head, sections, order) | rc int."""
    if not path.exists():
        if autoinit_by is None:
            print(f"error: {path} tak ada", file=sys.stderr)
            return 2
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(path, skeleton(module_name(args, path), None, doc_lang(args, path)))
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.lstrip().startswith("#"):
        print(f"error: {path} tak punya H1 — bukan artefak konteks module", file=sys.stderr)
        return 2
    head, sections, order = split_sections(text)
    titles = TEXTS[doc_lang(args, path)]["titles"]
    for sid in SECTIONS:  # seksi yang hilang (disunting tangan) dipulihkan kosong
        if sid not in sections:
            sections[sid] = []
            order[sid] = titles[sid]
    return head, sections, order


# --- marker Fakta -----------------------------------------------------------

def parse_fakta(line):
    """-> dict field | None (bukan baris Fakta) | {} (baris Fakta tapi rusak).

    Split di batas FIELD_RE supaya 'catatan' boleh berspasi tanpa kutip; bold/
    italic dibuang sebelum match, seperti parse_md_statuses.
    """
    m = FAKTA_RE.match(line.replace("*", ""))
    if not m:
        return None
    rest = m.group(1)
    # 'catatan' adalah teks bebas: begitu ia mulai, berhenti men-split — kalau tidak,
    # catatan yang kebetulan memuat 'status=...' akan dibaca sebagai field.
    cat = re.search(r"\bcatatan=", rest)
    catatan = rest[cat.end():].strip() if cat else None
    if cat:
        rest = rest[:cat.start()]
    bounds = list(FIELD_RE.finditer(rest))
    if not bounds:
        return {}
    out = {}
    for i, b in enumerate(bounds):
        end = bounds[i + 1].start() if i + 1 < len(bounds) else len(rest)
        out[b.group(1)] = rest[b.end():end].strip()
    if catatan is not None:
        out["catatan"] = catatan
    if not out.get("kind") or not out.get("key"):
        return {}
    return out


def render_fakta(f) -> str:
    parts = [f"kind={f['kind']}", f"key={f['key']}", f"status={f['status']}",
             f"sejak={f['sejak']}", f"oleh={f['oleh']}"]
    if f.get("catatan"):
        parts.append(f"catatan={f['catatan']}")
    return "- Fakta: " + " ".join(parts)


def fakta_lines(section):
    """-> [(index, dict|{})] untuk tiap baris Fakta di seksi."""
    return [(i, p) for i, line in enumerate(section)
            for p in [parse_fakta(line)] if p is not None]


def counts(sections):
    return (len(fakta_lines(sections.get(SEC_FAKTA, []))),
            sum(1 for ln in sections.get(SEC_JURNAL, []) if ln.startswith("- ")))


def ack(path: Path, sections) -> None:
    """Echo keadaan baru supaya pemanggil tak perlu membaca ulang file.

    Bentuk ack satu baris (memlog), BUKAN indent=2 seperti reconcile: ini
    konfirmasi tulis, bukan laporan. Dua idiom ini sengaja — jangan diseragamkan.
    """
    c, j = counts(sections)
    print(json.dumps({"ok": True, "context": str(path), "claims": c, "journal": j},
                     ensure_ascii=False))


# --- subcommand -------------------------------------------------------------

def cmd_init(args) -> int:
    path = resolve(args)
    if path.exists():
        print(f"error: {path} sudah ada; pakai note/claim untuk memperbaruinya", file=sys.stderr)
        return 2
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, skeleton(module_name(args, path), args.source, doc_lang(args, path)))
    _, sections, _ = split_sections(path.read_text(encoding="utf-8"))
    ack(path, sections)
    return 0


def cmd_note(args) -> int:
    path = resolve(args)
    doc = load_doc(path, args, autoinit_by=args.by or "workflow psm")
    if isinstance(doc, int):
        return doc
    head, sections, order = doc
    text = " ".join(args.text.split())  # kolapskan ke satu baris — jurnal bukan laporan
    label = args.type or ""
    if args.by:
        label = f"{label} by {args.by}".strip()
    entry = f"- ({label}) {text}" if label else f"- {text}"
    body = [ln for ln in sections[SEC_JURNAL] if ln.strip()]
    body.append(entry)  # selalu di akhir — kronologis
    sections[SEC_JURNAL] = body
    stamp_updated(head, args.by, doc_lang(args, path))
    write_atomic(path, render_doc(head, sections, order))
    ack(path, sections)
    return 0


def cmd_claim(args) -> int:
    if args.kind not in KINDS:
        print(f"error: --kind '{args.kind}' tak dikenal; pilih {'|'.join(KINDS)} "
              "(konvensi/keputusan bukan Fakta — tulis di seksi prosanya)", file=sys.stderr)
        return 2
    if args.status not in STATUSES:
        print(f"error: --status '{args.status}' tak dikenal; pilih {'|'.join(STATUSES)}",
              file=sys.stderr)
        return 2
    path = resolve(args)
    doc = load_doc(path, args, autoinit_by=args.by or "workflow psm")
    if isinstance(doc, int):
        return doc
    head, sections, order = doc
    fakta = {"kind": args.kind, "key": args.key, "status": args.status,
             "sejak": args.since or today(), "oleh": args.by or "workflow psm",
             "catatan": args.note or ""}
    section = sections[SEC_FAKTA]
    replaced = False
    out = []
    for line in section:
        p = parse_fakta(line)
        if p and p.get("kind") == args.kind and p.get("key") == args.key:
            if not replaced:  # upsert by (kind,key) — terbaru menang
                out.append(render_fakta(fakta))
                replaced = True
            continue
        out.append(line)
    if not replaced:
        out = [ln for ln in out if ln.strip()] or out
        out.append(render_fakta(fakta))
    sections[SEC_FAKTA] = out
    stamp_updated(head, args.by, doc_lang(args, path))
    write_atomic(path, render_doc(head, sections, order))
    ack(path, sections)
    return 0


def cmd_drop(args) -> int:
    if args.kind not in KINDS:
        print(f"error: --kind '{args.kind}' tak dikenal; pilih {'|'.join(KINDS)}", file=sys.stderr)
        return 2
    path = resolve(args)
    doc = load_doc(path, args)
    if isinstance(doc, int):
        return doc
    head, sections, order = doc
    section = sections[SEC_FAKTA]
    out = []
    for line in section:
        p = parse_fakta(line)
        if p and p.get("kind") == args.kind and p.get("key") == args.key:
            continue
        out.append(line)
    sections[SEC_FAKTA] = out
    stamp_updated(head, args.by, doc_lang(args, path))
    write_atomic(path, render_doc(head, sections, order))
    ack(path, sections)
    return 0


def build_present(inv):
    """Present-set dari inventaris — identik reconcile_plan (ps-module-inventory.py).

    implemented_hooks berprefiks 'hook' (mis. 'hookDisplayHeader'); normalkan ke
    bentuk bare + lowercase agar cocok dengan registered_hooks (case-insensitive).
    """
    hooks = {h.lower() for h in inv.get("registered_hooks", [])}
    hooks |= {re.sub(r"^hook", "", h, flags=re.IGNORECASE).lower()
              for h in inv.get("implemented_hooks", [])}
    oms = inv.get("object_models", [])
    return {
        "hook": hooks,
        "table": {o["table"] for o in oms if o.get("table")},
        "class": {o["class"] for o in oms if o.get("class")},
        "file": set(inv.get("files", [])),
    }


def cmd_reconcile(args) -> int:
    path = resolve(args)
    doc = load_doc(path, args)
    if isinstance(doc, int):
        return doc
    _, sections, _ = doc
    src = sys.stdin.read() if args.inventory == "-" else None
    try:
        inv = json.loads(src if src is not None
                         else Path(args.inventory).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: gagal baca inventaris {args.inventory}: {e}", file=sys.stderr)
        return 2
    mod = module_name(args, path)
    if inv.get("module") and inv["module"] != mod:
        print(f"error: inventaris untuk module '{inv['module']}' != konteks '{mod}' "
              "— pasangan salah", file=sys.stderr)
        return 2

    present = build_present(inv)
    drift, claimed = [], {k: set() for k in KINDS}
    for i, p in fakta_lines(sections[SEC_FAKTA]):
        if not p:  # baris Fakta rusak = artefak salah -> drift, bukan invokasi salah -> rc=2
            drift.append({"kind": "claim_malformed", "fact_kind": None, "key": None,
                          "detail": f"baris Fakta di seksi fakta (psm:fakta) tak bisa di-parse "
                                    f"(baris ke-{i + 1} seksi) — perbaiki lewat claim/drop"})
            continue
        kind, key, status = p["kind"], p["key"], p.get("status", "")
        if kind not in KINDS:
            drift.append({"kind": "claim_malformed", "fact_kind": kind, "key": key,
                          "detail": f"kind '{kind}' tak dikenal; pilih {'|'.join(KINDS)}"})
            continue
        if status == "planned":  # belum diterapkan — bukan klaim atas bukti
            continue
        claimed[kind].add(key.lower() if kind == "hook" else key)
        hit = (key.lower() if kind == "hook" else key) in present[kind]
        if status == "live" and not hit:
            drift.append({"kind": "live_but_missing", "fact_kind": kind, "key": key,
                          "detail": f"{kind} '{key}' diklaim live tapi tak ada di inventaris"})
        elif status == "retired" and hit:
            drift.append({"kind": "retired_but_present", "fact_kind": kind, "key": key,
                          "detail": f"{kind} '{key}' diklaim retired tapi muncul lagi di inventaris"})
        elif status not in STATUSES:
            drift.append({"kind": "claim_malformed", "fact_kind": kind, "key": key,
                          "detail": f"status '{status}' tak dikenal; pilih {'|'.join(STATUSES)}"})

    # uncovered INFORMASIONAL, tak pernah rc=1: konteks adalah lapis tak-terderivasi,
    # bukan cermin lengkap inventaris. Menjadikannya drift = tiap run merah sejak hari pertama.
    uncovered = {k: sorted(present[k] - claimed[k]) for k in KINDS}
    result = {
        "module": mod, "context": str(path), "ok": not drift,
        "claims_checked": sum(len(v) for v in claimed.values()),
        "drift": drift, "uncovered": uncovered,
        "note": "uncovered = fakta inventaris tanpa klaim; informasi, bukan drift. "
                "Keputusan atas drift milik model.",
    }
    out = json.dumps(result, indent=2, ensure_ascii=False)
    (Path(args.output).write_text(out, encoding="utf-8") if args.output else print(out))
    return 0 if result["ok"] else 1


def add_target(sp) -> None:
    """Tiap subcommand mengalamati artefak sama: folder KB + nama module, atau path eksplisit."""
    g = sp.add_mutually_exclusive_group(required=True)
    g.add_argument("--memory-dir", help="folder KB psm; artefak = <memory-dir>/projects/<module>.md")
    g.add_argument("--path", help="path artefak eksplisit (alternatif --memory-dir)")
    sp.add_argument("--module", help="nama module (wajib bersama --memory-dir)")
    sp.add_argument("--lang", help="bahasa dokumen untuk kerangka/judul baru (mis. English); "
                    "default: document_output_language dari _bmad/config.yaml, else English")


def main() -> int:
    p = argparse.ArgumentParser(
        description="Rawat konteks per-module PrestaShop (lapis tak-terderivasi) -> satu file .md.",
        formatter_class=argparse.RawDescriptionHelpFormatter, epilog=MARKER_SCHEMA)
    sub = p.add_subparsers(dest="cmd", required=True)

    pi = sub.add_parser("init", help="buat artefak berkerangka (rc=2 bila sudah ada)")
    add_target(pi)
    pi.add_argument("--source", help="sumber seed untuk baris provenance")
    pi.set_defaults(func=cmd_init)

    pn = sub.add_parser("note", help="tambah satu entri seksi jurnal (psm:jurnal) di akhir (auto-init)")
    add_target(pn)
    pn.add_argument("--text", required=True)
    pn.add_argument("--type", help="jenis entri, dirender jadi tag inline")
    pn.add_argument("--by", help="skill/agen penulis entri")
    pn.set_defaults(func=cmd_note)

    pc = sub.add_parser("claim", help="upsert satu Fakta by (kind,key) di seksi fakta (psm:fakta) (auto-init)")
    add_target(pc)
    pc.add_argument("--kind", required=True, choices=KINDS, metavar="KIND",
                    help=f"salah satu: {'|'.join(KINDS)}")
    pc.add_argument("--key", required=True, help="identifier (nama hook/tabel/class/path file)")
    pc.add_argument("--status", required=True, choices=STATUSES, metavar="STATUS",
                    help=f"salah satu: {'|'.join(STATUSES)}")
    pc.add_argument("--since", help="tanggal YYYY-MM-DD (default: hari ini)")
    pc.add_argument("--by", help="skill/agen yang mengklaim")
    pc.add_argument("--note", help="catatan bebas (dirender terakhir, boleh berspasi)")
    pc.set_defaults(func=cmd_claim)

    pd = sub.add_parser("drop", help="hapus satu Fakta by (kind,key)")
    add_target(pd)
    pd.add_argument("--kind", required=True, choices=KINDS, metavar="KIND",
                    help=f"salah satu: {'|'.join(KINDS)}")
    pd.add_argument("--key", required=True)
    pd.add_argument("--by", help="skill/agen yang menghapus")
    pd.set_defaults(func=cmd_drop)

    pr = sub.add_parser("reconcile", help="cocokkan Fakta dengan JSON inventaris (rc=1 bila drift)")
    add_target(pr)
    pr.add_argument("--inventory", required=True, metavar="FILE",
                    help="JSON ps-module-inventory.py ('-' = stdin)")
    pr.add_argument("-o", "--output", help="Tulis JSON ke file (default stdout)")
    pr.set_defaults(func=cmd_reconcile)

    args = p.parse_args()
    if args.memory_dir and not args.module:
        print("error: --memory-dir butuh --module", file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
