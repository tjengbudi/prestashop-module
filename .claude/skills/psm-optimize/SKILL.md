---
name: psm-optimize
description: Optimasi performa module PrestaShop via cache/service, cross-version. Use when the user says "psm-optimize", "optimasi module PrestaShop", "percepat module", or "tuning performa module".
---

# psm-optimize

## Overview

Bertindak sebagai insinyur performa PrestaShop yang berbasis bukti: operator (Budi) memegang module dan keputusan, skill memegang katalog peluang optimasi dan disiplin ukur-dulu. Percepat sebuah module PrestaShop existing dengan memanfaatkan cache & service container PrestaShop — **tanpa memecah kompatibilitas lintas versi (1.7.x/8.x/9.x) dan tanpa mengubah perilaku fungsional**. Karena ini mengubah source yang sudah dipakai dan tak mudah dibalik, kerjanya **profil → rencana → konfirmasi → terapkan → verifikasi**: ukur titik lambat dulu, rancang perbaikan, dapatkan persetujuan Budi, terapkan, lalu buktikan tetap lolos psm-validate di ketiga versi dan — sesuai kelas optimasi — lebih cepat terukur atau mekanismenya terpasang & terkonfirmasi. Konsumen hasil: Budi (module lebih cepat tanpa regresi) dan psm-agent-expert.

## Resolution rules

- Bare paths (mis. `references/optimization-catalog.md`) resolve dari direktori instal skill ini.
- `{project-root}` → direktori kerja project.
- `<skills-dir>` → direktori yang memuat skill ini (tempat sibling psm-* berada, install-relative). Rujuk sibling lewat `<skills-dir>/psm-validate/…`, bukan `{project-root}/skills/…` — jangan bergantung pada mirror `skills/` di root project.
- `<module-path>` → folder module yang dioptimasi, ditentukan di On Activation.

## On Activation

1. Muat config resolved via `uv run {project-root}/.claude/skills/psm-setup/scripts/resolve-psm-config.py --project-root {project-root}` — JSON berisi `psm_target_versions`, `communication_language`, dll. Baca apa adanya; default kanonik sudah diterapkan resolver (jangan parse `config.yaml` sendiri). Bahasa: bicara dengan pengguna dalam `communication_language`, tetapi tulis setiap dokumen/artefak yang kamu buat atau ubah (file markdown, rencana, laporan, catatan, memlog) dalam `document_output_language` — keduanya bisa berbeda; jangan ikuti bahasa SKILL.md ini atau bahasa percakapan untuk isi dokumen. Dokumen lama berbahasa lain: hanya bagian yang kamu tulis/ubah yang memakai bahasa dokumen — jangan terjemahkan borongan tanpa diminta. Token mesin (penanda `<!-- psm:… -->`, marker `Fakta:`/`Ide:`/`kind=`/`status=`, nilai status seperti `direncanakan`/`diterapkan`/`dipilih`, field JSON) tetap apa adanya.
2. Tentukan module yang dioptimasi (path folder) dari permintaan Budi. Bila ambigu, tanya satu pertanyaan.
3. Resume: bila `<module-path>/.psm-optimize-plan.md` ada, baca untuk melanjutkan dari keadaan terakhir. **Rekonsiliasi dulu, jangan percaya status buta:** jalankan ulang `ps-hotspot-scan.py`, bandingkan jumlah kandidat dengan blok baseline, dan cek item ber-status "diterapkan" terhadap kode (Budi bisa saja git-revert); koreksi status plan sebelum lanjut (headless: catat koreksi ke memlog). Baca juga `verify_attempts` (lihat Verifikasi).
4. **Konteks module.** Bila `{project-root}/_bmad/psm/memory/projects/<module>.md` ada, baca seksi konvensi (`psm:konvensi`), keputusan (`psm:keputusan`), dan ekor jurnal (`psm:jurnal`) — seksi dikenali dari penanda ID di baris judulnya, judulnya sendiri mengikuti bahasa dokumen sebelum merancang — itu lapis yang tak bisa diturunkan dari inventaris. Bila belum ada, lanjut; **psm-module-context** yang membuatnya.

## Profil: ukur titik lambat

Ukur sebelum mengubah apa pun — optimasi tanpa bukti adalah tebakan. Petakan struktur dengan `uv run <skills-dir>/psm-develop/scripts/ps-module-inventory.py <module-path>` (hook, ObjectModel, controller) dan surface kandidat hotspot dengan `uv run scripts/ps-hotspot-scan.py <module-path>` (lihat `--help`) — JSON berisi situs query/ObjectModel di dalam loop (kandidat N+1) dan method hook berat. Keduanya cuma butuh `<module-path>` dan tak saling bergantung.

**Gerbang target.** Scan kosong atas target yang salah berbentuk persis seperti sukses. Bila `<module-path>` bukan module berisi — folder kosong/tanpa `.php`, atau inventaris tak menemukan versi/hook/file — berhenti dan minta klarifikasi alih-alih menyimpulkan ramping; bila salah satu skrip exit non-zero, tampilkan error apa adanya (headless: `gagal`); exit "sudah ramping" di bawah hanya sah setelah gerbang ini lolos.

Rekonsiliasi dulu: `uv run <skills-dir>/psm-module-context/scripts/ps-module-context.py reconcile --memory-dir {project-root}/_bmad/psm/memory --module <module> --inventory <inventaris.json>` (rc=1 = drift klaim vs bukti; keputusan atas drift milikmu).

Jika tak ada hotspot nyata setelah kamu menilai kandidat (scan kosong, atau semua kandidat ternyata bukan N+1) dan profiler tak menunjukkan hotspot berarti, hentikan bersih: laporkan "module sudah ramping, tak ada peluang berbukti" sebelum gerbang rencana — itu hasil sukses, bukan kegagalan yang harus dipaksakan. Untuk profil runtime, gunakan flashlight dengan Blackfire (`BLACKFIRE_ENABLED=true`) atau Xdebug (`XDEBUG_ENABLED=true`) — lihat `<skills-dir>/psm-validate/SKILL.md` untuk cara spin flashlight; container profiler yang kamu nyalakan sendiri wajib bernama `psm-prof-<job-id>-…` dan berlabel `--label psm.job=<job-id>` (ID buatanmu: `<module>-prof-<HHMM>-<hex>`), lalu bongkar HANYA lewat `ps-flashlight-run.py --stop-job <job-id>` atau nama persisnya — larangan perintah luas di `references/run-phases.md` psm-validate berlaku — lalu ringkas output mentahnya via `uv run scripts/ps-profile-summary.py <file>` (lihat `--help`) → JSON `{wall_time_ms, memory_kb, sql_count}`; jangan ekstrak angka dengan tangan — before/after harus semetode agar perbandingannya sah. Tanpa profiler, andalkan kandidat dari hotspot-scan dan sebut bahwa angka baseline runtime tak terukur.

**Tulis blok baseline ke `<module-path>/.psm-optimize-plan.md` segera setelah diukur**, sebelum gerbang konfirmasi: per alur yang akan dioptimasi — JSON `ps-profile-summary.py` apa adanya plus nama profiler (atau "statis, tanpa angka"), plus jumlah kandidat hotspot-scan (query-in-loop / N+1) sebagai patokan statis. Catat juga status psm-validate awal per versi (lolos/gagal) untuk perbandingan delta saat verifikasi. Baseline yang hanya hidup di percakapan akan hilang saat resume/headless, dan gerbang performa kehilangan "before"-nya.

## Identifikasi & rencana

Dari hotspot terukur, identifikasi peluang memakai `references/optimization-catalog.md` (caching, query/N+1, service container, aset front). Rancang perbaikan yang **version-safe** dengan `<skills-dir>/psm-cross-version/references/version-safe-patterns.md` (bagian Services/Cache) — decorate > override, cabang versi bila menyentuh area legacy/modern.

Tulis rencana ke `<module-path>/.psm-optimize-plan.md` (blok baseline dari tahap Profil sudah di dalamnya): per optimasi — lokasi, masalah terukur (mis. "12 query dalam loop di hookDisplayHeader"), perbaikan yang diusulkan, dampak yang diharapkan, dan versi terpengaruh. Rencana adalah artefak yang dapat direvisi dan sumber resume.

**Review loop sebelum gerbang.** Panggil skill `psm-review-loop` atas `.psm-optimize-plan.md`, dengan sumber JSON inventaris, hotspot-scan, dan ps-profile-summary (simpan ke `{project-root}/_bmad-output/psm-optimize/<module>/`) dan `<module-path>`. Selalu panggil (ia melewati diri bila rencana tak berubah). `selesai` → lanjut ke gerbang; `butuh intervensi` → tampilkan eskalasi & `reason`-nya bersama rencana agar Budi memutuskan; `gagal` → laporkan dan berhenti. Ulangi setelah revisi substantif dari Budi (file, API, perilaku, data, cakupan) sebelum menampilkan lagi; revisi kata-kata saja → lewati dan sebutkan. Opt-out: Budi memintanya atau argumen `--no-review-loop` — sebutkan di gerbang.

Tampilkan ke Budi dan **minta persetujuan sebelum menyentuh file** — gerbang yang tak boleh dilewati.

## Terapkan

Sebelum menyentuh file, pastikan `<module-path>` di repo git dengan working tree bersih (`git status`) — itu satu-satunya jaring undo untuk operasi tak-mudah-dibalik ini. Bila tidak, peringatkan Budi / tawarkan backup folder sebelum lanjut (headless: jangan terapkan diam tanpa jaring undo — buat backup folder otomatis lalu catat path-nya ke memlog, atau bila tak bisa kembalikan `butuh intervensi`).

Setelah disetujui, terapkan sesuai rencana pada module di tempat. Tandai status tiap optimasi di `.psm-optimize-plan.md` saat diterapkan.

## Verifikasi (gerbang wajib)

Dua bukti diperlukan, karena lolos validate saja bisa menyembunyikan perubahan yang ternyata lebih lambat atau mengubah perilaku. Uji Docker di dalamnya berjalan sebagai **job ber-ID** yang dipantau lewat log kemajuan; jangan menjalankan uji atau perintah `docker` sendiri di luar psm-validate, dan bila harus menghentikan, hanya `--stop-job <id>` atas job yang dimulai run ini — tak pernah pkill/`docker rm` berdasarkan nama (aturan lengkap: `<skills-dir>/psm-validate/references/run-phases.md`, bagian Job ID). **Kompatibilitas:** panggil psm-validate atas module hasil terhadap ketiga versi (lihat `<skills-dir>/psm-validate/SKILL.md`); status lolos per versi adalah vonis JSON-nya — baca apa adanya. Nilai *delta* terhadap status awal di baseline: syaratnya tak ada kegagalan baru dibanding sebelum optimasi, bukan hijau mutlak (red bawaan module lama bukan regresimu). **Performa:** bukti mengikuti kelas optimasi dan isi baseline — jalur profiler bila baseline punya angka, dua jalur statis bila tidak; muat bagian **Bukti performa per kelas** di `references/optimization-catalog.md` untuk syarat lolos tiap jalur. Module teroptimasi bila kompatibilitas tak mundur di ketiga versi **dan** bukti performa sesuai kelasnya terpenuhi tanpa regresi perilaku. Bila ada kegagalan baru atau bukti performa tak membaik, tulis temuan itu kembali ke `.psm-optimize-plan.md` dan rancang ulang dari artefak, lalu bawa kembali lewat review loop dan gerbang persetujuan sebelum menerapkan — jangan menyatakan selesai.

**Batasi loop rancang-ulang → terapkan → verifikasi ke 3 percobaan.** Simpan `verify_attempts: N` di `.psm-optimize-plan.md` agar cap bertahan lintas sesi. Bila batas tercapai: berhenti, tulis diagnosis yang bertahan ke plan, dan serahkan ke Budi (headless: `butuh intervensi`) — jangan berputar tanpa henti. Reset `verify_attempts` ke 0 saat rencana baru/revisi disetujui pasca-intervensi — cap membatasi satu loop rancang-ulang, bukan seumur hidup module.

Bila psm-validate sendiri gagal berjalan atau vonisnya tak terbaca (skill absen, crash, non-JSON), perlakukan sebagai **BUKAN lolos** — jangan tafsir "tak ada error" sebagai hijau. Tulis kondisi ke plan dan serahkan (headless: `gagal`).

Ringkas ke Budi: apa yang dioptimasi, sebelum/sesudah per metrik, dan status lolos per versi. Setelah lolos, tawarkan satu commit untuk perubahan run ini (pesan menyebut optimasi yang diterapkan) agar jaring undo run berikutnya mulai bersih (headless: jangan commit — catat ke memlog bahwa tree memuat perubahan ter-apply belum di-commit, dan sertakan fakta itu di return).

Catat satu baris ke konteks module: `uv run <skills-dir>/psm-module-context/scripts/ps-module-context.py note --memory-dir {project-root}/_bmad/psm/memory --module <module> --by psm-optimize --type note --text "<satu baris>"` (auto-init bila belum ada). Satu entri per run — ini bukan laporan.

## Mode headless

Saat dipanggil dengan `--headless` atau oleh workflow/agent lain: ambil module-path & versi dari argumen alih-alih bertanya, dan jalankan alur normal **tanpa gerbang konfirmasi interaktif** (pemanggil bertanggung jawab atas persetujuan). Karena operator tak hadir, catat tiap asumsi ke memlog via `uv run {project-root}/_bmad/scripts/memlog.py append` (sumber versi, peluang yang dipilih, dan tiap revisi setelah validate/metrik gagal). Kembalikan `status: selesai` + ringkasan satu baris + path `.psm-optimize-plan.md` + path memlog + status lolos per versi dari vonis + ringkasan metrik sebelum/sesudah. Bila alur berhenti di exit "sudah ramping" (tak ada rencana, tak ada perubahan), kembalikan `status: sudah-ramping` + ringkasan kandidat hotspot-scan + path memlog, tanpa field plan/metrik — supaya pemanggil bisa bedakan no-op sukses dari run rusak. Tetap berlaku: gerbang Verifikasi penuh seperti di atas. Review loop dipanggil dengan `--headless`; rencana hanya diterapkan — dan `selesai` hanya sah — setelah ia mengembalikan `selesai` (atau `--no-review-loop`, dicatat ke memlog).

Empat status akhir — satu field yang dibaca pemanggil (pemetaan BMad: `selesai`/`sudah-ramping`=`complete`, dua lainnya=`blocked`). Dua status berhenti yang dirujuk gerbang-gerbang di atas: **`gagal`** (tak terpulihkan — target bukan module, skrip error, vonis validate tak terbaca, review loop `gagal`) dan **`butuh intervensi`** (butuh keputusan manusia — cap verify tercapai, tak ada jaring undo, review loop `butuh intervensi` dengan baris alasan `review-loop: <reason>`). Keduanya: kembalikan status + alasan satu baris + path memlog, lalu berhenti agar pemanggil memutuskan — jangan lanjut diam menyentuh file.
