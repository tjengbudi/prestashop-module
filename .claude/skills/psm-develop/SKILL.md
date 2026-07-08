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
- `<skills-dir>` → direktori yang memuat skill ini (tempat sibling psm-* berada, install-relative). Rujuk sibling lewat `<skills-dir>/psm-validate/…`, bukan `{project-root}/skills/…` — jangan bergantung pada mirror `skills/` di root project.
- `psm-develop` → basename direktori skill.
- `<module-path>` → folder module yang dikembangkan, ditentukan di On Activation #2.

## On Activation

1. Muat config resolved via `uv run {project-root}/skills/psm-setup/scripts/resolve-psm-config.py --project-root {project-root}` — JSON berisi `psm_target_versions`, `communication_language`, dll. Baca apa adanya; default kanonik sudah diterapkan resolver (jangan parse `config.yaml` sendiri).
2. Tentukan module yang dikembangkan (path folder) dan fungsi yang diinginkan dari permintaan Budi. Bila ambigu, tanya satu pertanyaan.
3. Resume: bila `<module-path>/.psm-develop-plan.md` ada, baca untuk melanjutkan dari keadaan terakhir. **Rekonsiliasi dulu, jangan percaya status buta:** jalankan `uv run scripts/ps-module-inventory.py <module-path> --reconcile <plan.json>` → skrip emit drift deterministik (item ber-status "diterapkan" yang buktinya hilang, mis. Budi git-revert). Keputusan atas drift milikmu: koreksi status plan sebelum lanjut. Baca juga `verify_attempts` saat resume (lihat Verifikasi).
4. **Augment katalog bila ada.** Bila `{project-root}/_bmad/psm/memory/ecommerce/function-catalog.md` ada, baca untuk fungsi tambahan di luar `references/ecommerce-function-catalog.md`. Bila belum, lanjut — katalog inti sudah di-embed.

## Pahami module existing

Petakan apa yang sudah ada sebelum menambah apa pun. Jalankan dua skrip deterministik ini **dalam satu batch** (keduanya independen atas `<module-path>` yang sama) lalu baca hasilnya — jangan parse PHP mentah dengan tangan:
- `uv run scripts/ps-module-inventory.py <module-path>` (lihat `--help`) → JSON inventaris: hook terdaftar & terimplementasi, ObjectModel + nama tabel, controller, versi module, ada/tidaknya folder `upgrade/`, daftar file. Ini peta titik sisip.
- `uv run <skills-dir>/psm-validate/scripts/ps-static-scan.py <module-path> --versions <target>` → peta API berisiko per versi, supaya fungsi baru tak menambah masalah lama.

**Gerbang target.** Bila `<module-path>` bukan module berisi — folder hilang/kosong/tanpa `.php`, atau inventaris tak menemukan versi/hook/ObjectModel — arahkan Budi ke **psm-scaffold** (skill ini menumbuhkan module existing, bukan membuat kerangka baru) dan berhenti; jangan merancang di atas ketiadaan. Bila skrip inventaris exit non-zero, tampilkan error apa adanya dan minta klarifikasi (headless: status `gagal`, lihat Mode headless).

Sisamu: menilai *di mana titik sisip aman*.

## Rancang fungsi & rencana

Tawarkan fungsi e-commerce yang relevan dengan maksud Budi memakai `references/ecommerce-function-catalog.md` (peta fungsi per domain + hook/persistensi relevan, plus aturan menambah-ke-existing di bagian akhirnya — patuhi itu). Untuk fungsi terpilih, rancang implementasi version-safe dengan `<skills-dir>/psm-cross-version/references/version-safe-patterns.md` sebagai rujukan teknis lintas versi.

Tulis rencana ke `<module-path>/.psm-develop-plan.md`: per fungsi — file & titik sisip, hook/tabel/service yang ditambah, perubahan per versi, dan alasan. Rencana adalah artefak yang dapat direvisi dan sumber resume.

**Validasi rencana terhadap inventaris sebelum konfirmasi.** Tulis item rencana terstruktur ke `plan.json` — `{"items":[{"function","status","add_hooks":[…],"insert_files":[…],"add_tables":[…],"add_classes":[…],"changes_objectmodel":bool}]}` (field `status`/`add_tables`/`add_classes` dipakai `--reconcile` saat resume) — lalu jalankan `uv run scripts/ps-module-inventory.py <module-path> --validate-plan <plan.json>` (rc=1 bila ada mismatch) → skrip emit mismatch deterministik per item (hook sudah ada di `registered_hooks`; titik sisip file tak ada; `$definition` diubah tanpa `upgrade/` — cek `has_upgrade_dir`). Sisamu: penilaian bermaksud yang tak bisa di-skrip — apakah suatu perubahan menyentuh `$definition` ObjectModel yang **sedang terpakai** (butuh migrasi tabel existing).

Bedakan dua jenis konflik dari mismatch:
- **Mekanis** (nama hook salah, upgrade script kurang) → perbaiki di rencana langsung.
- **Pengubah cakupan / menyentuh data existing** (ubah `$definition` terpakai, tabrak hook yang sudah ada) → jangan auto-fix diam; angkat sebagai pilihan singkat ke Budi sebelum menuliskannya (headless: `butuh intervensi`, jangan log-lalu-lanjut). Konflik mekanis tetap auto-fix.

Perbaiki konflik dulu, lalu tampilkan rencana ke Budi dan **minta persetujuan sebelum menyentuh file** — gerbang yang tak boleh dilewati.

## Terapkan

Sebelum menyentuh file, pastikan `<module-path>` di repo git dengan working tree bersih (`git status`) — itu satu-satunya jaring undo untuk operasi tak-mudah-dibalik ini. Bila tidak, peringatkan Budi / tawarkan backup folder sebelum lanjut (headless: jangan terapkan diam tanpa jaring undo — buat backup folder otomatis lalu catat path-nya ke memlog, atau bila tak bisa kembalikan `butuh intervensi`).

Setelah disetujui, terapkan sesuai rencana pada module di tempat. Tambah, jangan rusak — patuhi **Aturan menambah-ke-existing** di `references/ecommerce-function-catalog.md` (upgrade script untuk hook/tabel baru, cabang versi eksplisit untuk area legacy/modern, GDPR untuk data pelanggan). Tandai status tiap fungsi di `.psm-develop-plan.md` saat diterapkan.

## Verifikasi (gerbang wajib)

Panggil psm-validate atas module hasil terhadap ketiga versi target (lihat `<skills-dir>/psm-validate/SKILL.md`). Status lolos per versi adalah vonis JSON dari psm-validate — baca apa adanya, jangan menilai sendiri. Module dinyatakan siap **hanya bila lolos di 1.7.x, 8.x, dan 9.x**. Bila ada error tersisa, tulis temuan per versi itu kembali ke `.psm-develop-plan.md` dan rancang ulang dari artefak — jangan menyatakan selesai.

**Batasi loop rancang-ulang → apply → validate ke 2-3 percobaan.** Simpan `verify_attempts: N` di `.psm-develop-plan.md` agar cap bertahan lintas sesi. Bila batas tercapai: berhenti, tulis diagnosis error yang bertahan ke plan, dan serahkan ke Budi (headless: `butuh intervensi`) — jangan berputar tanpa henti.

Bila psm-validate sendiri gagal berjalan atau vonisnya tak terbaca (skill absen, crash, non-JSON), perlakukan sebagai **BUKAN lolos** — jangan tafsir "tak ada error" sebagai hijau. Tulis kondisi ke plan dan serahkan (headless: `gagal`).

Ringkas ke Budi: fungsi apa yang ditambahkan, dan status lolos per versi.

## Mode headless

Saat dipanggil dengan `--headless` atau oleh workflow/agent lain: ambil module-path, fungsi, & versi dari argumen alih-alih bertanya, dan jalankan alur normal **tanpa gerbang konfirmasi interaktif** (pemanggil bertanggung jawab atas persetujuan). Karena operator tak hadir, catat tiap asumsi ke memlog via `uv run {project-root}/_bmad/scripts/memlog.py append` (fungsi yang dipilih, sumber versi, dan tiap revisi rencana setelah validate gagal). Kembalikan ringkasan satu baris + path `.psm-develop-plan.md` + path memlog + status lolos per versi dari vonis. Tetap berlaku: jangan menyatakan lolos sebelum psm-validate hijau di ketiga versi.

Dua status berhenti yang dirujuk gerbang-gerbang di atas: **`gagal`** (tak terpulihkan — target bukan module, skrip/validate error) → kembalikan status + alasan; **`butuh intervensi`** (butuh keputusan manusia — konflik menyentuh data existing, cap verify tercapai, tak ada jaring undo) → kembalikan status + memlog dan berhenti agar pemanggil memutuskan. Keduanya: jangan lanjut diam menyentuh file.
