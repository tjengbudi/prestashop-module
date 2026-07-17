#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Satukan empat lapis validasi jadi satu vonis terstruktur — deterministik.

Menerima output JSON ps-static-scan.py (Lapis 1) dan ps-flashlight-run.py
(Lapis 2), file temuan adversarial buatan model (Lapis 3), plus output
ps-e2e-run.py (Lapis 4, uji perilaku browser), lalu menghitung `pass` per versi
dan keseluruhan secara NATIVE — bukan lewat model.

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
import importlib.util
import json
import sys
from pathlib import Path

ERROR = "error"
LAYERS = ("static", "flashlight", "adversarial", "e2e")

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
    for m in versions.values():
        if not m["pass"]:
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
    evaluated = v.get("rules_evaluated")
    # TIPE, bukan cuma nilai. `"0"`, `[]`, `true`, `-1` lolos cek nilai lalu memulihkan
    # ready=true — persis kelas yang validate_extra_rules ada untuk menutup ("'affects': [9]
    # (angka JSON tanpa kutip) lolos cek list lalu rule-nya DIAM-DIAM tak pernah menyala").
    # Absen, salah tipe, dan negatif sama-sama berarti "cakupan tak diketahui", dan tak
    # diketahui tak boleh terbaca sebagai lolos. bool lolos isinstance(int) di Python, jadi
    # disebut terpisah: `true` bukan hitungan.
    if isinstance(evaluated, bool) or not isinstance(evaluated, int) or evaluated < 0:
        notes.append("hasil static tak mencatat `rules_evaluated` yang sah (file lapis dari "
                     "skrip lama atau salah bentuk) — cakupan aturan tak bisa dipastikan; "
                     "jalankan ulang Lapis 1")
    elif evaluated == 0:
        notes.append("nol aturan dinilai di versi ini — ruleset yang dipakai tak menyebut "
                     "major-nya, jadi 0 error di sini bukan lolos")
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
    if infra:
        return {"state": "not_conclusive", "conclusive": False, "errors": 0,
                "reason": "; ".join(infra), "findings": []}

    # Konklusif: kumpulkan temuan error nyata (install ditolak / phpcs error).
    findings = []
    if not install.get("ok"):
        findings.append({"source": "flashlight", "id": "flashlight-install",
                         "severity": ERROR, "message": "modul gagal install di core asli",
                         "fix": "periksa log install flashlight", "location": v.get("image", "")})
    cs = v.get("coding_standard") or {}
    # Hanya errors konklusif yang memblok. Neon auto-generate (advisory) memetakan
    # temuannya ke warnings (errors=0) di ps-flashlight-run, jadi tak sampai sini.
    if cs.get("available") and cs.get("parse_ok") and cs.get("errors", 0) > 0:
        for m in cs.get("error_messages", []):
            findings.append({"source": "flashlight", "id": "flashlight-phpstan",
                             "severity": ERROR, "message": m.get("message", "phpstan error"),
                             "fix": m.get("source", ""), "location": f"line {m.get('line', '?')}"})
        if not cs.get("error_messages"):
            findings.append({"source": "flashlight", "id": "flashlight-phpstan",
                             "severity": ERROR, "message": f"{cs['errors']} phpstan error",
                             "fix": "", "location": v.get("image", "")})
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
    elif cs.get("coverage_ok") is False:
        # Canary tak terdeteksi: phpstan jalan & laporannya terparse, tapi TAK menganalisis satu
        # file pun dari module (mis. neon module meng-excludePaths dirinya sendiri). Laporan JSON
        # phpstan tak bisa membedakan ini dari "bersih" — map `files` cuma memuat file YANG
        # BER-ERROR — jadi tanpa kontrol positif sebuah module bisa MEMBELI vonis CS bersih
        # dengan neon yang mengecualikan dirinya.
        layer["inconclusive_note"] = ("phpstan tak menganalisis satu file pun dari module "
                                      "(neon module mengecualikannya — canary tak terdeteksi) "
                                      "— coding standard tak diuji; tak memblok")
    elif "coverage_ok" not in cs:
        layer["inconclusive_note"] = ("hasil flashlight tak mencatat `coverage_ok` (file lapis dari "
                                      "skrip lama) — cakupan phpstan tak bisa dipastikan; "
                                      "jalankan ulang Lapis 2")
    return layer


def authored_assertions(e2e, full_ver):
    """Assertion authored yang benar-benar dinilai di versi ini. None = tak tercatat.

    Tipe dijaga, bukan cuma nilai: `"0"`/`[]`/`true`/`-1` yang lolos jadi hitungan sah akan
    memulihkan `ready` persis seperti di static_layer. Tak tercatat = cakupan tak diketahui,
    dan tak diketahui tak pernah boleh terbaca sebagai teruji.
    """
    v = ((e2e or {}).get("versions") or {}).get(full_ver) or {}
    n = v.get("authored_assertions")
    if isinstance(n, bool) or not isinstance(n, int) or n < 0:
        return None
    return n


def is_smoke_only(e2e, full_ver):
    """True bila Lapis 4 di versi ini tak menegakkan satu assertion authored pun.

    Satu definisi dipakai e2e_layer (yang menjatuhkan `ready`) dan main (yang meng-echo
    field-nya): dua perhitungan terpisah atas pertanyaan yang sama pernah bikin field dan
    gerbang berbeda pendapat.

    Dulu jawabannya diambil dari NAMA skenario — ada `source` bukan `builtin:` = "ada uji
    perilaku". Premis struktural itu bisa dipuaskan file yang tak menegakkan apa pun: spec
    berisi dua `screenshot` membalik `ready` false->true tanpa menguji sebutir pun. Sekarang
    jawabannya hitungan assertion konklusif dari produsen. `None` (tak tercatat) BUKAN 0 —
    itu ditangani terpisah di e2e_layer sebagai "tak bisa dipastikan".
    """
    return authored_assertions(e2e, full_ver) == 0


def e2e_layer(e2e, full_ver):
    """Lapis 4 — konklusif hanya bila browser+container naik bersih & module ter-install.

    Tak konklusif (degrade jujur, tak memblok): Playwright/Docker absen, image belum
    ada, binary browser belum di-`install`, container tak healthy, PS tak terjangkau,
    module gagal install (itu wilayah vonis Lapis 2), atau timeout. Konklusif: assertion
    browser (smoke/skenario) benar-benar dievaluasi — kegagalannya memblok.
    """
    if not e2e or e2e.get("status") == "skipped" or not e2e.get("e2e_available", False):
        reason = (e2e or {}).get("reason", "Playwright/Docker tak tersedia — uji E2E dilewati.")
        return {"state": "skipped", "conclusive": False, "errors": 0, "reason": reason, "findings": []}

    v = e2e.get("versions", {}).get(full_ver)
    if v is None:
        return {"state": "skipped", "conclusive": False, "errors": 0,
                "reason": "versi tak ada di hasil e2e", "findings": []}

    # Kegagalan infrastruktur → tak konklusif, jangan memblok.
    infra = list(v.get("errors", []))
    if v.get("skipped_browser"):
        infra.append("tak ada browser yang bisa diluncurkan (jalankan 'playwright install')")
    if not (v.get("install") or {}).get("ok"):
        infra.append("module tak ter-install — perilaku browser tak bisa dinilai (Lapis 2 memvonis install)")
    if not v.get("browsers"):
        infra.append("tak ada browser dijalankan")
    if infra:
        return {"state": "not_conclusive", "conclusive": False, "errors": 0,
                "reason": "; ".join(dict.fromkeys(infra)), "findings": []}

    # Konklusif (≥1 browser jalan & module ter-install): temuan browser memblok versi ini.
    # Masalah per-browser (browser_notes) & spec authored rusak (scenario_notes) TAK
    # membatalkan temuan konklusif — hanya coverage yang disurface sbg catatan (tak memblok).
    findings = [
        {"source": "e2e", "id": f.get("id", "e2e"), "severity": f.get("severity", ERROR),
         "message": f.get("message", ""), "fix": f.get("fix", ""), "location": f.get("location", "")}
        for f in v.get("findings", [])
    ]
    errs = sum(1 for f in findings if f["severity"] == ERROR)
    layer = {"state": "fail" if errs else "pass", "conclusive": True, "errors": errs, "findings": findings}
    notes = []
    # Tanpa spec authored, Lapis 4 cuma membuktikan "shop tak rusak" — BUKAN perilaku
    # module. Itu setengah lapis yang tak pernah dievaluasi, kembar persis dgn phpstan-absen
    # di flashlight_layer, jadi ia lewat kanal yang sama: `ready` jatuh, `pass` tak diblok.
    # Dulu dihitung di main() sbg `e2e_smoke_only` yang tak dibaca gerbang mana pun, jadi
    # module tanpa satu pun uji perilaku dapat hijau empat-lapis penuh.
    n_assert = authored_assertions(e2e, full_ver)
    if n_assert is None:
        notes.append("hasil E2E tak mencatat `authored_assertions` (file lapis dari skrip lama "
                     "atau salah bentuk) — cakupan uji perilaku tak bisa dipastikan; "
                     "jalankan ulang Lapis 4")
    elif is_smoke_only(e2e, full_ver):
        notes.append("nol assertion authored dinilai — perilaku module tak teruji (spec tanpa "
                     "aksi expect_* tak menegakkan apa pun); tulis skenario di tests/e2e/")
    inc = v.get("inconclusive") or []
    if inc:
        notes.append(f"{len(inc)} assertion tak konklusif (mis. login BO gagal)")
    for bn in (v.get("browser_notes") or []):
        notes.append(f"coverage browser: {bn}")
    sn = e2e.get("scenario_notes") or []
    if sn:
        notes.append(f"{len(sn)} spec E2E authored dilewati: {'; '.join(sn)}")
    if notes:
        layer["inconclusive_note"] = "; ".join(notes) + " — tak memblok"
    # Error console/JS: OBSERVASI, bukan celah cakupan. Kanalnya dipisah dari
    # `inconclusive_note` karena compute_ready menjatuhkan `ready` atas note itu — dan
    # `ready` yang bergantung pada berisik-tidaknya skrip pihak-ketiga saat itu bukan
    # ketegasan, melainkan tak deterministik. Tetap disurface supaya tak jadi sinyal yatim.
    if v.get("console_errors"):
        layer["advisory_note"] = (f"{v['console_errors']} error console/JS terdeteksi — advisory: "
                                  "tak memblok & tak menjatuhkan `ready`; tegakkan dengan aksi "
                                  "`expect_no_console_error` di skenario")
    return layer


def _major(ver):
    """Petakan versi ke major key: 1.7.8.11 -> 1.7, 8.1 -> 8, 9.1 -> 9."""
    ver = str(ver).strip()
    return "1.7" if ver.startswith("1.7") else ver.split(".")[0]


def _version_matches(entry, full_ver):
    """Temuan berlaku utk full_ver bila entri sama persis ATAU semajor.

    Model bisa menulis 'versions' dalam bentuk penuh (8.1) atau major (8);
    keduanya harus resolve supaya temuan error tak diam-diam terlewat.
    Token non-string (mis. 8 alih-alih "8") di-coerce, bukan meledak: crash =
    exit 1 yang bertabrakan dgn kode vonis-gagal (validate_adversarial yang
    melaporkannya keras sbg pelanggaran skema).
    """
    entry = str(entry).strip()
    return entry == full_ver or _major(entry) == _major(full_ver)


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


def merge_version(full_ver, static, flash, adversarial, e2e):
    s = static_layer(static, full_ver)
    fl = flashlight_layer(flash, full_ver)
    adv = adversarial_layer(adversarial, full_ver)
    e = e2e_layer(e2e, full_ver)

    blocking = [f for layer in (s, fl, adv, e) for f in layer["findings"] if f["severity"] == ERROR]
    # Lolos bila tak ada error dari lapis KONKLUSIF manapun.
    passed = len(blocking) == 0
    # Vonis konklusif hanya bila setidaknya static teruji; catat flashlight/e2e tak konklusif.
    conclusive = s["conclusive"]  # vonis dasar ADA hanya bila aturan benar-benar dinilai
    return {
        "pass": passed,
        "conclusive": conclusive,
        "flashlight_conclusive": fl["conclusive"],
        "e2e_conclusive": e["conclusive"],
        "layers": {"static": s, "flashlight": fl, "adversarial": adv, "e2e": e},
        "blocking": blocking,
    }


def main():
    ap = argparse.ArgumentParser(description="Satukan empat lapis validasi jadi vonis terstruktur.",
                                 epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--static", required=True, help="JSON output ps-static-scan.py")
    ap.add_argument("--flashlight", help="JSON output ps-flashlight-run.py (opsional bila dilewati)")
    ap.add_argument("--adversarial", help="JSON temuan adversarial buatan model (opsional)")
    ap.add_argument("--e2e", help="JSON output ps-e2e-run.py (Lapis 4, opsional bila dilewati)")
    ap.add_argument("--versions", help="Versi target dipisah koma (default: dari hasil static)")
    ap.add_argument("--require", help="Lapis yang WAJIB tuntas agar `ready` true, dipisah koma "
                                      f"({'|'.join(LAYERS)}). DEFAULT: KEEMPATNYA — siap-rilis berarti "
                                      "keempat lapis membuktikannya. Runner yang tak sanggup (tanpa Docker/"
                                      "browser) memang menghasilkan ready=false: itu jujur, bukan cacat. "
                                      "Sengaja menggating lebih sempit? Nyatakan di sini — pilihannya terekam "
                                      "di `required_layers`, bukan tersembunyi di flag yang kebetulan tak dipakai.")
    ap.add_argument("-o", "--output", help="File output JSON (default: stdout)")
    args = ap.parse_args()

    static = load_json(args.static, "static-scan")
    flash = load_json(args.flashlight, "flashlight") if args.flashlight else None
    adversarial = load_json(args.adversarial, "adversarial") if args.adversarial else None
    e2e = load_json(args.e2e, "e2e") if args.e2e else None

    # Bentuk file lapis buatan skrip digerbang SEBELUM dibaca — kalau tidak, file terpotong
    # meledak jadi Traceback + exit 1 dan CI tak bisa membedakannya dari "module punya error
    # pemblokir". static_layer membaca f["id"]/f["severity"]/f["message"] langsung, jadi khusus
    # static kunci itu diwajibkan; lapis lain memakai .get() dan cukup dijaga bentuk containernya.
    for payload, label, keys in ((static, "static-scan", ("id", "severity", "message")),
                                 (flash, "flashlight", ()), (e2e, "e2e", ())):
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

    if args.versions:
        target_versions = [v.strip() for v in args.versions.split(",")]
    else:
        target_versions = list(static.get("versions", {}).keys())

    # Gerbang himpunan kosong, kembaran `--require` kosong di bawah. Nol versi target bikin
    # tiap loop cakupan lolos secara vakum -> ready=true atas NOL versi terbukti. Harus
    # mendahului gerbang skema adversarial: dengan target kosong, `known` juga kosong, jadi
    # tiap token versi reviewer gagal resolve dan exit 2-nya menyalahkan file yang benar.
    if not target_versions:
        print("error: tak ada versi target — hasil static-scan tak memuat satu versi pun",
              file=sys.stderr)
        print("jalankan ps-static-scan.py dengan --versions lalu ulangi, atau sebut "
              "--versions di sini (vonis atas nol versi bukan vonis)", file=sys.stderr)
        return 2

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

    # Gerbang input: Lapis 1 selalu jalan & selalu konklusif, jadi versi target yang TAK ADA
    # di hasilnya berarti pemanggil meminta vonis atas versi yang tak pernah dipindai. Dulu
    # versi itu cuma "tak menyumbang temuan" -> tak ada yang memblok -> pass=true & exit 0:
    # ketiadaan bukti terbaca sebagai lolos. Itu kekeliruan pemanggil, bukan vonis.
    scanned = set(static.get("versions", {}).keys())
    unscanned = [v for v in target_versions if v not in scanned]
    if unscanned:
        print(f"error: versi target tak ada di hasil static-scan: {', '.join(unscanned)}",
              file=sys.stderr)
        print(f"  hasil static memuat: {', '.join(sorted(scanned)) or '(kosong)'}", file=sys.stderr)
        print("jalankan ps-static-scan.py dengan --versions yang sama lalu ulangi "
              "(vonis atas versi yang tak dipindai bukan vonis)", file=sys.stderr)
        return 2

    versions = {}
    overall_pass = True
    all_conclusive = True
    all_e2e_conclusive = True
    for full_ver in target_versions:
        m = merge_version(full_ver, static, flash, adversarial, e2e)
        versions[full_ver] = m
        overall_pass = overall_pass and m["pass"]
        all_conclusive = all_conclusive and m["flashlight_conclusive"]
        all_e2e_conclusive = all_e2e_conclusive and m["e2e_conclusive"]

    flashlight_ran = bool(flash and flash.get("docker_available"))
    e2e_ran = bool(e2e and e2e.get("e2e_available") and e2e.get("status") == "ran")

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

    result = {
        "module": static.get("module", ""),
        "target_versions": target_versions,
        "versions": versions,
        "pass": overall_pass,
        "ready": compute_ready(versions, required),
        "required_layers": required,
        "flashlight_conclusive": all_conclusive,
        "e2e_conclusive": all_e2e_conclusive,
        "layers_run": {
            "static": True,
            "flashlight": flashlight_ran,
            "adversarial": adversarial is not None,
            "e2e": e2e_ran,
        },
    }
    # Spec E2E authored yang dilewati (JSON rusak / tanpa steps) di-echo di top-level supaya
    # TAK hilang walau semua versi tak konklusif — jangan biarkan uji authored diam-diam absen.
    e2e_scenario_notes = (e2e or {}).get("scenario_notes") or []
    if e2e_scenario_notes:
        result["e2e_scenario_notes"] = e2e_scenario_notes
    # Cakupan E2E: tanpa spec authored, Lapis 4 hanya membuktikan "shop tak rusak" —
    # BUKAN perilaku module. Tanpa penanda ini vonisnya identik dgn module yang punya
    # skenario use-case lengkap, jadi "E2E konklusif lolos" terbaca lebih dari faktanya.
    e2e_sources = (e2e or {}).get("scenario_sources") or []
    if e2e_ran:
        result["e2e_scenario_sources"] = e2e_sources
        # Field top-level = "tiap versi yang benar-benar jalan cuma smoke". Versi yang tak jalan
        # tak dihitung: ia sudah tak konklusif lewat kanal infra, dan menyebutnya "smoke only"
        # akan menyalahkan spec atas container yang gagal boot.
        ran_vers = [v for v in target_versions if v in ((e2e or {}).get("versions") or {})]
        result["e2e_smoke_only"] = bool(ran_vers) and all(is_smoke_only(e2e, v) for v in ran_vers)
    # Folder screenshot E2E di-echo agar path artefak visual ('cek web asli') sampai ke laporan
    # gabungan — supaya render bisa ditinjau, bukan cuma diproduksi lalu terlupakan.
    e2e_shot_dir = (e2e or {}).get("screenshot_dir")
    if e2e_shot_dir:
        result["e2e_screenshot_dir"] = e2e_shot_dir
    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"ditulis: {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
