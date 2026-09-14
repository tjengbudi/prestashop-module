---
name: psm-validate
description: Validasi kompatibilitas module PrestaShop 1.7/8/9 lewat pindai statis, uji flashlight, review adversarial, uji browser E2E, dan skenario kondisi-rusak. Use when the user says "psm-validate", "validasi module", "cek kompatibilitas module PrestaShop", or "audit module".
---

# psm-validate

## Overview

Bertindak sebagai validator module PrestaShop yang teliti dan jujur: operator memegang module, skill memegang aturan kompatibilitas lintas versi dan prosedur ujinya. Hasilkan **vonis berbasis bukti** apakah sebuah module sehat di PrestaShop **1.7.x, 8.x, dan 9.x sekaligus** — lima lapis bukti, dari yang murah dan deterministik sampai yang mahal dan nyata. Konsumen hasil: operator (perbaiki sebelum rilis) dan workflow lain (psm-cross-version, psm-develop, psm-scaffold) yang memanggil skill ini sebagai gerbang mutu — jadi output harus JSON terstruktur yang dapat dibaca mesin, dengan ringkasan yang bisa ditindaklanjuti manusia.

## Resolution rules

- Bare paths dan `{skill-root}` (mis. `assets/ps-rules.json`) resolve dari direktori instal skill ini.
- `{project-root}` → direktori kerja project.
- `<skills-dir>` → direktori yang memuat skill ini (tempat sibling psm-* berada, install-relative). Rujuk sibling lewat `<skills-dir>/psm-develop/…`, bukan `{project-root}/skills/…` — jangan bergantung pada mirror `skills/` di root project.

## On Activation

1. Muat config: `uv run <skills-dir>/psm-setup/scripts/resolve-psm-config.py --project-root {project-root}` — baca apa adanya, jangan parse `config.yaml` sendiri. Simpan ke `<psm_reports_dir>/psm-config.json` lalu teruskan `--config <file>` ke tiap lapis dan ke plan; flag eksplisit tetap menang. Resolver absen? Pakai default kanonik skrip, catat itu.
2. Tentukan module (path folder); nama telanjang di-resolve terhadap `psm_modules_dir`, bila tetap ambigu tanyakan. Interaktif: sebelum lapis jalan, tawarkan cakupan uji — versi dari `psm_target_versions`, browser Lapis 4 dari `psm_e2e_browsers`; default semua yang terkonfigurasi, dipakai seragam di semua lapis (`--versions`, `--browsers`).
3. **Konteks module.** Bila `{project-root}/_bmad/psm/memory/projects/<module>.md` ada, baca sebelum memvonis — konvensi & keputusan module tak bisa diturunkan dari pindai. Belum ada? Lanjut; **psm-module-context** yang membuatnya.

## Validate

Aturan di luar `assets/ps-rules.json` dan tag di luar `psm_flashlight_tag_map` hanya masuk lewat `--extra-rules` / `--extra-tag-map` (semantik menambah vs mengganti: `--help`) — jangan terjemahkan prosa jadi aturan dengan tangan.

Lima lapis bukti disatukan jadi vonis; lapis murah & deterministik dulu supaya run mahal tak diulang. Tiap skrip punya vonisnya sendiri: baca apa adanya, jangan nilai ulang, timpa, atau rakit ulang dengan tangan. File lapis hidup di `<psm_reports_dir>` dalam dua bentuk — **kanonik** (semua versi, dibaca agregat) dan **per-versi** (untuk konvergensi); namanya diturunkan skrip, tak diketik (`ps-run-layer.py --help`). Karena source module TUNGGAL untuk 1.7/8/9, satu patch membasikan bukti semua versi via mtime — jadi jangan sweep penuh tiap perbaikan. Validasi jalan **dua fase**.

**Fase 1 — konvergensi per versi (loop perbaikan).** Tuntaskan satu versi sebelum pindah: plan menandai lapis mana yang basi untuk versi itu, kamu jalankan hanya lapis itu, perbaiki error pemblokir di source, ulangi sampai bersih. Bukti versi lain menetap, jadi cek ulang satu versi = boot Docker 1×, bukan 3×.

**Fase 2 — gerbang rilis (sekali, di akhir).** `ready` yang jujur butuh bukti TERKINI untuk SEMUA versi — tak boleh dari fase konvergensi saja. Segarkan yang masih basi, satukan file per-versi jadi kanonik, lalu agregasi (lihat **Vonis dan output**).

Perintah persis kedua fase, konvensi nama file per-lapis, dan aturan **read-merge** file adversarial: `references/run-phases.md`. Baca sebelum menjalankan lapis mana pun — nama file lapis diturunkan skrip, dan mengetiknya sendiri adalah cara bukti mendarat di module lain.


**Lapis 1 — pindai statis lintas versi (selalu).** Jalankan `uv run scripts/ps-static-scan.py <module-path> --versions <target>` (lihat `--help`). Skrip mencocokkan ruleset lintas-versi `assets/ps-rules.json` ke source module dan mengeluarkan temuan JSON per versi dengan `pass`/`errors`/`warnings`. `main_file_reason: no_php_at_root` berarti folder itu bukan module PrestaShop — **berhenti**: lapis lain mahal dan tak ada yang bisa dinilai, dan temuan compliancy atas file yang tak ada itu menyesatkan. Interaktif: sebutkan + tawarkan kandidat dari `psm_modules_dir`; headless: `blocked`. `ambiguous_main_file` bukan alasan berhenti: `main_file_candidates` memuat `extends_module` — sebut file utama yang tepat atau folder yang perlu dinamai ulang.

**Lapis 2 — uji di flashlight per versi (bila Docker ada).** Jalankan `uv run scripts/ps-flashlight-run.py <module-path> --versions <target>` dengan `--config <psm_reports_dir>/psm-config.json` supaya sekali panggil langsung jalan (lihat `--help`). Skrip mengurus DB, phpstan, dan degrade sendiri lalu menandainya di output. Image flashlight besar: di sesi interaktif konfirmasi dulu, lalu ulangi dengan `--allow-image-pull`. Run yang di-kill paksa meninggalkan container/network `psm-fl` yatim; bersihkan dengan `uv run scripts/ps-flashlight-run.py --cleanup-orphans` — aman terhadap run sesi lain karena memvonis dari label `psm.owner-pid`, bukan dari nama (`--help`).

**Lapis 3 — review adversarial e-commerce (judgment).** Kamu sendiri yang meninjau, **inline**, di bawah kontrak `references/adversarial-lens.md` — buka file itu: sikap, empat lensa, prosedur, dan bentuk kembalian yang ditegakkan agregat. Konteksmu tak bersih, dan **pindai hijau terbaca sebagai bukti sehat**; itu dilawan urutan, bukan niat baik — kerjakan Lapis 3 sebagai langkah PERTAMA Fase 2, sebelum membuka hasil Lapis 1/2/4, satu lensa per pass, tiap lensa ditulis ke `<psm_reports_dir>/<module>-adversarial.json` (read-merge, jangan timpa) sebelum lensa berikutnya. Tinjau semua versi target; `{project-root}/_bmad/psm/memory/ecommerce/adversarial-checks.md` bila ada = lensa tambahan. **Sebut di ringkasan** bahwa review dikerjakan inline.

**Lapis 4 — uji perilaku browser E2E (bila `psm_e2e_enabled` ≠ false — gerbang orkestrator, bukan flag skrip — dan Docker + browser Playwright ada).** Prasyarat sekali (browser Playwright, mesin baru, loop TDD E2E): `references/e2e-quickstart.md`. Jalankan `uv run scripts/ps-e2e-run.py <module-path> --versions <target> --browsers <browser>` dengan setelan flashlight sama seperti Lapis 2 (format spec & degrade: `--help`). Verifikasi visual (interaktif saja — headless tak punya peninjau): `--screenshot-dir <psm_reports_dir>/e2e-shots`, lalu tinjau screenshot kunci dengan penglihatanmu; assertion buta pada layout ambruk. Cacat visual yang kamu yakini **memblok**: tambahkan ke `findings` di `<psm_reports_dir>/<module>-adversarial.json` sebelum agregat jalan — read-merge, jangan timpa (di situ ada temuan Lapis 3). Ini satu-satunya kanal judgment model ke vonis; sisanya catatan satu baris. Cara menulisnya, dan alat lain (`--headed`, error console), ada di reference yang sama.

**Lapis 5 — skenario kondisi-rusak (bila module punya `tests/scenarios/*.json`).** Lapis lain menguji dari keadaan BERSIH; ini dari keadaan RUSAK yang module nyatakan sebagai `given`/`when`/`then` — baris config membayangi, OrderState duplikat, template core tertimpa. Jalankan lewat `ps-run-layer.py --layer scenario` seperti Lapis 2/4 (bentuk & isolasi snapshot: `--help`). **Menggerbang hanya bila module mengapalkan skenario** — yang belum punya tak dijatuhkan `ready`-nya, yang MENYATAKAN wajib lolos.

## Vonis dan output

Ini langkah penutup **Fase 2 (gerbang rilis)**. Jalankan `uv run scripts/ps-aggregate.py --reports-dir <psm_reports_dir> --module <module-path>` — nama file tiap lapis dan nama output berstempel diturunkan di dalam skrip, lapis tanpa file dilewati, dan file lapis milik module lain ditolak (exit 2). Exit 2 dari skrip manapun = error input: baca stderr, perbaiki, ulangi — jangan tafsirkan sebagai vonis.

Untuk `{user_name}` (kosong → "operator"), ringkas dalam percakapan (bahasa: `{communication_language}`) dari JSON itu: per versi lolos/gagal, error yang memblok beserta fix-nya, dan warning. Aturan jujur, sekali untuk semua lapis: laporkan apa yang TIDAK terbukti — tiap field konklusivitas yang false, lapis yang tak jalan, dan cakupan versi/browser yang dipersempit. Dua hal tak terbaca dari nama fieldnya: `advisory_note` dilaporkan tapi tak menggerbang, dan `e2e_smoke_only` berarti shop terbukti tak rusak sementara perilaku module belum teruji — ini **menjatuhkan `ready`**. E2E smoke-only atau spec dilewati (`e2e_scenario_notes`)? Tawarkan menulis skenario (`references/e2e-quickstart.md`) — rilis tanpa uji perilaku disempitkan lewat `--require`, bukan dengan mengabaikan `ready`. Sebut folder screenshot (`e2e_screenshot_dir`) bila ada. Bila vonis keseluruhan gagal, tutup dengan satu tawaran langkah lanjut: serahkan error pemblokir ke psm-develop untuk diperbaiki, atau validasi ulang setelah dipatch.

Catat satu baris ke konteks module: `uv run <skills-dir>/psm-module-context/scripts/ps-module-context.py note --memory-dir {project-root}/_bmad/psm/memory --module <module> --by psm-validate --type vonis --text "<satu baris>"` (auto-init bila belum ada). Satu entri per run — ini bukan laporan.

## Mode headless

Dipanggil workflow lain atau dengan `--headless`? Kontrak input, kembalian JSON, dan aturan memlog: `references/headless.md`. Satu aturan yang berlaku bahkan bila reference itu tak dibuka: jalankan Lapis 2 & Lapis 4 **tanpa** `--allow-image-pull` — jangan pernah tarik image tanpa manusia.
