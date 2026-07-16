---
name: psm-plan
description: Rencanakan fungsi e-commerce module PrestaShop tanpa menerapkan. Use when the user says "psm-plan", "rencanakan fungsi module", "planning module PrestaShop", or "buat rencana pengembangan module".
---

# psm-plan

## Overview

Bertindak sebagai pendamping perencanaan module PrestaShop: operator (Budi) memutuskan fitur apa yang dibangun, skill memegang katalog fungsi e-commerce dan pola version-safe untuk merancang penanamannya. Skill ini mengerjakan tiga fase awal psm-develop — **pahami existing → rancang → konfirmasi** — lalu **berhenti** setelah rencana disetujui. Gunanya: perencanaan bisa jadi sesi terpisah dari eksekusi. Konsumen hasil: Budi (rencana yang bisa direview tenang) dan **psm-develop**, yang melanjutkan dari artefak rencana lewat mekanisme resume-nya tanpa modifikasi apa pun.

## Resolution rules

- Bare paths dan `{skill-root}` resolve dari direktori instal skill ini.
- `{project-root}` → direktori kerja project.
- `<skills-dir>` → direktori yang memuat skill ini (tempat sibling psm-* berada, install-relative). Rujuk sibling lewat `<skills-dir>/psm-develop/…`, bukan `{project-root}/skills/…` — jangan bergantung pada mirror `skills/` di root project.
- `<module-path>` → folder module yang direncanakan, ditentukan di On Activation #2.
- Artefak rencana (pasangan, path kanonik): `<module-path>/.psm-develop-plan.md` (naratif, untuk Budi) + `<module-path>/.psm-develop-plan.json` (terstruktur, dibaca skrip). Nama file sengaja memakai prefix psm-develop (kontrak bersama).

## On Activation

1. Muat config resolved via `uv run <skills-dir>/psm-setup/scripts/resolve-psm-config.py --project-root {project-root}` — JSON berisi `psm_target_versions`, `communication_language`, dll. Baca apa adanya; jangan parse `config.yaml` sendiri dan jangan embed default versi target.
2. Tentukan module yang direncanakan (path folder) dan fungsi yang diinginkan dari permintaan Budi. Bila ambigu, tanya satu pertanyaan.
3. Resume: bila `<module-path>/.psm-develop-plan.md` ada, baca untuk melanjutkan atau merevisi dari keadaan terakhir. **Rekonsiliasi dulu, jangan percaya status buta** — dua cek deterministik dari `uv run <skills-dir>/psm-develop/scripts/ps-module-inventory.py <module-path>`: `--pair-check` → drift .md↔.json (json hilang, status beda, item hilang; `no_markers` = .md lama tanpa marker `Status:` — hanya pada kasus itu regenerasi/backfill dari naratif `.md`), lalu `--reconcile <module-path>/.psm-develop-plan.json` → item ber-status "diterapkan" yang buktinya hilang (mis. Budi git-revert). Koreksi status di kedua artefak sebelum merancang di atasnya.
4. **Augment katalog bila ada.** Bila `{project-root}/_bmad/psm/memory/ecommerce/function-catalog.md` ada, baca untuk fungsi tambahan di luar katalog inti. Bila belum, lanjut.

## Pahami module existing

Petakan apa yang sudah ada sebelum merancang apa pun. Jalankan dua skrip deterministik ini **dalam satu batch** lalu baca hasilnya — jangan parse PHP mentah dengan tangan:
- `uv run <skills-dir>/psm-develop/scripts/ps-module-inventory.py <module-path>` (lihat `--help`) → JSON inventaris: hook terdaftar & terimplementasi, ObjectModel + nama tabel, controller, versi module, ada/tidaknya folder `upgrade/`, daftar file. Ini peta titik sisip.
- `uv run <skills-dir>/psm-validate/scripts/ps-static-scan.py <module-path> --versions <target>` → baseline API berisiko per versi, supaya rencana tak dibangun di atas masalah lama tanpa menyebutnya.

**Gerbang target.** Bila folder module hilang atau inventaris emit `looks_like_module: false` (aturan pastinya di skrip), arahkan Budi ke **psm-scaffold** dan berhenti; jangan merancang di atas ketiadaan. Bila skrip exit non-zero, tampilkan error apa adanya dan minta klarifikasi (headless: status `gagal`).

## Rancang fungsi & rencana

Tawarkan fungsi e-commerce yang relevan dengan maksud Budi memakai `<skills-dir>/psm-develop/references/ecommerce-function-catalog.md` (peta fungsi per domain; patuhi aturan menambah-ke-existing di bagian akhirnya). Untuk fungsi terpilih, rancang implementasi version-safe dengan `<skills-dir>/psm-cross-version/references/version-safe-patterns.md` sebagai rujukan teknis lintas versi.

Tulis rencana ke kedua artefak (skema kanonik `items[]` + kontrak marker: lihat `--help` ps-module-inventory.py):
- `.psm-develop-plan.md`: seksi `## <function>` per fungsi, dibuka baris `Status: direncanakan` (marker yang dibaca `--pair-check`), lalu file & titik sisip, hook/tabel/service yang ditambah, perubahan per versi, dan alasan. Naratif untuk Budi, dapat direvisi, sumber resume.
- `.psm-develop-plan.json`: item terstruktur per fungsi sesuai skema kanonik. Status awal tiap item `direncanakan` — psm-develop yang menandainya `diterapkan` saat apply; `--reconcile` hanya memeriksa status itu.

**Validasi rencana terhadap inventaris sebelum konfirmasi:** `uv run <skills-dir>/psm-develop/scripts/ps-module-inventory.py <module-path> --validate-plan <module-path>/.psm-develop-plan.json` (rc=1 bila ada mismatch) → mismatch deterministik per item (hook sudah ada di `registered_hooks`; titik sisip file tak ada; `$definition` diubah tanpa `upgrade/` — cek `has_upgrade_dir`). Sisamu: penilaian yang tak bisa di-skrip — apakah perubahan menyentuh `$definition` ObjectModel yang **sedang terpakai** (butuh migrasi tabel existing). Bedakan dua jenis konflik:
- **Mekanis** (nama hook salah, upgrade script kurang) → perbaiki di rencana langsung.
- **Pengubah cakupan / menyentuh data existing** (ubah `$definition` terpakai, tabrak hook yang sudah ada) → jangan auto-fix diam; angkat sebagai pilihan singkat ke Budi sebelum menuliskannya (headless: `butuh intervensi`).

Keputusan cakupan serupa: bila temuan baseline `ps-static-scan` bersinggungan dengan file/hook yang akan disentuh rencana, angkat opsi port-dulu via **psm-cross-version** sebagai pilihan singkat ke Budi dan catat pilihannya di naratif rencana (headless: catat asumsi ke memlog, atau `butuh intervensi` bila tumpang-tindihnya parah).

## Konfirmasi & berhenti

Tampilkan rencana tervalidasi ke Budi dan minta persetujuan. Bila Budi minta revisi, revisi kedua artefak dan validasi ulang sebelum menampilkan lagi. Setelah disetujui, **berhenti** — jangan menyentuh file module, jangan memanggil psm-validate, jangan commit; satu-satunya file yang skill ini tulis adalah pasangan artefak rencana (plus `<module-path>/.memlog.md` di mode headless). Tutup dengan menyarankan **psm-develop** sebagai langkah lanjutan untuk menerapkan rencana: resume-nya membaca pasangan artefak ini apa adanya (psm-develop tetap punya gerbang persetujuannya sendiri sebelum menyentuh file).

## Mode headless

Saat dipanggil dengan `--headless` atau oleh workflow/agent lain: ambil module-path, fungsi, & versi dari argumen alih-alih bertanya, dan jalankan alur normal tanpa gerbang konfirmasi interaktif. Bila argumen fungsi absen, inferensi dari maksud pemanggil + domain module + katalog diizinkan — tiap fungsi terpilih dicatat sebagai asumsi. Karena operator tak hadir, catat tiap asumsi ke memlog via `uv run {project-root}/_bmad/scripts/memlog.py append --path <module-path>/.memlog.md` (init dulu bila belum ada): fungsi yang dipilih, sumber versi, dan konflik mekanis yang di-auto-fix.

Tiga status akhir — satu field yang dibaca pemanggil (pemetaan BMad: `selesai`=`complete`, dua lainnya=`blocked`): **`selesai`** (rencana tervalidasi tertulis di kedua artefak — persetujuan jadi tanggung jawab pemanggil) menyertai ringkasan satu baris + path kedua artefak + path memlog; **`gagal`** (tak terpulihkan — target bukan module, skrip error); **`butuh intervensi`** (butuh keputusan manusia — konflik pengubah cakupan / menyentuh data existing). Dua status berhenti: kembalikan status + alasan satu baris + path memlog, lalu berhenti agar pemanggil memutuskan.
