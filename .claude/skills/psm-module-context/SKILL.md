---
name: psm-module-context
description: Rawat konteks per-module PrestaShop yang mengendap lintas sesi. Use when the user says "psm-module-context", "konteks module", "rekonsiliasi konteks module", or "catat konvensi module".
---

# psm-module-context

## Overview

Bertindak sebagai perawat memori per-module: operator (Budi) memutuskan apa yang layak diingat, skill memegang jalur tulis tunggal dan rekonsiliasi deterministik terhadap kode. Yang dirawat adalah lapis **tak-terderivasi** — kenapa keputusan diambil, tabel mana yang hidup di produksi, konvensi khusus module ini, riwayat validasi. Fakta terderivasi (hook, ObjectModel, file) tetap milik `ps-module-inventory.py`, segar tiap run; skill ini tak pernah menyalinnya. Hasil: **satu artefak per module di `<memory-dir>/projects/<module>.md`** yang mengendap lintas sesi dan direkonsiliasi terhadap bukti, sehingga tak ada workflow yang menurunkan ulang pemahaman module dari nol. Konsumen hasil: **psm-plan**, **psm-develop**, **psm-optimize**, **psm-validate**, **psm-cross-version**, **psm-scaffold**, dan **psm-agent-expert** sebagai kurator knowledge base.

## Resolution rules

- Bare paths dan `{skill-root}` resolve dari direktori instal skill ini.
- `{project-root}` → direktori kerja project.
- `<skills-dir>` → direktori yang memuat skill ini (tempat sibling psm-* berada, install-relative). Rujuk sibling lewat `<skills-dir>/psm-develop/…`, bukan `{project-root}/skills/…` — jangan bergantung pada mirror `skills/` di root project.
- `<memory-dir>` → `{project-root}/_bmad/psm/memory` (knowledge base bersama module psm).
- `<module-path>` → folder module yang dirawat, ditentukan di On Activation #2.

## On Activation

1. Muat config resolved via `uv run <skills-dir>/psm-setup/scripts/resolve-psm-config.py --project-root {project-root}` — JSON berisi `psm_modules_dir`, `communication_language`, dll. Baca apa adanya; jangan parse `config.yaml` sendiri.
2. Tentukan module dari permintaan Budi. Nama telanjang (mis. `psbanner`) di-resolve ke `<psm_modules_dir>/<nama>`; path lengkap dipakai apa adanya. Bila ambigu, tanya satu pertanyaan.
3. Jalankan `uv run <skills-dir>/psm-develop/scripts/ps-module-inventory.py <module-path>` → JSON inventaris. **Gerbang target:** bila folder hilang atau inventaris emit `looks_like_module: false`, arahkan Budi ke **psm-scaffold** dan berhenti; jangan merawat konteks atas ketiadaan. Bila skrip exit non-zero, tampilkan error apa adanya (headless: `gagal`).
4. Baca `<memory-dir>/projects/<module>.md` bila ada. Bila belum, `uv run scripts/ps-module-context.py init --memory-dir <memory-dir> --module <module> --source "<sumber seed>"` — kontrak marker & pembagian zona seksi ada di `--help` skrip; jangan menyusun format sendiri.

## Rekonsiliasi (deterministik)

`uv run scripts/ps-module-context.py reconcile --memory-dir <memory-dir> --module <module> --inventory <inventaris.json>` — cocokkan klaim di `## Fakta terkonsiliasi` dengan bukti inventaris. **rc=1 bukan status gagal skill ini**; itu justru hasil kerjanya. Tiga jenis drift, dua penanganan:

- **Jelas** — `live_but_missing` pada fakta yang memang sengaja dihapus, atau `claim_malformed`: koreksi langsung (`claim --status retired` / `drop`), lalu catat satu baris ke Jurnal. Tak perlu bertanya.
- **Ambigu, dan semua `retired_but_present`** — fakta yang sengaja absen tapi muncul lagi berarti sesuatu menghidupkannya kembali; itu keputusan manusia, bukan koreksi klerikal. Angkat sebagai pilihan singkat ke Budi (headless: `butuh intervensi`).

`uncovered` di output adalah informasi, bukan drift: konteks memang bukan cermin lengkap inventaris. Pakai untuk memilih apa yang layak diklaim, jangan diklaim borongan.

## Kurasi konvensi & keputusan

Zona prosa (`## Konvensi module`, `## Keputusan`) disunting **tangan** — tak ada subcommand untuknya; itu memang batasnya. Gali dari Budi lalu tulis padat:

- **Konvensi module** — namespace, layout service, prefix tabel, kesepakatan tim. Aturan tak-duplikasi: yang benar untuk **PrestaShop umum tak pernah ditulis di sini**, cukup rujuk `[[cross-version-patterns]]`, `[[persistence]]`, `[[services-di]]` di `tech/`. Yang masuk hanya yang khusus module ini.
- **Keputusan** — butir bertanggal `- YYYY-MM-DD — <keputusan>: <alasan>`. Alasannya yang bernilai; keputusan tanpa alasan sama tak bergunanya dengan tak dicatat.

Bila sesuatu bisa dibuktikan dari inventaris (hook/tabel/class/file), tempatnya **Fakta**, bukan prosa — pakai `claim`. Skrip menolak `--kind konvensi` justru supaya drift tak pernah lahir dari klaim yang tak punya cara diselesaikan.

Headless: infer konvensi dari inventaris + `git log` + `<module-path>/.psm-develop-plan.md` bila ada. Tiap inferensi dicatat sebagai asumsi ke memlog via `uv run {project-root}/_bmad/scripts/memlog.py append --path <module-path>/.memlog.md` (init dulu bila belum ada) — jangan tuliskan tebakan ke Konvensi/Keputusan seolah terkonfirmasi.

## Tutup sesi

Catat satu baris ke Jurnal: `uv run scripts/ps-module-context.py note --memory-dir <memory-dir> --module <module> --by psm-module-context --type note --text "<satu baris>"`. Ekor Jurnal adalah "di mana kita tadi" untuk sesi berikutnya — satu entri per run, bukan laporan. Tampilkan path artefak dan ringkas apa yang berubah.

## Mode headless

Saat dipanggil dengan `--headless` atau oleh workflow/agent lain: ambil module dari argumen alih-alih bertanya, dan jalankan alur normal tanpa gerbang interaktif.

Tiga status akhir — satu field yang dibaca pemanggil (pemetaan BMad: `selesai`=`complete`, dua lainnya=`blocked`): **`selesai`** (artefak terekonsiliasi & tertulis) menyertai ringkasan satu baris + path artefak + path memlog; **`gagal`** (tak terpulihkan — target bukan module, skrip error); **`butuh intervensi`** (drift ambigu atau `retired_but_present`). Dua status berhenti: kembalikan status + alasan satu baris + path memlog, lalu berhenti agar pemanggil memutuskan.
