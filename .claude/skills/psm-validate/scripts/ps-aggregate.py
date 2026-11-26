#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Satukan empat lapis validasi jadi satu vonis terstruktur — deterministik.

Menerima output JSON ps-static-scan.py (Lapis 1) dan ps-flashlight-run.py
(Lapis 2), file temuan adversarial buatan model (Lapis 3), plus histori bukti E2E
per sel (Lapis 4, `<reports>/<module>-e2e-<ver>-<browser>.jsonl`, dibaca lewat
--reports-dir + --module), lalu menghitung `pass` per versi dan keseluruhan secara
NATIVE — bukan lewat model.

Versi target = psm_target_versions dari --config (default skrip bila absen); sel E2E
wajib = psm_target_versions x psm_e2e_browsers. Per sel dipilih record gate-grade
terbaru, else record terbaru (aturan state/kesegaran milik ps-plan-layers). Bila
`--require` memuat e2e, `ready` jatuh selama ada sel terkonfigurasi tanpa bukti lulus
gate-grade. `--e2e` = exit 2; `<module>-e2e.json`/`<module>-e2e-<ver>.json` diabaikan.
Versi terkonfigurasi yang absen dari hasil static = belum terbukti (ready false), bukan exit 2.

Aturan lolos: sebuah versi lolos hanya bila TAK ADA temuan severity `error` dari
lapis manapun yang KONKLUSIF di versi itu. Lapis yang tak konklusif (Docker absen,
gagal pull, timeout, tak ada console) TAK PERNAH memblok — vonis versi itu jatuh
ke lapis yang benar-benar teruji (jujur: tak klaim lolos maupun gagal atas yang
tak diuji). Skrip menandai `conclusive` per versi supaya pemanggil tahu seberapa
kuat vonisnya.

Pembagian kerja: skrip menghitung/menggabung/membandingkan (satu jawaban benar);
model tinggal menghasilkan temuan adversarial (Lapis 3) & prosa untuk manusia.
"""
import argparse
import datetime
import importlib.util
import json
import re
import sys
from pathlib import Path

ERROR = "error"
LAYERS = ("static", "flashlight", "adversarial", "e2e", "scenario")

# "Cakupan apa yang DITINJAU file lapis ini" hanya boleh punya SATU definisi. Dulu
# ps-plan-layers menegakkannya (menolak reuse file yang cakupannya kurang) sementara
# skrip ini mengabaikannya -> `ready` true atas versi yang reviewer bilang tak ditinjau.
# Pakai-ulang lewat impor by-path (nama file ber-tanda-hubung), pola yang sama dgn
# ps-plan-layers -> ps-static-scan dan ps-e2e-run -> ps-flashlight-run.
def load_sibling(path, name):
    """Muat skrip sibling by-path. Gagal = exit 2, BUKAN exit 1.

    exit 1 adalah kode "vonis gagal" skrip ini. Sibling yang absen (folder scripts/ disalin
    sebagian) yang meledak jadi traceback exit 1 tak bisa dibedakan pemanggil/CI dari
    "module ini punya error yang memblok" — kelas yang sudah dihilangkan _version_matches
    dan validate_extra_rules di file ini, jadi seam impor tak boleh memasukkannya kembali.
    `assert spec and spec.loader` saja tak menjaga apa pun: spec_from_file_location tetap
    mengembalikan spec sah untuk path yang tak ada, dan kegagalannya baru muncul di
    exec_module.
    """
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if not (spec and spec.loader):
            raise ImportError(f"spec tak terbentuk untuk {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except (OSError, ImportError, SyntaxError) as e:
        print(f"error: skrip sibling tak bisa dimuat: {path.name} ({e})", file=sys.stderr)
        print("skrip psm-validate saling bergantung — salin folder scripts/ utuh", file=sys.stderr)
        sys.exit(2)


pl = load_sibling(Path(__file__).resolve().parent / "ps-plan-layers.py", "ps_plan_layers")
# Domain key versi (`affects`) punya satu pemilik: ps-static-scan. _version_matches di
# bawah membutuhkannya, dan menulis ulang "apa itu major" di sini persis kelas duplikasi
# yang sudah dihilangkan dari file ini sekali (lihat load_sibling).
ss = load_sibling(Path(__file__).resolve().parent / "ps-static-scan.py", "ps_static_scan")


def compute_ready(versions, required):
    """`ready` = lolos DAN tiap lapis yang diwajibkan benar-benar TUNTAS dinilai
    di SEMUA versi target — konklusif dan tanpa catatan cakupan tersisa.

    `pass` sengaja buta konklusivitas (lapis yang tak jalan tak boleh memblok), jadi
    `pass` sendirian bukan sinyal siap-rilis: di runner tanpa Docker ia hijau atas
    2 dari 4 lapis. `ready` menjawab itu dalam SATU field supaya tiap pemanggil tak
    merakit sendiri dari pass + empat flag.

    `inconclusive_note` ikut dihitung: lapis boleh konklusif (mis. install teruji)
    sambil separuhnya tak pernah dievaluasi (phpstan absen) atau cakupannya menyusut
    (browser absen, spec authored dilewati). Itu tetap "tak tuntas" — kalau tidak,
    `ready` mengklaim persis coverage yang tak diuji.
    """
    # Nol versi = nol bukti, dan `for m in {}.values()` tak pernah jalan -> True: "semua versi
    # terbukti" secara vakum. Bentuk yang sama sudah digerbang satu tingkat di bawah (`--require`
    # kosong, di main()), tapi kembarannya di loop LUAR ini tak pernah ikut — dan dari sanalah
    # ready=true keluar atas nol versi, di gerbang paling ketat, di runner tanpa Docker. main()
    # menolaknya keras (exit 2); di sini dijaga juga karena fungsi ini dibaca skill sibling,
    # bukan cuma jalur CLI.
    if not versions:
        return False
    return all(version_ready(m, required) for m in versions.values())


def version_ready(m, required):
    """`ready` untuk SATU versi. Pemilik tunggal aturannya; `ready` keseluruhan = AND-nya.

    Dipisah karena kontrak yang dibaca TIGA skill sibling ditulis per-versi ("siap hanya bila
    `ready` true di 1.7.x, 8.x, dan 9.x") sementara yang diemit cuma satu `ready` top-level:
    per-versi bukan sekadar tak ditulis, ia TAK BISA dinyatakan. Model lalu berimprovisasi —
    membaca `ready` global lalu melaporkannya tiga kali — yang diam-diam mengubah klaim
    per-versi jadi klaim global, persis kegagalan yang pemisahan `pass`/`ready` ada untuk cegah.
    Satu fungsi, dua pemakai, jadi keduanya tak bisa berbeda pendapat.
    """
    if not m["pass"]:
        return False
    # Lantai, terlepas dari `--require`: versi tanpa vonis DASAR (nol aturan dinilai, main file
    # tak resolve) tak pernah siap-rilis. Tanpa ini `--require e2e` melewati konklusivitas static
    # sepenuhnya -> ready=true atas versi yang nol aturan pernah menyentuhnya, dan satu-satunya
    # yang mencatatnya (`conclusive` per-versi) tak dibaca siapa pun. Penyempitan itu memilih
    # lapis mana yang WAJIB, bukan izin untuk memvonis tanpa dasar.
    if not m.get("conclusive"):
        return False
    for layer in required:
        info = m["layers"].get(layer)
        if info is None or not info.get("conclusive") or info.get("inconclusive_note"):
            return False
    return True


def load_json(path, label):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: gagal baca {label} ({path}): {e}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(data, dict):
        print(f"error: {label} ({path}) bukan JSON object melainkan {type(data).__name__}",
              file=sys.stderr)
        sys.exit(2)
    return data


def validate_layer_shape(payload, finding_keys=()):
    """Gerbang bentuk file lapis buatan SKRIP. Return list pelanggaran (kosong = lolos).

    validate_adversarial menjaga seam model->skrip dengan alasan yang ditulis eksplisit: payload
    salah-bentuk meledak AttributeError -> exit 1 = kode vonis-gagal, jadi file rusak terbaca
    "module gagal". Alasan itu tak pernah khusus file buatan model — file lapis yang TERPOTONG
    (run di-kill saat tulis, disk penuh) atau ditulis versi skrip lain meledak persis sama, dan
    ps-plan-layers memang ada untuk memakai ulang file lapis lintas run. Gerbangnya sudah ada;
    ia cuma tak pernah dipasang di tiga seam di sebelahnya.
    """
    notes = []
    versions = payload.get("versions")
    if versions is None:
        return notes
    if not isinstance(versions, dict):
        return [f"'versions' bertipe {type(versions).__name__}, harus object {{versi: {{...}}}}"]
    for ver, entry in versions.items():
        if not isinstance(entry, dict):
            notes.append(f"versions['{ver}'] bertipe {type(entry).__name__}, harus object")
            continue
        finds = entry.get("findings")
        if finds is None:
            continue
        if not isinstance(finds, list):
            notes.append(f"versions['{ver}'].findings bertipe {type(finds).__name__}, harus list")
            continue
        for i, f in enumerate(finds):
            if not isinstance(f, dict):
                notes.append(f"versions['{ver}'].findings[{i}] bertipe {type(f).__name__}, "
                             "harus object")
                continue
            for k in finding_keys:
                if k not in f:
                    notes.append(f"versions['{ver}'].findings[{i}] tak punya '{k}'")
    return notes


def _int_fact(container, key):
    """Baca hitungan cakupan bertipe KETAT dari container; None bila absen/salah-tipe/negatif.

    Satu pemilik untuk kelas gerbang-tipe cakupan (dipakai rules_evaluated & authored_assertions).
    `"0"`/`[]`/`true`/`-1` lolos cek nilai lalu memulihkan `ready` — persis kelas yang
    validate_extra_rules ada untuk menutup. bool lolos isinstance(int) di Python, jadi dibuang
    eksplisit: `true` bukan hitungan. None = "tak diketahui", dan tak diketahui ≠ teruji.
    """
    val = (container or {}).get(key)
    if isinstance(val, bool) or not isinstance(val, int) or val < 0:
        return None
    return val


def _bool_fact(container, key):
    """Baca fakta cakupan boolean bertipe KETAT; None bila absen/salah-tipe.

    Pasangan `_int_fact` untuk seam boolean (coverage_ok, no_verdict). `"false"`/`0`/`[]`
    BUKAN False — truthiness telanjang dulu menelan `"false"` ke satu arah & `[]`/`{}` ke
    arah lain. Hanya bool asli yang fakta; sisanya None = tak bisa dipastikan. Seam kelima
    yang lahir nanti memanggil salah satu helper ini, tak bisa lupa menggerbang tipe.
    """
    val = (container or {}).get(key)
    return val if isinstance(val, bool) else None


def static_layer(static, full_ver):
    """Lapis 1 selalu JALAN — tapi "jalan" bukan "menilai", dan cuma yang kedua itu bukti.

    `conclusive` di sini dulu konstanta True, dengan alasan "Lapis 1 selalu jalan". Itu benar
    tentang SKRIPnya dan salah tentang ATURANnya: versi yang major-nya tak disebut satu rule
    pun (`--rules` KB yang cuma menyebut major lain) dilewati SETIAP aturan, keluar 0 error,
    lalu terbaca konklusif lolos — module ber-eval() dinyatakan siap-rilis di versi yang nol
    aturan pernah menyentuhnya. Ketiadaan aturan bukan bukti, jadi cakupan di sini fakta yang
    DIHITUNG (`rules_evaluated`), bukan diasumsikan.

    Main file yang tak resolve punya bentuk yang sama, sekali lagi diam-diam: aturan
    ber-`files: ["__MAIN__"]` no-op tanpa sepatah kata, jadi lapis ini menilai lebih sedikit
    dari yang diklaimnya. Keduanya lewat `inconclusive_note` — kanal yang sudah dibaca
    compute_ready — supaya `ready` jatuh sementara `pass` tetap buta konklusivitas.
    """
    v = static.get("versions", {}).get(full_ver)
    if v is None:
        return {"ran": False, "conclusive": False, "errors": 0, "warnings": 0,
                "reason": "versi tak ada di hasil static-scan", "findings": []}
    findings = [
        {"source": "static", "id": f["id"], "severity": f["severity"],
         "message": f["message"], "fix": f.get("fix", ""),
         "location": _first_loc(f.get("occurrences")), "count": f.get("count", 1)}
        for f in v.get("findings", [])
    ]
    notes = []
    evaluated = _int_fact(v, "rules_evaluated")  # None = absen/salah-tipe/negatif (tak diketahui)
    if evaluated is None:
        notes.append("hasil static tak mencatat `rules_evaluated` yang sah (file lapis dari "
                     "skrip lama atau salah bentuk) — cakupan aturan tak bisa dipastikan; "
                     "jalankan ulang Lapis 1")
    elif evaluated == 0:
        notes.append("nol aturan dinilai di versi ini — ruleset yang dipakai tak menyebut "
                     "major-nya, jadi 0 error di sini bukan lolos")
    # Cakupan yang hilang SEBAGIAN: target ditulis telanjang ('9') sementara ruleset punya
    # aturan khas-minor ('9.1'). rules_evaluated tetap positif, jadi cek di atas tak
    # menangkapnya — tapi aturan Hummingbird memang tak pernah jalan. Bentuk kegagalan
    # yang sama, cuma tak total; ia layak kanal yang sama, bukan didiamkan.
    skipped = v.get("minor_rules_skipped")
    if isinstance(skipped, list) and skipped:
        notes.append(f"aturan khas-minor tak dinilai ({', '.join(str(s) for s in skipped)}) — "
                     "versi target ditulis tanpa komponen minor; sebut minor-nya "
                     "(mis. 9.1, bukan 9) agar aturan itu ikut menyala")
    # `is not True`, bukan `is False`: string "false" dan key yang absen sama-sama bukan bukti.
    if static.get("main_file_found") is not True:
        notes.append("main module file tak resolve — aturan ber-`files: __MAIN__` tak dinilai")

    # Dihitung dari catatan di atas, BUKAN konstanta. Sebelumnya field ini pin True sementara
    # docstring-nya bilang cakupan sudah dihitung: objek yang sama memuat `conclusive: true`
    # dan catatan yang bilang cakupannya tak diketahui — dan yang dipercaya pemanggil field-nya.
    layer = {"ran": True, "conclusive": not notes, "errors": v.get("errors", 0),
             "warnings": v.get("warnings", 0), "findings": findings}
    if notes:
        layer["inconclusive_note"] = "; ".join(notes)
    return layer


def _first_loc(occ):
    if occ:
        o = occ[0]
        return f"{o.get('file', '?')}:{o.get('line', 0)}"
    return ""


def _log_tail(log, label, limit=300):
    """Ekor log, bila ada — supaya bukti ikut ke vonis alih-alih menganggur di file lapis."""
    tail = (log or "").strip()
    return f" — {label}: …{tail[-limit:]}" if tail else ""


def _phpstan_loc(m):
    """Lokasi temuan phpstan: file:line, bukan 'line 42' telanjang.

    `file` diemit tiap pesan lalu tak dibaca siapa pun, jadi temuan yang MEMBLOK melaporkan
    nomor baris tanpa nama file — tak bisa ditindaklanjuti di module banyak-file, padahal
    _first_loc di atas sudah menjawab pertanyaan yang sama dengan benar untuk lapis static.
    """
    line = m.get("line", "?")
    f = m.get("file")
    return f"{f}:{line}" if f else f"line {line}"


def flashlight_layer(flash, full_ver):
    """Lapis 2 — konklusif hanya bila container benar-benar menjalankan uji.

    Tak konklusif (degrade jujur, tak memblok): Docker absen, gagal pull, timeout,
    PS console/root tak ada. Konklusif = install benar-benar diuji (lolos/ditolak);
    bila phpstan tak terbaca, install tetap divonis tapi separuh CS disurface lewat
    `inconclusive_note` — bukan diklaim teruji.
    """
    if not flash or flash.get("status") == "skipped" or not flash.get("docker_available", False):
        reason = (flash or {}).get("reason", "Docker tidak tersedia — uji flashlight dilewati.")
        return {"state": "skipped", "conclusive": False, "errors": 0, "reason": reason, "findings": []}

    v = flash.get("versions", {}).get(full_ver)
    if v is None:
        return {"state": "skipped", "conclusive": False, "errors": 0,
                "reason": "versi tak ada di hasil flashlight", "findings": []}

    # Kegagalan infrastruktur → tak konklusif, jangan memblok.
    infra = list(v.get("errors", []))  # gagal pull / timeout container
    install = v.get("install") or {}
    if install.get("no_console"):
        infra.append("PrestaShop console tak ada di image — install tak bisa diuji")
    if install.get("no_psroot"):
        infra.append("PS root tak ada di image — install tak bisa diuji")
    # Install gagal TAPI installer tak TERBUKTI mencapai vonis tolak → infra, bukan vonis
    # memblok atas module. Vonis memblok 'modul gagal install' HANYA sah bila PSM_INSTALL_FAIL
    # benar-benar diemit, yaitu no_verdict IS False (bool). Gerbang identity-strict, sekelas
    # coverage_ok/rules_evaluated: `not False` menangkap True (exec mati), None (file lapis
    # lama tak mencatat), dan salah-tipe ("false"/[]/{}) — semuanya "tak bisa dipastikan",
    # bukan module ditolak. Dulu truthiness telanjang: "false" ditelan ke infra & []/{} jatuh
    # jadi vonis memblok. `no_console`/`no_psroot` punya pesannya sendiri di atas — jangan dobel.
    # `ok` digerbang IDENTITY-STRICT sekelas coverage_ok/no_verdict (sibling di dict install
    # yang sama): dulu truthiness telanjang -> `ok="false"`/0/1 (truthy/falsy non-bool) bikin
    # install GAGAL terbaca SUKSES (ready UP palsu) atau sukses terbaca gagal. Hanya bool asli
    # fakta; None = file lapis lama/salah bentuk = tak bisa dipastikan.
    iok = _bool_fact(install, "ok")          # True=sukses; False=gagal; None=lama/salah
    nv = _bool_fact(install, "no_verdict")   # True=exec mati; False=installer memvonis; None=lama/salah
    if not (install.get("no_console") or install.get("no_psroot")):
        if iok is None:
            infra.append("hasil flashlight tak mencatat status install yang sah (file lapis dari "
                         "skrip lama atau salah bentuk) — install tak bisa diuji")
        elif iok is False and nv is not False:
            # Gagal TAPI installer tak TERBUKTI menolak: vonis memblok 'modul gagal install'
            # HANYA sah bila PSM_INSTALL_FAIL diemit (nv is False). nv True = exec mati; nv
            # None = file lapis lama tak mencatat. Keduanya "tak bisa dipastikan", bukan ditolak.
            infra.append("inner-script tak mencapai vonis install (exec/container gagal) — "
                         "install tak bisa diuji" if nv is True else
                         "hasil flashlight tak mencatat vonis install (file lapis dari skrip "
                         "lama atau salah bentuk) — jalankan ulang Lapis 2")
    if infra:
        # Ekor log container ikut: kegagalan boot adalah kegagalan yang PALING sulit
        # didiagnosis, dan tanpa ini vonisnya cuma "flashlight tak jadi healthy (timeout)".
        # `boot_log` ditangkap tepat pada kondisi ini lalu tak dibaca siapa pun — kelas
        # PSM_NO_CONSOLE, dan ia yatim di KEDUA lapis, jadi keduanya diikat sekarang.
        return {"state": "not_conclusive", "conclusive": False, "errors": 0,
                "reason": "; ".join(infra) + _log_tail(v.get("boot_log"), "log container"),
                "findings": []}

    # Konklusif: kumpulkan temuan error nyata (install ditolak / phpcs error).
    findings = []
    if iok is False:  # sampai sini hanya bila nv is False = PSM_INSTALL_FAIL benar-benar diemit
        # Ekor log install ikut ke temuan. Ini temuan pemblokir yang PALING sering, `install.log`
        # menangkap sebabnya, dan tak ada yang membacanya — sementara fix-nya menyuruh operator
        # "periksa log install flashlight" yang tak pernah dibawa vonis, padahal SKILL.md
        # melarang menilai ulang dengan tangan.
        findings.append({"source": "flashlight", "id": "flashlight-install",
                         "severity": ERROR, "message": "modul gagal install di core asli",
                         "fix": "periksa log install flashlight" + _log_tail(install.get("log"), "ekor log"),
                         "location": v.get("image", "")})
    cs = v.get("coding_standard") or {}
    # Hanya errors konklusif yang memblok. Neon auto-generate (advisory) memetakan
    # temuannya ke warnings (errors=0) di ps-flashlight-run, jadi tak sampai sini.
    if cs.get("available") and cs.get("parse_ok") and cs.get("errors", 0) > 0:
        for m in cs.get("error_messages", []):
            findings.append({"source": "flashlight", "id": "flashlight-phpstan",
                             "severity": ERROR, "message": m.get("message", "phpstan error"),
                             "fix": m.get("source", ""), "location": _phpstan_loc(m)})
        if not cs.get("error_messages"):
            findings.append({"source": "flashlight", "id": "flashlight-phpstan",
                             "severity": ERROR, "message": f"{cs['errors']} phpstan error",
                             "fix": "", "location": v.get("image", "")})
    # Neon auto-generate: phpstan BENAR-BENAR jalan dan temuannya nyata, tapi penegakannya
    # sengaja ditahan — menjatuhkan rilis atas config yang kami karang sendiri, bukan milik
    # module, bukan vonis. Temuannya tetap dibawa sebagai WARNING supaya sampai ke laporan
    # seperti warning static. Dulu ke-N pesan itu dibuang di lantai dan satu-satunya penandanya
    # (`generated_config`) tak dibaca siapa pun, jadi run advisory tak terbedakan dari run
    # bersih yang ditegakkan. Cabang ini tak pernah bentrok dgn yang di atas: advisory selalu
    # errors=0 by construction di ps-flashlight-run.
    if cs.get("available") and cs.get("parse_ok") and cs.get("generated_config"):
        for m in cs.get("error_messages", []):
            findings.append({"source": "flashlight", "id": "flashlight-phpstan-advisory",
                             "severity": "warning", "message": m.get("message", "phpstan"),
                             "fix": "kirim phpstan.neon milik module untuk menegakkannya",
                             "location": _phpstan_loc(m)})
    errs = sum(1 for f in findings if f["severity"] == ERROR)
    layer = {"state": "fail" if errs else "pass", "conclusive": True,
             "errors": errs, "findings": findings}
    # CS tak dievaluasi: install TETAP konklusif (benar-benar diuji), tapi separuh
    # vonis Lapis 2 (phpstan) tak pernah terbaca. Disurface lewat `inconclusive_note`
    # — kanal yang memang dibaca aturan jujur SKILL.md & dipakai e2e_layer. Dulu
    # dicatat di `cs_note` yang tak dibaca siapa pun = gap senyap.
    if not cs.get("available"):
        layer["inconclusive_note"] = "phpstan tak ada di image — coding standard tak diuji; tak memblok"
    elif cs.get("parse_ok") is False:
        layer["inconclusive_note"] = (cs.get("note", "laporan phpstan tak terparse")
                                      + " — coding standard tak diuji; tak memblok")
    elif _bool_fact(cs, "coverage_ok") is False:
        # Canary tak terdeteksi: phpstan jalan & laporannya terparse, tapi TAK menganalisis satu
        # file pun dari module (mis. neon module meng-excludePaths dirinya sendiri). Laporan JSON
        # phpstan tak bisa membedakan ini dari "bersih" — map `files` cuma memuat file YANG
        # BER-ERROR — jadi tanpa kontrol positif sebuah module bisa MEMBELI vonis CS bersih
        # dengan neon yang mengecualikan dirinya.
        layer["inconclusive_note"] = ("phpstan tak menganalisis satu file pun dari module "
                                      "(neon module mengecualikannya — canary tak terdeteksi) "
                                      "— coding standard tak diuji; tak memblok")
    elif _bool_fact(cs, "coverage_ok") is None:
        # Absen ATAU salah-tipe (`"false"`/`0`/`1.5`/`[]`): dulu `is False`+`not in` meloloskan
        # non-bool non-False sbg cakupan teruji (leak determinism-2). Tak bisa dipastikan.
        layer["inconclusive_note"] = ("hasil flashlight tak mencatat `coverage_ok` yang sah (file "
                                      "lapis dari skrip lama atau salah bentuk) — cakupan phpstan "
                                      "tak bisa dipastikan; jalankan ulang Lapis 2")
    # OBSERVASI, bukan celah cakupan — kanal yang sama dengan error console di e2e_layer:
    # disurface supaya tak jadi sinyal yatim, tapi TAK menggerbang, dan jalan keluarnya
    # (kirim neon sendiri) disebut supaya "advisory" bukan jalan buntu.
    if cs.get("generated_config") and cs.get("parse_ok"):
        layer["advisory_note"] = (f"{cs.get('warnings', 0)} temuan phpstan lewat neon "
                                  "auto-generate — advisory: tak memblok & tak menjatuhkan "
                                  "`ready`; tegakkan dengan mengirim phpstan.neon milik module")
    return layer


# --- Lapis 4 (E2E): histori bukti per sel (cell-contract.md > Aggregate) -----------------
# Bukti E2E dibaca HANYA dari histori append-only per sel `<reports>/<module>-e2e-<ver>-<browser>.jsonl`.
# Aturan state/kesegaran/gate-grade TIDAK ditulis ulang di sini: semuanya milik ps-plan-layers
# (record_state, newest_gate_grade, has_passing_evidence, cell_reason, is_failing) supaya plan
# dan vonis tak pernah berbeda pendapat soal sel yang sama.
_RUN_DIR_RE = re.compile(r"^run-\d{8}-\d{6}$")
E2E_MISSING_REASON = "missing"


def evaluate_cell(records, corrupt_tail, fingerprint, image_tag, current_notes):
    """Nilai satu sel dari histori valid-nya. Return dict internal:

    `selected` = record gate-grade TERBARU, else record terbaru (None bila tak ada record);
    `gate_grade` = selected gate-grade; `newest_gate_grade`; `passing` = punya bukti lulus
    gate-grade; `reason` = alasan plan (None bila passing), dengan `stale-fail` menggantikan
    `stale-source`/`stale-tag` bila sel `failing` (Plan > Derivation). `corrupt_tail` selalu
    memberi `corrupt-history` dan tak pernah bukti lulus (lewat cell_reason/has_passing_evidence).
    """
    g = pl.newest_gate_grade(records, fingerprint, image_tag)
    selected = g if g is not None else (records[-1] if records else None)
    passing = pl.has_passing_evidence(records, corrupt_tail, fingerprint, image_tag)
    reason = pl.cell_reason(records, corrupt_tail, fingerprint, image_tag, current_notes)
    if reason in ("stale-source", "stale-tag") and pl.is_failing(records):
        reason = "stale-fail"
    return {"records": records, "corrupt_tail": corrupt_tail, "selected": selected,
            "gate_grade": g is not None, "newest_gate_grade": g, "passing": passing,
            "reason": None if passing else reason}


def _missing_cell():
    return evaluate_cell([], False, None, None, None)


def evaluate_e2e_cells(reports_dir, module_name, versions, browsers, fingerprint, tag_map,
                       current_notes):
    """Semua sel terkonfigurasi -> {ver: {browser: info evaluate_cell}}.

    Tanpa `reports_dir` (tanpa --reports-dir + --module) tiap sel `missing`. Error OS saat
    membaca histori -> pl.PlanInputError (CLI: exit 2 menyebut path-nya).
    """
    out = {}
    for ver in versions:
        tag = pl.fl.resolve_tag(tag_map, ver)
        row = {}
        for b in browsers:
            if reports_dir is None:
                row[b] = _missing_cell()
                continue
            records, corrupt = pl.read_history(pl.history_path(reports_dir, module_name, ver, b),
                                               ver, b)
            row[b] = evaluate_cell(records, corrupt, fingerprint, tag, current_notes)
        out[ver] = row
    return out


def e2e_cell_entry(info):
    """Entri `e2e_cells[ver][browser]` = {state, gate_grade, reason, findings, parallel_only}.

    `findings` = temuan record terpilih APA ADANYA, gate-grade atau tidak — di sini saja temuan
    record non-gate-grade tampil; yang memblok hanya dari record gate-grade (e2e_layer).
    """
    sel = info["selected"]
    if sel is None:
        return {"state": None, "gate_grade": False, "reason": info["reason"], "findings": [],
                "parallel_only": None}
    finds = sel.get("findings")
    return {"state": pl.record_state(sel)["state"], "gate_grade": info["gate_grade"],
            "reason": info["reason"], "findings": list(finds) if isinstance(finds, list) else [],
            "parallel_only": sel.get("parallel_only")}


def _console_count(val):
    if isinstance(val, bool):
        return 0
    if isinstance(val, int):
        return max(val, 0)
    if isinstance(val, list):
        return len(val)
    return 0


def e2e_verdict(row, browsers):
    """(e2e_state, reason) satu versi atas sel terkonfigurasinya.

    `fail` bila record gate-grade terbaru suatu sel = fail (reason literal `fail`); selain itu
    `inconclusive` bila ada sel tanpa bukti lulus gate-grade (reason = alasan sel PERTAMA
    seperti itu, urut psm_e2e_browsers); selain itu `pass` (reason None). Tanpa browser
    terkonfigurasi = tak ada bukti (`inconclusive`, `missing`) — tak pernah lolos vakum.
    """
    if not browsers:
        return "inconclusive", E2E_MISSING_REASON
    infos = [(row or {}).get(b) or _missing_cell() for b in browsers]
    if any(i["newest_gate_grade"] is not None
           and pl.record_state(i["newest_gate_grade"])["state"] == "fail" for i in infos):
        return "fail", "fail"
    lacking = [i for i in infos if not i["passing"]]
    if lacking:
        return "inconclusive", lacking[0]["reason"]
    return "pass", None


def e2e_layer(row, full_ver, browsers):
    """Lapis 4 satu versi, dari record TERPILIH sel-sel terkonfigurasinya saja.

    `conclusive` = tiap sel punya record terpilih yang konklusif. Temuan yang MEMBLOK hanya dari
    record terpilih yang gate-grade. `inconclusive_note` menyebut sel tanpa bukti lulus
    gate-grade beserta alasannya — kanal yang menjatuhkan `ready` (compute_ready), jadi
    sel yang dipersempit/parsial/hilang/rusak/basi tak pernah terhitung. Error console =
    advisory (tak menggerbang). Ekor `boot_log` ikut ke `reason` seperti dulu.
    """
    row = row or {}
    infos = [(b, row.get(b) or _missing_cell()) for b in browsers]
    state, reason = e2e_verdict(row, browsers)
    conclusive = bool(infos) and all(
        i["selected"] is not None and pl.record_state(i["selected"])["conclusive"]
        for _b, i in infos)
    findings = []
    for b, i in infos:
        if not i["gate_grade"]:
            continue
        for f in i["selected"].get("findings") or []:
            if not isinstance(f, dict):
                continue
            findings.append({"source": "e2e", "id": f.get("id", "e2e"),
                             "severity": f.get("severity", ERROR),
                             "message": f.get("message", ""), "fix": f.get("fix", ""),
                             "location": f.get("location", ""), "browser": b})
        # Rekaman gate-grade ber-state `fail` tanpa satu pun temuan ERROR (findings rusak /
        # severity lain) tak boleh membuat versi `pass`: state rekaman yang memvonis.
        if pl.record_state(i["selected"])["state"] == "fail" and not any(
                f["severity"] == ERROR and f.get("browser") == b for f in findings):
            findings.append({"source": "e2e", "id": "e2e-fail", "severity": ERROR,
                             "message": f"[{b}] sel E2E gagal (rekaman tanpa temuan ERROR yang terbaca)",
                             "fix": "baca rekaman histori sel ini", "location": "", "browser": b})
    errs = sum(1 for f in findings if f["severity"] == ERROR)
    lacking = [(b, i) for b, i in infos if not i["passing"]]
    tail = ""
    if reason:
        for _b, i in lacking:
            log = (i["selected"] or {}).get("boot_log")
            if isinstance(log, str) and log.strip():
                tail = _log_tail(log, "log container")
                break
    layer = {"state": state, "conclusive": conclusive, "errors": errs,
             "reason": (reason + tail) if reason else None, "findings": findings}
    if lacking:
        cells = ", ".join(f"{full_ver}:{b} ({i['reason']})" for b, i in lacking)
        layer["inconclusive_note"] = f"sel E2E tanpa bukti lulus gate-grade: {cells}"
    console = sum(_console_count((i["selected"] or {}).get("console_errors")) for _b, i in infos)
    if console:
        layer["advisory_note"] = (f"{console} error console/JS terdeteksi — advisory: "
                                  "tak memblok & tak menjatuhkan `ready`; tegakkan dengan aksi "
                                  "`expect_no_console_error` di skenario")
    return layer


def _selected_records(cells, versions, browsers):
    for ver in versions:
        for b in browsers:
            sel = cells[ver][b]["selected"]
            if sel is not None:
                yield ver, b, sel


def e2e_phase_durations(cells, versions, browsers):
    """`e2e_phase_durations[ver] = {boots: {<boot_id>: {phases, wall_clock}}, browsers:
    {<engine>: {phases, wall_clock}}}` dari record terpilih; tiap boot_id (keeper_boot
    termasuk) sekali. Record ber-boot_id null tak menambah boots."""
    out = {}
    for ver in versions:
        boots, brs = {}, {}
        for b in browsers:
            sel = cells[ver][b]["selected"]
            if sel is None:
                continue
            bid = sel.get("boot_id")
            if isinstance(bid, str) and bid not in boots:
                boots[bid] = {"phases": sel.get("boot_phases") or {},
                              "wall_clock": sel.get("boot_wall_clock")}
            kb = sel.get("keeper_boot")
            if isinstance(kb, dict) and isinstance(kb.get("boot_id"), str) \
                    and kb["boot_id"] not in boots:
                boots[kb["boot_id"]] = {"phases": kb.get("boot_phases") or {},
                                        "wall_clock": kb.get("wall_clock")}
            brs[b] = {"phases": sel.get("phase_durations") or {},
                      "wall_clock": sel.get("wall_clock")}
        out[ver] = {"boots": boots, "browsers": brs}
    return out


def _run_folder(shot):
    """Folder run berstempel (`run-YYYYMMDD-HHMMSS`) sebuah path screenshot; fallback induk berkas."""
    path = Path(shot)
    for parent in path.parents:
        if _RUN_DIR_RE.match(parent.name):
            return str(parent)
    return str(path.parent)


def e2e_summary(cells, versions, browsers):
    """Field E2E top-level dari record TERPILIH (cell-contract.md > Aggregate)."""
    selected = list(_selected_records(cells, versions, browsers))
    pf = [s for _v, _b, s in selected if pl.record_state(s)["state"] in ("pass", "fail")]
    notes, shot_dirs = [], []
    for _v, _b, s in selected:
        for n in s.get("scenario_notes") or []:
            if n not in notes:
                notes.append(n)
        shots = s.get("screenshots")
        for shot in (shots if isinstance(shots, list) else []):
            if isinstance(shot, str) and shot:
                d = _run_folder(shot)
                if d not in shot_dirs:
                    shot_dirs.append(d)
    run = [b for b in browsers
           if any(pl._driven(s.get("phase_durations"), b) for _v, bb, s in selected if bb == b)]
    not_run = []
    for ver in versions:
        for b in browsers:
            recs = cells[ver][b]["records"]
            if recs and recs[-1].get("state") == "not-run":
                not_run.append({"cell": f"{ver}:{b}", "reason": recs[-1].get("reason")})
    return {
        "e2e_cells": {ver: {b: e2e_cell_entry(cells[ver][b]) for b in browsers}
                      for ver in versions},
        "not_run_cells": not_run,
        "e2e_smoke_only": bool(pf) and all(pl._authored(s) == 0 for s in pf),
        "e2e_scenario_notes": notes,
        "e2e_browsers": list(browsers),
        "e2e_browsers_run": run,
        "e2e_screenshot_dir": shot_dirs,
        "e2e_phase_durations": e2e_phase_durations(cells, versions, browsers),
        "e2e_has_records": any(cells[v][b]["records"] for v in versions for b in browsers),
    }


def _version_matches(entry, full_ver):
    """Temuan berlaku utk full_ver bila entri semajor DAN prefix-komponen target.

    Model bisa menulis 'versions' dalam bentuk penuh (8.1) atau major (8); keduanya
    harus resolve supaya temuan error tak diam-diam terlewat.

    Dulu ini melebur keduanya lewat kesamaan MAJOR saja, yang benar untuk major-form
    dan SALAH begitu reviewer menyebut minor: '9.0' dan '9.1' semajor, jadi temuan
    yang eksplisit dibatasi ke 9.0 ikut memblok 9.1 — dan sebaliknya. Kini major harus
    sama (menjaga '1.7' tetap atomik, jadi '1' tak menyapu 1.7.x) DAN komponen yang
    dua-duanya sebutkan harus cocok — itu yang memisahkan minor yang bertentangan
    sambil membiarkan '8' resolve ke '8.1'. Domain key-nya sama dgn `affects`
    ps-static-scan, jadi definisinya diambil dari sana, bukan ditulis ulang.
    Token non-string (mis. 8 alih-alih "8") di-coerce, bukan meledak: crash =
    exit 1 yang bertabrakan dgn kode vonis-gagal (validate_adversarial yang
    melaporkannya keras sbg pelanggaran skema).
    """
    a, b = str(entry).strip(), str(full_ver).strip()
    if ss.key_major(a) != ss.key_major(b):
        return False
    pa, pb = a.split("."), b.split(".")
    n = min(len(pa), len(pb))
    return n > 0 and pa[:n] == pb[:n]


def validate_adversarial(adversarial, target_versions):
    """Validasi struktural payload adversarial buatan model. Return list pelanggaran.

    Tanpa ini pelanggaran skema DIAM-DIAM melemahkan vonis: severity di luar enum
    ('critical'/'high'/'blocker') tak pernah dihitung memblok, dan token versi yang
    tak resolve ke target ('PS8', '1.7-9') membuat temuan di-drop dari semua versi.
    Pelanggaran = input error (perbaiki file, jalankan ulang), bukan vonis.
    """
    notes = []
    if adversarial is None:
        return notes
    # BENTUK dulu, baru nilai field: payload salah-bentuk (list telanjang, findings
    # dict, entri string) dulu meledak AttributeError -> exit 1 = kode vonis-gagal,
    # jadi file rusak terbaca "module gagal". Bentuk salah = pelanggaran skema (exit 2).
    if not isinstance(adversarial, dict):
        return ["payload bukan JSON object — bentuk: {\"versions\": [...], \"findings\": [ {...} ]}"]
    # Cakupan yang DITINJAU wajib dinyatakan: tanpanya reviewer yang meninjau satu versi
    # tak bisa dibedakan dari yang meninjau semuanya, dan adversarial_layer tak punya dasar
    # untuk menolak klaim. Absen = pelanggaran skema (keras), bukan diam-diam dianggap penuh.
    scope = adversarial.get("versions")
    if scope is None:
        notes.append("'versions' top-level tak ada — nyatakan versi yang KAMU TINJAU "
                     "(bentuk: \"versions\": [\"1.7.8\", \"8.1\", \"9.1\"])")
    elif not isinstance(scope, list):
        notes.append(f"'versions' top-level bertipe {type(scope).__name__}, harus list of string")
    elif not scope:
        notes.append("'versions' top-level kosong — lapis yang tak meninjau versi apa pun bukan review")
    else:
        # Token cakupan TIDAK diwajibkan resolve ke target run ini: review penuh
        # (1.7.8+8.1+9.1) yang dipakai-ulang di run yang dipersempit ke 9.1 itu sah —
        # justru superset itulah yang membuat ps-plan-layers membolehkan reuse. Yang
        # menilai cukup/tidaknya cakupan adalah adversarial_layer, per versi.
        for e in scope:
            if not isinstance(e, str) or not e.strip():
                notes.append(f"'versions' top-level: token {e!r} bukan string tak-kosong "
                             "— tulis sebagai teks (\"8.1\")")
    # Token per-temuan diukur terhadap CAKUPAN YANG DITINJAU, bukan target run ini. Review
    # penuh (1.7.8+8.1+9.1) yang dipakai-ulang di run yang dipersempit ke 9.1 sah membawa
    # temuan bertanda 8.1 — adversarial_layer yang memfilternya per versi. Mengukurnya ke
    # target run membuat gerbang ini menolak persis alur reuse yang dibolehkan cek cakupan
    # di atas: dua cek dalam satu fungsi berbeda pendapat soal pertanyaan yang sama. Yang
    # tetap ditangkap: token ngawur ('PS8') yang tak resolve ke mana pun -> temuan ter-drop diam-diam.
    known = (scope if isinstance(scope, list) and scope
             and all(isinstance(e, str) and e.strip() for e in scope) else target_versions)
    findings = adversarial.get("findings", [])
    if not isinstance(findings, list):
        notes.append(f"'findings' bertipe {type(findings).__name__}, harus list")
        return notes
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            notes.append(f"finding[{i}]: bertipe {type(f).__name__}, harus object")
            continue
        fid = f.get("id", f"finding[{i}]")
        sev = f.get("severity")
        if sev not in ("error", "warning"):
            notes.append(f"{fid}: severity '{sev}' di luar enum error|warning — tak akan pernah memblok")
        vers = f.get("versions")
        if vers is not None and not isinstance(vers, list):
            # Skalar truthy (8.1, true) tak bisa di-iterasi -> TypeError -> exit 1 =
            # kode vonis-gagal. String pun salah: iterasinya per-karakter.
            notes.append(f"{fid}: 'versions' bertipe {type(vers).__name__}, harus list of string")
            continue
        for e in (vers or []):
            if not isinstance(e, str):
                notes.append(f"{fid}: token versi {e!r} bukan string — tulis sebagai teks (\"8.1\")")
                continue
            if not any(_version_matches(e, k) for k in known):
                notes.append(f"{fid}: token versi '{e}' tak resolve ke cakupan yang ditinjau "
                             f"({','.join(known)}) — temuan diam-diam ter-drop")
    return notes


def adversarial_layer(adversarial, full_ver):
    """Lapis 3 — temuan judgment model. Konklusif hanya untuk versi yang BENAR-BENAR ditinjau.

    Reviewer menyatakan cakupannya di `versions` top-level (references/adversarial-lens.md).
    Versi di luar cakupan itu TAK punya bukti adversarial: menandainya konklusif membuat
    `ready` mengklaim persis review yang tak pernah terjadi — reviewer yang jujur bilang
    "aku cuma meninjau 8.1" lalu dibaca sbg "ketiga versi bersih". Cakupan dibaca lewat
    pl.layer_versions supaya definisinya sama dgn yang menolak reuse di pra-pass.
    """
    if adversarial is None:
        return {"ran": False, "conclusive": False, "errors": 0,
                "reason": "tak ada file temuan adversarial", "findings": []}
    reviewed = pl.layer_versions(adversarial)
    if reviewed is not None and not any(_version_matches(e, full_ver) for e in reviewed):
        return {"ran": True, "conclusive": False, "errors": 0,
                "reason": f"versi tak ditinjau reviewer (cakupan: {', '.join(sorted(reviewed)) or 'kosong'})",
                "findings": []}
    findings = []
    for f in adversarial.get("findings", []):
        vers = f.get("versions")  # kosong/None = semua versi target
        if vers and not any(_version_matches(e, full_ver) for e in vers):
            continue
        findings.append({"source": "adversarial", "id": f.get("id", "adv"),
                         "severity": f.get("severity", "warning"),
                         "message": f.get("message", ""), "fix": f.get("fix", ""),
                         "location": f.get("location", "")})
    errs = sum(1 for f in findings if f["severity"] == ERROR)
    return {"ran": True, "conclusive": True, "errors": errs, "findings": findings}


def scenario_layer(scen, full_ver):
    """Lapis 5 — skenario kondisi-rusak. Konklusif hanya bila ADA skenario yang dinilai.

    Nol skenario BUKAN lolos: module tanpa `tests/scenarios/` tak membuktikan apa pun tentang
    perilakunya di keadaan rusak, dan menandainya konklusif membuat `ready` mengklaim
    pengujian yang tak pernah ada. Itu juga sebabnya lapis ini hanya MENGGERBANG bila module
    memang mengapalkan skenario (lihat gerbang `required` di main) — memaksanya ke tiap module
    akan menjatuhkan `ready` semua module lama demi lapis yang belum mereka pakai.

    Skenario yang `given`-nya gagal masuk kanal TAK KONKLUSIF, bukan gagal: kondisi rusaknya
    tak terbentuk, jadi apa pun yang dinilai sesudahnya bicara tentang keadaan yang bukan
    yang dimaksud.
    """
    if scen is None:
        return {"ran": False, "conclusive": False, "errors": 0,
                "reason": "tak ada file lapis skenario", "findings": []}
    ver = (scen.get("versions") or {}).get(full_ver)
    if ver is None:
        return {"ran": True, "conclusive": False, "errors": 0,
                "reason": "versi tak dijalankan di lapis skenario", "findings": []}
    findings = []
    for s in ver.get("scenarios", []):
        if s.get("conclusive") and not s.get("ok"):
            gagal = [st for st in s.get("steps", []) if not st.get("ok")]
            findings.append({
                "source": "scenario", "id": f"scenario-{s.get('name', '?')}",
                "severity": ERROR,
                "message": f"skenario kondisi-rusak gagal: {s.get('name', '?')}",
                "fix": "; ".join(f"{g.get('phase')}: {g.get('detail', '')[:120]}" for g in gagal[:3]),
                "location": s.get("source", ""),
            })
    return {"ran": True, "conclusive": bool(ver.get("conclusive")),
            "errors": len(findings), "findings": findings,
            "scenarios_run": len(ver.get("scenarios", []))}


def merge_version(full_ver, static, flash, adversarial, e2e_row=None, scen=None, browsers=()):
    """Vonis satu versi. `e2e_row` = {browser: info evaluate_cell} sel versi ini, `browsers` =
    psm_e2e_browsers terkonfigurasi; tanpa keduanya Lapis 4 = tanpa bukti (`missing`)."""
    s = static_layer(static, full_ver)
    fl = flashlight_layer(flash, full_ver)
    adv = adversarial_layer(adversarial, full_ver)
    e = e2e_layer(e2e_row, full_ver, browsers)
    e2e_state, e2e_reason = e2e_verdict(e2e_row, browsers)
    sc = scenario_layer(scen, full_ver)

    all_findings = [f for layer in (s, fl, adv, e, sc) for f in layer["findings"]]
    blocking = [f for f in all_findings if f["severity"] == ERROR]
    # Lolos bila tak ada error dari lapis KONKLUSIF manapun.
    passed = len(blocking) == 0
    # Vonis konklusif hanya bila setidaknya static teruji; catat flashlight/e2e tak konklusif.
    conclusive = s["conclusive"]  # vonis dasar ADA hanya bila aturan benar-benar dinilai
    return {
        "pass": passed,
        "conclusive": conclusive,
        "flashlight_conclusive": fl["conclusive"],
        "e2e_conclusive": e["conclusive"],
        # Vonis E2E per versi (cell-contract.md > Aggregate): fail | inconclusive | pass, dan
        # alasannya (`fail` literal; alasan sel pertama tanpa bukti lulus; null saat pass).
        "e2e_state": e2e_state,
        "reason": e2e_reason,
        # Rollup KEEMPAT lapis. SKILL.md & psm-scaffold sudah disuruh membaca "hitungan
        # error/warning per versi dari situ apa adanya" — hitungan yang tak pernah ada
        # produsennya: satu-satunya `warnings` yang diemit milik lapis static saja, jadi
        # warning adversarial/flashlight tak terhitung. Pemilik hitungannya agregat, bukan prosa.
        "errors": len(blocking),
        "warnings": len([f for f in all_findings if f["severity"] == "warning"]),
        "scenario_conclusive": sc["conclusive"],
        "layers": {"static": s, "flashlight": fl, "adversarial": adv, "e2e": e, "scenario": sc},
        "blocking": blocking,
    }


def _input_error(msg, *hints):
    print(f"error: {msg}", file=sys.stderr)
    for h in hints:
        print(h, file=sys.stderr)
    return 2


def read_aggregate_config(path):
    """--config -> (versions, browsers, psm_flashlight_tag_map). Error -> CellConfigError.

    Himpunan sel dibaca LANGSUNG lewat normalizer bersama (ps-flashlight-run), bukan
    apply_config_file: `--versions` tak pernah menyusutkan himpunan wajib.
    """
    fl = pl.fl
    cfg = fl.read_config_json(path) if path else {}
    versions = fl.normalize_versions(cfg.get("psm_target_versions"))
    browsers = fl.normalize_engines(cfg.get("psm_e2e_browsers"))
    tag_map = cfg.get("psm_flashlight_tag_map")
    if tag_map is not None and not isinstance(tag_map, str):
        raise fl.CellConfigError(f"psm_flashlight_tag_map={tag_map!r} harus string versi=tag,...")
    return versions, browsers, tag_map


def main():
    ap = argparse.ArgumentParser(description="Satukan empat lapis validasi jadi vonis terstruktur.",
                                 epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reports-dir", help="Folder laporan. Dengan --module, nama file lapis "
                                          "kanonik DITURUNKAN (<module>-<lapis>.json) dan lapis "
                                          "yang filenya absen dilewati — path tak perlu diketik. "
                                          "Flag lapis eksplisit tetap menang bila diberikan. Lapis 4 "
                                          "(E2E) dibaca dari histori per sel di folder ini.")
    ap.add_argument("--module", help="Path folder module. Wajib bersama --reports-dir; juga "
                                     "menegakkan identitas: file lapis milik module lain ditolak.")
    ap.add_argument("--static", help="JSON output ps-static-scan.py (wajib kecuali --reports-dir/--module)")
    ap.add_argument("--flashlight", help="JSON output ps-flashlight-run.py (opsional bila dilewati)")
    ap.add_argument("--adversarial", help="JSON temuan adversarial buatan model (opsional)")
    ap.add_argument("--e2e", help="DIHAPUS — Lapis 4 dibaca dari histori sel lewat --reports-dir "
                                  "+ --module; memberi flag ini = exit 2")
    ap.add_argument("--scenario", help="JSON output ps-scenario-run.py (Lapis 5, opsional bila dilewati)")
    ap.add_argument("--config", help="JSON hasil resolve-psm-config.py. Versi target = "
                                     "psm_target_versions, sel E2E wajib = psm_target_versions x "
                                     "psm_e2e_browsers, tag image dari psm_flashlight_tag_map "
                                     "(default skrip bila absen).")
    ap.add_argument("--tag-map", help="Peta LENGKAP versi=tag (MENGGANTI psm_flashlight_tag_map/"
                                      "default) — sama seperti yang diteruskan ke plan & runner")
    ap.add_argument("--extra-tag-map", help="Tag TAMBAHAN versi=tag (MENAMBAH di atas peta)")
    ap.add_argument("--session", help="Token sesi validasi (opsional; divalidasi [a-z0-9]{16}, "
                                      "belum dipakai)")
    ap.add_argument("--versions", help="Opsional, harus SAMA (sebagai himpunan) dengan "
                                       "psm_target_versions dari --config; beda = exit 2")
    ap.add_argument("--require", help="Lapis yang WAJIB tuntas agar `ready` true, dipisah koma "
                                      f"({'|'.join(LAYERS)}). DEFAULT: KEEMPATNYA — siap-rilis berarti "
                                      "keempat lapis membuktikannya. Runner yang tak sanggup (tanpa Docker/"
                                      "browser) memang menghasilkan ready=false: itu jujur, bukan cacat. "
                                      "Sengaja menggating lebih sempit? Nyatakan di sini — pilihannya terekam "
                                      "di `required_layers`, bukan tersembunyi di flag yang kebetulan tak dipakai.")
    ap.add_argument("-o", "--output", help="File output JSON (default: stdout)")
    args = ap.parse_args()

    # File E2E tunggal bukan lagi bukti: sel dibuktikan oleh historinya sendiri. Menerima
    # --e2e diam-diam akan mengkredit file lama (atau run langsung ps-e2e-run) ke `ready`.
    if args.e2e:
        return _input_error("--e2e tak lagi diterima — bukti Lapis 4 = histori per sel "
                            "<module>-e2e-<ver>-<browser>.jsonl",
                            "beri --reports-dir + --module (histori dibaca dari folder laporan)")
    if args.session is not None and not pl.valid_session(args.session):
        return _input_error(f"--session tak valid: {args.session!r} — harus [a-z0-9]{{16}} "
                            "(dari ps-plan-layers.py --new-session)")

    # Nama file lapis DITURUNKAN bila folder+module diberi. Mengetik empat path dengan tangan
    # di akhir run panjang adalah kerja deterministik yang sudah punya satu jawaban benar
    # (cermin layer_file() di ps-run-layer.py), dan salah ketik segmen module diam-diam
    # mengkreditkan bukti module lain ke vonis ini.
    if bool(args.reports_dir) != bool(args.module):
        print("error: --reports-dir dan --module harus diberikan bersama", file=sys.stderr)
        sys.exit(2)

    # Versi target = himpunan TERKONFIGURASI (bukan --versions, bukan versi di hasil static).
    try:
        target_versions, cfg_browsers, cfg_tag_map = read_aggregate_config(args.config)
    except pl.fl.CellConfigError as e:
        return _input_error(f"himpunan sel terkonfigurasi tak sah: {e}")
    if args.versions is not None:
        try:
            asked = pl.fl.normalize_versions(args.versions, key="--versions")
        except pl.fl.CellConfigError as e:
            return _input_error(str(e))
        if set(asked) != set(target_versions):
            return _input_error(f"--versions {','.join(asked)} beda dari versi terkonfigurasi "
                                f"({','.join(target_versions)})",
                                "versi target agregat = psm_target_versions dari --config; "
                                "hapus --versions atau samakan")

    if args.reports_dir:
        mod_name = Path(args.module).resolve().name
        for layer in LAYERS:
            # Lapis 4 tak punya file kanonik lagi: <module>-e2e.json / -e2e-<ver>.json yang
            # tersisa (run lama, atau report view --merge-only) DIABAIKAN, bukan bukti.
            if layer == "e2e" or getattr(args, layer, None):
                continue  # flag eksplisit menang
            cand = Path(args.reports_dir) / f"{mod_name}-{layer}.json"
            if cand.exists():
                setattr(args, layer, str(cand))
        if not args.output:
            stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d-%H%M%S")
            args.output = str(Path(args.reports_dir) / f"{mod_name}-{stamp}.json")
    if not args.static:
        print("error: --static wajib (atau beri --reports-dir + --module agar diturunkan)",
              file=sys.stderr)
        sys.exit(2)

    static = load_json(args.static, "static-scan")
    flash = load_json(args.flashlight, "flashlight") if args.flashlight else None
    adversarial = load_json(args.adversarial, "adversarial") if args.adversarial else None
    scen = load_json(args.scenario, "scenario") if args.scenario else None

    # Bentuk file lapis buatan skrip digerbang SEBELUM dibaca — kalau tidak, file terpotong
    # meledak jadi Traceback + exit 1 dan CI tak bisa membedakannya dari "module punya error
    # pemblokir". static_layer membaca f["id"]/f["severity"]/f["message"] langsung, jadi khusus
    # static kunci itu diwajibkan; lapis lain memakai .get() dan cukup dijaga bentuk containernya.
    # Gerbang identitas module: ps-aggregate dulu membaca `module` HANYA dari payload static
    # dan tak pernah membandingkannya dengan lapis lain, jadi satu path salah ketik di folder
    # yang memuat beberapa module dikreditkan diam-diam ke vonis ini. Ini satu-satunya skrip
    # yang mengemit `ready`, jadi kelas itu tak boleh punya permukaan di sini.
    static_module = (static or {}).get("module")
    if static_module:
        for payload, label in ((flash, "flashlight"), (adversarial, "adversarial")):
            other = (payload or {}).get("module")
            if other and other != static_module:
                print(f"error: file lapis {label} milik module '{other}', bukan '{static_module}' "
                      "— bukti module lain tak boleh masuk vonis ini", file=sys.stderr)
                sys.exit(2)

    for payload, label, keys in ((static, "static-scan", ("id", "severity", "message")),
                                 (flash, "flashlight", ())):
        if payload is None:
            continue
        shape_notes = validate_layer_shape(payload, keys)
        if shape_notes:
            print(f"error: file lapis {label} tak lolos gerbang bentuk:", file=sys.stderr)
            for n in shape_notes:
                print(f"  - {n}", file=sys.stderr)
            print("file lapis rusak = input rusak (exit 2), bukan vonis gagal (exit 1) — "
                  "jalankan ulang lapis itu lalu ulangi", file=sys.stderr)
            return 2

    # Gerbang himpunan kosong, kembaran `--require` kosong di bawah. Nol versi target bikin
    # tiap loop cakupan lolos secara vakum -> ready=true atas NOL versi terbukti. Normalizer
    # sudah menolak daftar kosong; gerbang ini tetap dijaga di titik pakai.
    if not target_versions:
        return _input_error("tak ada versi target — psm_target_versions kosong",
                            "vonis atas nol versi bukan vonis")

    # Gerbang skema di satu-satunya seam model->skrip: tolak KERAS (exit 2, bukan
    # exit 1 vonis-gagal) supaya pelanggaran tak diam-diam tak-memblok / ter-drop.
    schema_notes = validate_adversarial(adversarial, target_versions)
    if schema_notes:
        print("error: file adversarial tak lolos validasi skema:", file=sys.stderr)
        for n in schema_notes:
            print(f"  - {n}", file=sys.stderr)
        print("perbaiki file temuan adversarial lalu jalankan ulang "
              "(severity: error|warning; versions: token yang sama dengan --versions)", file=sys.stderr)
        return 2

    # Versi terkonfigurasi yang TAK ADA di hasil static (run yang dipersempit) BUKAN input error:
    # static_layer menandainya tak konklusif, version_ready menjatuhkan `ready` versi itu, dan
    # laporan menyebutnya belum terbukti. (Gerbang `unscanned` exit 2 lama dihapus.)

    # Lapis 4: histori per sel, dinilai dgn fungsi plan (fingerprint + tag sama dgn runner).
    raw_tag_map = args.tag_map if args.tag_map is not None else cfg_tag_map
    tag_map = pl.fl.parse_tag_map(raw_tag_map, args.extra_tag_map)
    try:
        if args.reports_dir:
            module_dir = Path(args.module).resolve()
            fingerprint = pl.source_fingerprint(module_dir, args.reports_dir)
            current_notes = pl._e2e_scenario_notes(module_dir)
            cells = evaluate_e2e_cells(args.reports_dir, module_dir.name, target_versions,
                                       cfg_browsers, fingerprint, tag_map, current_notes)
        else:
            cells = evaluate_e2e_cells(None, None, target_versions, cfg_browsers, None,
                                       tag_map, None)
    except pl.PlanInputError as e:
        return _input_error(str(e))

    versions = {}
    overall_pass = True
    all_conclusive = True
    all_e2e_conclusive = True
    for full_ver in target_versions:
        m = merge_version(full_ver, static, flash, adversarial, cells[full_ver], scen,
                          browsers=cfg_browsers)
        versions[full_ver] = m
        overall_pass = overall_pass and m["pass"]
        all_conclusive = all_conclusive and m["flashlight_conclusive"]
        all_e2e_conclusive = all_e2e_conclusive and m["e2e_conclusive"]
    e2e = e2e_summary(cells, target_versions, cfg_browsers)

    flashlight_ran = bool(flash and flash.get("docker_available"))

    # Default KETAT: keempat lapis. Dulu defaultnya "lapis yang filenya diberikan" —
    # itu membuat lapis yang TAK dijalankan otomatis TAK diwajibkan, jadi pemanggil
    # yang melewatkan flag dapat ready=true atas satu lapis saja: bug lama bersalin nama.
    # Penyempitan harus jadi pernyataan sadar yang terekam, bukan efek samping kelalaian.
    if args.require:
        required = [l.strip() for l in args.require.split(",") if l.strip()]
        # Container KOSONG = seam yang sama dgn token salah, satu tingkat lebih dalam:
        # `--require ','` itu truthy (jadi tak jatuh ke default ketat) tapi memfilter jadi []
        # -> `for layer in []` tak pernah jalan -> ready=true atas NOL lapis terbukti, di
        # runner tanpa Docker sekalipun. Persis pola 'affects: []' yang digerbang
        # ps-static-scan.validate_extra_rules. Penyempitan harus menyebut lapis, atau bukan
        # penyempitan — ia pembatalan gerbang.
        if not required:
            print(f"error: --require tak menyebut satu lapis pun — sah: {', '.join(LAYERS)}",
                  file=sys.stderr)
            print("hapus flagnya untuk default ketat (keempat lapis)", file=sys.stderr)
            return 2
        bad = [l for l in required if l not in LAYERS]
        if bad:
            print(f"error: --require memuat lapis tak dikenal: {', '.join(bad)} — sah: {', '.join(LAYERS)}",
                  file=sys.stderr)
            return 2
    else:
        required = list(LAYERS)
        # Lapis 5 hanya menggerbang bila module MEMANG mengapalkan skenario. Memaksanya ke
        # tiap module akan menjatuhkan `ready` semua module lama demi lapis yang belum mereka
        # pakai — regresi yang kena semua orang. Sebaliknya, module yang MENYATAKAN skenario
        # wajib melewatinya: menyatakan lalu gagal tak boleh tetap siap-rilis.
        # Konsekuensi jujur & disengaja: menghapus tests/scenarios/ menghijaukan `ready`,
        # sama seperti menghapus test mana pun. Gerbang mengukur yang ADA, bukan yang mungkin.
        if not (scen and scen.get("scenario_sources")):
            required = [l for l in required if l != "scenario"]

    # `ready` per versi, dari fungsi yang sama yang menghitung `ready` keseluruhan. Kontrak
    # ketiga skill sibling ditulis per-versi ("siap hanya bila `ready` true di 1.7.x, 8.x, 9.x")
    # dan sampai sekarang tak ada yang mengemitnya, jadi mereka membaca yang global lalu
    # menyebutnya per-versi. Diisi di sini karena `required` baru diketahui setelah gerbangnya.
    # Bila `e2e` diwajibkan, sel tanpa bukti lulus gate-grade membawa `inconclusive_note` di
    # layers.e2e versinya, jadi `ready` jatuh lewat kanal yang sama (sel tak-gradeable juga).
    for m in versions.values():
        m["ready"] = version_ready(m, required)

    result = {
        "module": static.get("module", ""),
        "target_versions": target_versions,
        "versions": versions,
        "pass": overall_pass,
        "ready": compute_ready(versions, required),
        "required_layers": required,
        "flashlight_conclusive": all_conclusive,
        "e2e_conclusive": all_e2e_conclusive,
        "scenario_conclusive": all(m["layers"]["scenario"]["conclusive"] for m in versions.values()),
        "layers_run": {
            "static": True,
            "flashlight": flashlight_ran,
            "adversarial": adversarial is not None,
            "e2e": e2e["e2e_has_records"],
            "scenario": scen is not None,
        },
        # Bukti E2E per sel: tiap sel terkonfigurasi tampil, termasuk yang dipersempit/hilang.
        "e2e_cells": e2e["e2e_cells"],
        "not_run_cells": e2e["not_run_cells"],
        # Cakupan E2E: tanpa assertion authored, Lapis 4 hanya membuktikan "shop tak rusak".
        "e2e_smoke_only": e2e["e2e_smoke_only"],
        # Himpunan browser WAJIB (terkonfigurasi) vs engine yang benar-benar men-drive di
        # record terpilih — penyempitan terekam di laporan, bukan diingat model.
        "e2e_browsers": e2e["e2e_browsers"],
        "e2e_browsers_run": e2e["e2e_browsers_run"],
        "e2e_phase_durations": e2e["e2e_phase_durations"],
    }
    # Spec E2E authored yang dilewati di-echo top-level supaya TAK hilang walau semua versi tak
    # konklusif — dari record terpilih (bukan dari module sekarang).
    if e2e["e2e_scenario_notes"]:
        result["e2e_scenario_notes"] = e2e["e2e_scenario_notes"]
    # Folder run screenshot record terpilih — supaya render bisa ditinjau, bukan cuma diproduksi.
    if e2e["e2e_screenshot_dir"]:
        result["e2e_screenshot_dir"] = e2e["e2e_screenshot_dir"]
    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"ditulis: {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
