#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Rawat backlog ide per-module PrestaShop (satu domain) -> satu file .md.

Pasangan ps-module-inventory.py + .psm-develop-plan.json, bukan penggantinya:
inventaris memegang apa yang ADA, rencana memegang apa yang SEDANG dikerjakan,
skrip ini memegang apa yang BELUM — ide yang sudah dipikirkan, ditimbang, lalu
diparkir karena siklus ini mengerjakan yang lain. Rencana sengaja sekali pakai
per siklus; backlog inilah yang bertahan lintas sesi.

Artefaknya `<module-path>/.psm-ideas.md`, satu file tanpa sidecar JSON. Alasan
sama dengan ps-module-context.py: pasangan .md/.json butuh --pair-check justru
karena dua file bisa drift. Klaim mesin hidup sebagai marker di dalam .md.

Nilai utamanya bukan menyimpan daftar, tapi `sync`: backlog yang tak pernah
dicocokkan dengan rencana akan menawarkan ulang fungsi yang SUDAH dibangun —
mode gagal yang persis membuat backlog tak dipercaya lalu ditinggalkan.

Lima mode:
- init: buat artefak berkerangka (rc=2 bila sudah ada).
- add:  upsert satu ide by key — terbaru menang.
- drop: hapus satu ide by key.
- sync: cocokkan backlog dengan .psm-develop-plan.json (rc=1 bila drift).
- list: emit backlog sebagai JSON (untuk memilih, bukan untuk disunting).

sync menerima rencana sebagai INPUT path, tak mencarinya sendiri: skill pemanggil
sudah memegang <module-path> di fase yang sama, dan menebak lokasi rencana adalah
cara halus untuk diam-diam menyinkronkan ke artefak module yang salah.

add AUTO-INIT bila artefak absen (ikut ps-module-context.py): mengulang "init
dulu" di tiap langkah SKILL.md ber-budget adalah biaya prosa sekaligus mode gagal
hidup.

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

# Empat status. 'terwujud' satu-satunya yang punya bukti di luar backlog (item
# rencana ber-status diterapkan), jadi satu-satunya yang bisa drift dua arah.
STATUSES = ("baru", "dipilih", "terwujud", "ditolak")

# Lima arah penggalian Lensa adjacency di
# psm-develop/references/ecommerce-function-catalog.md. Himpunan tertutup supaya
# backlog tetap terbaca sebagai peta, bukan tumpukan; arah yang tak muat di sini
# biasanya tanda idenya lintas domain — tempatnya katalog, bukan backlog ini.
ARAH = ("varian", "kelengkapan", "otomasi", "visibilitas", "ketahanan")

SEC_DOMAIN = "Domain & posisi"
SEC_BACKLOG = "Backlog"
SECTIONS = (SEC_DOMAIN, SEC_BACKLOG)

MARKER_SCHEMA = """\
Marker kanonik di seksi '## Backlog' (kontrak bersama psm-ideate/psm-plan):
  - Ide: key=<slug> status=<baru|dipilih|terwujud|ditolak>
         arah=<varian|kelengkapan|otomasi|visibilitas|ketahanan>
         [prasyarat=<key,key>] [rencana=<nama fungsi di rencana>]
         sejak=<YYYY-MM-DD> oleh=<skill> [catatan=<bebas, sampai akhir baris>]

Identity = key; add meng-upsert, terbaru menang. 'catatan' wajib field terakhir
agar boleh berspasi tanpa kutip. Parsing toleran bullet/bold.

status=baru     -> tertangkap, belum dipilih
status=dipilih  -> diambil untuk siklus ini; sync menuntut item rencana ada
status=terwujud -> sudah dibangun; sync menuntut item rencana 'diterapkan'
status=ditolak  -> sengaja tak dikerjakan (alasannya di catatan) — sync melewati

'rencana' menjembatani backlog dan .psm-develop-plan.json: nilainya HARUS sama
persis dengan field 'function' item rencana. Bila kosong, 'key' yang dipakai.
Pencocokan sengaja eksak — pencocokan fuzzy antar dua artefak yang disunting
manusia akan diam-diam menandai ide yang salah sebagai terwujud.

'prasyarat' menyebut key ide lain yang harus terwujud lebih dulu (anak tangga
keluarga fungsi). sync memeriksanya hanya untuk ide 'dipilih' — itu momen ketika
melompat anak tangga benar-benar berbiaya.

Zona artefak <module-path>/.psm-ideas.md:
  '## Domain & posisi' -> prosa terkurasi, disunting TANGAN (psm-ideate).
  '## Backlog'         -> milik skrip ini saja; jangan disunting tangan.
Tiap write hanya menyentuh satu seksi; sisanya disalin byte-for-byte.
"""

IDE_RE = re.compile(r"^\s*(?:[-*]\s+)?Ide\s*:\s*(.+?)\s*$", re.IGNORECASE)
FIELD_RE = re.compile(r"\b(key|status|arah|prasyarat|rencana|sejak|oleh|catatan)=")
H2_RE = re.compile(r"^##\s+(.+?)\s*$")
APPLIED = ("diterapkan", "applied")


def today() -> str:
    return date.today().strftime("%Y-%m-%d")


def write_atomic(path: Path, text: str) -> None:
    """Temp + flush + fsync + rename atomik, supaya crash tak pernah menulis separuh.

    Disalin dari ps-module-context.py (bukan di-import): tiap skrip skill berdiri
    sendiri agar bisa dijalankan lewat `uv run` tanpa sys.path lintas-skill.
    """
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def resolve(args) -> Path:
    """Artefak: <module-path>/.psm-ideas.md, atau --path apa adanya."""
    if getattr(args, "path", None):
        return Path(args.path)
    return Path(args.module_path) / ".psm-ideas.md"


def module_name(args, path: Path) -> str:
    if getattr(args, "module_path", None):
        return Path(args.module_path).resolve().name
    return path.resolve().parent.name


# --- struktur artefak -------------------------------------------------------

def split_sections(text):
    """Pecah jadi (head, {judul: [baris]}, urutan) per batas H2.

    head = semua sebelum H2 pertama. Seksi tak dikenal ikut terbawa apa adanya —
    skrip ini tak pernah membuang apa yang tak dimilikinya.
    """
    head, sections, order = [], {}, []
    current = None
    for line in text.splitlines():
        h = H2_RE.match(line)
        if h:
            current = h.group(1)
            if current not in sections:
                sections[current] = []
                order.append(current)
            continue
        (sections[current] if current is not None else head).append(line)
    return head, sections, order


def render_doc(head, sections, order) -> str:
    parts = ["\n".join(head).rstrip("\n")]
    for title in order:
        body = "\n".join(sections[title]).strip("\n")
        parts.append(f"## {title}\n{body}" if body else f"## {title}")
    return "\n\n".join(parts).rstrip("\n") + "\n"


def stamp_updated(head, by):
    """Perbarui klausa 'Diperbarui' di baris provenance (gaya rumah KB psm)."""
    clause = f"Diperbarui {today()} oleh {by or 'psm-ideate'}."
    for i, line in enumerate(head):
        if line.startswith("Dibuat "):
            base = re.sub(r"\s*Diperbarui .*$", "", line).rstrip()
            head[i] = f"{base} {clause}"
            return
    # tak ada baris provenance (disunting tangan sampai hilang) — jangan memaksa.


def skeleton(module, domain) -> str:
    dom = domain or "_Belum ditentukan — isi saat psm-ideate mengenali domain module dari inventaris._"
    return (
        f"# Backlog ide module {module}\n\n"
        f"Dibuat {today()} oleh psm-ideate.\n\n"
        f"## {SEC_DOMAIN}\n"
        f"{dom}\n\n"
        "_Domain module + posisinya di keluarga fungsi (bila ada), diturunkan dari bukti\n"
        "inventaris: hook terdaftar, nama tabel, controller. Prosa, disunting tangan._\n\n"
        f"## {SEC_BACKLOG}\n"
        "_Milik `ps-idea-backlog.py` (add/drop). Jangan sunting tangan._\n\n"
        "Sumber: sesi psm-ideate + inventaris ps-module-inventory.py; katalog fungsi di\n"
        "`psm-develop/references/ecommerce-function-catalog.md`.\n"
    )


def load_doc(path: Path, args, autoinit=False):
    """Baca artefak; auto-init bila absen dan diizinkan. -> (head, sections, order) | rc int."""
    if not path.exists():
        if not autoinit:
            print(f"error: {path} tak ada — jalankan init dulu", file=sys.stderr)
            return 2
        path.parent.mkdir(parents=True, exist_ok=True)
        write_atomic(path, skeleton(module_name(args, path), None))
    text = path.read_text(encoding="utf-8", errors="replace")
    if not text.lstrip().startswith("#"):
        print(f"error: {path} tak punya H1 — bukan artefak backlog ide", file=sys.stderr)
        return 2
    head, sections, order = split_sections(text)
    for title in SECTIONS:  # seksi yang hilang (disunting tangan) dipulihkan kosong
        if title not in sections:
            sections[title] = []
            order.append(title)
    return head, sections, order


# --- marker Ide -------------------------------------------------------------

def parse_ide(line):
    """-> dict field | None (bukan baris Ide) | {} (baris Ide tapi rusak).

    Split di batas FIELD_RE supaya 'catatan' boleh berspasi tanpa kutip; bold/
    italic dibuang sebelum match.
    """
    m = IDE_RE.match(line.replace("*", ""))
    if not m:
        return None
    rest = m.group(1)
    # 'catatan' teks bebas: begitu ia mulai, berhenti men-split — kalau tidak,
    # catatan yang memuat 'status=...' akan dibaca sebagai field.
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
    if not out.get("key"):
        return {}
    return out


def render_ide(d) -> str:
    parts = [f"key={d['key']}", f"status={d['status']}", f"arah={d['arah']}"]
    if d.get("prasyarat"):
        parts.append(f"prasyarat={d['prasyarat']}")
    if d.get("rencana"):
        parts.append(f"rencana={d['rencana']}")
    parts += [f"sejak={d['sejak']}", f"oleh={d['oleh']}"]
    if d.get("catatan"):
        parts.append(f"catatan={d['catatan']}")
    return "- Ide: " + " ".join(parts)


def read_backlog(sections):
    """-> (ide terurut [dict], malformed [str]). Baris rusak dilaporkan, tak dibuang diam."""
    ideas, bad = [], []
    for line in sections.get(SEC_BACKLOG, []):
        d = parse_ide(line)
        if d is None:
            continue
        if not d:
            bad.append(line.strip())
            continue
        ideas.append(d)
    return ideas, bad


def target_of(idea) -> str:
    """Nama fungsi yang dipakai mencocokkan ke rencana — 'rencana' bila ada, else 'key'."""
    return idea.get("rencana") or idea["key"]


# --- mode -------------------------------------------------------------------

def cmd_init(args) -> int:
    path = resolve(args)
    if path.exists():
        print(f"error: {path} sudah ada — pakai add, atau sunting seksi prosa langsung",
              file=sys.stderr)
        return 2
    path.parent.mkdir(parents=True, exist_ok=True)
    write_atomic(path, skeleton(module_name(args, path), args.domain))
    print(str(path))
    return 0


def cmd_add(args) -> int:
    if args.status not in STATUSES:
        print(f"error: status '{args.status}' tak dikenal (pilih: {'|'.join(STATUSES)})",
              file=sys.stderr)
        return 1
    if args.arah not in ARAH:
        print(f"error: arah '{args.arah}' tak dikenal (pilih: {'|'.join(ARAH)})",
              file=sys.stderr)
        return 1
    path = resolve(args)
    doc = load_doc(path, args, autoinit=True)
    if isinstance(doc, int):
        return doc
    head, sections, order = doc
    ideas, _ = read_backlog(sections)
    entry = {
        "key": args.key,
        "status": args.status,
        "arah": args.arah,
        "prasyarat": args.prasyarat or "",
        "rencana": args.rencana or "",
        "sejak": today(),
        "oleh": args.by,
        "catatan": args.catatan or "",
    }
    replaced = False
    out = []
    for existing in ideas:
        if existing["key"] == args.key:
            # upsert: 'sejak' ide lama dipertahankan — itu kapan ide LAHIR, bukan
            # kapan terakhir disentuh; yang terakhir hidup di baris provenance.
            entry["sejak"] = existing.get("sejak", entry["sejak"])
            # Field opsional yang TAK disebut di invokasi diwarisi, bukan dikosongkan.
            # Pemakaian terbanyak add-ulang adalah menaikkan status ('baru' ->
            # 'terwujud' saat sync menemukan bukti); menghapus catatan/prasyarat di
            # situ akan diam-diam membuang justru yang membuat ide bisa dinilai
            # ulang berbulan kemudian. Untuk mengosongkan, sebut eksplisit ("").
            for field, given in (("prasyarat", args.prasyarat),
                                 ("rencana", args.rencana),
                                 ("catatan", args.catatan)):
                if given is None:
                    entry[field] = existing.get(field, "")
            out.append(entry)
            replaced = True
        else:
            out.append(existing)
    if not replaced:
        out.append(entry)
    sections[SEC_BACKLOG] = [render_ide(d) for d in out]
    stamp_updated(head, args.by)
    write_atomic(path, render_doc(head, sections, order))
    print(f"{'update' if replaced else 'tambah'}: {args.key} -> {args.status}")
    return 0


def cmd_drop(args) -> int:
    path = resolve(args)
    doc = load_doc(path, args)
    if isinstance(doc, int):
        return doc
    head, sections, order = doc
    ideas, _ = read_backlog(sections)
    kept = [d for d in ideas if d["key"] != args.key]
    if len(kept) == len(ideas):
        print(f"error: ide '{args.key}' tak ada di backlog", file=sys.stderr)
        return 2
    sections[SEC_BACKLOG] = [render_ide(d) for d in kept]
    stamp_updated(head, args.by)
    write_atomic(path, render_doc(head, sections, order))
    print(f"hapus: {args.key}")
    return 0


def cmd_list(args) -> int:
    path = resolve(args)
    doc = load_doc(path, args)
    if isinstance(doc, int):
        return doc
    _, sections, _ = doc
    ideas, bad = read_backlog(sections)
    if args.status:
        ideas = [d for d in ideas if d.get("status") == args.status]
    print(json.dumps({"module": module_name(args, path), "path": str(path),
                      "ideas": ideas, "malformed": bad},
                     indent=2, ensure_ascii=False))
    return 0


def sync_backlog(ideas, plan):
    """Cocokkan backlog dengan rencana; emit drift deterministik.

    Dua arah, karena backlog basi gagal dua cara: mengklaim yang belum ada, dan
    diam soal yang sudah ada (yang inilah penyebab ide terbangun ditawarkan ulang).
    """
    items = plan.get("items", []) if plan else []
    planned = {str(i.get("function", "")) for i in items}
    applied = {str(i.get("function", "")) for i in items
               if str(i.get("status", "")).lower() in APPLIED}
    by_key = {d["key"]: d for d in ideas}
    drift, info = [], []

    for d in ideas:
        key, status, tgt = d["key"], d.get("status", ""), target_of(d)
        if status == "ditolak":
            continue
        if status == "terwujud" and tgt not in applied:
            drift.append({"key": key, "kind": "terwujud_tanpa_bukti",
                          "detail": f"ide '{key}' berstatus terwujud tapi tak ada item rencana "
                                    f"'{tgt}' ber-status diterapkan"})
        if status in ("baru", "dipilih") and tgt in applied:
            drift.append({"key": key, "kind": "terwujud_belum_ditandai",
                          "detail": f"item rencana '{tgt}' sudah diterapkan tapi ide '{key}' "
                                    f"masih '{status}' — backlog basi, tandai terwujud"})
        if status == "dipilih" and tgt not in planned:
            drift.append({"key": key, "kind": "dipilih_tanpa_rencana",
                          "detail": f"ide '{key}' dipilih tapi tak ada item rencana '{tgt}'"})
        if status == "dipilih":
            for p in [x.strip() for x in (d.get("prasyarat") or "").split(",") if x.strip()]:
                if p not in by_key:
                    drift.append({"key": key, "kind": "prasyarat_belum_terwujud",
                                  "detail": f"prasyarat '{p}' tak dikenal di backlog"})
                elif by_key[p].get("status") != "terwujud":
                    drift.append({"key": key, "kind": "prasyarat_belum_terwujud",
                                  "detail": f"prasyarat '{p}' berstatus "
                                            f"'{by_key[p].get('status')}', belum terwujud"})

    # Item rencana tanpa ide bukan drift: backlog memang bukan cermin rencana.
    # Informasi, seperti 'uncovered' di ps-module-context.py.
    linked = {target_of(d) for d in ideas}
    for fn in sorted(planned - linked):
        info.append({"kind": "rencana_tanpa_ide",
                     "detail": f"item rencana '{fn}' tak punya ide di backlog"})
    return {"ok": not drift, "drift": drift, "info": info}


def cmd_sync(args) -> int:
    path = resolve(args)
    doc = load_doc(path, args)
    if isinstance(doc, int):
        return doc
    _, sections, _ = doc
    ideas, bad = read_backlog(sections)
    plan = None
    if args.plan:
        plan_path = Path(args.plan)
        if not plan_path.exists():
            print(f"error: rencana {plan_path} tak ada", file=sys.stderr)
            return 2
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            print(f"error: rencana {plan_path} bukan JSON valid: {e}", file=sys.stderr)
            return 2
    result = sync_backlog(ideas, plan)
    result["module"] = module_name(args, path)
    result["plan"] = str(args.plan) if args.plan else None
    if bad:
        # Baris rusak bukan drift rencana, tapi tak boleh lolos diam: ia tak
        # pernah cocok apa pun, jadi backlog akan tampak lebih bersih dari aslinya.
        result["malformed"] = bad
        result["ok"] = False
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 1 if not result["ok"] else 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Rawat backlog ide per-module PrestaShop + sync ke rencana -> .psm-ideas.md",
        epilog=MARKER_SCHEMA, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    def addr(p):
        g = p.add_mutually_exclusive_group(required=True)
        g.add_argument("--module-path", help="Folder module (artefak: <module-path>/.psm-ideas.md)")
        g.add_argument("--path", help="Path artefak backlog langsung")

    p = sub.add_parser("init", help="Buat artefak backlog berkerangka")
    addr(p)
    p.add_argument("--domain", help="Satu baris domain & posisi module (prosa awal)")
    p.set_defaults(fn=cmd_init)

    p = sub.add_parser("add", help="Upsert satu ide by key")
    addr(p)
    p.add_argument("--key", required=True, help="Slug ide (identity)")
    p.add_argument("--status", required=True, choices=STATUSES)
    p.add_argument("--arah", required=True, choices=ARAH, help="Arah Lensa adjacency")
    p.add_argument("--prasyarat", help="Key ide lain yang harus terwujud dulu (dipisah koma)")
    p.add_argument("--rencana", help="Nama 'function' di .psm-develop-plan.json (default: key)")
    p.add_argument("--catatan", help="Dampak bisnis / titik sisip / alasan tolak")
    p.add_argument("--by", default="psm-ideate", help="Skill yang menulis")
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("drop", help="Hapus satu ide by key")
    addr(p)
    p.add_argument("--key", required=True)
    p.add_argument("--by", default="psm-ideate")
    p.set_defaults(fn=cmd_drop)

    p = sub.add_parser("sync", help="Cocokkan backlog dengan rencana (rc=1 bila drift)")
    addr(p)
    p.add_argument("--plan", help="Path .psm-develop-plan.json; tanpa ini hanya cek prasyarat")
    p.set_defaults(fn=cmd_sync)

    p = sub.add_parser("list", help="Emit backlog sebagai JSON")
    addr(p)
    p.add_argument("--status", choices=STATUSES, help="Saring per status")
    p.set_defaults(fn=cmd_list)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
