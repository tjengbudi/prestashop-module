---
name: psm-scaffold
description: Scaffold module PrestaShop baru cross-version 1.7/8/9. Use when the user says "psm-scaffold", "bikin module PrestaShop baru", "scaffold module", or "buat module baru cross-version".
---

# psm-scaffold

## Overview

Bertindak sebagai pendamping pembuatan module PrestaShop: operator (Budi) memutuskan apa yang dibangun, skill memastikan kerangkanya benar dan cross-version sejak baris pertama. Hasilkan **kerangka module PrestaShop baru yang dijamin lolos standar di 1.7.x, 8.x, dan 9.x** — struktur file baku, composer/autoload benar, `ps_versions_compliancy` terisi, index.php di tiap folder — lalu bantu Budi mengisi fungsi e-commerce yang relevan. Konsumen hasil: Budi (lanjut mengembangkan module yang sudah berfondasi benar) dan psm-develop/psm-validate yang melanjutkan. Kerangka deterministik dibangkitkan oleh skrip generator (bukan diketik ulang model), dan tidak pernah dinyatakan siap sebelum lolos psm-validate.

## Resolution rules

- Bare paths dan `{skill-root}` (mis. `scripts/ps-scaffold.py`) resolve dari direktori instal skill ini.
- `{project-root}` → direktori kerja project.
- `psm-scaffold` → basename direktori skill.

## On Activation

1. Muat config dari `{project-root}/_bmad/config.yaml` (+ `.user.yaml` bila ada). Ambil versi target dari section `psm` (`psm_target_versions`, default `1.7.8,8.1,9.0`) dan folder module (`psm_modules_dir`, default `{project-root}/modules`). Komunikasi dalam `communication_language` (default Indonesia).
2. Kumpulkan identitas module dari Budi: nama (lowercase, mis. `ps_mybanner`), author, dan rentang versi target. Tanya hanya yang belum jelas dari permintaan.

## Bangkitkan kerangka

Jalankan generator deterministik: `uv run scripts/ps-scaffold.py <nama> --dest <psm_modules_dir> --author "<author>" --ps-min <min> --ps-max <max>` (lihat `scripts/ps-scaffold.py --help`). Skrip membuat struktur minimal yang **dijamin lolos standar**: main file dengan guard `_PS_VERSION_`, `ps_versions_compliancy`, install/uninstall; `composer.json` dengan PSR-4 dan `prepend-autoloader: false`; serta `index.php` di setiap folder. Jangan menulis ulang file-file ini dengan tangan — generator adalah sumber kebenaran kerangka.

Setelah dibangkitkan, ingatkan Budi menjalankan `composer dump-autoload` di folder module agar autoloader namespace aktif.

## Tawarkan fungsi e-commerce

Kerangka sengaja telanjang. Tawarkan fungsi e-commerce yang relevan dengan maksud module Budi (mis. untuk module promosi: banner terjadwal, segmentasi; untuk katalog: filter, badge stok) dan, bila disetujui, implementasikan dengan pola version-safe. Gunakan `{project-root}/skills/psm-cross-version/references/version-safe-patterns.md` sebagai rujukan teknis lintas versi (hook, controller, template, persistence, service). Bila `{project-root}/_bmad/psm/memory/ecommerce/function-catalog.md` ada, baca untuk katalog fungsi yang lebih kaya; bila belum, andalkan pengetahuan e-commerce umum. Ini judgment — tawarkan, jangan paksakan; Budi yang memilih.

## Verifikasi (gerbang wajib)

Panggil psm-validate atas module hasil terhadap ketiga versi target (lihat `{project-root}/skills/psm-validate/SKILL.md`). Status lolos per versi adalah vonis JSON dari psm-validate — baca `pass` & hitungan error/warning per versi dari situ apa adanya, jangan menilai sendiri. Kerangka dinyatakan siap hanya bila JSON itu lolos di 1.7.x, 8.x, dan 9.x; bila fungsi e-commerce ditambahkan, validasi ulang. Ringkas ke Budi: apa yang dibangkitkan, fungsi apa yang ditambahkan, dan status lolos per versi dari vonis.

## Mode headless

Saat dipanggil dengan `--headless` atau oleh workflow/agent lain: ambil nama/author/versi dari argumen alih-alih bertanya, bangkitkan kerangka, lewati penawaran fungsi e-commerce interaktif (kecuali fungsi diberikan eksplisit), panggil psm-validate. Karena operator tak hadir, catat tiap resolusi tak-sepele ke memlog via `uv run {project-root}/_bmad/scripts/memlog.py append` (sumber versi bila di-default, resolusi nama/dest atau keputusan `--force`, dan fungsi e-commerce apa pun yang diimplementasikan). Kembalikan ringkasan satu baris + path module + path memlog + status lolos per versi dari vonis psm-validate. Jejak tipis saja — ini nyaris satu tembakan, bukan loop iteratif.
