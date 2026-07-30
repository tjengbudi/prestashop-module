---
name: psm-ideate
description: Gali & rawat backlog ide untuk memperdalam satu module PrestaShop dalam domainnya sendiri. Use when the user says "psm-ideate", "perkaya module", "kembangkan module ini lebih jauh", "brainstorm fitur module", or "backlog ide module".
---

# psm-ideate

## Overview

Bertindak sebagai pendamping penggalian ide per-module: operator (Budi) memutuskan mana yang layak dibangun, skill memegang lensa penggalian dan backlog yang bertahan lintas sesi. Yang digali bukan fungsi lintas domain — itu milik psm-plan dengan katalog penuh — melainkan **pendalaman satu module di dalam topiknya sendiri**: bankwire tumbuh jadi QR payment, bukti bayar, konfirmasi manual, rekonsiliasi. Karena satu sesi penggalian melahirkan lebih banyak ide daripada yang dikerjakan satu siklus, hasilnya adalah **backlog** — `<module-path>/.psm-ideas.md` yang hidup lintas sesi dan disinkronkan ke rencana, bukan daftar sekali pakai. Konsumen hasil: Budi (peta jalan module) dan **psm-plan**, yang mengambil ide berstatus `dipilih` sebagai masukan.

## Resolution rules

- Bare paths dan `{skill-root}` (mis. `scripts/ps-idea-backlog.py`) resolve dari direktori instal skill ini.
- `{project-root}` → direktori kerja project.
- `<skills-dir>` → direktori yang memuat skill ini (tempat sibling psm-* berada, install-relative). Rujuk sibling lewat `<skills-dir>/psm-develop/…`, bukan `{project-root}/skills/…` — jangan bergantung pada mirror `skills/` di root project.
- `<module-path>` → folder module yang digali, ditentukan di On Activation #2.
- Artefak backlog (path kanonik): `<module-path>/.psm-ideas.md`. Kontrak marker & zona seksinya ada di `--help` ps-idea-backlog.py; jangan menyusun format sendiri.

## On Activation

1. Muat config resolved via `uv run <skills-dir>/psm-setup/scripts/resolve-psm-config.py --project-root {project-root}` — JSON berisi `psm_modules_dir`, `psm_target_versions`, `communication_language`, dll. Baca apa adanya; jangan parse `config.yaml` sendiri.
2. Tentukan module yang digali. Nama telanjang (mis. `psbankwire`) di-resolve ke `<psm_modules_dir>/<nama>`; path lengkap dipakai apa adanya. Bila ambigu, tanya satu pertanyaan.
3. **Konteks module.** Bila `{project-root}/_bmad/psm/memory/projects/<module>.md` ada, baca **Konvensi module**, **Keputusan**, dan ekor **Jurnal** — keputusan lama sering sudah menolak sebuah ide beserta alasannya; menggalinya ulang membuang waktu Budi. Bila belum ada, lanjut; **psm-module-context** yang membuatnya.
4. **Augment katalog bila ada.** Bila `{project-root}/_bmad/psm/memory/ecommerce/function-catalog.md` ada, baca untuk fungsi tambahan di luar katalog inti.

## Kenali domain & posisi

Gali dari bukti, bukan dari nama module. Jalankan:

`uv run <skills-dir>/psm-develop/scripts/ps-module-inventory.py <module-path>` (lihat `--help`) → JSON inventaris: hook terdaftar & terimplementasi, ObjectModel + nama tabel, controller, versi module, daftar file.

**Gerbang target.** Bila folder module hilang atau inventaris emit `looks_like_module: false` (aturan pastinya di skrip), arahkan Budi ke **psm-scaffold** dan berhenti — tak ada domain untuk digali dari ketiadaan. Bila skrip exit non-zero, tampilkan error apa adanya dan minta klarifikasi (headless: status `gagal`).

Dari inventaris itu, tentukan domain module dan posisinya: `paymentOptions` → domain pembayaran; `actionCarrierProcess` → pengiriman; `displayHome` + ObjectModel konten → marketing. Bila domainnya punya keluarga fungsi yang sudah dipetakan di `<skills-dir>/psm-develop/references/ecommerce-function-catalog.md` (mis. **Keluarga fungsi: pembayaran manual/offline → semi-otomatis**), posisikan module di tangga itu — anak tangga yang sudah dilewati dan yang berikutnya adalah kerangka penggalian yang paling berguna.

Tulis hasilnya ke seksi prosa **Domain & posisi** di artefak backlog (`init --domain "<satu-dua baris>"` bila artefak belum ada; sunting tangan bila sudah). Itu satu-satunya seksi prosa di artefak ini.

## Sinkronkan backlog dulu

Bila `<module-path>/.psm-ideas.md` sudah ada, **rekonsiliasi sebelum menggali** — backlog basi menawarkan ulang fungsi yang sudah dibangun, dan sekali itu terjadi Budi berhenti memercayainya:

`uv run scripts/ps-idea-backlog.py sync --module-path <module-path> --plan <module-path>/.psm-develop-plan.json` (rc=1 = drift; tanpa `--plan` hanya prasyarat yang dicek — pakai bentuk itu bila rencana belum pernah dibuat).

Empat jenis drift, dua penanganan:

- **Klerikal** — `terwujud_belum_ditandai` (rencana sudah `diterapkan` tapi ide masih `baru`/`dipilih`): koreksi langsung dengan `add --status terwujud`. Tak perlu bertanya; bukti sudah memutuskan.
- **Butuh keputusan** — `terwujud_tanpa_bukti` (ide diklaim terwujud tapi jejaknya hilang dari rencana, mis. Budi git-revert), `dipilih_tanpa_rencana` (dipilih tapi tak pernah masuk rencana), `prasyarat_belum_terwujud` (anak tangga dilompati): angkat sebagai pilihan singkat ke Budi (headless: `butuh intervensi` untuk `terwujud_tanpa_bukti`; dua sisanya boleh dicatat sebagai asumsi ke memlog lalu lanjut).

`info.rencana_tanpa_ide` bukan drift — rencana boleh memuat fungsi yang tak pernah lewat backlog. Pakai sebagai kandidat gratis: fungsi yang sudah dikerjakan tapi belum terpeta, sering menyingkap anak tangga berikutnya.

## Gali ide

Pakai **Lensa adjacency** di `<skills-dir>/psm-develop/references/ecommerce-function-catalog.md` — lima arah berurut biaya: varian → kelengkapan alur → otomasi langkah manual → visibilitas → ketahanan & kepatuhan. Patuhi empat aturan pakainya di file itu (kaitkan ke bukti; sebut prasyarat; tandai yang menyentuh data existing; tawarkan 3–5, jangan borong). Bila skill `bmad-brainstorming` atau `bmad-advanced-elicitation` tersedia dan Budi ingin menggali lebih liar, pakai tekniknya — jangan menduplikasi metodenya di sini.

Yang membedakan penggalian di sini dari obrolan: **tiap ide dikaitkan ke bukti inventaris**. Sebut titik sisipnya (hook/ObjectModel/controller yang benar-benar ada), atau sebut eksplisit bahwa ia butuh titik sisip baru. Ide tanpa kaitan itu belum matang untuk masuk backlog — ia masih pertanyaan, dan tempatnya percakapan.

Jangan gali ulang yang sudah dijawab: ide berstatus `ditolak` di backlog sudah ditimbang dan dibuang beserta alasannya. Tawarkan lagi hanya bila alasan penolakannya sudah kedaluwarsa (mis. "butuh PS9" pada module yang kini menargetkan PS9) — dan katakan alasan itu saat menawarkannya.

Tulis tiap ide yang Budi setujui untuk disimpan:

`uv run scripts/ps-idea-backlog.py add --module-path <module-path> --key <slug> --status <baru|dipilih|ditolak> --arah <varian|kelengkapan|otomasi|visibilitas|ketahanan> [--prasyarat <key,key>] [--rencana "<nama fungsi>"] --catatan "<dampak bisnis + titik sisip>"`

Disiplin isi:

- **`--catatan` adalah nilai backlog ini.** Ide tanpa dampak bisnis dan titik sisip tak bisa dipilih tiga bulan lagi — ia jadi judul yang harus dipikirkan ulang dari nol. Untuk `ditolak`, alasan penolakannya yang ditulis.
- **`--prasyarat` menjaga tangga.** Bila ide berdiri di atas anak tangga yang belum ada, sebutkan key-nya; itu yang membuat `sync` menolak melompat diam-diam.
- **`--rencana` bila nama fungsi di rencana beda dari key.** Pencocokan ke rencana eksak — bukan fuzzy, supaya tak ada ide yang salah ditandai terwujud.
- **`--status dipilih` hanya untuk yang benar-benar diambil siklus ini.** Memilih semuanya sama dengan tak memilih apa pun.

## Tutup & serahkan

Tampilkan backlog terkini ke Budi (`list --module-path <module-path>` untuk bentuk JSON-nya) — ide `dipilih` di depan, sisanya sebagai peta jalan. Skill ini **tak pernah menyentuh file module dan tak menulis rencana**: satu-satunya file yang ditulisnya adalah `<module-path>/.psm-ideas.md` (plus `.memlog.md` di mode headless).

Tutup dengan menyarankan **psm-plan** atas ide berstatus `dipilih` — psm-plan yang menjalankan validasi rencana terhadap inventaris dan punya gerbang persetujuannya sendiri; teruskan key ide + catatannya sebagai maksud. Setelah rencana itu diterapkan psm-develop, jalankan `sync` lagi di sesi berikutnya agar statusnya naik ke `terwujud`.

Catat satu baris ke konteks module: `uv run <skills-dir>/psm-module-context/scripts/ps-module-context.py note --memory-dir {project-root}/_bmad/psm/memory --module <module> --by psm-ideate --type note --text "<satu baris>"` (auto-init bila belum ada). Satu entri per run — ini bukan laporan. Keputusan menolak sebuah ide beserta alasannya layak masuk `## Keputusan` lewat **psm-module-context**; backlog memegang statusnya, konteks memegang alasan yang mengikat lintas module.

## Mode headless

Saat dipanggil dengan `--headless` atau oleh workflow/agent lain: ambil module-path & maksud penggalian dari argumen alih-alih bertanya, dan jalankan alur normal tanpa gerbang interaktif. Karena operator tak hadir, tulis ide hasil inferensi dengan status `baru` — **jangan pernah `dipilih`**; memilih adalah keputusan Budi, dan backlog yang memilih sendiri akan menyeret psm-plan mengerjakan yang tak diminta. Catat tiap asumsi ke memlog via `uv run {project-root}/_bmad/scripts/memlog.py append --path <module-path>/.memlog.md` (init dulu bila belum ada): domain yang disimpulkan, ide yang ditulis, dan drift yang dikoreksi otomatis.

Tiga status akhir — satu field yang dibaca pemanggil (pemetaan BMad: `selesai`=`complete`, dua lainnya=`blocked`): **`selesai`** (backlog tersinkron & ide tertulis) menyertai ringkasan satu baris + path artefak backlog + path memlog + jumlah ide per status; **`gagal`** (tak terpulihkan — target bukan module, skrip error); **`butuh intervensi`** (drift `terwujud_tanpa_bukti`, atau backlog memuat marker rusak yang tak bisa dipulihkan tanpa keputusan). Dua status berhenti: kembalikan status + alasan satu baris + path memlog, lalu berhenti agar pemanggil memutuskan.
