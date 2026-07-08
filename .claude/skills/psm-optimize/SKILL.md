---
name: psm-optimize
description: Optimasi performa module PrestaShop via cache/service, cross-version. Use when the user says "psm-optimize", "optimasi module PrestaShop", "percepat module", or "tuning performa module".
---

# psm-optimize

## Overview

Bertindak sebagai insinyur performa PrestaShop yang berbasis bukti: operator (Budi) memegang module dan keputusan, skill memegang katalog peluang optimasi dan disiplin ukur-dulu. Percepat sebuah module PrestaShop existing dengan memanfaatkan cache & service container PrestaShop — **tanpa memecah kompatibilitas lintas versi (1.7.x/8.x/9.x) dan tanpa mengubah perilaku fungsional**. Karena ini mengubah source yang sudah dipakai dan tak mudah dibalik, kerjanya **profil → rencana → konfirmasi → terapkan → verifikasi**: ukur titik lambat dulu, rancang perbaikan, dapatkan persetujuan Budi, terapkan, lalu buktikan tetap lolos psm-validate di ketiga versi dan — sesuai kelas optimasi — lebih cepat terukur atau mekanismenya terpasang & terkonfirmasi. Konsumen hasil: Budi (module lebih cepat tanpa regresi) dan psm-agent-expert. Tiga pantangan menjiwai alur ini: jangan optimasi tanpa bukti profil, jangan terapkan tanpa rencana disetujui, jangan nyatakan selesai sebelum kedua bukti verifikasi hijau.

## Resolution rules

- Bare paths dan `{skill-root}` (mis. `references/optimization-catalog.md`) resolve dari direktori instal skill ini.
- `{project-root}` → direktori kerja project.
- `psm-optimize` → basename direktori skill.
- `<module-path>` → folder module yang dioptimasi, ditentukan di On Activation.

## On Activation

1. Muat config resolved via `uv run {project-root}/skills/psm-setup/scripts/resolve-psm-config.py --project-root {project-root}` — JSON berisi `psm_target_versions`, `communication_language`, dll. Baca apa adanya; default kanonik sudah diterapkan resolver (jangan parse `config.yaml` sendiri).
2. Tentukan module yang dioptimasi (path folder) dari permintaan Budi. Bila ambigu, tanya satu pertanyaan.
3. Resume: bila `<module-path>/.psm-optimize-plan.md` ada, baca untuk melanjutkan dari keadaan terakhir.

## Profil: ukur titik lambat

Ukur sebelum mengubah apa pun — optimasi tanpa bukti adalah tebakan. Petakan struktur dengan `uv run {project-root}/skills/psm-develop/scripts/ps-module-inventory.py <module-path>` (hook, ObjectModel, controller) dan surface kandidat hotspot dengan `uv run scripts/ps-hotspot-scan.py <module-path>` (lihat `--help`) — JSON berisi situs query/ObjectModel di dalam loop (kandidat N+1) dan method hook berat. Keduanya cuma butuh `<module-path>` dan tak saling bergantung, jadi jalankan sekaligus dalam satu batch. Skrip mengumpulkan kandidat; kamu yang memutuskan mana N+1 nyata dan cara perbaikannya. Jika tak ada hotspot nyata setelah kamu menilai kandidat (scan kosong, atau semua kandidat ternyata bukan N+1) dan profiler tak menunjukkan hotspot berarti, hentikan bersih: laporkan "module sudah ramping, tak ada peluang berbukti" sebelum gerbang rencana — itu hasil sukses, bukan kegagalan yang harus dipaksakan (jangan optimasi spekulatif). Untuk profil runtime, gunakan flashlight dengan Blackfire (`BLACKFIRE_ENABLED=true`) atau Xdebug (`XDEBUG_ENABLED=true`) — lihat `{project-root}/skills/psm-validate/SKILL.md` untuk cara spin flashlight. Tanpa profiler, andalkan kandidat dari hotspot-scan dan sebut bahwa angka baseline runtime tak terukur.

**Tulis baseline ke artefak segera setelah diukur**, sebelum gerbang konfirmasi: per alur yang akan dioptimasi — wall-time, jumlah query, memori, dan profiler yang dipakai (atau "statis, tanpa angka"), plus jumlah kandidat hotspot-scan (query-in-loop / N+1) sebagai patokan statis. Catat juga status psm-validate awal per versi (lolos/gagal) untuk perbandingan delta saat verifikasi. Baseline yang hanya hidup di percakapan akan hilang saat resume/headless, dan gerbang performa kehilangan "before"-nya.

## Identifikasi & rencana

Dari hotspot terukur, identifikasi peluang memakai `references/optimization-catalog.md` (caching, query/N+1, service container, aset front). Rancang perbaikan yang **version-safe** dengan `{project-root}/skills/psm-cross-version/references/version-safe-patterns.md` (bagian Services/Cache) — decorate > override, cabang versi bila menyentuh area legacy/modern.

Tulis rencana ke `<module-path>/.psm-optimize-plan.md` (memuat blok baseline yang sudah ditulis di tahap Profil): per optimasi — lokasi, masalah terukur (mis. "12 query dalam loop di hookDisplayHeader"), perbaikan yang diusulkan, dampak yang diharapkan, dan versi terpengaruh. Rencana adalah artefak yang dapat direvisi dan sumber resume. Tampilkan ke Budi dan **minta persetujuan sebelum menyentuh file** — gerbang yang tak boleh dilewati.

## Terapkan

Setelah disetujui, terapkan sesuai rencana pada module di tempat (asumsikan Budi memakai git untuk pembatalan). Optimasi tak boleh mengubah perilaku fungsional — hasil harus identik, hanya lebih cepat. Pakai cabang versi eksplisit untuk area legacy/modern. Tandai status tiap optimasi di `.psm-optimize-plan.md` saat diterapkan.

## Verifikasi (gerbang wajib)

Dua bukti diperlukan, karena lolos validate saja bisa menyembunyikan perubahan yang ternyata lebih lambat atau mengubah perilaku. **Kompatibilitas:** panggil psm-validate atas module hasil terhadap ketiga versi (lihat `{project-root}/skills/psm-validate/SKILL.md`); status lolos per versi adalah vonis JSON-nya — baca apa adanya. Nilai *delta* terhadap status awal di baseline: syaratnya tak ada kegagalan baru dibanding sebelum optimasi, bukan hijau mutlak (red bawaan module lama bukan regresimu). **Performa:** ada dua jalur, tergantung baseline. Bila baseline punya angka profiler, ukur ulang dengan profiler yang sama lalu bandingkan dengan blok baseline di `.psm-optimize-plan.md` (bukan dari ingatan) — syaratnya metrik membaik. Bila baseline "statis, tanpa angka" (tak ada profiler), bukti performa bergantung kelas optimasi — sebab `ps-hotspot-scan.py` hanya melihat query-in-loop dan hook berat, bukan cache/service/aset. Untuk fix kelas N+1 / hook berat: jalankan ulang `ps-hotspot-scan.py` dan buktikan jumlah kandidat (query-in-loop / hook berat) turun terhadap baseline. Untuk fix cache/service/aset yang tak tampak di scan: bukti statisnya adalah mekanisme terpasang & jalur-pakainya terkonfirmasi dari diff (cache benar di-hit, service ter-decorate, aset ter-defer), dan laporkan jujur "kompatibilitas terverifikasi, mekanisme optimasi terpasang, performa runtime tak terukur (bukan kelas N+1) — perlu profiler untuk angka". Module teroptimasi bila kompatibilitas tak mundur di ketiga versi **dan** bukti performa yang sesuai kelasnya (metrik profiler membaik, atau delta hotspot statis turun, atau mekanisme terpasang & terkonfirmasi di diff untuk fix tak-terpantau) terpenuhi tanpa regresi perilaku. Bila ada kegagalan baru atau bukti performa tak membaik, tulis temuan itu kembali ke `.psm-optimize-plan.md` dan rancang ulang dari artefak — jangan menyatakan selesai. Ringkas ke Budi: apa yang dioptimasi, sebelum/sesudah per metrik, dan status lolos per versi.

## Mode headless

Saat dipanggil dengan `--headless` atau oleh workflow/agent lain: ambil module-path & versi dari argumen alih-alih bertanya, dan jalankan alur normal **tanpa gerbang konfirmasi interaktif** (pemanggil bertanggung jawab atas persetujuan). Karena operator tak hadir, catat tiap asumsi ke memlog via `uv run {project-root}/_bmad/scripts/memlog.py append` (sumber versi, peluang yang dipilih, dan tiap revisi setelah validate/metrik gagal). Kembalikan ringkasan satu baris + path `.psm-optimize-plan.md` + path memlog + status lolos per versi dari vonis + ringkasan metrik sebelum/sesudah. Bila alur berhenti di exit "sudah ramping" (tak ada rencana, tak ada perubahan), kembalikan hasil berbeda — `status: sudah-ramping` + ringkasan kandidat hotspot-scan + status validate per versi, tanpa field plan/metrik — supaya pemanggil bisa bedakan no-op sukses dari run rusak. Tetap berlaku: gerbang Verifikasi penuh seperti di atas — hanya gerbang konfirmasi interaktif yang dilewati di headless, bukan verifikasi.
