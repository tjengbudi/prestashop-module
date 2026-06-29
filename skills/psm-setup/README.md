# PrestaShop Module Builder (`psm`)

Module BMad untuk membuat, mengembangkan, meng-cross-version-kan, memvalidasi, dan mengoptimasi module PrestaShop — dengan satu prinsip inti: **satu codebase yang jalan di PrestaShop 1.7.x, 8.x, dan 9.x sekaligus**, tanpa perubahan, siap dipakai siapa pun.

> Bukan upgrade satu arah. Bukan dua codebase. Satu module yang kompatibel ke atas **dan** tetap jalan di versi lawas.

---

## Apa isinya

Satu agent konsultan + lima workflow + satu setup skill, berbagi knowledge base PrestaShop yang hidup.

| Skill | Peran | Panggil saat |
|---|---|---|
| 🛒 **psm-agent-expert** | Agent hub: konsultan PrestaShop & e-commerce, pintu masuk + router | "tanya PrestaShop", "konsultasi module", bingung mulai dari mana |
| **psm-validate** | Validasi module di 1.7/8/9 (flashlight) + review adversarial e-commerce | "validasi module", "audit module", sebelum rilis |
| **psm-cross-version** | Buat module existing kompatibel 1.7/8/9 sekaligus | "buat module compatible 1.7 8 9", module lama mau jalan di versi baru |
| **psm-scaffold** | Bikin module PrestaShop baru cross-version dari nol | "bikin module baru" |
| **psm-develop** | Tambah fungsi e-commerce ke module existing tanpa regresi | "tambah fitur ke module", "kembangkan module" |
| **psm-optimize** | Percepat module via cache/service tanpa memecah kompatibilitas | "optimasi module", "percepat module" |
| **psm-setup** | Pasang & konfigurasi module ke project | "setup psm", sekali di awal |

---

## Instalasi & setup

1. **Pasang module** — jalankan setup skill:
   ```
   /psm-setup
   ```
   Setup akan menanyakan 4 nilai konfigurasi (semua punya default masuk akal — tekan terima saja bila cocok), mendaftarkan capability ke help system, dan membuat folder knowledge base `_bmad/psm/memory/`.

2. **Seed knowledge base** — jalankan agent sekali agar pengetahuannya terisi:
   ```
   /psm-agent-expert
   ```
   First run mengisi `_bmad/psm/memory/` dari riset & katalog yang sudah disiapkan: **9 file `tech/`** (breaking changes 8 & 9, pola cross-version, hooks, services-di, persistence, composer-structure, validator-rules, flashlight) + **3 file `ecommerce/`** (function-catalog, elicitation-lenses, adversarial-checks). Folder `projects/` terisi seiring kamu menggarap module. Lihat [Knowledge base](#knowledge-base) di bawah.

3. **Pastikan Docker ada** — uji `psm-validate` & `psm-optimize` berjalan di dalam container `prestashop/prestashop-flashlight`. Cek `docker --version`; image flashlight ditarik otomatis saat workflow uji pertama dijalankan, lalu di-cache lokal. Setiap tag versi ditarik terpisah sesuai `psm_flashlight_tag_map` (mis. `nightly` untuk 9.0 sudah cukup besar ±1.3 GB; tag `1.7.8.11` & `8.1` ditarik saat pertama kali menguji versi itu).

### Konfigurasi (config section `psm`)

| Key | Arti | Default |
|---|---|---|
| `psm_target_versions` | Versi PrestaShop target default | `1.7.8,8.1,9.0` |
| `psm_flashlight_tag_map` | Pemetaan versi → tag image flashlight | `1.7.8=1.7.8.11,8.1=8.1,9.0=nightly` |
| `psm_modules_dir` | Folder tempat module PrestaShop kamu | `{project-root}/modules` |
| `psm_reports_dir` | Output laporan validasi/optimasi | `{project-root}/_bmad-output/psm-validate` |

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

### Contoh end-to-end: cross-version module lama

Module `ps_banner` ditulis untuk 1.7, mau jalan di 8 & 9 sekaligus.

```
/psm-cross-version /home/budi/modules/ps_banner
```

1. **Analisis** — workflow memindai source terhadap `ps-rules.json`. Temuan contoh:
   - `Tools::jsonEncode(...)` → dihapus PS8 (error)
   - hook `actionAdminLoginControllerBefore` → dihapus PS9 (error)
   - variabel Smarty `{$title}` tak di-escape (warning)
2. **Rencana** — ditulis ke `.psm-cross-plan.md` di folder module: tiap temuan + perbaikan version-safe yang diusulkan (mis. ganti ke `json_encode` native; daftarkan hook dengan cabang `version_compare`).
3. **Konfirmasi** — kamu setujui/koreksi rencana. Tak ada yang diubah sebelum kamu OK.
4. **Terapkan** — patch source + tambah `ps_versions_compliancy` bila belum ada.
5. **Verifikasi** — otomatis memanggil `psm-validate`; module dipasang di flashlight 1.7.8 / 8.1 / 9.0. Laporan JSON per versi ke `psm_reports_dir`, status **lolos/gagal** + sisa temuan.

Hasil akhir: satu codebase `ps_banner` yang sama, lolos di tiga versi. Pakai git untuk membandingkan/membatalkan diff.

### Contoh: validasi cepat sebelum rilis

```
/psm-validate /home/budi/modules/ps_banner
```

Output: laporan per versi target — cek statis (API/hook/dependency dihapus, index.php, Smarty escaped, `ps_versions_compliancy`), hasil instalasi di core asli, dan temuan adversarial e-commerce (harga server-side? GDPR? multistore?). Tanpa Docker, cek statis tetap jalan; uji instalasi dilewati.

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

## Knowledge base

Pengetahuan PrestaShop yang sulit & berulang hidup di `_bmad/psm/memory/` — **milik bersama semua workflow psm**, dibaca tiap kali sebuah workflow butuh konteks lintas versi, dan dirawat oleh `psm-agent-expert`. Tujuannya: kamu tak perlu menjelaskan ulang standar yang sama.

```
_bmad/psm/memory/
  tech/         # pengetahuan teknis lintas versi
    breaking-changes-8.md     # API/kelas/konstanta dihapus di PS8
    breaking-changes-9.md     # dependency/hook/kelas dihapus di PS9
    cross-version-patterns.md # ringkasan pola version-safe + checklist
    hooks.md                  # registrasi & cabang versi hook
    services-di.md            # akses service/DI lintas versi
    persistence.md            # ObjectModel vs Doctrine, aturan tabel
    composer-structure.md     # composer.json, ps_versions_compliancy, struktur folder
    validator-rules.md        # ringkasan aturan Validator (rujuk ps-rules.json)
    flashlight.md             # lingkungan uji Docker + status tag lokal
  ecommerce/    # pengetahuan domain
    function-catalog.md       # peta fungsi e-commerce → hook → persistensi
    elicitation-lenses.md     # lensa menggali kebutuhan saat brainstorm
    adversarial-checks.md     # pertanyaan tajam mengkritik module sebelum matang
  projects/     # state per module yang digarap (<module>.md) — terisi seiring kerja
```

**Hidup, bukan statis.** Saat agent menemukan breaking change baru atau pola yang terbukti, dia menulis/memperbarui file yang relevan (riset devdocs via WebReader, catat sumber & tanggal). Setiap rilis PrestaShop baru memicu pembaruan `tech/breaking-changes-*.md`. Satu fakta per tempat yang jelas; bila katalog skill sudah lengkap, file memory merujuk ke sana alih-alih menyalin.

**Cara memakai:** jalankan `/psm-agent-expert` dan tanya apa saja — jawaban datang dari knowledge base ini (dan riset bila ada celah, lalu KB diperbarui). Kamu juga bisa membaca/menyunting file-nya langsung.

---

## Struktur

```
skills/
  psm-agent-expert/      # agent hub + 4 capability (references/)
  psm-validate/          # + ps-static-scan.py, ps-flashlight-run.py, ps-rules.json
  psm-cross-version/     # + references/version-safe-patterns.md
  psm-scaffold/          # + ps-scaffold.py (generator kerangka)
  psm-develop/           # + ps-module-inventory.py, references/ecommerce-function-catalog.md
  psm-optimize/          # + ps-hotspot-scan.py, references/optimization-catalog.md
  psm-setup/             # setup skill (module.yaml, module-help.csv, merge scripts)
  reports/
    prestashop-module-builder-plan.md   # rencana & riset lengkap

_bmad/psm/memory/        # knowledge base bersama → lihat section "Knowledge base"
  tech/  ecommerce/  projects/
```

---

## Troubleshooting

- **"Docker tidak tersedia"** saat validasi/optimasi → uji flashlight dilewati; validasi tetap jalan dengan aturan statis saja, tapi uji perilaku di core asli butuh Docker. Pasang Docker lalu ulangi.
- **Knowledge base kosong** (`_bmad/psm/memory/tech` & `ecommerce` tak ada isi) → jalankan `/psm-agent-expert` sekali untuk men-seed-nya dari riset & katalog.
- **Image flashlight lama diunduh** → image besar (GB); unduhan pertama per tag versi makan waktu, setelahnya di-cache lokal. Cek tag yang sudah ada: `docker images | grep flashlight`.
- **Uji versi tertentu dilewati** → tag untuk versi itu belum di-pull. Tarik manual sesuai `psm_flashlight_tag_map`, mis. `docker pull prestashop/prestashop-flashlight:1.7.8.11`.
- **Mau ubah versi target** → jalankan ulang `/psm-setup` atau sunting `psm_target_versions` di `_bmad/config.yaml`.
