# PrestaShop Module Builder (`psm`)

Module BMad untuk membuat, mengembangkan, meng-cross-version-kan, memvalidasi, dan mengoptimasi module PrestaShop — satu codebase yang jalan di PrestaShop 1.7.x, 8.x, dan 9.x sekaligus.

📖 **Dokumentasi lengkap (sumber tunggal):** [`docs/psm/README.md`](docs/psm/README.md)
— konfigurasi, [cara pakai + alur kerja](docs/psm/README.md#cara-pakai), [referensi per skill](docs/psm/README.md#referensi-per-skill), [knowledge base](docs/psm/install.md#knowledge-base), dan troubleshooting. Panduan pasang dari nol: [`docs/psm/install.md`](docs/psm/install.md).

Mulai cepat:
1. Sambungkan harness ke pohon skill — **Claude Code** & **opencode** nol konfigurasi; **pi** butuh satu baris di `.pi/settings.json` ([langkah 4](docs/psm/install.md#4-sambungkan-harness-ke-pohon-skill))
2. `/psm-setup` — pasang & konfigurasi module
3. `/psm-agent-expert` — seed knowledge base (9 file `tech/` + 3 `ecommerce/`) & mulai berkonsultasi
4. Pastikan Docker terpasang untuk uji di `prestashop-flashlight`

> Sintaks perintah mengikuti harness: `/psm-setup` di Claude Code, `/skill:psm-setup` di pi.

## Sepuluh skill

| Skill | Fungsi | Panggil |
|---|---|---|
| 🛒 **psm-agent-expert** | Konsultan PrestaShop & e-commerce; pintu masuk + router ke workflow | `/psm-agent-expert` |
| **psm-setup** | Pasang & konfigurasi module ke project (sekali di awal) | `/psm-setup` |
| **psm-scaffold** | Bikin module baru cross-version dari nol, lolos standar sejak awal | `/psm-scaffold <nama>` |
| **psm-ideate** | Gali & rawat backlog ide untuk memperdalam module dalam domainnya sendiri | `/psm-ideate <module>` |
| **psm-plan** | Rencanakan fungsi tanpa menyentuh file; rencananya dilanjutkan psm-develop | `/psm-plan <module>` |
| **psm-develop** | Tambah fungsi e-commerce ke module existing tanpa regresi | `/psm-develop <module>` |
| **psm-cross-version** | Ubah module lama jadi satu codebase yang jalan di 1.7/8/9 | `/psm-cross-version <module>` |
| **psm-optimize** | Percepat module via cache/service tanpa memecah kompatibilitas | `/psm-optimize <module>` |
| **psm-validate** | Vonis berbasis bukti lewat 4 lapis (statis, flashlight, adversarial, E2E) | `/psm-validate <module>` |
| **psm-module-context** | Rawat konteks per-module lintas sesi + rekonsiliasi terhadap kode | `/psm-module-context <module>` |

Apa yang dihasilkan tiap skill, contoh pemakaian, dan kapan memanggilnya: [Referensi per skill](docs/psm/README.md#referensi-per-skill). Skill mana memanggil skill mana, skrip milik siapa dipakai siapa, dan artefak apa yang menjembatani keduanya: [Bagaimana skill saling memanggil](docs/psm/README.md#bagaimana-skill-saling-memanggil).

## Alur khas

```
Module baru       psm-scaffold → psm-develop → psm-validate
Module lama       psm-cross-version → psm-validate
Memperdalam       psm-ideate → psm-plan → psm-develop → psm-validate
Module lambat     psm-optimize (profil → terapkan → validate + metrik)
```

Tiap panah boleh jadi sesi terpisah — backlog dan artefak rencana bertahan lintas sesi. Semua workflow yang mengubah source bekerja **rencana → konfirmasi → terapkan → verifikasi**; tak ada yang disebut selesai sebelum `psm-validate` hijau di ketiga versi — dan vonis itu bukan penilaian mereka sendiri, melainkan JSON dari `psm-validate` yang dibaca apa adanya.

Skill-nya mengikuti Agent Skills open standard, jadi bukan cuma Claude Code: **opencode** membacanya tanpa konfigurasi apa pun dan **pi** lewat `.pi/settings.json` — detail & status **droid** di [Harness lain](docs/psm/README.md#harness-lain-opencode-pi-droid).
