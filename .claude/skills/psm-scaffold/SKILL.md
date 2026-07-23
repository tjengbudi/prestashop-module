---
name: psm-scaffold
description: Scaffold module PrestaShop baru cross-version 1.7/8/9. Use when the user says "psm-scaffold", "bikin module PrestaShop baru", "scaffold module", or "buat module baru cross-version".
---

# psm-scaffold

## Overview

Bertindak sebagai pendamping pembuatan module PrestaShop: operator (Budi) memutuskan apa yang dibangun, skill memastikan kerangkanya benar dan cross-version sejak baris pertama. Hasilkan **kerangka module PrestaShop baru yang dijamin lolos standar di 1.7.x, 8.x, dan 9.x** — dibangkitkan skrip generator deterministik, dinyatakan siap hanya setelah lolos psm-validate — lalu bantu Budi mengisi fungsi e-commerce yang relevan. Konsumen hasil: Budi (lanjut mengembangkan module yang sudah berfondasi benar) dan psm-develop/psm-validate yang melanjutkan.

## Resolution rules

- Bare paths dan `{skill-root}` (mis. `scripts/ps-scaffold.py`) resolve dari direktori instal skill ini.
- `{project-root}` → direktori kerja project.
- `<skills-dir>` → direktori yang memuat skill ini (tempat sibling psm-* berada, install-relative). Rujuk sibling lewat `<skills-dir>/psm-validate/…`, bukan `{project-root}/skills/…` — jangan bergantung pada mirror `skills/` di root project.

## On Activation

1. Muat config resolved via `uv run {project-root}/.claude/skills/psm-setup/scripts/resolve-psm-config.py --project-root {project-root}` — JSON berisi `psm_target_versions`, `psm_modules_dir` (folder module), `communication_language`, dll. Baca apa adanya; default kanonik sudah diterapkan resolver (jangan parse `config.yaml` sendiri).
2. Kumpulkan dari Budi: nama module (lowercase, mis. `ps_mybanner`), author, dan maksud module satu kalimat (dasar display-name/description dan penawaran fungsi nanti). Tanya hanya yang belum jelas dari permintaan. Rentang versi target jangan ditanya: default dari `psm_target_versions` config, sebut sepintas saja ("kerangka untuk 1.7–9.x sesuai config"), dan tanya hanya bila permintaan Budi menyiratkan penyimpangan.

## Bangkitkan kerangka

Jalankan generator deterministik: `uv run scripts/ps-scaffold.py <nama> --dest <psm_modules_dir> --author "<author>" --ps-min <min> --ps-max <max>` (lihat `scripts/ps-scaffold.py --help`). Skrip membuat struktur minimal yang **dijamin lolos standar**: main file dengan guard `_PS_VERSION_`, `ps_versions_compliancy`, install/uninstall; `composer.json` dengan PSR-4 dan `prepend-autoloader: false`; serta `index.php` di setiap folder. Jangan menulis ulang file-file ini dengan tangan — generator adalah sumber kebenaran kerangka.

Bila folder module tujuan sudah ada, skrip menolak — itu gerbang keputusan, bukan gangguan. Jangan pernah memakai `--force` tanpa konfirmasi eksplisit Budi: ia menimpa main file, composer.json, dan tiap index.php yang ada. Bila folder itu module berisi yang ingin Budi kembangkan, arahkan ke psm-develop dan berhenti (cermin gerbang target psm-develop).

Setelah dibangkitkan, ingatkan Budi menjalankan `composer dump-autoload` di folder module agar autoloader namespace aktif.

## Tawarkan fungsi e-commerce

Kerangka sengaja telanjang. Tawarkan fungsi e-commerce yang relevan dengan maksud module Budi (mis. untuk module promosi: banner terjadwal, segmentasi; untuk katalog: filter, badge stok) dan, bila disetujui, implementasikan dengan pola version-safe. Gunakan `<skills-dir>/psm-cross-version/references/version-safe-patterns.md` sebagai rujukan teknis lintas versi (hook, controller, template, persistence, service). Bila `{project-root}/_bmad/psm/memory/ecommerce/function-catalog.md` ada, baca untuk katalog fungsi yang lebih kaya; bila belum, andalkan pengetahuan e-commerce umum. Ini judgment — tawarkan, jangan paksakan; Budi yang memilih.

## Verifikasi (gerbang wajib)

Panggil psm-validate atas module hasil terhadap ketiga versi target (lihat `<skills-dir>/psm-validate/SKILL.md`). Status lolos per versi adalah vonis JSON dari psm-validate — baca `ready` & hitungan error/warning per versi dari situ apa adanya, jangan menilai sendiri. Kerangka dinyatakan siap hanya bila `ready` true di 1.7.x, 8.x, dan 9.x; bila fungsi e-commerce ditambahkan, validasi ulang. Baca `ready`, bukan `pass`: `pass` sengaja tak diblok oleh lapis yang tak pernah jalan, jadi ia hijau juga saat cuma 2 dari 4 lapis teruji. Bila psm-validate sendiri gagal berjalan atau vonisnya tak terbaca (skill absen, crash, non-JSON), perlakukan sebagai **BUKAN lolos** — jangan tafsir "tak ada error" sebagai hijau. Ringkas ke Budi: apa yang dibangkitkan, fungsi apa yang ditambahkan, dan status lolos per versi dari vonis.

## Mode headless

Saat dipanggil dengan `--headless` atau oleh workflow/agent lain: ambil nama/author/versi dari argumen alih-alih bertanya, bangkitkan kerangka, lewati penawaran fungsi e-commerce interaktif (kecuali fungsi diberikan eksplisit), panggil psm-validate. Karena operator tak hadir, catat tiap resolusi tak-sepele ke memlog via `uv run {project-root}/_bmad/scripts/memlog.py append` (sumber versi bila di-default, resolusi nama/dest, dan fungsi e-commerce apa pun yang diimplementasikan). Jejak tipis saja — ini nyaris satu tembakan, bukan loop iteratif.

Kembalikan JSON bertipe: `status` (`complete` | `gagal` | `butuh intervensi`) + ringkasan satu baris + path module + path memlog + status lolos per versi dari vonis psm-validate. **`butuh intervensi`** — titik keputusan manusia: folder module tujuan sudah ada (jangan pernah `--force` atas inisiatif sendiri; hanya bila pemanggil memberikannya eksplisit) → kembalikan alasan satu baris (path yang bertabrakan) + path memlog, dan berhenti agar pemanggil memutuskan. **`gagal`** — tak terpulihkan: skrip generator error, atau vonis psm-validate tak terbaca (= BUKAN lolos, lihat Verifikasi) → alasan satu baris + path memlog.
