# PrestaShop Module Builder (`psm`)

Module BMad untuk membuat, mengembangkan, meng-cross-version-kan, memvalidasi, dan mengoptimasi module PrestaShop — dengan satu prinsip inti: **satu codebase yang jalan di PrestaShop 1.7.x, 8.x, dan 9.x sekaligus**, tanpa perubahan, siap dipakai siapa pun.

> Bukan upgrade satu arah. Bukan dua codebase. Satu module yang kompatibel ke atas **dan** tetap jalan di versi lawas.

---

## Apa isinya

Satu agent konsultan + enam workflow + satu setup skill, berbagi knowledge base PrestaShop yang hidup.

| Skill | Peran | Panggil saat |
|---|---|---|
| 🛒 **psm-agent-expert** | Agent hub: konsultan PrestaShop & e-commerce, pintu masuk + router | "tanya PrestaShop", "konsultasi module", bingung mulai dari mana |
| **psm-validate** | Validasi module di 1.7/8/9 (flashlight) + review adversarial e-commerce | "validasi module", "audit module", sebelum rilis |
| **psm-cross-version** | Buat module existing kompatibel 1.7/8/9 sekaligus | "buat module compatible 1.7 8 9", module lama mau jalan di versi baru |
| **psm-scaffold** | Bikin module PrestaShop baru cross-version dari nol | "bikin module baru" |
| **psm-plan** | Rencanakan fungsi e-commerce module existing tanpa menerapkan; hasilnya dilanjutkan psm-develop | "rencanakan fungsi module", "buat rencana pengembangan module" |
| **psm-develop** | Tambah fungsi e-commerce ke module existing tanpa regresi | "tambah fitur ke module", "kembangkan module" |
| **psm-optimize** | Percepat module via cache/service tanpa memecah kompatibilitas | "optimasi module", "percepat module" |
| **psm-setup** | Pasang & konfigurasi module ke project | "setup psm", sekali di awal |

---

## Instalasi & setup

1. **Pasang module** — jalankan setup skill:
   ```
   /psm-setup
   ```
   Setup akan menanyakan 4 nilai konfigurasi (semua punya default masuk akal — balas "pakai default semua" bila cocok), mendaftarkan capability ke help system, dan membuat folder knowledge base `_bmad/psm/memory/`.

2. **Seed knowledge base** — jalankan agent sekali agar pengetahuannya terisi:
   ```
   /psm-agent-expert
   ```
   First run akan mengisi `_bmad/psm/memory/` dari riset & katalog yang sudah disiapkan.

3. **Pastikan Docker ada** — uji `psm-validate` & `psm-optimize` berjalan di dalam container `prestashop/prestashop-flashlight`. Cek `docker --version`; image flashlight ditarik otomatis saat workflow uji pertama dijalankan.

### Konfigurasi (config section `psm`)

| Key | Arti | Default |
|---|---|---|
| `psm_target_versions` | Versi PrestaShop target default | `1.7.8,8.1,9.1` |
| `psm_flashlight_tag_map` | Pemetaan versi → tag image flashlight | `1.7.8=1.7.8.11,8.1=8.1.6-nginx,9.1=9.1.4-nginx` |
| `psm_flashlight_orchestrator` | Cara flashlight menghidupkan DB+web: `auto`/`compose`/`manual` | `auto` |
| `psm_flashlight_db_image` | Image server DB (flashlight = web-tier saja, DB terpisah) | `mariadb:lts` |
| `psm_flashlight_ps_domain` | `PS_DOMAIN` container flashlight | `localhost:8000` |
| `psm_flashlight_startup_timeout` | Maks detik menunggu container `healthy` | `180` |
| `psm_e2e_enabled` | Gerbang uji browser E2E psm-validate (Lapis 4): `true`/`false` | `true` |
| `psm_e2e_browsers` | Engine Playwright untuk uji E2E, dipisah koma | `chromium,firefox` |
| `psm_modules_dir` | Folder tempat module PrestaShop kamu | `{project-root}/modules` |
| `psm_reports_dir` | Output laporan validasi/optimasi | `{project-root}/_bmad-output/psm-validate` |

> **Sumber kebenaran** daftar key & default di atas: `PSM_DEFAULTS` di `.claude/skills/psm-setup/scripts/resolve-psm-config.py` — resolver yang dibaca semua workflow psm saat runtime. Default yang juga dideklarasikan `module.yaml` psm-setup dijaga selaras oleh test anti-drift; key baru harus mendarat di resolver **dan** tabel ini.

Ubah kapan saja dengan menjalankan ulang `/psm-setup` atau menyunting `_bmad/config.yaml`.

---

## Cara pakai

### Lewat agent (disarankan)

Cara paling natural: ngobrol dengan **psm-agent-expert**. Dia menjawab pertanyaan teknis lintas versi, membantu brainstorm fungsi e-commerce, dan mengarahkan ke workflow yang tepat.

```
/psm-agent-expert
> "Module ps_banner-ku ditulis untuk 1.7, mau jalan juga di 8 dan 9. Bisa bantu?"
   → agent mengarahkan ke psm-cross-version

> "Hook displaySearch masih ada nggak di PrestaShop 9?"
   → agent menjawab dari knowledge base (dan riset bila perlu)

> "Aku mau bikin module loyalty point baru."
   → agent brainstorm fungsi, lalu mengarahkan ke psm-scaffold
```

### Langsung ke workflow

Bila sudah tahu mau apa, panggil workflow langsung dengan path module:

```
/psm-validate /home/budi/modules/ps_banner
/psm-cross-version /home/budi/modules/ps_banner
/psm-scaffold ps_newmodule
/psm-develop /home/budi/modules/ps_banner
/psm-optimize /home/budi/modules/ps_banner
```

---

## Alur kerja umum

**Module lama → cross-version → rilis**
```
psm-cross-version <module>   # analisis API berisiko → rencana → konfirmasi → terapkan
        ↓ (memanggil otomatis)
psm-validate <module>        # bukti lolos di 1.7.x + 8.x + 9.x
```

**Module baru dari ide**
```
psm-agent-expert             # brainstorm fungsi e-commerce
        ↓
psm-scaffold <nama>          # kerangka cross-version, lolos standar sejak awal
        ↓
psm-develop <module>         # tambah fungsi terpilih
        ↓
psm-validate <module>        # verifikasi
```

**Module lambat → cepat**
```
psm-optimize <module>        # profil (Blackfire/Xdebug) → rencana → terapkan
                             # verifikasi GANDA: kompatibilitas + metrik membaik
```

> **Pola keamanan:** semua workflow yang mengubah source (cross-version, develop, optimize) bekerja **rencana → konfirmasi → terapkan → verifikasi**. Perubahan tak diterapkan tanpa persetujuanmu, dan tak ada yang dinyatakan "selesai" sebelum lolos `psm-validate` di ketiga versi. Gunakan git untuk pembatalan.

---

## Apa yang membuat hasilnya akurat

- **Aturan kompatibilitas di-embed** — daftar API/hook/kelas/dependency yang dihapus per versi (PS8 & PS9) ada di `psm-validate/assets/ps-rules.json`, dari riset devdocs resmi. Validasi tak menebak.
- **Uji di PrestaShop core asli** — `psm-validate` & `psm-optimize` menjalankan tool terhadap PrestaShop sungguhan di flashlight per versi, bukan stub.
- **Pola version-safe** — katalog cara aman menjembatani legacy/modern (hook, controller, template, persistence, service) di `psm-cross-version/references/version-safe-patterns.md`.
- **Knowledge base hidup** — agent memperbarui pengetahuan saat menemukan breaking change/versi baru, jadi module makin pintar seiring waktu.

---

## Struktur

```
.claude/skills/          # pohon skill terpasang (live)
  psm-agent-expert/      # agent hub + 4 capability (references/)
  psm-validate/          # + ps-static-scan.py, ps-flashlight-run.py, uji E2E, ps-rules.json
  psm-cross-version/     # + references/version-safe-patterns.md
  psm-scaffold/          # + ps-scaffold.py (generator kerangka)
  psm-develop/           # + ps-module-inventory.py, references/ecommerce-function-catalog.md
  psm-optimize/          # + ps-hotspot-scan.py, references/optimization-catalog.md
  psm-setup/             # setup skill (module.yaml, merge scripts, resolver config runtime)

skills/reports/
  prestashop-module-builder-plan.md   # rencana & riset lengkap (sumber seed knowledge base)

_bmad/psm/memory/        # knowledge base bersama (dibuat saat setup, di-seed oleh agent)
  tech/                  # breaking changes, hooks, services, persistence, dll
  ecommerce/             # katalog fungsi, lensa elicitation, checklist adversarial
  projects/              # state per module yang dikerjakan
```

---

## Troubleshooting

- **"Docker tidak tersedia"** saat validasi/optimasi → uji flashlight dilewati; validasi tetap jalan dengan aturan statis saja, tapi uji perilaku di core asli butuh Docker. Pasang Docker lalu ulangi.
- **Knowledge base kosong** → jalankan `/psm-agent-expert` sekali untuk men-seed-nya.
- **Image flashlight lama diunduh** → image besar (GB); unduhan pertama per tag versi makan waktu, setelahnya di-cache lokal.
- **Mau ubah versi target** → jalankan ulang `/psm-setup` atau sunting `psm_target_versions` di `_bmad/config.yaml`.
- **Mau melewati uji browser E2E** → set `psm_e2e_enabled: 'false'` di section `psm` pada `_bmad/config.yaml` (atau batasi engine via `psm_e2e_browsers`).
