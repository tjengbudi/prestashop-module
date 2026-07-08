---
name: psm-develop
description: Tambah fungsi e-commerce ke module PrestaShop existing, cross-version. Use when the user says "psm-develop", "tambah fungsi ke module", "kembangkan module PrestaShop", or "tambah fitur module".
---

# psm-develop

## Overview

Bertindak sebagai pendamping pengembangan module PrestaShop: operator (Budi) memutuskan fitur apa yang dibangun, skill memegang katalog fungsi e-commerce dan pola version-safe untuk menanamnya dengan aman. Tambahkan fungsi baru ke module yang **sudah ada dan berjalan** — tanpa memecah fungsi lama, dengan kompatibilitas tetap di 1.7.x, 8.x, dan 9.x. Karena ini mengubah source code yang sudah dipakai dan tak mudah dibalik, kerjanya **pahami existing → rancang → konfirmasi → terapkan → verifikasi**. Konsumen hasil: Budi (module yang tumbuh tanpa regresi) dan psm-agent-expert. Berbeda dari psm-scaffold (membuat kerangka kosong baru) — di sini module sudah berisi, jadi memahami yang eksisting lebih dulu adalah keharusan.

## Resolution rules

- Bare paths dan `{skill-root}` (mis. `references/ecommerce-function-catalog.md`) resolve dari direktori instal skill ini.
- `{project-root}` → direktori kerja project.
- `psm-develop` → basename direktori skill.
- `<module-path>` → folder module yang dikembangkan, ditentukan di On Activation #2.

## On Activation

1. Muat config dari `{project-root}/_bmad/config.yaml` (+ `.user.yaml` bila ada). Ambil versi target dari section `psm` (`psm_target_versions`, default `1.7.8,8.1,9.0`). Komunikasi dalam `communication_language` (default Indonesia).
2. Tentukan module yang dikembangkan (path folder) dan fungsi yang diinginkan dari permintaan Budi. Bila ambigu, tanya satu pertanyaan.
3. Resume: bila `<module-path>/.psm-develop-plan.md` ada, baca untuk melanjutkan dari keadaan terakhir.
4. **Augment katalog bila ada.** Bila `{project-root}/_bmad/psm/memory/ecommerce/function-catalog.md` ada, baca untuk fungsi tambahan di luar `references/ecommerce-function-catalog.md`. Bila belum, lanjut — katalog inti sudah di-embed.

## Pahami module existing

Petakan apa yang sudah ada sebelum menambah apa pun. Jalankan dua skrip deterministik dan baca hasilnya, jangan parse PHP mentah dengan tangan:
- `uv run scripts/ps-module-inventory.py <module-path>` (lihat `--help`) → JSON inventaris: hook terdaftar & terimplementasi, ObjectModel + nama tabel, controller, versi module, ada/tidaknya folder `upgrade/`, daftar file. Ini peta titik sisip.
- `uv run {project-root}/skills/psm-validate/scripts/ps-static-scan.py <module-path> --versions <target>` → peta API berisiko per versi, supaya fungsi baru tak menambah masalah lama. Bila script tidak ditemukan, beri tahu Budi bahwa psm-validate harus terinstal di `{project-root}/skills/psm-validate/` lalu hentikan.

Sisakan untuk dirimu hanya penilaian *di mana sisip yang aman* — itu judgment, bukan pengulangan kedua skrip.

## Rancang fungsi & rencana

Tawarkan fungsi e-commerce yang relevan dengan maksud Budi memakai `references/ecommerce-function-catalog.md` (peta fungsi per domain + hook/persistensi relevan, plus aturan menambah-ke-existing di bagian akhirnya — patuhi itu). Untuk fungsi terpilih, rancang implementasi version-safe dengan `{project-root}/skills/psm-cross-version/references/version-safe-patterns.md` sebagai rujukan teknis lintas versi.

Tulis rencana ke `<module-path>/.psm-develop-plan.md`: per fungsi — file & titik sisip, hook/tabel/service yang ditambah, perubahan per versi, dan alasan. Rencana adalah artefak yang dapat direvisi dan sumber resume.

**Validasi rencana terhadap inventaris sebelum konfirmasi:** cocokkan tiap item rencana dengan JSON inventaris — hook baru belum ada di `registered_hooks`; perubahan `$definition` ObjectModel terpakai disertai `upgrade/upgrade-x.y.z.php` (cek `has_upgrade_dir`); file/titik sisip benar-benar ada. Perbaiki konflik di rencana dulu. Lalu tampilkan ke Budi dan **minta persetujuan sebelum menyentuh file** — gerbang yang tak boleh dilewati.

## Terapkan

Setelah disetujui, terapkan sesuai rencana pada module di tempat (asumsikan Budi memakai git untuk pembatalan). Tambah, jangan rusak: pertahankan hook & data lama, pakai cabang versi eksplisit untuk area legacy/modern, sertakan upgrade script bila menambah hook/tabel. Tandai status tiap fungsi di `.psm-develop-plan.md` saat diterapkan.

## Verifikasi (gerbang wajib)

Panggil psm-validate atas module hasil terhadap ketiga versi target (lihat `{project-root}/skills/psm-validate/SKILL.md`). Status lolos per versi adalah vonis JSON dari psm-validate — baca apa adanya, jangan menilai sendiri. Module dinyatakan siap **hanya bila lolos di 1.7.x, 8.x, dan 9.x**. Bila ada error tersisa, tulis temuan per versi itu kembali ke `.psm-develop-plan.md` dan rancang ulang dari artefak — jangan menyatakan selesai. Ringkas ke Budi: fungsi apa yang ditambahkan, dan status lolos per versi.

## Mode headless

Saat dipanggil dengan `--headless` atau oleh workflow/agent lain: ambil module-path, fungsi, & versi dari argumen alih-alih bertanya, dan jalankan alur normal **tanpa gerbang konfirmasi interaktif** (pemanggil bertanggung jawab atas persetujuan). Karena operator tak hadir, catat tiap asumsi ke memlog via `uv run {project-root}/_bmad/scripts/memlog.py append` (fungsi yang dipilih, sumber versi, dan tiap revisi rencana setelah validate gagal). Kembalikan ringkasan satu baris + path `.psm-develop-plan.md` + path memlog + status lolos per versi dari vonis. Tetap berlaku: jangan menyatakan lolos sebelum psm-validate hijau di ketiga versi.
