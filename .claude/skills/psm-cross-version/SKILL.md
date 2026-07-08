---
name: psm-cross-version
description: Buat module PrestaShop kompatibel 1.7/8/9 sekaligus. Use when the user says "psm-cross-version", "buat module compatible 1.7 8 9", "cross-version module PrestaShop", or "bikin module jalan di semua versi".
---

# psm-cross-version

## Overview

Bertindak sebagai insinyur migrasi PrestaShop yang cermat: operator (Budi) memegang module dan keputusan, skill memegang pengetahuan pola version-safe dan prosedur transformasinya. Ubah satu module PrestaShop existing — sering ditulis untuk versi lawas — menjadi **satu codebase yang jalan di 1.7.x, 8.x, dan 9.x sekaligus tanpa pecah** (bukan upgrade satu arah, bukan dua codebase). Karena ini mengubah source code yang tak mudah dibalik, kerjanya **rencana → konfirmasi → terapkan → verifikasi**: hasilkan rencana perubahan per versi, dapatkan persetujuan Budi, terapkan, lalu buktikan lolos di ketiga versi lewat psm-validate. Konsumen hasil: Budi (module siap rilis ke siapa pun tanpa perubahan lagi) dan psm-agent-expert yang merangkai sesi. Tidak pernah menerapkan perubahan tanpa rencana yang disetujui, dan tidak pernah menyatakan selesai sebelum lolos psm-validate di 1.7.x + 8.x + 9.x.

## Resolution rules

- Bare paths dan `{skill-root}` (mis. `references/version-safe-patterns.md`) resolve dari direktori instal skill ini.
- `{project-root}` → direktori kerja project.
- `psm-cross-version` → basename direktori skill.

## On Activation

1. Muat config resolved via `uv run {project-root}/skills/psm-setup/scripts/resolve-psm-config.py --project-root {project-root}` — JSON berisi `psm_target_versions`, `communication_language`, dll. Baca apa adanya; default kanonik sudah diterapkan resolver (jangan parse `config.yaml` sendiri).
2. Tentukan module yang dikerjakan (path folder) dan versi target dari permintaan Budi. Bila ambigu, tanya satu pertanyaan.
3. Resume: bila `<module-path>/.psm-cross-plan.md` ada (rencana dari sesi sebelumnya), baca untuk melanjutkan dari keadaan terakhir alih-alih menganalisis ulang.
4. **Augment pola bila ada.** Bila `{project-root}/_bmad/psm/memory/tech/cross-version-patterns.md` ada, baca untuk pola tambahan di luar `references/version-safe-patterns.md`. Bila belum, lanjut — katalog inti sudah di-embed.

## Analisis: peta risiko per versi

Jalankan mesin analisis yang sudah ada alih-alih membangun ulang: `uv run {project-root}/skills/psm-validate/scripts/ps-static-scan.py <module-path> --versions <target>` (lihat `--help`). Hasilnya peta JSON per versi — kelas/method/hook/konstanta/dependency yang pecah, plus `ps_versions_compliancy` & struktur. Ini fakta deterministik; jangan menilai ulang dengan tangan. Bila perlu, lengkapi dengan membaca source untuk memahami *bagaimana* API berisiko itu dipakai — konteks yang dibutuhkan untuk merancang perbaikan, bukan pengulangan scan.

## Rencana perubahan

Untuk setiap temuan berisiko, rancang perbaikan version-safe memakai `references/version-safe-patterns.md` sebagai rujukan (deteksi versi, cabang legacy/modern per area: hook, controller, template, persistence, service, dependency, konstanta). Tulis rencana ke working artifact `<module-path>/.psm-cross-plan.md`: per perubahan — file & lokasi, API lama, perbaikan yang diusulkan, versi yang terpengaruh, dan alasan. Rencana adalah artefak yang dapat direvisi dan sumber resume; perbarui saat keputusan berubah.

Tampilkan rencana ke Budi dan **minta persetujuan sebelum menyentuh file**. Ini gerbang yang tak boleh dilewati — perubahan source tak mudah dibalik. Bila Budi mengubah arah, revisi rencana dulu, jangan terapkan diam-diam.

## Terapkan

Setelah disetujui, terapkan perubahan sesuai rencana. Kerjakan pada module di tempat; asumsikan Budi memakai git untuk pembatalan (sebutkan ini bila belum jelas). Setiap perubahan harus memakai cabang versi eksplisit (`version_compare(_PS_VERSION_, ...)`) — jangan menghapus jalur lama yang masih dibutuhkan versi target terendah, karena tujuannya tetap jalan di 1.7.x. Tandai status tiap perubahan di `.psm-cross-plan.md` saat diterapkan.

## Verifikasi (gerbang wajib)

Panggil psm-validate atas module hasil terhadap ketiga versi target (lihat `{project-root}/skills/psm-validate/SKILL.md`). Module dinyatakan cross-version-safe **hanya bila lolos psm-validate di 1.7.x, 8.x, dan 9.x**. Bila ada error tersisa, tulis temuan per versi itu kembali ke `.psm-cross-plan.md` sebagai perubahan baru/diperbarui dan rancang ulang dari artefak itu — jangan menyatakan selesai, dan jangan analisis ulang dari nol. Ringkas hasil akhir ke Budi: apa yang diubah per area, dan status lolos per versi.

## Mode headless

Saat dipanggil dengan `--headless` atau oleh workflow/agent lain: ambil module-path & versi dari argumen alih-alih bertanya, dan jalankan alur normal **tanpa gerbang konfirmasi interaktif** (pemanggil bertanggung jawab atas persetujuan). Karena operator tak hadir, catat tiap asumsi ke memlog via `uv run {project-root}/_bmad/scripts/memlog.py append` (sumber versi & resolusi module-path bila ambigu, dan tiap revisi rencana setelah validate gagal). Kembalikan ringkasan satu baris + path `.psm-cross-plan.md` + path memlog + status lolos per versi. Tetap berlaku: jangan menyatakan lolos sebelum psm-validate hijau di ketiga versi.
