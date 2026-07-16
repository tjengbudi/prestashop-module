---
name: psm-cross-version
description: Ubah module PrestaShop existing jadi kompatibel 1.7/8/9 sekaligus. Use when the user says "psm-cross-version", "buat module compatible 1.7 8 9", "cross-version module PrestaShop", or "bikin module jalan di semua versi".
---

# psm-cross-version

## Overview

Bertindak sebagai insinyur migrasi PrestaShop yang cermat: operator (Budi) memegang module dan keputusan, skill memegang pengetahuan pola version-safe dan prosedur transformasinya. Ubah satu module PrestaShop existing — sering ditulis untuk versi lawas — menjadi **satu codebase yang jalan di 1.7.x, 8.x, dan 9.x sekaligus tanpa pecah** (bukan upgrade satu arah, bukan dua codebase). Karena ini mengubah source code yang tak mudah dibalik, kerjanya **rencana → konfirmasi → terapkan → verifikasi**: hasilkan rencana perubahan per versi, dapatkan persetujuan Budi, terapkan, lalu buktikan lolos di ketiga versi lewat psm-validate. Konsumen hasil: Budi (module siap rilis ke siapa pun tanpa perubahan lagi) dan psm-agent-expert yang merangkai sesi.

## Resolution rules

- Bare paths dan `{skill-root}` (mis. `references/version-safe-patterns.md`) resolve dari direktori instal skill ini.
- `{project-root}` → direktori kerja project.
- `<skills-dir>` → direktori yang memuat skill ini (tempat sibling psm-* berada, install-relative). Rujuk sibling lewat `<skills-dir>/psm-validate/…`, bukan `{project-root}/skills/…` — jangan bergantung pada mirror `skills/` di root project.
- `<module-path>` → folder module yang diubah, ditentukan di On Activation.

## On Activation

- Muat config resolved via `uv run {project-root}/.claude/skills/psm-setup/scripts/resolve-psm-config.py --project-root {project-root}` — JSON berisi `psm_target_versions`, `communication_language`, dll. Baca apa adanya; default kanonik sudah diterapkan resolver (jangan parse `config.yaml` sendiri).
- Tentukan module yang dikerjakan (path folder) dan versi target dari permintaan Budi. Bila ambigu, tanya satu pertanyaan. Bila tak ada module existing (Budi ingin module baru), arahkan ke psm-scaffold dan berhenti — skill ini mengubah module berisi, bukan membuat kerangka baru.
- Resume: bila `<module-path>/.psm-cross-plan.md` ada (rencana dari sesi sebelumnya), baca untuk melanjutkan dari keadaan terakhir alih-alih menganalisis ulang. Baca juga `verify_attempts` di dalamnya (lihat Verifikasi).
- **Augment pola bila ada.** Bila `{project-root}/_bmad/psm/memory/tech/cross-version-patterns.md` ada, baca untuk pola tambahan di luar `references/version-safe-patterns.md`. Bila belum, lanjut — katalog inti sudah di-embed.

## Analisis: peta risiko per versi

Jalankan mesin analisis yang sudah ada alih-alih membangun ulang: `uv run <skills-dir>/psm-validate/scripts/ps-static-scan.py <module-path> --versions <target>` (lihat `--help`). Hasilnya peta JSON per versi — kelas/method/hook/konstanta/dependency yang pecah, plus `ps_versions_compliancy` & struktur. Ini fakta deterministik; jangan menilai ulang dengan tangan. Bila perlu, lengkapi dengan membaca source untuk memahami *bagaimana* API berisiko itu dipakai — konteks yang dibutuhkan untuk merancang perbaikan, bukan pengulangan scan.

Bila scan bersih (tak ada temuan berisiko di semua versi target), lewati Rencana & Terapkan: langsung ke gerbang Verifikasi dan laporkan "module sudah cross-version-safe" dengan status per versi (headless: `status: sudah-aman`).

## Rencana perubahan

Untuk setiap temuan berisiko, rancang perbaikan version-safe memakai `references/version-safe-patterns.md` sebagai rujukan (deteksi versi, cabang legacy/modern per area: hook, controller, template, persistence, service, dependency, konstanta). Tulis rencana ke working artifact `<module-path>/.psm-cross-plan.md`: per perubahan — file & lokasi, API lama, perbaikan yang diusulkan, versi yang terpengaruh, dan alasan. Rencana adalah artefak yang dapat direvisi dan sumber resume; perbarui saat keputusan berubah.

Tampilkan rencana ke Budi dan **minta persetujuan sebelum menyentuh file**. Ini gerbang yang tak boleh dilewati — perubahan source tak mudah dibalik. Bila Budi mengubah arah, revisi rencana dulu, jangan terapkan diam-diam.

## Terapkan

Sebelum menyentuh file, pastikan `<module-path>` di repo git dengan working tree bersih (`git status`) — itu satu-satunya jaring undo untuk operasi tak-mudah-dibalik ini. Bila tidak, peringatkan Budi / tawarkan backup folder sebelum lanjut (headless: jangan terapkan diam tanpa jaring undo — buat backup folder otomatis lalu catat path-nya ke memlog, atau bila tak bisa kembalikan `butuh intervensi`).

Setelah disetujui, terapkan perubahan sesuai rencana pada module di tempat. Setiap perubahan harus memakai cabang versi eksplisit (`version_compare(_PS_VERSION_, ...)`) — jangan menghapus jalur lama yang masih dibutuhkan versi target terendah, karena tujuannya tetap jalan di 1.7.x. Tandai status tiap perubahan di `.psm-cross-plan.md` saat diterapkan.

## Verifikasi (gerbang wajib)

Panggil psm-validate atas module hasil terhadap ketiga versi target (lihat `<skills-dir>/psm-validate/SKILL.md`). Module dinyatakan cross-version-safe **hanya bila lolos psm-validate di 1.7.x, 8.x, dan 9.x**. Bila ada error tersisa, tulis temuan per versi itu kembali ke `.psm-cross-plan.md` sebagai perubahan baru/diperbarui dan rancang ulang dari artefak itu — jangan menyatakan selesai, dan jangan analisis ulang dari nol.

**Batasi loop rancang-ulang → terapkan → validate ke 2-3 percobaan.** Simpan `verify_attempts: N` di `.psm-cross-plan.md` agar cap bertahan lintas sesi. Bila batas tercapai: berhenti, tulis diagnosis error yang bertahan ke plan, dan serahkan ke Budi (headless: `butuh intervensi`) — jangan berputar tanpa henti.

Bila psm-validate sendiri gagal berjalan atau vonisnya tak terbaca (skill absen, crash, non-JSON), perlakukan sebagai **BUKAN lolos** — jangan tafsir "tak ada error" sebagai hijau. Tulis kondisi ke plan dan serahkan (headless: `gagal`).

Ringkas hasil akhir ke Budi: apa yang diubah per area, dan status lolos per versi.

## Mode headless

Saat dipanggil dengan `--headless` atau oleh workflow/agent lain: ambil module-path & versi dari argumen alih-alih bertanya, dan jalankan alur normal **tanpa gerbang konfirmasi interaktif** (pemanggil bertanggung jawab atas persetujuan). Karena operator tak hadir, catat tiap asumsi ke memlog — memlog hidup di `<module-path>/.memlog.md` di samping `.psm-cross-plan.md` (`uv run {project-root}/_bmad/scripts/memlog.py init` bila belum ada, lalu `append`); itu path yang dikembalikan ke pemanggil. Yang dicatat: sumber versi & resolusi module-path bila ambigu, dan tiap revisi rencana setelah validate gagal. Kembalikan ringkasan satu baris + path `.psm-cross-plan.md` + path memlog + status lolos per versi. Bila scan bersih, kembalikan `status: sudah-aman` + status validate per versi tanpa field perubahan rencana — supaya pemanggil bisa bedakan no-op sukses dari run rusak. Tetap berlaku: jangan menyatakan lolos sebelum psm-validate hijau di ketiga versi.

Dua status berhenti yang dirujuk gerbang-gerbang di atas: **`gagal`** (tak terpulihkan — target bukan module, skrip scan/validate error) → kembalikan status + alasan satu baris + path memlog; **`butuh intervensi`** (butuh keputusan manusia — cap verify tercapai, tak ada jaring undo) → kembalikan status + path plan + path memlog dan berhenti agar pemanggil memutuskan. Keduanya: jangan lanjut diam menyentuh file.
