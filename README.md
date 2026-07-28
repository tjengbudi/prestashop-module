# PrestaShop Module Builder (`psm`)

Module BMad untuk membuat, mengembangkan, meng-cross-version-kan, memvalidasi, dan mengoptimasi module PrestaShop — satu codebase yang jalan di PrestaShop 1.7.x, 8.x, dan 9.x sekaligus.

📖 **Dokumentasi lengkap (sumber tunggal):** [`docs/psm/README.md`](docs/psm/README.md)
— konfigurasi, [cara pakai + alur kerja](docs/psm/README.md#cara-pakai), [knowledge base](docs/psm/install.md#knowledge-base), dan troubleshooting. Panduan pasang dari nol: [`docs/psm/install.md`](docs/psm/install.md).

Mulai cepat:
1. Sambungkan harness ke pohon skill — **Claude Code** & **opencode** nol konfigurasi; **pi** butuh satu baris di `.pi/settings.json` ([langkah 4](docs/psm/install.md#4-sambungkan-harness-ke-pohon-skill))
2. `/psm-setup` — pasang & konfigurasi module
3. `/psm-agent-expert` — seed knowledge base (9 file `tech/` + 3 `ecommerce/`) & mulai berkonsultasi
4. Pastikan Docker terpasang untuk uji di `prestashop-flashlight`

> Sintaks perintah mengikuti harness: `/psm-setup` di Claude Code, `/skill:psm-setup` di pi.

Delapan skill: **psm-agent-expert** (agent hub) + enam workflow (**validate**, **cross-version**, **scaffold**, **plan**, **develop**, **optimize**) + **psm-setup**. Satu codebase module, lolos di 1.7.x / 8.x / 9.x.

Skill-nya mengikuti Agent Skills open standard, jadi bukan cuma Claude Code: **opencode** membacanya tanpa konfigurasi apa pun dan **pi** lewat `.pi/settings.json` — detail & status **droid** di [Harness lain](docs/psm/README.md#harness-lain-opencode-pi-droid).
