---
name: psm-scaffold
description: Scaffold module PrestaShop baru cross-version 1.7/8/9. Use when the user says "psm-scaffold", "bikin module PrestaShop baru", "scaffold module", or "buat module baru cross-version".
---

# psm-scaffold

## Overview

Bertindak sebagai pendamping pembuatan module PrestaShop: operator (Budi) memutuskan apa yang dibangun, skill memastikan kerangkanya benar dan cross-version sejak baris pertama. Hasilkan **kerangka module PrestaShop baru yang dijamin lolos standar di 1.7.x, 8.x, dan 9.x**, lalu bantu Budi menempel fungsi e-commerce **pemantik** yang minimal di atas fondasi itu. Batas kepemilikan: scaffold hanya menegakkan fondasi + satu-dua fungsi pemantik; **pengembangan fitur berkelanjutan adalah domain psm-develop**, dan verifikasi lolos adalah vonis psm-validate. Konsumen hasil: Budi dan psm-develop yang melanjutkan dari fondasi yang sudah benar. Kerangka deterministik dibangkitkan oleh skrip generator, bukan diketik ulang model.

## Resolution rules

- Bare paths dan `{skill-root}` (mis. `scripts/ps-scaffold.py`) resolve dari direktori instal skill ini.
- `{project-root}` → direktori kerja project.
- `psm-scaffold` → basename direktori skill.

## On Activation

1. Muat config dari `{project-root}/_bmad/config.yaml` (+ `.user.yaml` bila ada). Ambil `psm_target_versions` (default `1.7.8,8.1,9.0`), `psm_modules_dir` (default `{project-root}/modules`), dan `communication_language` (default Indonesia) apa adanya dari section `psm`.
2. Kumpulkan identitas module dari Budi: nama (lowercase, mis. `ps_mybanner`) dan author. Tanya hanya yang belum jelas dari permintaan; versi target ambil dari `psm_target_versions` kecuali Budi menyebut lain. Bila nama menyerupai module core/native PrestaShop (mis. `ps_checkout`, `contactform`, `productcomments`), konfirmasi ke Budi dulu — nama begitu lolos scaffold & psm-validate tapi bentrok saat instal ke toko nyata.

## Bangkitkan kerangka

Jalankan generator deterministik: `uv run scripts/ps-scaffold.py <nama> --dest <psm_modules_dir> --author "<author>" --target-versions <psm_target_versions>` (lihat `scripts/ps-scaffold.py --help`). Generator menghitung min/max `ps_versions_compliancy` secara semver dari `--target-versions`, jadi jangan hitung atau oper `--ps-min`/`--ps-max` sendiri kecuali Budi minta rentang di luar daftar target. Skrip membuat struktur minimal yang **dijamin lolos standar**: main file dengan guard `_PS_VERSION_`, `ps_versions_compliancy`, install/uninstall; `composer.json` dengan PSR-4 dan `prepend-autoloader: false`; serta `index.php` di setiap folder. Jangan menulis ulang file-file ini dengan tangan — generator adalah sumber kebenaran kerangka.

Bila generator gagal karena folder module sudah ada, **jangan** otomatis `--force` — itu menimpa (menghapus) isi lama yang mungkin berisi kerja Budi. Surface ke Budi dan konfirmasi timpa dulu sebelum menjalankan ulang dengan `--force`. Bila gagal karena sebab lain (mis. `psm_modules_dir` tak writable atau path tak valid), surface pesan error apa adanya ke Budi dan hentikan — jangan lanjut ke penawaran fungsi atau validasi seolah kerangka sudah jadi.

Setelah dibangkitkan, ingatkan Budi menjalankan `composer dump-autoload` di folder module agar autoloader namespace aktif.

## Tawarkan fungsi e-commerce

Kerangka sengaja telanjang. Tawarkan fungsi e-commerce **pemantik** yang relevan dengan maksud module Budi (mis. untuk module promosi: satu hook banner terjadwal; untuk katalog: satu badge stok) — fungsi minimal yang menempel pada fondasi agar Budi punya titik mulai, **bukan** fitur berkembang penuh. Bila disetujui, implementasikan dengan pola version-safe: gunakan `{project-root}/skills/psm-cross-version/references/version-safe-patterns.md` sebagai rujukan teknis lintas versi (hook, controller, template, persistence, service). Bila `{project-root}/_bmad/psm/memory/ecommerce/function-catalog.md` ada, baca untuk katalog fungsi yang lebih kaya; bila belum, andalkan pengetahuan e-commerce umum. Ini judgment — tawarkan, jangan paksakan; Budi yang memilih.

## Verifikasi (gerbang wajib)

Panggil psm-validate atas module hasil terhadap ketiga versi target (lihat `{project-root}/skills/psm-validate/SKILL.md`). Status lolos per versi adalah vonis JSON dari psm-validate — baca `pass` & hitungan error/warning per versi dari situ apa adanya, jangan menilai sendiri. Kerangka dinyatakan siap hanya bila JSON itu lolos di 1.7.x, 8.x, dan 9.x.

Kerangka telanjang dijamin lolos, jadi bila fungsi e-commerce ditambahkan, validasi ulang — dan bila revalidasi gagal, sumbernya pasti fungsi tambahan itu: perbaiki mengikuti version-safe-patterns lalu validasi lagi sampai lolos, atau lepaskan fungsi bermasalah dan serahkan ke psm-develop. Ringkas ke Budi: apa yang dibangkitkan, fungsi apa yang ditambahkan, dan status lolos per versi dari vonis.

## Mode headless

Saat dipanggil dengan `--headless` atau oleh workflow/agent lain: ambil nama/author/versi dari argumen alih-alih bertanya, bangkitkan kerangka, lewati penawaran fungsi e-commerce interaktif (kecuali fungsi diberikan eksplisit), panggil psm-validate. Karena operator tak hadir, catat tiap resolusi tak-sepele ke memlog via `uv run {project-root}/_bmad/scripts/memlog.py append` (sumber versi bila di-default, resolusi nama/dest atau keputusan `--force`, dan fungsi e-commerce apa pun yang diimplementasikan). Soft-check nama core tak bisa konfirmasi ke operator di sini; bila nama menyerupai module core/native PrestaShop, catat sebagai peringatan ke memlog dan sertakan di ringkasan return alih-alih dianggap sepele. Kembalikan ringkasan satu baris + path module + path memlog + status lolos per versi dari vonis psm-validate. Jejak tipis saja — ini nyaris satu tembakan, bukan loop iteratif.
