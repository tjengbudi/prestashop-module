---
name: psm-validate
description: Validasi kompatibilitas module PrestaShop 1.7/8/9 lewat pindai statis, uji flashlight, dan review adversarial. Use when the user says "psm-validate", "validasi module", "cek kompatibilitas module PrestaShop", or "audit module".
---

# psm-validate

## Overview

Bertindak sebagai validator module PrestaShop yang teliti dan jujur: operator (Budi) memegang module, skill memegang aturan kompatibilitas lintas versi dan prosedur ujinya. Hasilkan **vonis berbasis bukti** apakah sebuah module sehat di PrestaShop **1.7.x, 8.x, dan 9.x sekaligus** — tiga lapis: aturan deterministik yang diketahui pasti (skrip), perilaku nyata terhadap PrestaShop core asli di Docker flashlight, dan review adversarial e-commerce (judgment). Konsumen hasil: Budi (perbaiki sebelum rilis) dan workflow lain (psm-cross-version, psm-develop, psm-scaffold) yang memanggil skill ini sebagai gerbang mutu — jadi output harus JSON terstruktur yang dapat dibaca mesin, dengan ringkasan yang bisa ditindaklanjuti manusia. Tidak pernah meloloskan module yang masih memakai dependency terlarang PS9, hook yang dihapus, atau tanpa `ps_versions_compliancy`.

## Resolution rules

- Bare paths dan `{skill-root}` (mis. `assets/ps-rules.json`) resolve dari direktori instal skill ini.
- `{project-root}` → direktori kerja project.
- `psm-validate` → basename direktori skill.

## On Activation

1. Muat config resolved via `uv run {project-root}/skills/psm-setup/scripts/resolve-psm-config.py --project-root {project-root}` — JSON berisi `psm_target_versions`, `psm_flashlight_tag_map` (pemetaan tag), `psm_reports_dir` (folder laporan), `communication_language`, dll. Baca apa adanya; default kanonik sudah diterapkan resolver (jangan parse `config.yaml` sendiri).
2. Tentukan module yang divalidasi dari permintaan user (path folder). Bila ambigu, tanya satu pertanyaan: module mana dan versi target apa.
3. **Augment aturan bila knowledge base ada.** Bila `{project-root}/_bmad/psm/memory/tech/validator-rules.md` atau `tech/flashlight.md` ada, baca untuk aturan/tag tambahan di luar yang sudah di-embed di `assets/ps-rules.json`. Bila belum ada (module psm belum di-scaffold), lanjut tanpanya — aturan inti sudah di-embed.

## Validate

Jalankan tiga lapis pengujian, lalu satukan jadi vonis. Lapis deterministik dulu (cepat, selalu jalan); lapis flashlight bila Docker tersedia; lapis adversarial selalu (judgment-mu sendiri).

**Lapis 1 — pindai statis lintas versi (selalu).** Jalankan `uv run scripts/ps-static-scan.py <module-path> --versions <target>` (lihat `scripts/ps-static-scan.py --help`). Skrip mencocokkan ruleset di `assets/ps-rules.json` (dependency terlarang PS9, kelas/method/hook/konstanta dihapus, fungsi terlarang, `ps_versions_compliancy`, index.php, Smarty unescaped) ke source module dan mengeluarkan temuan JSON per versi dengan `pass`/`errors`/`warnings`. Ini sumber kebenaran untuk aturan yang diketahui pasti — jangan menilai ulang temuannya dengan tangan.

**Lapis 2 — uji di flashlight per versi (bila Docker ada).** Jalankan `uv run scripts/ps-flashlight-run.py <module-path> --versions <target>` (lihat `--help`). Skrip spin container `prestashop/prestashop-flashlight` per versi, install module via PrestaShop CLI, dan jalankan coding standard terhadap core asli. Bila Docker tak tersedia, skrip mengembalikan `status: skipped` — **degrade dengan jujur**: laporkan bahwa uji perilaku dilewati dan vonis hanya berdasar Lapis 1, jangan diam-diam mengklaim lolos penuh. Image flashlight besar; bila belum ada lokal, skrip **melewati versi itu** (degrade jujur, `skipped_image`) alih-alih menarik diam-diam. Dalam sesi interaktif, bila user memang mau uji perilaku, beri tahu unduhannya besar dan jalankan ulang dengan `--allow-image-pull` setelah konfirmasi.

**Lapis 3 — review adversarial e-commerce (judgment, kamu sendiri).** Skrip tidak bisa menilai ini. Baca source module dan cari risiko yang lolos dari aturan statis, dengan sikap skeptis seorang reviewer yang berasumsi ada yang salah. Bila `{project-root}/_bmad/psm/memory/ecommerce/adversarial-checks.md` ada, pakai sebagai checklist; bila tidak, pakai lensa inti: **keamanan transaksi** (validasi input order/pembayaran, SQL injection, CSRF, harga/diskon dimanipulasi sisi klien), **edge case cart/order/stock** (stok negatif, race saat checkout, mata uang/pajak/multistore, status order tak konsisten), **kompatibilitas lintas versi** (perilaku berbeda diam-diam antar 1.7/8/9 walau lolos statis), dan **performa** (query dalam loop, hook berat, tanpa cache). Tulis temuanmu sebagai JSON ke file sementara — bentuk `{"findings": [{"id", "severity": "error|warning", "message", "location", "fix", "versions": [versi terpengaruh pakai token yang sama dengan --versions, kosongkan bila semua target]}]}` — supaya skrip agregat memperlakukannya setara lapis lain.

## Vonis dan output

Serahkan penggabungan ke skrip; jangan rakit vonis dengan tangan. Jalankan `uv run scripts/ps-aggregate.py --static <static.json> --flashlight <flashlight.json> --adversarial <adv.json> -o <psm_reports_dir>/<module>-<timestamp>.json` (lewati `--flashlight` bila Lapis 2 tak dijalankan, `--adversarial` bila tak ada temuan). Skrip menghitung `pass` per versi dan keseluruhan dan menegakkan aturan jujurnya sendiri. Jangan menilai ulang atau menimpa `pass`, `conclusive`, atau `flashlight_conclusive` yang dikeluarkannya.

Untuk Budi, ringkas dalam percakapan dari JSON itu: per versi lolos/gagal, error yang memblok beserta fix-nya, dan warning yang sebaiknya ditangani. Bila `flashlight_conclusive` false, sebutkan eksplisit bahwa uji perilaku tak konklusif untuk versi terkait dan vonis bersandar pada lapis lain — jangan sembunyikan. Bila vonis keseluruhan gagal, tutup dengan satu tawaran langkah lanjut: serahkan error pemblokir ke psm-develop untuk diperbaiki, atau validasi ulang setelah dipatch. Untuk pemanggil workflow (headless), JSON itu cukup — jangan tambah prosa.

## Mode headless

Saat dipanggil workflow lain atau dengan `--headless`, lewati pertanyaan klarifikasi: ambil module-path & versi dari argumen/konteks, jalankan ketiga lapis, tulis JSON, dan kembalikan ringkasan satu baris + path JSON. Cocok sebagai gerbang CI: exit berdasarkan `pass` keseluruhan. Jalankan Lapis 2 **tanpa** `--allow-image-pull` — jangan pernah tarik image tanpa manusia, walau tak ada yang mengonfirmasi. Versi tanpa image lokal ter-`skipped_image` seperti biasa (vonis jatuh ke Lapis 1). Pemanggil yang memang mau menarik image harus meneruskan `--allow-image-pull` eksplisit.
