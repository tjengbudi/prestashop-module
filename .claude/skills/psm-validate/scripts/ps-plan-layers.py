#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Pra-pass: putuskan lapis mana yang boleh dipakai-ulang dan mana yang harus dijalankan ulang.

Deterministik: input sama -> keputusan sama. Menjawab satu pertanyaan yang punya satu
jawaban benar — apakah `<reports>/<module>-<lapis>.json` masih mewakili module dan
cakupan versi yang diminta SEKARANG?

Sebuah file lapis boleh dipakai ulang HANYA bila ketiganya benar:
  1. file itu ada dan terbaca sebagai JSON,
  2. mtime-nya LEBIH BARU dari file termuda di source module (vendor/ diabaikan),
  3. cakupan versinya memuat semua versi yang diminta.
Selain itu -> rerun, dengan alasan yang bisa dibaca manusia.

Lapis 4 (E2E) TIDAK lagi dinilai lewat file lapis: buktinya histori append-only per SEL
(versi, browser) `<reports>/<module>-e2e-<ver>-<browser>.jsonl`, dinilai per sel atas
`source_fingerprint` + tag image (cell-contract.md > Evidence record / State, freshness,
gate-grade / Plan). Himpunan sel wajib = psm_target_versions x psm_e2e_browsers dari
--config (bukan --versions). Fungsi bukti E2E di modul ini (source_fingerprint, history_path,
read_history, append_record, derive_state, record_state, is_fresh, is_gate_grade,
is_passing_gate_grade, has_passing_evidence, is_failing, is_not_gradeable, cell_reason,
plan_e2e_cells, derive_e2e_step) dipakai ulang ps-run-layer & ps-aggregate — nama & bentuknya
stabil.

Tier E2E (CAP-1, cell-contract.md > Plan; tier-matrix.md): skrip ini PEMILIK urutan tier.
`derive_e2e_step` (murni, tanpa I/O) menurunkan langkah dari histori sel, yang pertama cocok
menang: `done`, `blocked-not-gradeable`, `blocked-infra`, `gate` (tier 1), `cold-version`,
`cold-canary`, `focus` (tier 0); lalu filter cakupan run `--versions` x `--browsers` (keduanya
cakupan saja; absen -> --config, else default skrip) — langkah ber-tier yang tersaring kosong
jadi `blocked-by-scope`. Kedua mode memancarkan `e2e_step`, `e2e_tier`, `e2e_focus_cell`,
`e2e_focus_recorded_failure`, `e2e_next_cells`, `e2e_required_cells`, `e2e_cells_arg` (nilai
`ps-run-layer.py --cells`), `e2e_blocked_causes`, `e2e_scenarios`, `e2e_warm` dan
`phase1_reuse`; mode `--per-version` juga `per_version[V].phase1_reuse`/`clean` (Lapis 1/2/5
V dinilai lewat fungsi lapis ps-aggregate, dimuat malas). Orkestrator menjalankan PERSIS
`e2e_cells_arg` dgn `--tier <e2e_tier>`, tak pernah memilih tier dgn judgment. Canary
`psm_e2e_canary` dinormalisasi `fl.normalize_canary` (salah bentuk = exit 2).

Sesi: `--new-session` mencetak token acak [a-z0-9]{16} (flag lain apa pun = exit 2);
selain itu `--session <token>` wajib (absen/salah bentuk = exit 2); dipakai langkah
`blocked-infra` dan `e2e_warm` (record sesi ini).

Kenapa skrip, bukan prompt: menghitung mtime rekursif, menstat empat file, dan
membandingkan himpunan versi tiap run adalah kerja mekanis yang mahal diulang dan
berbahaya bila salah — file lapis basi membuat vonis mengklaim coverage atas kode yang
sudah berubah, dan ps-aggregate tak bisa mendeteksinya (ia percaya JSON yang disodorkan).
"""
import argparse
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import secrets
import stat
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

LAYERS = ("static", "flashlight", "adversarial", "e2e", "scenario")
# Lapis yang PUNYA bentuk per-versi. flashlight/e2e dijalankan & disatukan ps-run-layer.py;
# static ditulis per-versi oleh pemanggil lewat -o. `adversarial` sengaja TAK di sini: ia
# satu review lintas-versi di Fase 2 (ps-run-layer menolaknya, agregat cuma baca kanonik).
PER_VERSION_LAYERS = ("static", "flashlight", "e2e", "scenario")

# Default kanonik psm_reports_dir, bentuk TANPA token (relatif cwd project). SKILL.md
# menjanjikan "resolver absen -> lanjut dengan default kanonik skrip", tapi --reports-dir
# dulu required=True tanpa default -> janji itu tak bisa ditepati & satu-satunya bentuk
# tertulis yang dilihat model ber-token ({project-root}/...). Nilai TANPA token supaya tak
# jadi bahan token tak-terekspansi; dikunci ke PSM_DEFAULTS['psm_reports_dir'] via test drift.
DEFAULT_REPORTS_DIR = "_bmad-output/psm-validate"

# "Folder mana yang bukan source module" hanya boleh punya SATU definisi — dua
# implementasi berbeda (substring vs komponen path) pernah sama-sama salah &
# gagal ke arah tak aman. Pakai-ulang dari ps-static-scan (impor by-path karena
# nama file ber-tanda-hubung), pola yang sama dgn ps-e2e-run -> ps-flashlight-run.
def load_sibling(path, name):
    """Muat skrip sibling by-path. Gagal = exit 2 berpesan, bukan traceback telanjang.

    `assert spec and spec.loader` tak menjaga apa pun: spec_from_file_location tetap
    mengembalikan spec sah untuk path yang tak ada, jadi kegagalannya jatuh di exec_module
    sebagai traceback mentah. Folder scripts/ yang disalin sebagian adalah skenario nyata
    (SKILL.md sendiri mengantisipasi salinan tanpa psm-setup).
    """
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if not (spec and spec.loader):
            raise ImportError(f"spec tak terbentuk untuk {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except (OSError, ImportError, SyntaxError) as e:
        print(f"error: skrip sibling tak bisa dimuat: {Path(path).name} ({e})", file=sys.stderr)
        print("skrip psm-validate saling bergantung — salin folder scripts/ utuh", file=sys.stderr)
        sys.exit(2)


ss = load_sibling(Path(__file__).resolve().parent / "ps-static-scan.py", "ps_static_scan")
fl = load_sibling(Path(__file__).resolve().parent / "ps-flashlight-run.py", "ps_flashlight_run")


class PlanInputError(Exception):
    """Input/IO yang membuat vonis mustahil (stat sumber, baca/tulis histori). CLI: exit 2.

    Pesannya selalu menyebut path pemicunya.
    """


def is_bookkeeping_name(name):
    """File catatan di AKAR module yang ditulis skill saudara & tak pernah dimuat PrestaShop.

    Hanya berlaku untuk entri top-level: `.psm-*` (mis. `.psm-develop-plan.json`) dan
    `.memlog.md`. Menulisnya tak boleh membasikan bukti lapis mana pun.
    """
    return name.startswith(".psm-") or name == ".memlog.md"


def _reports_rel(root_real, reports_dir):
    """Posisi folder laporan relatif akar module (keduanya realpath).

    None = di luar module (atau tak disebut); "" = SAMA dengan akar module; selain itu path
    relatif POSIX folder laporan yang terletak tegas DI DALAM module.
    """
    if not reports_dir:
        return None
    rep = os.path.realpath(reports_dir)
    if rep == root_real:
        return ""
    rel = os.path.relpath(rep, root_real)
    if rel == os.pardir or rel.startswith(os.pardir + os.sep) or os.path.isabs(rel):
        return None
    return Path(rel).as_posix()


def newest_source_mtime(module_dir, reports_dir=None):
    """mtime file termuda di source module. Return (mtime, path) — (0.0, None) bila kosong.

    Dilewati: `ss.is_skipped` (vendor/, node_modules/, .git/ — dan penghapusan tetap tak
    membasikan Lapis 1/2/5), file catatan top-level (is_bookkeeping_name), dan `reports_dir`
    bila ia tegas di dalam module — jadi menulis laporan tak membasikan lapis mana pun.
    """
    newest, where = 0.0, None
    module_dir = Path(module_dir)
    skip_rel = _reports_rel(os.path.realpath(module_dir), reports_dir)
    for p in module_dir.rglob("*"):
        if not p.is_file() or ss.is_skipped(p, module_dir):
            continue
        rel = p.relative_to(module_dir)
        if len(rel.parts) == 1 and is_bookkeeping_name(rel.name):
            continue
        if skip_rel and (rel.as_posix() + "/").startswith(skip_rel + "/"):
            continue
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if m > newest:
            newest, where = m, p
    return newest, where


def source_fingerprint(module_dir, reports_dir=None):
    """SHA-256 (hex) atas daftar terurut (path relatif, size, mtime_ns) tiap file module.

    Satu-satunya definisi "source sama" untuk bukti E2E — plan, runner, agregat memanggil ini.
    Akar diresolve realpath, lalu di-walk dengan lstat tanpa pernah mengikuti symlink di
    bawahnya (symlink dicatat sbg entri, tak dimasuki). Dikecualikan: `.git` top-level, file
    catatan top-level (is_bookkeeping_name), dan `reports_dir` bila tegas di dalam module.
    vendor/, node_modules/, tests/e2e TERMASUK (install menyalin seluruh folder). Menambah,
    menghapus, me-rename atau menyentuh file mana pun mengubah fingerprint.

    Entri yang lenyap selama walk dilewati; error stat lain -> PlanInputError (exit 2) yang
    menyebut path-nya. `reports_dir` == akar module juga PlanInputError.
    """
    root = os.path.realpath(module_dir)
    try:
        st_root = os.lstat(root)
    except OSError as e:
        raise PlanInputError(f"akar module tak bisa di-stat: {root} ({e})") from None
    if not stat.S_ISDIR(st_root.st_mode):
        raise PlanInputError(f"akar module bukan folder: {root}")
    skip_rel = _reports_rel(root, reports_dir)
    if skip_rel == "":
        raise PlanInputError(f"folder laporan sama dengan akar module: {root} — "
                             "psm_reports_dir harus di luar module atau di sub-foldernya")
    entries = []
    stack = [(root, "")]
    while stack:
        abs_dir, rel_dir = stack.pop()
        try:
            with os.scandir(abs_dir) as it:
                children = list(it)
        except FileNotFoundError:
            if not rel_dir:
                raise PlanInputError(f"akar module lenyap: {root}") from None
            continue
        except OSError as e:
            raise PlanInputError(f"folder module tak terbaca: {abs_dir} ({e})") from None
        for ent in children:
            rel = f"{rel_dir}/{ent.name}" if rel_dir else ent.name
            if not rel_dir and ent.name == ".git":
                continue
            try:
                st = ent.stat(follow_symlinks=False)
            except FileNotFoundError:
                continue
            except OSError as e:
                raise PlanInputError(f"file module tak bisa di-stat: {ent.path} ({e})") from None
            if stat.S_ISDIR(st.st_mode):
                if rel != skip_rel:
                    stack.append((ent.path, rel))
                continue
            if not rel_dir and is_bookkeeping_name(ent.name):
                continue
            entries.append([rel, st.st_size, st.st_mtime_ns])
    payload = json.dumps(sorted(entries), separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("ascii")).hexdigest()


# --- Histori bukti E2E per sel (cell-contract.md > Evidence record) ------------------
RECORD_STATES = ("pass", "fail", "inconclusive", "not-run")
# Record pass/fail yang salah satu key ini absen/null dibaca `inconclusive`,
# reason `incomplete-record` (aturan authored_assertions=None lama, digeneralisasi).
INCOMPLETE_KEYS = ("session", "source_fingerprint", "image_tag", "boot", "scenario_set",
                   "install", "authored_assertions", "inconclusive", "scenario_notes",
                   "browser_notes")
SESSION_RE = re.compile(r"^[a-z0-9]{16}$")
_SESSION_ALPHABET = "abcdefghijklmnopqrstuvwxyz0123456789"


def new_session_token():
    """Token sesi validasi acak `[a-z0-9]{16}` (dicetak `--new-session`)."""
    return "".join(secrets.choice(_SESSION_ALPHABET) for _ in range(16))


def valid_session(token):
    """True bila `token` berbentuk `[a-z0-9]{16}`."""
    return isinstance(token, str) and bool(SESSION_RE.match(token))


def history_path(reports_dir, module_name, ver, browser):
    """Path histori satu sel: `<reports>/<module>-e2e-<ver>-<browser>.jsonl` (string versi terkonfigurasi)."""
    return Path(reports_dir) / f"{module_name}-e2e-{ver}-{browser}.jsonl"


def parse_utc(value):
    """String UTC ISO-8601 -> datetime ber-tz; selain itu None.

    Menerima `+00:00` maupun `Z`, dengan atau tanpa pecahan detik. Offset selain nol,
    tanpa zona waktu, atau bukan string -> None.
    """
    if not isinstance(value, str) or "T" not in value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None or dt.utcoffset() != timedelta(0):
        return None
    return dt


def _parse_record(raw, ver, browser):
    """Satu baris histori -> dict record, atau None bila baris itu RUSAK.

    Rusak = tak ter-decode/ter-parse jadi objek JSON, `started_at` bukan UTC ISO-8601,
    `state` di luar enum, atau `version`/`browser` bukan sel file ini.
    """
    try:
        rec = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(rec, dict):
        return None
    if parse_utc(rec.get("started_at")) is None:
        return None
    if rec.get("state") not in RECORD_STATES:
        return None
    if rec.get("version") != ver or rec.get("browser") != browser:
        return None
    return rec


def read_history(path, ver, browser):
    """Baca histori satu sel di bawah LOCK_SH. Return (records, corrupt_tail).

    `records` = record valid dalam urutan append (yang terakhir = terbaru; started_at tak
    pernah dipakai untuk mengurutkan dalam satu sel). Baris rusak dilewati dan tak
    menyembunyikan record sebelumnya; `corrupt_tail` True selama tak ada baris valid sesudah
    baris rusak terakhir (sel itu: reason `corrupt-history`, tanpa bukti lulus). Baris kosong
    bukan baris. File absen -> ([], False). Error OS lain -> PlanInputError (exit 2).
    """
    try:
        with open(path, "rb") as f:
            fcntl.flock(f.fileno(), fcntl.LOCK_SH)
            try:
                data = f.read()
            finally:
                fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except FileNotFoundError:
        return [], False
    except OSError as e:
        raise PlanInputError(f"histori E2E tak terbaca: {path} ({e})") from None
    records, corrupt_tail = [], False
    for raw in data.split(b"\n"):
        if not raw.strip():
            continue
        rec = _parse_record(raw, ver, browser)
        if rec is None:
            corrupt_tail = True
        else:
            records.append(rec)
            corrupt_tail = False
    return records, corrupt_tail


def append_record(path, record):
    """Tambahkan SATU record ke histori sel: satu write() di bawah LOCK_EX.

    Diawali `\\n` bila byte terakhir file bukan newline (penulis yang terbunuh di tengah
    baris), jadi baris setengah jadi itu tetap terbaca sbg satu baris rusak, bukan menelan
    record baru. Baris tak pernah ditulis ulang. Error OS -> PlanInputError (exit 2).
    """
    data = (json.dumps(record, ensure_ascii=True) + "\n").encode("ascii")
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            size = os.fstat(fd).st_size
            if size and os.pread(fd, 1, size - 1) != b"\n":
                data = b"\n" + data
            written = os.write(fd, data)
            while written < len(data):  # tulis pendek (jarang di file biasa): sisanya, masih ber-lock
                written += os.write(fd, data[written:])
        finally:
            os.close(fd)  # melepas LOCK_EX
    except OSError as e:
        raise PlanInputError(f"histori E2E tak bisa ditulis: {path} ({e})") from None


# --- State, freshness, gate-grade (cell-contract.md) ------------------------------
def _driven(phase_durations, engine):
    keys = (phase_durations or {}) if isinstance(phase_durations, dict) else {}
    head = f"{fl.CELL_PHASE_PREFIX}{engine}"
    return any(k == head or k.startswith(head + "#") for k in keys)


def derive_state(cell, engine=None):
    """Aturan State atas hasil satu sel (dipakai ps-run-layer saat merge). Return
    {state, conclusive, reason}.

    `inconclusive` bila engine tak di-drive (tak ada `browser:<engine>` di phase_durations
    sel), `errors` tak kosong, `install.ok` tak true, atau `launch_error` terisi; reason =
    sebab pertama: `install` (hasil install yang ok-nya tak true), `launch-error`, `errors`,
    `not-driven` (install absen/null tanpa sebab lain juga `install`). Selain itu `fail` bila
    `findings` tak kosong, else `pass`.
    """
    engine = engine or cell.get("browser")
    install = cell.get("install")
    install_ok = isinstance(install, dict) and install.get("ok") is True
    driven = _driven(cell.get("phase_durations"), engine)
    if not driven or cell.get("errors") or not install_ok or cell.get("launch_error"):
        if isinstance(install, dict) and not install_ok:
            reason = "install"
        elif cell.get("launch_error"):
            reason = "launch-error"
        elif cell.get("errors"):
            reason = "errors"
        elif not driven:
            reason = "not-driven"
        else:
            reason = "install"
        return {"state": "inconclusive", "conclusive": False, "reason": reason}
    if cell.get("findings"):
        return {"state": "fail", "conclusive": True, "reason": None}
    return {"state": "pass", "conclusive": True, "reason": None}


def record_state(rec):
    """State EFEKTIF record yang dibaca dari histori: {state, conclusive, reason}.

    Pembaca percaya state tersimpan, kecuali aturan incomplete-record: `pass`/`fail` yang
    salah satu INCOMPLETE_KEYS-nya absen/null -> `inconclusive`, reason `incomplete-record`.
    `conclusive` = state pass/fail; reason null untuk pass/fail.
    """
    state = rec.get("state")
    if state in ("pass", "fail"):
        if any(rec.get(k) is None for k in INCOMPLETE_KEYS):
            return {"state": "inconclusive", "conclusive": False, "reason": "incomplete-record"}
        return {"state": state, "conclusive": True, "reason": None}
    return {"state": state, "conclusive": False, "reason": rec.get("reason")}


def is_fresh(rec, fingerprint, image_tag):
    """Segar = source_fingerprint record == fingerprint sekarang DAN image_tag == tag ter-resolve."""
    return (rec.get("source_fingerprint") is not None
            and rec.get("source_fingerprint") == fingerprint
            and rec.get("image_tag") is not None and rec.get("image_tag") == image_tag)


def is_gate_grade(rec, fingerprint, image_tag):
    """Gate-grade = segar + conclusive (efektif) + `boot: cold` + `scenario_set: full`."""
    return (is_fresh(rec, fingerprint, image_tag) and record_state(rec)["conclusive"]
            and rec.get("boot") == "cold" and rec.get("scenario_set") == "full")


def _authored(rec):
    a = rec.get("authored_assertions")
    return a if isinstance(a, int) and not isinstance(a, bool) else None


def is_passing_gate_grade(rec, fingerprint, image_tag):
    """Gate-grade + state pass + `inconclusive` kosong + authored_assertions >= 1 +
    `scenario_notes` kosong + `browser_notes` kosong."""
    return (is_gate_grade(rec, fingerprint, image_tag)
            and record_state(rec)["state"] == "pass"
            and not rec.get("inconclusive")
            and (_authored(rec) or 0) >= 1
            and not rec.get("scenario_notes")
            and not rec.get("browser_notes"))


def _newest(records, pred):
    for rec in reversed(records):
        if pred(rec):
            return rec
    return None


def newest_gate_grade(records, fingerprint, image_tag):
    """Record gate-grade TERBARU (urutan append) sebuah sel, atau None."""
    return _newest(records, lambda r: is_gate_grade(r, fingerprint, image_tag))


def has_passing_evidence(records, corrupt_tail, fingerprint, image_tag):
    """Sel punya bukti lulus gate-grade: record gate-grade TERBARU-nya passing gate-grade.

    `fail` gate-grade yang lebih baru selalu mengalahkan pass lama; ekor histori rusak
    (corrupt_tail) = tak pernah punya bukti lulus.
    """
    if corrupt_tail:
        return False
    g = newest_gate_grade(records, fingerprint, image_tag)
    return g is not None and is_passing_gate_grade(g, fingerprint, image_tag)


def newest_cold_full(records):
    """Record cold, full-scenario, conclusive (efektif) TERBARU — segar atau basi — atau None."""
    return _newest(records, lambda x: x.get("boot") == "cold" and x.get("scenario_set") == "full"
                   and record_state(x)["conclusive"])


def is_failing(records):
    """Plan > Derivation `failing`: record cold, full, conclusive TERBARU (segar atau basi) = fail."""
    r = newest_cold_full(records)
    return r is not None and record_state(r)["state"] == "fail"


def has_recorded_failure(records):
    """Plan `recorded failure`: record conclusive TERBARU (boot, set skenario, kesegaran apa pun) = fail."""
    r = _newest(records, lambda x: record_state(x)["conclusive"])
    return r is not None and record_state(r)["state"] == "fail"


def _notes_equal(a, b):
    return list(a or []) == list(b or [])


def is_not_gradeable(records, fingerprint, image_tag, current_notes):
    """Plan > Derivation `not-gradeable`: record gate-grade terbaru = pass dgn `inconclusive`
    kosong yang authored_assertions-nya 0, ATAU yang scenario_notes-nya tak kosong & SAMA dgn
    `e2e_scenario_notes` sekarang (`current_notes`, dari _e2e_scenario_notes)."""
    g = newest_gate_grade(records, fingerprint, image_tag)
    if g is None or record_state(g)["state"] != "pass" or g.get("inconclusive"):
        return False
    if _authored(g) == 0:
        return True
    notes = g.get("scenario_notes")
    return bool(notes) and _notes_equal(notes, current_notes)


def cell_reason(records, corrupt_tail, fingerprint, image_tag, current_notes):
    """Alasan rerun satu sel (cell-contract.md > Plan), None bila sel punya bukti lulus.

    Urutan, yang pertama berlaku: `corrupt-history`; `missing` (tak ada record valid);
    tanpa record segar -> menilai record valid terbaru: fingerprint cocok tapi tag beda ->
    `stale-tag`, selain itu `stale-source`; lalu menurut record SEGAR terbaru: `fail`,
    `not-run`, `inconclusive`, `warm-only`, `partial`, `inconclusive-steps` (pass gate-grade
    dgn `inconclusive` tak kosong), `not-gradeable`, `scenario-notes` (notes tak kosong yang
    beda dari notes sekarang), `browser-notes` (pass gate-grade lain yang tak passing).
    """
    if corrupt_tail:
        return "corrupt-history"
    if has_passing_evidence(records, corrupt_tail, fingerprint, image_tag):
        return None
    if not records:
        return "missing"
    fresh = _newest(records, lambda r: is_fresh(r, fingerprint, image_tag))
    if fresh is None:
        last = records[-1]
        if last.get("source_fingerprint") == fingerprint and fingerprint is not None:
            return "stale-tag"
        return "stale-source"
    st = record_state(fresh)["state"]
    if st in ("fail", "not-run", "inconclusive"):
        return st
    if fresh.get("boot") != "cold":
        return "warm-only"
    if fresh.get("scenario_set") != "full":
        return "partial"
    if fresh.get("inconclusive"):
        return "inconclusive-steps"
    if is_not_gradeable(records, fingerprint, image_tag, current_notes):
        return "not-gradeable"
    notes = fresh.get("scenario_notes")
    if notes and not _notes_equal(notes, current_notes):
        return "scenario-notes"
    return "browser-notes"


def cell_key(ver, browser):
    """Nama sel `"<ver>:<browser>"` — bentuk yang dipakai e2e_* plan & psm_e2e_canary."""
    return f"{ver}:{browser}"


def split_cell(cell):
    """`"<ver>:<browser>"` -> (ver, browser)."""
    ver, _, browser = cell.partition(":")
    return ver, browser


def read_e2e_histories(reports_dir, module_name, versions, browsers):
    """Baca histori tiap sel terkonfigurasi -> {"<ver>:<browser>": (records, corrupt_tail)}.

    Urutan kunci = versi (urut numerik) lalu psm_e2e_browsers. Error baca -> PlanInputError.
    """
    return {cell_key(v, b): read_history(history_path(reports_dir, module_name, v, b), v, b)
            for v in versions for b in browsers}


def plan_e2e_cells(reports_dir, module_name, versions, browsers, fingerprint, tag_map,
                   current_notes, histories=None):
    """Vonis tiap sel terkonfigurasi -> {ver: {browser: {reuse, reason, path}}}.

    `versions` (urut numerik) x `browsers` (urut psm_e2e_browsers) = himpunan TERKONFIGURASI,
    bukan --versions. `path` = histori sel; `reason` null saat reuse. `histories` (hasil
    read_e2e_histories) opsional supaya histori tak dibaca dua kali; absen -> dibaca di sini.
    Error baca histori -> PlanInputError (exit 2).
    """
    out = {}
    for ver in versions:
        tag = fl.resolve_tag(tag_map, ver)
        row = {}
        for browser in browsers:
            path = history_path(reports_dir, module_name, ver, browser)
            if histories is not None and cell_key(ver, browser) in histories:
                records, corrupt_tail = _history_entry(histories[cell_key(ver, browser)])
            else:
                records, corrupt_tail = read_history(path, ver, browser)
            reason = cell_reason(records, corrupt_tail, fingerprint, tag, current_notes)
            row[browser] = {"reuse": reason is None, "reason": reason, "path": str(path)}
        out[ver] = row
    return out


# --- Tier E2E (cell-contract.md > Plan; tier-matrix.md > Loop-back) -------------------
# Langkah tier diturunkan MURNI dari histori sel (derive_e2e_step, tanpa I/O): urutan tier
# milik skrip ini, bukan judgment orkestrator — ia menjalankan PERSIS e2e_cells_arg dengan
# --tier <e2e_tier>.
E2E_STEP_TIER = {"focus": 0, "cold-version": 0, "cold-canary": 0, "gate": 1}
E2E_BLOCKED_STEPS = ("blocked-not-gradeable", "blocked-infra")
WARM_BLOCK_REASONS = ("warm-reset", "keeper-start")
_UTC_MIN = datetime.min.replace(tzinfo=timezone.utc)


def _history_entry(value):
    """Nilai `histories[sel]` -> (records, corrupt_tail).

    Diterima: list record (ekor tak rusak), tuple/list `(records, corrupt_tail)` hasil
    read_history, atau None (tanpa record).
    """
    if value is None:
        return [], False
    if (isinstance(value, (tuple, list)) and len(value) == 2 and isinstance(value[1], bool)
            and isinstance(value[0], list)):
        return list(value[0]), value[1]
    recs = list(value)
    if not all(isinstance(r, dict) for r in recs):
        raise ValueError("histories[sel] harus list record (dict) atau (records, corrupt_tail)")
    return recs, False


def infra_cause(rec):
    """Sebab infra satu record (Plan langkah 3), apa pun boot/set skenarionya, atau None.

    `inconclusive` (efektif, termasuk incomplete-record) -> reason-nya; `pass` dgn
    `inconclusive` tak kosong -> `inconclusive-steps`; `pass` lain dgn `browser_notes` tak
    kosong -> `browser-notes`; selain itu (fail, pass bersih, not-run) None — memutus pasangan.
    """
    st = record_state(rec)
    if st["state"] == "inconclusive":
        return st["reason"] or "inconclusive"
    if st["state"] == "pass":
        if rec.get("inconclusive"):
            return "inconclusive-steps"
        if rec.get("browser_notes"):
            return "browser-notes"
    return None


def infra_blocked_cause(records, fingerprint, image_tag, session):
    """Plan langkah 3 untuk satu sel: sebab infra record terbaru bila DUA record terbaru —
    tanpa menghitung record ber-reason `stopped` (stop operator: dilewati, tak dihitung dan tak
    memutus) — sama-sama ber-`--session` sekarang, segar (fingerprint sama) dan ber-sebab infra
    (sebab sama atau beda). Selain itu None."""
    recent = [r for r in records if r.get("reason") != "stopped"][-2:]
    if len(recent) < 2:
        return None
    if any(r.get("session") != session or not is_fresh(r, fingerprint, image_tag)
           for r in recent):
        return None
    causes = [infra_cause(r) for r in recent]
    if any(c is None for c in causes):
        return None
    return causes[-1]


def _is_warm_or_partial(rec):
    return rec.get("boot") == "warm" or rec.get("scenario_set") == "partial"


def diverges(records, fingerprint):
    """Focus cell DIVERGE (bacaan Budi, ronde 1): ada `fail` cold full atas fingerprint sekarang
    yang LEBIH BARU di histori sel daripada `pass` warm/partial atas fingerprint itu
    (`source_fingerprint` saja, tag tak dinilai) — residu/urutan yang disembunyikan reset warm
    atau subset."""
    soft_pass = False
    for r in records:
        if fingerprint is None or r.get("source_fingerprint") != fingerprint:
            continue
        st = record_state(r)["state"]
        if st == "pass" and _is_warm_or_partial(r):
            soft_pass = True
        elif (soft_pass and st == "fail" and r.get("boot") == "cold"
              and r.get("scenario_set") == "full"):
            return True
    return False


def failed_set(rec):
    """Failed set record (Failed-only rerun): union `findings[].scenario` & `inconclusive[].scenario`.

    Plan hanya menguji kekosongannya: cuma nilai `scenario` string tak kosong yang dihitung
    (null / non-string diabaikan). Return set nama.
    """
    out = set()
    for key in ("findings", "inconclusive"):
        items = rec.get(key)
        if not isinstance(items, list):
            continue
        for it in items:
            name = it.get("scenario") if isinstance(it, dict) else None
            if isinstance(name, str) and name:
                out.add(name)
    return out


def _focus_cell(cells, hist, canary):
    """Focus cell: di antara sel failing, yang record failing-nya milik run TERBARU (run =
    record ber-`job_id` sama; `job_id` null = run sendiri; run terbaru memegang record failing
    ber-`started_at` tertinggi — seri lintas run diputus seperti di dalam run). Seri di dalam
    run: urutan versi numerik (tertua dulu) lalu psm_e2e_browsers = urutan `cells`. Tanpa sel
    failing -> canary."""
    failing = []
    for c in cells:
        r = newest_cold_full(hist[c][0])
        if r is not None and record_state(r)["state"] == "fail":
            failing.append((c, r))
    if not failing:
        return canary
    best = None
    for c, r in failing:  # `>` ketat: seri jatuh ke sel pertama dalam urutan `cells`
        t = parse_utc(r.get("started_at")) or _UTC_MIN
        if best is None or t > best[2]:
            best = (c, r, t)
    run = best[1].get("job_id")
    if run is None:
        return best[0]
    return next(c for c, r in failing if r.get("job_id") == run)


def e2e_cells_arg(cells):
    """`e2e_next_cells` dikelompokkan per versi sbg nilai `ps-run-layer.py --cells`:
    `<ver>:<browser>[+<browser>],...` (versi berurutan seperti di daftar, browser dlm urutan
    daftar). Daftar kosong -> None."""
    if not cells:
        return None
    groups = {}
    for c in cells:
        ver, browser = split_cell(c)
        groups.setdefault(ver, []).append(browser)
    return ",".join(f"{ver}:{'+'.join(bs)}" for ver, bs in groups.items())


def derive_e2e_step(histories, cells, canary, scope_versions, scope_browsers, fingerprint,
                    tag_map, session, *, current_notes=None):
    """Turunkan langkah tier E2E dari histori sel — MURNI (tanpa I/O). Return semua field tier.

    `histories` = {"<ver>:<browser>": records | (records, corrupt_tail)} yang sudah dibaca;
    `cells` = sel terkonfigurasi `"<ver>:<browser>"` urut versi numerik lalu psm_e2e_browsers;
    `canary` = hasil fl.normalize_canary; `scope_versions`/`scope_browsers` = cakupan run
    (--versions/--browsers); `tag_map` = fl.parse_tag_map; `session` = token --session;
    `current_notes` = e2e_scenario_notes sekarang (pembanding not-gradeable).

    Langkah, yang pertama cocok menang (cell-contract.md > Plan): 1 `done`, 2
    `blocked-not-gradeable`, 3 `blocked-infra`, 4 `gate`, 5 `cold-version`, 6 `cold-canary`,
    7 `focus`. Di langkah 4–7 sel not-gradeable dihitung punya bukti lulus. Lalu filter cakupan
    run: `e2e_next_cells` hanya sel di dalam scope_versions x scope_browsers; bila langkah
    ber-tier tersaring kosong -> `blocked-by-scope` (tier langkah yang diblok).

    Return {e2e_step, e2e_tier, e2e_focus_cell, e2e_focus_recorded_failure, e2e_next_cells,
    e2e_required_cells, e2e_cells_arg, e2e_blocked_causes, e2e_scenarios, e2e_warm}.
    """
    cells = list(cells)
    if canary not in cells:  # API murni dipakai ulang: galat input, bukan KeyError
        raise ValueError(f"canary {canary!r} bukan sel terkonfigurasi ({', '.join(cells)})")
    notes = list(current_notes or [])
    hist = {c: _history_entry(histories.get(c)) for c in cells}
    tags = {c: fl.resolve_tag(tag_map, split_cell(c)[0]) for c in cells}
    passing, ok47, failing = {}, {}, {}
    not_gradeable = {}
    for c in cells:
        recs, tail = hist[c]
        passing[c] = has_passing_evidence(recs, tail, fingerprint, tags[c])
        # Bacaan harfiah kontrak (Plan > not-gradeable menilai record gate-grade terbaru saja,
        # tanpa pengecualian ekor rusak): sel corrupt-tail yang pass terakhirnya smoke-only tetap
        # not-gradeable. Menambal ekornya = ubah aturan kontrak -> deferred-work (CAP-1 review r5).
        not_gradeable[c] = (not passing[c]
                            and is_not_gradeable(recs, fingerprint, tags[c], notes))
        ok47[c] = passing[c] or not_gradeable[c]
        failing[c] = is_failing(recs)
    focus = _focus_cell(cells, hist, canary)

    def newest_fresh_conclusive(c):
        return _newest(hist[c][0], lambda r: is_fresh(r, fingerprint, tags[c])
                       and record_state(r)["conclusive"])

    def is_pass(rec):
        return rec is not None and record_state(rec)["state"] == "pass"

    causes = {}
    if all(passing.values()):
        step, required = "done", []
    elif all(ok47.values()):
        step = "blocked-not-gradeable"
        causes = {c: "not-gradeable" for c in cells if not_gradeable[c]}
        required = list(causes)
    else:
        infra = {}
        for c in cells:
            cause = infra_blocked_cause(hist[c][0], fingerprint, tags[c], session)
            if cause is not None:
                infra[c] = cause
        if infra:
            step, causes, required = "blocked-infra", infra, list(infra)
        elif ok47[canary] and not any(failing.values()):
            step, required = "gate", [c for c in cells if not ok47[c]]
        elif focus != canary and is_pass(newest_fresh_conclusive(focus)):
            fver = split_cell(focus)[0]
            step, required = "cold-version", [c for c in cells if split_cell(c)[0] == fver]
        elif (not any(failing[c] for c in cells if c != canary) and not ok47[canary]
              and (is_pass(newest_fresh_conclusive(canary))
                   or (newest_fresh_conclusive(canary) is None
                       and is_pass(newest_cold_full(hist[canary][0]))))):
            step, required = "cold-canary", [canary]
        else:
            step, required = "focus", [focus]

    focus_recs = hist[focus][0]
    recorded = has_recorded_failure(focus_recs)
    warm, scenarios = False, "full"
    if step == "focus" and recorded and not diverges(focus_recs, fingerprint):
        warm = not any(r.get("session") == session and r.get("reason") in WARM_BLOCK_REASONS
                       for r in focus_recs)
        latest_full = _newest(focus_recs, lambda r: r.get("scenario_set") == "full")
        if latest_full is not None and failed_set(latest_full):
            scenarios = "failed-only"

    tier = E2E_STEP_TIER.get(step)
    next_cells = []
    if tier is not None:
        sv, sb = set(scope_versions), set(scope_browsers)
        next_cells = [c for c in required if split_cell(c)[0] in sv and split_cell(c)[1] in sb]
        if not next_cells:
            # Cakupan run menyingkirkan semua sel langkah ini: tak ada yang jalan, tier tetap
            # tier langkah yang diblok, field fix-loop kembali ke cold full.
            step, causes = "blocked-by-scope", {c: "out-of-scope" for c in required}
            warm, scenarios = False, "full"
    return {"e2e_step": step, "e2e_tier": tier, "e2e_focus_cell": focus,
            "e2e_focus_recorded_failure": recorded, "e2e_next_cells": next_cells,
            "e2e_required_cells": required, "e2e_cells_arg": e2e_cells_arg(next_cells),
            "e2e_blocked_causes": causes, "e2e_scenarios": scenarios, "e2e_warm": warm}


def layer_versions(payload):
    """Versi yang DITINJAU file lapis. None = tak bisa ditentukan (jangan pakai ulang).

    Dua bentuk sah: `versions` dict (static/flashlight/e2e, kunci = versi) dan
    `versions` list (lapis adversarial menyatakan cakupan yang ditinjau — lihat
    references/adversarial-lens.md). Cakupan TAK diturunkan dari `findings`:
    versi di temuan adalah versi TERPENGARUH, bukan yang ditinjau — review 3 versi
    yang menemukan satu bug di 8.1 akan terbaca "cuma meninjau 8.1".
    """
    if not isinstance(payload, dict):
        return None
    versions = payload.get("versions")
    if isinstance(versions, dict):
        return set(versions.keys())
    if isinstance(versions, list) and all(isinstance(v, str) for v in versions):
        return set(versions)
    return None


def plan_layer(path, requested, src_mtime, src_path, provenance=None):
    """Putuskan reuse/rerun satu file lapis + alasannya.

    `provenance` = INPUT KEDUA lapis ini (selain source module), bila punya. Tiap lapis punya
    satu, dan membandingkan mtime module saja membuat perubahan pada input kedua itu tak pernah
    menyala di file lapis yang dipakai ulang:
      {"kind": "ruleset", "files": [...], "mtime": float}  — Lapis 1: aturan KB baru ditambahkan
      {"kind": "image", "expect": {versi: tag}}             — Lapis 2/4: tag-map di-bump, jadi
          file lapis lama memvonis core yang BERBEDA dari yang jadi target sekarang

    Dulu param ini bernama `ruleset` dan hanya Lapis 1 yang mengisinya — padahal alasan yang
    ditulisnya berlaku sama persis untuk Lapis 2/4, yang bahkan SUDAH mencatat tag/image-nya dan
    tak dibaca siapa pun. Bentuk umum ini supaya input kedua Lapis 3 (kontrak lensa adversarial)
    punya rumah kalau nanti dipasang, bukan jadi korban berikutnya.
    """
    p = Path(path)
    if not p.is_file():
        return {"reuse": False, "reason": "file lapis belum ada", "path": str(p)}
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"reuse": False, "reason": f"file lapis tak terbaca ({str(e)[:60]})", "path": str(p)}
    try:
        age = p.stat().st_mtime
    except OSError:
        return {"reuse": False, "reason": "mtime file lapis tak terbaca", "path": str(p)}
    if age <= src_mtime:
        where = f" ({src_path})" if src_path else ""
        return {"reuse": False, "reason": f"module lebih baru dari file lapis{where}", "path": str(p)}
    kind = (provenance or {}).get("kind")
    if kind == "ruleset":
        recorded = payload.get("ruleset")
        if not isinstance(recorded, dict) or not recorded.get("files"):
            return {"reuse": False, "path": str(p),
                    "reason": "file lapis tak mencatat ruleset yang memproduksinya"}
        if set(recorded.get("files") or []) != set(provenance["files"]):
            return {"reuse": False, "path": str(p),
                    "reason": "ruleset berbeda dari yang memproduksi file lapis"}
        if provenance["mtime"] > float(recorded.get("mtime") or 0.0):
            return {"reuse": False, "path": str(p), "reason": "ruleset lebih baru dari file lapis"}
    elif kind == "image":
        # Versi yang TAK ada di file lapis dilewati di sini — itu celah cakupan, dan pemeriksaan
        # `missing` di bawah yang menjawabnya dengan alasan yang benar.
        vers = payload.get("versions") or {}
        for ver in requested:
            entry = vers.get(ver)
            if not isinstance(entry, dict):
                continue
            recorded_tag = entry.get("tag")
            expect = (provenance.get("expect") or {}).get(ver)
            if not recorded_tag:
                return {"reuse": False, "path": str(p),
                        "reason": "file lapis tak mencatat tag image yang memproduksinya"}
            if expect and recorded_tag != expect:
                return {"reuse": False, "path": str(p),
                        "reason": f"image berbeda dari yang memproduksi file lapis "
                                  f"({ver}: {recorded_tag} vs {expect})"}
    covered = layer_versions(payload)
    if covered is None:
        return {"reuse": False, "reason": "cakupan versi file lapis tak bisa dipastikan", "path": str(p)}
    # Nol versi diminta = `set() - covered` kosong = "cakupan cocok" secara vakum, dan justru
    # skrip yang tugasnya MENOLAK bukti basi yang mengucapkannya. File lapis yang meninjau versi
    # yang sama sekali lain pun lolos. Kembaran gerbang himpunan kosong di ps-aggregate; dijaga
    # di sini juga karena plan_layer bisa diimpor, bukan cuma dipanggil lewat main().
    if not requested:
        return {"reuse": False, "path": str(p),
                "reason": "cakupan tak bisa dinilai atas nol versi diminta"}
    missing = sorted(set(requested) - covered)
    if missing:
        return {"reuse": False, "reason": f"cakupan kurang: {', '.join(missing)}", "path": str(p)}
    return {"reuse": True, "reason": "lebih baru dari module & cakupan versi cocok", "path": str(p)}


def per_version_path(reports_dir, module_name, layer, ver):
    """Path file lapis PER-VERSI — `<reports>/<module>-<lapis>-<versi>.json`.

    Diturunkan dari (folder laporan, module, lapis, versi) di dalam skrip, tak pernah dari
    daftar yang diketik pemanggil: gerbang identitas file lapis kanonik (ps-run-layer.layer_file)
    berlaku sama di sini — bukti tak bisa mendarat di file module/lapis/versi lain. Segmen versi
    selalu ada, jadi tak pernah bentrok dengan nama kanonik `<module>-<lapis>.json`.
    """
    return Path(reports_dir) / f"{module_name}-{layer}-{ver}.json"


def prov_for(layer, versions, ruleset, tag_map):
    """Provenance (INPUT KEDUA) satu lapis atas himpunan versi ini — lihat plan_layer.

    Satu pemilik untuk "input kedua lapis apa": mode kanonik & mode per-versi memanggil fungsi
    yang SAMA, jadi keduanya tak bisa mendrift. static -> ruleset; flashlight/e2e -> image (tag
    yang diharapkan diresolve lewat ps-flashlight-run, bukan disalin); adversarial -> None
    (judgment model belum punya jejak yang bisa dibandingkan).
    """
    if layer == "static":
        return {"kind": "ruleset", **ruleset}
    if layer in ("flashlight", "e2e", "scenario"):
        # scenario ikut kanal image: ia mem-boot core yang sama, jadi bukti dari tag lain
        # sama basinya seperti pada flashlight/e2e.
        return {"kind": "image", "expect": {v: fl.resolve_tag(tag_map, v) for v in versions}}
    return None


def plan_per_version(reports_dir, module_name, requested, src_mtime, rel, ruleset, tag_map, *,
                     e2e_cells):
    """Vonis reuse/rerun tiap (lapis, versi) atas file per-versi, tiap versi DINILAI SENDIRI.

    Inti siklus version-first: file per-versi 9.1 yang basi tak menyeret file 8.1 yang segar ke
    rerun — beda dengan file kanonik satu-untuk-semua-versi yang satu patch source membasikannya
    serentak. Tiap file per-versi mestinya bercakupan PERSIS {versi}-nya; plan_layer([versi])
    menuntut itu (cakupan kurang/lebih -> rerun beralasan). Deterministik: urutan versi mengikuti
    `requested`, urutan lapis mengikuti LAYERS.

    Lapis `e2e` TIDAK dinilai dari file: `layers.e2e` = entri sel versi itu dari `e2e_cells`
    (hasil plan_e2e_cells, wajib), berkunci browser `{reuse, reason, path}`; `rerun` memuat
    `e2e` selama salah satu browser versi itu reuse=false.
    """
    out = {}
    for ver in requested:
        layers = {}
        for layer in LAYERS:
            if layer == "e2e":
                layers[layer] = dict(e2e_cells.get(ver) or {})
                continue
            path = per_version_path(reports_dir, module_name, layer, ver)
            layers[layer] = plan_layer(path, [ver], src_mtime, rel,
                                       provenance=prov_for(layer, [ver], ruleset, tag_map))
        out[ver] = {"layers": layers, "rerun": _rerun_list(layers)}
    return out


def _rerun_list(layers):
    """Lapis yang rerun, urut LAYERS. `e2e` (berkunci browser) rerun bila ada sel reuse=false."""
    out = []
    for layer in LAYERS:
        entry = layers.get(layer)
        if entry is None:
            continue
        if layer == "e2e":
            if any(not c["reuse"] for c in entry.values()):
                out.append(layer)
        elif not entry["reuse"]:
            out.append(layer)
    return out


def canonical_e2e_layer(e2e_cells):
    """Bentuk `layers.e2e` mode kanonik: {browser: {ver: {reuse, reason, path}}} atas sel terkonfigurasi."""
    out = {}
    for ver, row in e2e_cells.items():
        for browser, entry in row.items():
            out.setdefault(browser, {})[ver] = entry
    return out


def per_version_rollup(per_version, e2e_cells):
    """Roll-up Fase 2: `all_reuse` + matriks (lapis, versi[, browser]) yang masih rerun.

    Mode kanonik selalu punya roll-up `rerun` top-level; mode per-versi dulu tidak, jadi
    model meng-union sampai 4 lapis x N versi boolean DENGAN TANGAN di tiap iterasi loop
    konvergensi — hitung/banding murni dengan satu jawaban benar.

    `per_version_capable` menandai cara tiap entri diproduksi: `ps-run-layer.py` hanya
    menjalankan/menyatukan lapis PER-VERSI (flashlight, e2e); `static` ditulis per-versi oleh
    pemanggil lewat `-o`, sedangkan `adversarial` sama sekali tak punya bentuk per-versi —
    ia satu review lintas-versi di Fase 2.

    Entri lapis non-e2e dibatasi versi di `per_version` (--versions), urut versi lalu LAYERS.
    Entri `e2e` menyusul, meliputi SETIAP sel terkonfigurasi di `e2e_cells` yang tak punya
    bukti lulus, berapa pun --versions (urut versi numerik lalu psm_e2e_browsers), dan
    membawa `browser` + `reason`. `all_reuse` = tiap `per_version[V].rerun` kosong —
    informatif saja (mode per-versi selalu memuat `adversarial`).
    """
    matrix = []
    for ver, entry in per_version.items():
        for layer in entry["rerun"]:
            if layer == "e2e":
                continue
            matrix.append({"layer": layer, "version": ver,
                           "per_version_capable": layer in PER_VERSION_LAYERS})
    for ver, row in e2e_cells.items():
        for browser, cell in row.items():
            if not cell["reuse"]:
                matrix.append({"layer": "e2e", "version": ver, "browser": browser,
                               "reason": cell["reason"],
                               # e2e dijalankan lewat `--cells`, bukan `--per-version` (exit 2)
                               "per_version_capable": False})
    return {"all_reuse": all(not e["rerun"] for e in per_version.values()),
            "rerun_matrix": matrix}


# --- Fase 1: phase1_reuse & clean (cell-contract.md > Plan > Phase 1) ---------------
# Lapis yang TAK menggerbang Fase 1: e2e (diurus tier) dan adversarial (Fase 2).
PHASE1_FREE_LAYERS = ("e2e", "adversarial")
# Lapis per-versi yang dinilai `clean` + kunci temuan yang diwajibkan gerbang bentuknya
# (sama dgn gerbang ps-aggregate main: static membaca id/severity/message langsung).
CLEAN_LAYERS = (("static", ("id", "severity", "message")), ("flashlight", ()), ("scenario", ()))
_AGG = {"mod": None}


def phase1_reuse_of(rerun):
    """True bila tak ada lapis selain e2e/adversarial di daftar `rerun`."""
    return all(layer in PHASE1_FREE_LAYERS for layer in rerun)


def _aggregate():
    """ps-aggregate dimuat MALAS (ia memuat modul ini saat impor; ia membawa instans
    ps_plan_layers-nya sendiri). Dipakai hanya untuk fungsi lapis + validate_layer_shape."""
    if _AGG["mod"] is None:
        _AGG["mod"] = load_sibling(Path(__file__).resolve().parent / "ps-aggregate.py",
                                   "ps_aggregate")
    return _AGG["mod"]


def _list_of_objects(val):
    return isinstance(val, list) and all(isinstance(x, dict) for x in val)


def _scenario_shape_notes(payload, ver):
    """Gerbang bentuk tambahan payload skenario: `versions[ver].scenarios` dan `steps` tiap
    skenario, bila ada, harus list objek (scenario_layer membacanya dgn .get)."""
    versions = payload.get("versions")
    if not isinstance(versions, dict):  # validate_layer_shape sudah menandainya; jangan crash
        return []
    entry = versions.get(ver)
    if not isinstance(entry, dict) or "scenarios" not in entry:
        return []
    scen = entry["scenarios"]
    if not _list_of_objects(scen):
        return [f"versions['{ver}'].scenarios harus list objek"]
    return [f"versions['{ver}'].scenarios[{i}].steps harus list objek"
            for i, sc in enumerate(scen) if "steps" in sc and not _list_of_objects(sc["steps"])]


def version_clean(reports_dir, module_name, ver):
    """`per_version[V].clean` untuk V yang phase1_reuse-nya true: tak satu pun file per-versi
    Lapis 1, 2, 5 V memuat temuan pemblokir (severity `error`) menurut fungsi lapis
    ps-aggregate; lapis inconclusive tanpa temuan seperti itu = bersih.

    File yang tak termuat, gagal validate_layer_shape, atau payload skenario yang
    `versions[V].scenarios`/`steps`-nya bukan list objek -> PlanInputError (exit 2) yang
    menyebut path-nya. Ketiga file selalu dimuat & divalidasi.
    """
    agg = _aggregate()
    layer_fn = {"static": agg.static_layer, "flashlight": agg.flashlight_layer,
                "scenario": agg.scenario_layer}
    blocking = False
    for layer, keys in CLEAN_LAYERS:
        path = per_version_path(reports_dir, module_name, layer, ver)
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            raise PlanInputError(f"file lapis tak termuat: {path} ({e})") from None
        if not isinstance(payload, dict):
            raise PlanInputError(f"file lapis bukan objek JSON: {path}")
        shape = agg.validate_layer_shape(payload, keys)
        if layer == "scenario":
            shape += _scenario_shape_notes(payload, ver)
        if shape:
            raise PlanInputError(f"file lapis tak lolos gerbang bentuk: {path} ({'; '.join(shape)})")
        try:
            res = layer_fn[layer](payload, ver)
        except (AttributeError, TypeError, KeyError, ValueError, IndexError) as e:
            # Bentuk bersarang yang lolos gerbang tapi tetap tak terbaca. Sebut tipe galatnya:
            # bila file-nya tampak sah, ini bisa bug fungsi lapis, bukan file rusak.
            raise PlanInputError(f"file lapis tak terbaca fungsi lapis: {path} "
                                 f"({type(e).__name__}: {e}; bila file tampak sah, "
                                 f"kemungkinan bug skrip)") from None
        if any(isinstance(f, dict) and f.get("severity") == agg.ERROR
               for f in res.get("findings") or []):
            blocking = True
    return not blocking


def _e2e_scenario_notes(module_dir):
    """Catatan spec authored yang DILEWATI (JSON rusak / tanpa expect_*) — milik ps-e2e-run.

    Diimpor malas & by-path: aturan "spec mana yang sah" hanya boleh punya satu pemilik,
    dan menyalinnya ke sini akan jadi implementasi kedua yang mendrift diam-diam. Impor
    di dalam fungsi supaya pemanggil lain (ps-aggregate -> modul ini) tak ikut menyeretnya.
    Daftar sumber (dulu juga dikembalikan) DIHAPUS: e2e_scenarios cuma echo nama file, nol
    pembaca — cakupan authored sudah dipikul e2e_smoke_only di agregat.
    """
    e2e_path = Path(__file__).resolve().parent / "ps-e2e-run.py"
    if not e2e_path.is_file():
        return []
    spec = importlib.util.spec_from_file_location("ps_e2e_run", e2e_path)
    if not (spec and spec.loader):
        return []
    e2e = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(e2e)
    _found, notes = e2e.discover_scenarios(module_dir)
    return notes


def _parse_scope_versions(raw):
    """--versions (string koma, atau list bila diisi --config) -> list unik urut tertulis."""
    items = raw if isinstance(raw, list) else str(raw or "").split(",")
    out = []
    for v in items:
        v = str(v).strip()
        if v and v not in out:
            out.append(v)
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else list(argv)
    ap = argparse.ArgumentParser(
        description="Pra-pass: tentukan file lapis mana yang masih sah dipakai ulang.",
        epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("module_path", nargs="?", help="Path folder module PrestaShop "
                                                   "(tak dipakai dengan --new-session)")
    ap.add_argument("--new-session", action="store_true",
                    help="Cetak token sesi validasi acak [a-z0-9]{16} lalu keluar. Eksklusif: "
                         "tanpa module_path & tanpa flag lain (selain itu exit 2).")
    ap.add_argument("--session", help="Token sesi validasi dari --new-session (WAJIB kecuali "
                                      "--new-session; absen/salah bentuk = exit 2)")
    ap.add_argument("--reports-dir", default=DEFAULT_REPORTS_DIR,
                    help=f"Folder laporan (psm_reports_dir; default kanonik: {DEFAULT_REPORTS_DIR})")
    # default None (bukan literal): nilai eksplisit yang kebetulan sama dgn default skrip tetap
    # cakupan run & menang atas --config (apply_config_file mengisi hanya dest yang = default).
    ap.add_argument("--versions", default=None,
                    help="Versi yang dinilai/dijalankan (cakupan run), dipisah koma — tiap entri "
                         "harus string versi terkonfigurasi (psm_target_versions). Absen -> "
                         f"psm_target_versions dari --config, else {fl.DEFAULT_TARGET_VERSIONS}. "
                         "Sel E2E wajib tetap SEMUA sel terkonfigurasi, berapa pun --versions.")
    ap.add_argument("--browsers", default=None,
                    help="Browser cakupan run E2E (dinormalisasi seperti psm_e2e_browsers), "
                         "dipisah koma. Absen -> psm_e2e_browsers dari --config, else "
                         f"{fl.DEFAULT_E2E_BROWSERS}. Kosong / di luar browser terkonfigurasi = "
                         "exit 2. Hanya menyaring e2e_next_cells, tak pernah menyusutkan sel wajib.")
    ap.add_argument("--config", help="JSON hasil resolve-psm-config.py — setelan keluarga (tag map, image DB, ps-domain, orchestrator, timeout, versi, browser) diisi dari sini untuk argumen yang tak diberikan eksplisit. Flag eksplisit selalu menang. Himpunan sel E2E wajib (psm_target_versions x psm_e2e_browsers) dibaca LANGSUNG dari sini (default skrip bila absen).")
    ap.add_argument("--rules", default=str(ss.DEFAULT_RULES),
                    help="Path ps-rules.json yang akan dipakai Lapis 1 (default: assets/ps-rules.json)")
    ap.add_argument("--extra-rules", help="Path aturan TAMBAHAN yang akan dipakai Lapis 1 — "
                                          "teruskan yang sama seperti ke ps-static-scan.py, "
                                          "supaya kesegaran dinilai atas ruleset yang benar-benar berlaku")
    ap.add_argument("--tag-map", help="Peta versi->tag image yang berlaku (mis. dari "
                                      "psm_flashlight_tag_map) — MENGGANTI peta default. Dipakai "
                                      "untuk tahu apakah file lapis 2/4 diproduksi image yang SAMA "
                                      "dengan target sekarang; tag di-bump = bukti dari core lain.")
    ap.add_argument("--extra-tag-map", help="Tag TAMBAHAN di atas peta yang berlaku — MENAMBAH, "
                                            "bukan mengganti. Teruskan yang sama seperti ke Lapis 2/4.")
    ap.add_argument("--per-version", action="store_true",
                    help="Vonis file lapis PER-VERSI `<module>-<lapis>-<versi>.json` (tiap versi "
                         "dinilai sendiri) alih-alih file kanonik. Untuk siklus konvergensi "
                         "version-first: patch demi satu versi tak menyeret versi lain ke rerun.")
    ap.add_argument("-o", "--output", help="File output JSON (default: stdout)")
    args = ap.parse_args(argv)

    # --new-session eksklusif: satu-satunya token argv. Flag lain apa pun (bahkan yang bernilai
    # sama dgn default) = pemanggil salah paham kontraknya -> exit 2, bukan diabaikan diam-diam.
    if args.new_session:
        if len(argv) != 1:
            print("error: --new-session eksklusif — tanpa module_path & tanpa flag lain",
                  file=sys.stderr)
            return 2
        print(new_session_token())
        return 0
    if args.session is None:
        print("error: --session wajib — buat token sekali per run dengan "
              "`ps-plan-layers.py --new-session` lalu teruskan ke tiap panggilan plan",
              file=sys.stderr)
        return 2
    if not valid_session(args.session):
        print(f"error: --session tak valid: {args.session!r} — harus [a-z0-9]{{16}} "
              "(dari --new-session)", file=sys.stderr)
        return 2
    if not args.module_path:
        print("error: module_path wajib (kecuali --new-session)", file=sys.stderr)
        return 2
    if args.config:
        fl.apply_config_file(args, ap, args.config)

    # customization-3: token {project-root} yang tak terekspansi sampai titik pakai = folder
    # harfiah -> "file lapis belum ada" percaya diri -> rerun semua lapis mahal. Gerbang di
    # konsumen terberat (satu pemilik di ps-static-scan). --reports-dir yang mengonstruksi
    # path lapis adalah leak yang direproduksi; --rules/--extra-rules mirror nilai config juga.
    bad = ss.unresolved_path_args([("--reports-dir", args.reports_dir), ("-o", args.output),
                                   ("--rules", args.rules), ("--extra-rules", args.extra_rules)])
    if bad:
        for name, val in bad:
            print(f"error: token '{{project-root}}' belum diresolve di {name}: {val!r} — resolve "
                  "ke root project dulu; ini path filesystem, bukan nilai config.", file=sys.stderr)
        return 2

    module_dir = Path(args.module_path).resolve()
    if not module_dir.is_dir():
        print(f"error: bukan folder: {module_dir}", file=sys.stderr)
        return 2
    if args.versions is None:
        args.versions = fl.DEFAULT_TARGET_VERSIONS
    requested = _parse_scope_versions(args.versions)
    if not requested:
        print("error: tak ada versi target — pra-pass atas nol versi memakai-ulang file lapis "
              "apa pun, termasuk yang meninjau versi lain", file=sys.stderr)
        print("sebut --versions (mis. dari psm_target_versions) lalu ulangi", file=sys.stderr)
        return 2
    # Himpunan sel WAJIB dibaca langsung dari --config (bukan dari args.versions yang diisi
    # apply_config_file): --versions cuma cakupan run, tak pernah menyusutkan himpunan ini.
    try:
        fl.require_config(args.config, args.reports_dir)
        cfg_versions, cfg_browsers = fl.configured_cells(args.config)
    except fl.CellConfigError as e:
        print(f"error: himpunan sel terkonfigurasi tak sah: {e}", file=sys.stderr)
        return 2
    outside = [v for v in requested if v not in cfg_versions]
    if outside:
        print(f"error: --versions {', '.join(outside)} bukan versi terkonfigurasi — tiap entri "
              f"harus PERSIS salah satu dari: {', '.join(cfg_versions)}", file=sys.stderr)
        return 2
    # Canary dinilai di SETIAP panggilan plan (apa pun psm_e2e_enabled): satu normalizer.
    try:
        canary = fl.configured_canary(args.config, cfg_versions, cfg_browsers)
    except fl.CellConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    # --browsers: cakupan run saja, dinormalisasi seperti psm_e2e_browsers.
    try:
        scope_browsers = fl.normalize_engines(
            fl.DEFAULT_E2E_BROWSERS if args.browsers is None else args.browsers, key="--browsers")
    except fl.CellConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    off = [b for b in scope_browsers if b not in cfg_browsers]
    if off:
        print(f"error: --browsers {', '.join(off)} bukan browser terkonfigurasi — tiap entri "
              f"harus salah satu dari: {', '.join(cfg_browsers)}", file=sys.stderr)
        return 2

    try:
        fingerprint = source_fingerprint(module_dir, args.reports_dir)
    except PlanInputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    src_mtime, src_path = newest_source_mtime(module_dir, args.reports_dir)
    rel = str(src_path.relative_to(module_dir)) if src_path else None

    ruleset = ss.ruleset_provenance([args.rules, args.extra_rules])
    # Tag yang berlaku SEKARANG untuk tiap versi target. Diresolve lewat pemilik aturannya
    # (ps-flashlight-run), bukan disalin ke sini — implementasi ketiga yang mendrift akan
    # membuat gerbang ini menolak reuse yang sah, atau menerima bukti dari core yang lain.
    # Input kedua tiap lapis dibangun oleh prov_for (satu pemilik) — mode kanonik & per-versi
    # memanggilnya sama persis, jadi vonis reuse keduanya tak bisa mendrift.
    tag_map = fl.parse_tag_map(args.tag_map, args.extra_tag_map)

    # Spec E2E authored adalah satu-satunya input yang ditulis TANGAN, dan satu-satunya
    # yang mengangkat Lapis 4 di atas smoke-only. Validasinya murah, tapi dulu hanya
    # dijalankan di dalam ps-e2e-run — setelah boot flashlight x N versi x M browser —
    # jadi satu typo baru ketahuan setelah run mahal selesai. Di sini penulisnya sempat
    # memperbaiki lebih dulu. Sengaja TAK memblok: smoke universal tetap berguna walau
    # spec authored rusak (kejujurannya sudah dipikul e2e_smoke_only). Juga pembanding
    # `not-gradeable`/`scenario-notes` sel E2E.
    notes = _e2e_scenario_notes(module_dir)
    try:
        histories = read_e2e_histories(args.reports_dir, module_dir.name, cfg_versions,
                                       cfg_browsers)
        e2e_cells = plan_e2e_cells(args.reports_dir, module_dir.name, cfg_versions, cfg_browsers,
                                   fingerprint, tag_map, notes, histories=histories)
    except PlanInputError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    # Tier E2E: diturunkan murni dari histori yang sama (cakupan run = requested x scope_browsers).
    tier = derive_e2e_step(histories, list(histories), canary, requested, scope_browsers,
                           fingerprint, tag_map, args.session, current_notes=notes)

    if args.per_version:
        pv = plan_per_version(args.reports_dir, module_dir.name, requested,
                              src_mtime, rel, ruleset, tag_map, e2e_cells=e2e_cells)
        # phase1_reuse per versi = tak ada lapis selain e2e/adversarial yang rerun; clean hanya
        # dimuat bila phase1_reuse V true (file Lapis 1/2/5 V lewat fungsi lapis ps-aggregate).
        try:
            for ver, entry in pv.items():
                entry["phase1_reuse"] = phase1_reuse_of(entry["rerun"])
                entry["clean"] = (entry["phase1_reuse"]
                                  and version_clean(args.reports_dir, module_dir.name, ver))
        except PlanInputError as e:
            print(f"error: {e}", file=sys.stderr)
            return 2
        result = {"module": module_dir.name, "versions": requested,
                  "newest_source": rel, "source_fingerprint": fingerprint,
                  "mode": "per-version", "per_version": pv,
                  **per_version_rollup(pv, e2e_cells),
                  "phase1_reuse": all(e["phase1_reuse"] for e in pv.values()),
                  **tier}
    else:
        plans = {}
        for layer in LAYERS:
            if layer == "e2e":
                plans[layer] = canonical_e2e_layer(e2e_cells)
                continue
            path = Path(args.reports_dir) / f"{module_dir.name}-{layer}.json"
            plans[layer] = plan_layer(path, requested, src_mtime, rel,
                                      provenance=prov_for(layer, requested, ruleset, tag_map))
        rerun = [l for l in LAYERS if l != "e2e" and not plans[l]["reuse"]]
        if any(not c["reuse"] for row in e2e_cells.values() for c in row.values()):
            rerun = sorted(rerun + ["e2e"], key=LAYERS.index)
        result = {"module": module_dir.name, "versions": requested,
                  "newest_source": rel, "source_fingerprint": fingerprint,
                  "layers": plans, "rerun": rerun,
                  "phase1_reuse": phase1_reuse_of(rerun), **tier}

    if notes:
        result["e2e_scenario_notes"] = notes
    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"ditulis: {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
