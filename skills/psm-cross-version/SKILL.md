---
name: psm-cross-version
description: Buat module PrestaShop kompatibel 1.7/8/9 sekaligus. Use when the user says "psm-cross-version", "buat module compatible 1.7 8 9", "cross-version module PrestaShop", or "bikin module jalan di semua versi".
---

# psm-cross-version

## Overview

Bertindak sebagai insinyur migrasi PrestaShop yang cermat: operator (Budi) memegang module dan keputusan, skill memegang pengetahuan pola version-safe dan prosedur transformasinya. Ubah satu module PrestaShop existing — sering ditulis untuk versi lawas — menjadi **satu codebase yang jalan di 1.7.x, 8.x, dan 9.x sekaligus tanpa pecah** (bukan upgrade satu arah, bukan dua codebase). Karena ini mengubah source code yang tak mudah dibalik, kerjanya **rencana → konfirmasi → terapkan → verifikasi**: hasilkan rencana perubahan per versi, dapatkan persetujuan Budi, terapkan, lalu buktikan lolos di ketiga versi lewat psm-validate. Konsumen hasil: Budi (module siap rilis ke siapa pun tanpa perubahan lagi) dan psm-agent-expert yang merangkai sesi.

## Resolution rules

- Bare paths dan `{skill-root}` (mis. `references/version-safe-patterns.md`) resolve dari direktori instal skill ini.
- `{project-root}` → direktori kerja project.
- `psm-cross-version` → basename direktori skill.

## On Activation

1. Muat config dari `{project-root}/_bmad/config.yaml` (+ `.user.yaml` bila ada). Ambil versi target dari section `psm` (`psm_target_versions`, default `1.7.8,8.1,9.0`). Komunikasi dalam `communication_language` (default Indonesia).
2. Tentukan module yang dikerjakan (path folder) dan versi target dari permintaan Budi. Bila ambigu, tanya satu pertanyaan. Versi target yang didukung hanya major yang punya ruleset di ps-static-scan/psm-validate dan pola di katalog (1.7/8/9). Bila ada target di luar itu (mis. "juga PS 1.6" atau "PS 10"), jangan lanjut diam-diam — gerbang verifikasi tak bisa menilai versi yang tak dicakup: interaktif, beri tahu Budi versi itu tak didukung dan minta drop/sesuaikan; headless, kembalikan status `blocked` dengan alasan "unsupported target version <x>" dan catat ke memlog.
3. Resume: bila `<module-path>/.psm-cross-plan.md` ada (rencana dari sesi sebelumnya), baca untuk melanjutkan dari keadaan terakhir alih-alih menganalisis ulang. Status rencana mencerminkan sesi terakhir — sebelum menerapkan sisa perubahan, jalankan ulang ps-static-scan (murah, deterministik) untuk memastikan peta risiko masih cocok dengan rencana. Bila menyimpang (source di-edit tangan, tool lain jalan, apply parsial sebelumnya), revisi rencana dari scan segar, jangan terapkan buta.
4. **Augment pola bila ada.** Bila `{project-root}/_bmad/psm/memory/tech/cross-version-patterns.md` ada, baca untuk pola tambahan di luar `references/version-safe-patterns.md`. Bila belum, lanjut — katalog inti sudah di-embed.

## Analisis: peta risiko per versi

Jalankan mesin analisis yang sudah ada alih-alih membangun ulang: `uv run {project-root}/skills/psm-validate/scripts/ps-static-scan.py <module-path> --versions <target>` (lihat `--help`). Bila script tidak ditemukan, jangan lanjut tanpa peta risiko: interaktif, beri tahu Budi bahwa psm-validate harus terinstal di `{project-root}/skills/psm-validate/` lalu hentikan; headless, kembalikan status `blocked` dengan alasan "psm-validate not installed" dan catat ke memlog. Hasilnya peta JSON per versi — kelas/method/hook/konstanta/dependency yang pecah, plus `ps_versions_compliancy` & struktur. Ini fakta deterministik; jangan menilai ulang dengan tangan. Bila perlu, lengkapi dengan membaca source untuk memahami *bagaimana* API berisiko itu dipakai — konteks yang dibutuhkan untuk merancang perbaikan, bukan pengulangan scan.

**Bila peta risiko kosong** (nol temuan lintas-versi), hati-hati: peta kosong bisa berarti module sudah cross-version-safe, atau scan menunjuk folder yang bukan module PrestaShop (path salah, dir induk, php nyasar) — keduanya nol temuan. Cek dulu struktur module dari output scan (`ps_versions_compliancy` & struktur — file module utama ada, struktur valid).

- **Tak ada struktur module.** Interaktif, laporkan "tidak ada module PrestaShop di `<path>`" dan minta Budi konfirmasi path — jangan menyatakan cross-version-safe. Headless, kembalikan status `blocked` dengan alasan "no PrestaShop module at `<path>`" dan catat ke memlog (tak ada operator untuk ditanya).
- **Struktur valid.** Konfirmasi sekali dengan menjalankan psm-validate. **Hanya bila hijau**, module sudah lolos di ketiga versi — selesai tanpa rencana atau gerbang persetujuan; ini status akhir `passed` (interaktif, laporkan ke Budi). Bila konfirmasi tidak hijau, jangan menyatakan lolos — perlakukan errornya sebagai temuan dan lanjut ke rencana.

## Rencana perubahan

Untuk setiap temuan berisiko, rancang perbaikan version-safe memakai `references/version-safe-patterns.md` sebagai rujukan (deteksi versi, cabang legacy/modern per area: hook, controller, template, persistence, service, dependency, konstanta). Tulis rencana ke working artifact `<module-path>/.psm-cross-plan.md`: per perubahan — file & lokasi, API lama, perbaikan yang diusulkan, versi yang terpengaruh, dan alasan. Rencana adalah artefak yang dapat direvisi dan sumber resume; perbarui saat keputusan berubah.

Tampilkan rencana ke Budi dan **minta persetujuan sebelum menyentuh file**. Ini gerbang yang tak boleh dilewati — perubahan source tak mudah dibalik. Bila Budi mengubah arah, revisi rencana dulu, jangan terapkan diam-diam.

## Terapkan

Sebelum sentuhan pertama, amankan titik balik: pastikan working tree bersih atau sarankan Budi commit/branch dulu supaya ada rollback yang pasti (nudge lembut, bukan gerbang keras; lewati di mode headless — pemanggil pegang workspace). Setelah disetujui, terapkan perubahan sesuai rencana. Kerjakan pada module di tempat; asumsikan Budi memakai git untuk pembatalan. Setiap perubahan harus memakai cabang versi eksplisit (`version_compare(_PS_VERSION_, ...)`) — jangan menghapus jalur lama yang masih dibutuhkan versi target terendah, karena tujuannya tetap jalan di 1.7.x. Tandai status tiap perubahan di `.psm-cross-plan.md` saat diterapkan.

**Bila sebuah perubahan gagal diterapkan** (edit tak cocok, file pindah, atau perubahan yang diterapkan memecah module), berhenti segera — jangan menerapkan perubahan berikutnya di atas basis yang rusak. Tandai perubahan itu `failed` di `.psm-cross-plan.md` dan laporkan keadaan parsial: sebutkan perubahan yang sudah masuk tetap ada (git adalah jalur undo). Interaktif, tanya Budi cara lanjut; headless, kembalikan status `partial` dengan perubahan yang gagal dan catat ke memlog.

## Verifikasi (gerbang wajib)

Panggil psm-validate atas module hasil terhadap ketiga versi target (lihat `{project-root}/skills/psm-validate/SKILL.md`). Module dinyatakan cross-version-safe **hanya bila lolos psm-validate di 1.7.x, 8.x, dan 9.x**. Bila ada error tersisa, tulis temuan per versi itu kembali ke `.psm-cross-plan.md` sebagai perubahan baru/diperbarui dan rancang ulang dari artefak itu — jangan menyatakan selesai, dan jangan analisis ulang dari nol.

**Gerbang ini memblokir lolos palsu, tetapi bukan loop tanpa akhir.** Bila sebuah temuan bertahan setelah rancang-ulang, atau memang tak punya jalur version-safe untuk versi target (mis. konflik keras 1.7-vs-9, dependency yang tak bisa di-bundle), berhenti mengulang dan angkat sebagai keputusan — jangan spinning. Interaktif, tampilkan blocker spesifik ke Budi dengan opsi: turunkan satu versi target, terima limitasi yang didokumentasikan, atau pisah codebase. Headless, kembalikan status `blocked` dengan temuan yang tak terselesaikan dan catat alasannya ke memlog. Gerbang tetap utuh — jalur buntu dapat langkah nyata tanpa lolos palsu.

Ringkas hasil akhir ke Budi: apa yang diubah per area, dan status lolos per versi. Bila lolos di ketiga versi, tawarkan (bukan hapus otomatis — ini juga sumber resume) untuk membersihkan `.psm-cross-plan.md` atau mengecualikannya dari build rilis, supaya module yang dikirim tidak menyisakan dotfile proses. Headless, tetap kembalikan path-nya tapi tandai sebagai artefak kerja yang harus dikecualikan dari rilis.

## Mode headless

Saat dipanggil dengan `--headless` atau oleh workflow/agent lain: ambil module-path & versi dari argumen alih-alih bertanya, dan jalankan alur normal **tanpa gerbang konfirmasi interaktif** (pemanggil bertanggung jawab atas persetujuan). Karena operator tak hadir, catat tiap asumsi ke memlog via `uv run {project-root}/_bmad/scripts/memlog.py append` (sumber versi & resolusi module-path bila ambigu, dan tiap revisi rencana setelah validate gagal). Kembalikan ringkasan satu baris + path `.psm-cross-plan.md` + path memlog + status lolos per versi, dengan tepat satu status akhir sebagai kontrak return — kontrak ini total, tiap masuk headless berujung di salah satunya:

- `passed` — hijau di ketiga versi lewat gerbang wajib, atau module yang sudah cross-version-safe lolos konfirmasi (cabang peta-kosong).
- `partial` — sebuah perubahan gagal diterapkan (Terapkan).
- `blocked` — ada temuan tanpa jalur version-safe (Verifikasi), path bukan module PrestaShop (cabang peta-kosong), versi target tak didukung (aktivasi), atau psm-validate tak terinstal (Analisis).
