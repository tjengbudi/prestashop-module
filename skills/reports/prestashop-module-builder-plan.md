---
title: 'PrestaShop Module Builder — Plan'
status: 'complete'
module_name: 'PrestaShop Module Builder'
module_code: 'psm'
module_description: 'Bikin, kembangkan, buat cross-version (1.7/8/9), validasi, dan optimasi module PrestaShop dengan standar baku & uji flashlight.'
architecture: 'hybrid: 1 agent expert + 5 workflow (cross-version, scaffold, develop, validate, optimize) + shared knowledge base'
standalone: true
expands_module: ''
skills_planned: ['psm-agent-expert', 'psm-cross-version', 'psm-scaffold', 'psm-develop', 'psm-validate', 'psm-optimize']
config_variables: ['psm_target_versions', 'psm_flashlight_tag_map', 'psm_modules_dir', 'psm_reports_dir']
created: '2026-06-25'
updated: '2026-06-25'
---

# Module Plan

## Vision

**PrestaShop Module Builder (psm)** menangkap pengetahuan PrestaShop yang sulit & berulang menjadi standar baku, supaya Budi tak perlu menjelaskan kebutuhan yang sama setiap kali. Inti pembedanya: **satu codebase module yang jalan di PrestaShop 1.7.x, 8.x, dan 9.x sekaligus** (cross-version, bukan upgrade satu arah) — praktis dipakai orang lain tanpa perubahan lagi.

Module ini melayani Budi sebagai developer module PrestaShop, dengan empat kerja utama: **cross-version** module existing (prioritas — store punya banyak module perlu dikompatibelkan), **scaffold** module baru cross-version dari awal, **validasi** terhadap 1.7/8/9 + coding standard, dan **optimasi performa** (manfaatkan cache & service container PrestaShop). Lebih dari generator kode: agent-nya juga **partner ide e-commerce** yang menggali kebutuhan (advanced elicitation) dan mengkritik secara adversarial sebelum module dianggap matang. Semua uji dibakukan di Docker **prestashop-flashlight**.

Pengetahuan teknis (breaking change versi, hooks, services, Doctrine/ObjectModel, composer, aturan Validator) dan domain (katalog fungsi e-commerce) hidup di **knowledge base bersama** yang bisa diperbarui agent seiring waktu.

## Architecture

**Hybrid: 1 agent expert (pintu masuk) + 4 workflow + knowledge base bersama.**

- **psm-agent-expert** — agent "PrestaShop Module Expert", konsultan e-commerce + ahli teknis PrestaShop. Pintu masuk obrolan: Budi minta bikin/cross-version/validasi/optimasi, agent menjawab pertanyaan teknis, brainstorm fungsi e-commerce, dan **me-route ke workflow** yang tepat. Pegang & rawat knowledge base.
- **psm-cross-version** (workflow, prioritas #1) — module existing → analisis API dipakai → deteksi yang pecah di 8/9 → terapkan pola version-safe → panggil validasi flashlight 1.7/8/9.
- **psm-scaffold** (workflow) — module baru cross-version dari awal (composer/autoload, struktur file, ps_versions_compliancy, boilerplate hook/install) lolos standar + siap uji.
- **psm-develop** (workflow) — menambah/mengembangkan fungsi ke module yang **sudah ada**: pahami struktur eksisting → sisipkan fungsi baru (hook/service/entity) dengan pola cross-version tanpa memecah yang lama → panggil validasi. Agent brainstorm fungsi e-commerce lebih dulu, lalu route ke sini.
- **psm-validate** (workflow, berdiri sendiri & dipanggil yang lain) — validasi terhadap **ketiga versi** di flashlight: PHPStan lvl5, coding standard, cek dependency terlarang PS9, hook dihapus, Smarty escaped, index.php, dll. **+ review adversarial e-commerce** (cek kritis: keamanan transaksi, edge case order/cart/stock, kompatibilitas, performa). Output: laporan HTML per versi.
- **psm-optimize** (workflow) — profil module → peluang cache/service → terapkan → verifikasi di flashlight.

**Rationale:** Budi solo developer → satu agent percakapan sebagai hub terasa paling natural untuk brainstorming & tanya-jawab. Tapi kerja berat (cross-version, develop fitur, validasi 3 versi, optimasi) bersifat multi-langkah & butuh hasil yang dapat diprediksi → workflow. Pemisahan tujuan workflow tegas: **scaffold** = module baru kosong, **develop** = tambah fitur ke module berisi, **cross-version** = kompatibilitas lintas versi, **validate** = bukti sehat, **optimize** = performa. Validate berdiri sendiri karena metodenya menguji **ketiga versi** (bukan satu) dan sering dipanggil ulang (fleksibel), sekaligus jadi sub-langkah wajib di cross-version. Knowledge base dipisah dari logika skill supaya bisa tumbuh tanpa mengubah skill.

### Memory Architecture

**Single shared knowledge base** di folder memory module — dibaca semua skill, ditulis/diperbarui agent (knowledge "hidup"). Plus personal memory agent untuk preferensi Budi & log pekerjaan.

Struktur folder (final disempurnakan di Fase 7):

```
_bmad/psm/memory/
  tech/
    breaking-changes-8.md      # breaking change PS8 (kelas/method/hook dihapus, Symfony 4.4, Twig3)
    breaking-changes-9.md      # breaking change PS9 (Symfony 6.4, PHP8.1, dependency dihapus, context split)
    cross-version-patterns.md  # pola version-safe: deteksi versi, legacy vs modern (hook/controller/template/persistence/service)
    hooks.md                   # registrasi/eksekusi/trigger hook lintas versi
    services-di.md             # service container, override vs decorate, container per konteks
    persistence.md             # ObjectModel vs Doctrine, kapan pakai yang mana
    composer-structure.md      # composer.json baku, autoload, struktur file module
    validator-rules.md         # aturan PrestaShop Validator + coding standard + PHPStan
    flashlight.md              # cara pakai flashlight: tag versi, ENV, compose, install module
  ecommerce/
    function-catalog.md        # KATALOG fungsi e-commerce lengkap (konversi/retensi/katalog/checkout/SEO/marketing/analytics/multistore/GDPR)
    elicitation-lenses.md      # lensa advanced-elicitation untuk e-commerce (konversi, AOV, retensi, dst)
    adversarial-checks.md      # checklist review adversarial e-commerce (keamanan transaksi, edge case order/cart/stock, dst)
  projects/                    # state per module yang sedang dikerjakan Budi (target versi, status, temuan)
```

### Memory Contract

- **tech/\*.md** — Ditulis awal dari hasil riset di plan ini (knowledge sudah terkumpul). Dibaca semua workflow + agent. Diperbarui agent saat menemukan breaking change/versi baru (riset devdocs via WebReader). Sumber kebenaran teknis lintas versi.
- **ecommerce/function-catalog.md** — Dibaca agent saat brainstorm/scaffold untuk menawarkan fungsi relevan. Dibaca psm-scaffold. Diperbarui agent saat menemukan pola e-commerce baru.
- **ecommerce/elicitation-lenses.md** — Dibaca agent saat menggali kebutuhan module (capability elicitation).
- **ecommerce/adversarial-checks.md** — Dibaca psm-validate (langkah review adversarial) + agent.
- **projects/&lt;module&gt;.md** — Ditulis semua workflow saat mengerjakan sebuah module (target versi, API berisiko, hasil validasi per versi, optimasi diterapkan). Dibaca agent untuk konteks "di mana kita tadi". Memungkinkan resume lintas sesi.

### Cross-Agent Patterns

- **Agent = router & konsultan.** Budi ngobrol dengan psm-agent-expert; agent memutuskan workflow mana yang dipanggil dan menyiapkan konteks (baca `projects/<module>.md`).
- **psm-cross-version memanggil psm-validate** sebagai sub-langkah wajib (validasi 3 versi setelah perubahan).
- **psm-scaffold** & **psm-develop** membaca `ecommerce/function-catalog.md` agar module bisa langsung menawarkan fungsi relevan; keduanya memanggil **psm-validate** setelah selesai.
- **psm-develop** lebih dulu memetakan struktur module existing (baca `projects/<module>.md` bila ada) agar penambahan fungsi tidak memecah yang lama.
- **Knowledge base bersama** = mekanisme koordinasi: semua skill baca `tech/` yang sama, jadi standar konsisten tanpa duplikasi. Agent satu-satunya penulis utama `tech/` & `ecommerce/` (kurasi), workflow menulis `projects/`.

## Skills

### psm-agent-expert

**Type:** agent

**Persona:** "PrestaShop Module Expert" — konsultan e-commerce senior + ahli teknis PrestaShop yang sudah lama mengarungi 1.6→1.7→8→9. Bicara santai tapi tajam, proaktif menawarkan ide bisnis, jujur soal risiko teknis. Bahasa: Indonesia (komunikasi), output dokumen sesuai konfigurasi.

**Core Outcome:** Budi merasa punya partner yang paham PrestaShop luar-dalam — tak perlu menjelaskan ulang standar, dapat ide fungsi e-commerce yang relevan, dan diarahkan ke aksi (workflow) yang tepat.

**The Non-Negotiable:** Selalu sadar konteks cross-version (1.7/8/9) — tak pernah menyarankan API yang pecah di salah satu versi target tanpa memberi tahu.

**Capabilities:**

| Capability | Outcome | Inputs | Outputs |
| ---------- | ------- | ------ | ------- |
| Tanya-jawab teknis PrestaShop | Jawaban akurat lintas versi dari knowledge base | Pertanyaan Budi | Penjelasan + rujukan tech/*.md |
| Brainstorm fungsi e-commerce (advanced elicitation) | Daftar fungsi relevan + dampak bisnis, digali dengan lensa e-commerce | Ide/domain module | Daftar fungsi terprioritas (konversi/retensi/dll) |
| Route ke workflow | Workflow tepat dipanggil dengan konteks siap | Maksud Budi ("upgrade X", "bikin baru") | Pemanggilan psm-cross-version/scaffold/validate/optimize |
| Rawat knowledge base | tech/ & ecommerce/ tetap mutakhir | Temuan baru / versi PS baru | Update file memory (riset via WebReader) |

**Memory:** Baca semua `tech/`, `ecommerce/`, dan `projects/<module>.md` aktif saat aktivasi. Tulis ke `tech/`, `ecommerce/` (kurasi knowledge) & personal memory (preferensi Budi).

**Init Responsibility:** First run — buat struktur knowledge base, seed `tech/*.md` dari riset plan ini, seed `ecommerce/function-catalog.md`. Cek dependency Docker + image flashlight (lihat External Dependencies), bantu setup bila belum ada.

**Activation Modes:** Interaktif (utama). 

**Tool Dependencies:** WebReader/web search (riset devdocs), Docker (cek flashlight). Memanggil workflow lain.

**Design Notes:** Agent adalah satu-satunya penulis kurasi knowledge teknis & e-commerce agar konsisten. Elicitation memakai teknik bmad-advanced-elicitation tapi dengan lensa e-commerce (`ecommerce/elicitation-lenses.md`).

---

### psm-cross-version

**Type:** workflow

**Core Outcome:** Satu module existing menjadi kompatibel 1.7.x + 8.x + 9.x tanpa pecah, terverifikasi di flashlight.

**The Non-Negotiable:** Tidak menandai "selesai" sebelum lolos psm-validate di ketiga versi target.

**Capabilities:**

| Capability | Outcome | Inputs | Outputs |
| ---------- | ------- | ------ | ------- |
| Analisis API module | Peta API/hook/class yang dipakai + mana yang berisiko per versi | Path module + versi target | Laporan risiko per versi |
| Terapkan pola version-safe | Kode bercabang legacy/modern aman lintas versi | Laporan risiko + knowledge cross-version-patterns | Module termodifikasi |
| Validasi (panggil psm-validate) | Bukti lolos 3 versi | Module termodifikasi | Laporan validasi |

**Memory:** Baca `tech/*`. Tulis `projects/<module>.md` (API berisiko, perubahan, status).

**Activation Modes:** Interaktif + headless.

**Design Notes:** Pakai deteksi `_PS_VERSION_`/`version_compare`, `module-lib-service-container`, hindari dependency yang dihapus PS9.

---

### psm-scaffold

**Type:** workflow

**Core Outcome:** Module PrestaShop baru yang dari awal cross-version, lolos standar, siap diisi fungsi e-commerce.

**The Non-Negotiable:** composer.json benar (`prepend-autoloader: false`), `ps_versions_compliancy` terisi, index.php di tiap folder, struktur file baku.

**Capabilities:**

| Capability | Outcome | Inputs | Outputs |
| ---------- | ------- | ------ | ------- |
| Generate kerangka module | Struktur folder + main file + composer + autoload | Nama/namespace/versi target | Module kerangka siap pakai |
| Tawarkan fungsi e-commerce | Module mulai dengan fungsi relevan terpilih | Domain module + function-catalog | Hook/boilerplate fungsi terpilih |
| Validasi awal (panggil psm-validate) | Kerangka lolos standar dari awal | Module kerangka | Laporan validasi |

**Memory:** Baca `tech/composer-structure`, `tech/cross-version-patterns`, `ecommerce/function-catalog`. Tulis `projects/<module>.md`.

**Activation Modes:** Interaktif + headless.

---

### psm-develop

**Type:** workflow

**Core Outcome:** Module yang sudah ada bertambah fungsi baru yang relevan e-commerce, terpasang dengan pola cross-version, tanpa memecah fungsi lama.

**The Non-Negotiable:** Memahami struktur module existing lebih dulu; perubahan harus tetap lolos psm-validate di 3 versi.

**Capabilities:**

| Capability | Outcome | Inputs | Outputs |
| ---------- | ------- | ------ | ------- |
| Petakan module existing | Pemahaman struktur (hook, service, entity, controller) module saat ini | Path module | Peta struktur module |
| Implementasi fungsi baru | Fungsi e-commerce terpilih tertanam cross-version | Peta + fungsi terpilih (dari brainstorm agent) + function-catalog | Module dengan fitur baru |
| Validasi (panggil psm-validate) | Bukti fitur baru tak memecah apa pun di 3 versi | Module termodifikasi | Laporan validasi |

**Memory:** Baca `tech/*`, `ecommerce/function-catalog`. Baca/tulis `projects/<module>.md`.

**Activation Modes:** Interaktif + headless.

**Design Notes:** Beda dari scaffold — scaffold bikin kerangka kosong, develop menyisipkan fitur ke module berisi. Sering dipanggil agent setelah sesi brainstorm fungsi e-commerce.

---

### psm-validate

**Type:** workflow

**Core Outcome:** Bukti objektif sebuah module sehat di 1.7.x + 8.x + 9.x — teknis maupun kualitas e-commerce.

**The Non-Negotiable:** Menguji **ketiga versi** (bukan satu) di flashlight; tidak meloloskan module dengan dependency terlarang PS9 atau hook yang dihapus.

**Capabilities:**

| Capability | Outcome | Inputs | Outputs |
| ---------- | ------- | ------ | ------- |
| Uji statis lintas versi | Hasil PHPStan lvl5 + coding standard + cek aturan Validator | Path module + versi target | Temuan per versi |
| Uji instalasi flashlight | Module terpasang & jalan di tiap versi | Module zip + flashlight | Status install per versi |
| Review adversarial e-commerce | Daftar risiko kritis (keamanan transaksi, edge case cart/order/stock, kompatibilitas, performa) | Module + adversarial-checks | Temuan adversarial |
| Laporan gabungan | Ringkasan lolos/gagal yang mudah dibaca | Semua temuan | **Laporan HTML** per versi + ringkasan |

**Memory:** Baca `tech/validator-rules`, `tech/flashlight`, `ecommerce/adversarial-checks`. Tulis hasil ke `projects/<module>.md`.

**Activation Modes:** Interaktif + headless (cocok untuk CI).

**Tool Dependencies:** Docker + flashlight (tag per versi), PHPStan, coding standard tools. Web Validator opsional manual (butuh login seller).

**Design Notes:** Output HTML report kandidat kuat (hasil validasi multi-versi). Review adversarial mengadopsi bmad-review-adversarial-general dengan lensa e-commerce.

---

### psm-optimize

**Type:** workflow

**Core Outcome:** Module memakai cache & service container PrestaShop untuk performa/integrasi lebih baik, terverifikasi tidak merusak fungsi.

**The Non-Negotiable:** Optimasi tidak boleh memecah kompatibilitas lintas versi — verifikasi ulang via psm-validate.

**Capabilities:**

| Capability | Outcome | Inputs | Outputs |
| ---------- | ------- | ------ | ------- |
| Profil module | Titik lambat / query berulang teridentifikasi | Path module (+ Blackfire/Xdebug flashlight) | Laporan profil |
| Identifikasi peluang cache/service | Rekomendasi konkret (Cache::clean, Configuration batch, decorate service) | Laporan profil + tech/services-di, persistence | Daftar rekomendasi |
| Terapkan & verifikasi | Optimasi diterapkan, lolos validasi | Rekomendasi disetujui | Module teroptimasi + laporan |

**Memory:** Baca `tech/services-di`, `tech/persistence`, `tech/flashlight`. Tulis `projects/<module>.md`.

**Activation Modes:** Interaktif.

**Design Notes:** Manfaatkan Blackfire/Xdebug yang sudah ada di flashlight (ENV `BLACKFIRE_ENABLED`/`XDEBUG_ENABLED`).

---

## Configuration

| Variable | Prompt | Default | Result Template | User Setting |
| -------- | ------ | ------- | --------------- | ------------ |
| psm_target_versions | Versi PrestaShop target default untuk cross-version & validasi? | `1.7.8,8.1,9.0` | `{value}` | No |
| psm_flashlight_tag_map | Pemetaan versi→tag image flashlight | `1.7.8=1.7.8.11, 8.1=8.1, 9.0=nightly` | `{value}` | No |
| psm_modules_dir | Folder tempat module PrestaShop Budi berada | `{project-root}/modules` | `{value}` | No |
| psm_reports_dir | Output laporan validasi/optimasi (HTML) | `{bmad_builder_reports}/psm` | `{value}` | No |

## External Dependencies

- **Docker** — wajib untuk menjalankan flashlight. Agent cek ketersediaan (`docker --version`) saat init; bila tak ada, beri panduan instalasi (tidak menginstal otomatis).
- **prestashop/prestashop-flashlight** (Docker Hub image) — lingkungan uji. Agent bantu pull image per tag target & siapkan `docker-compose.yml` (flashlight + MySQL). ENV kunci: `INSTALL_MODULES_DIR`, `PS_DOMAIN`, `XDEBUG_ENABLED`, `BLACKFIRE_ENABLED`, `ON_INSTALL_MODULES_FAILURE=continue`.
- **PHPStan + PrestaShop coding standard tools** — untuk psm-validate. Dijalankan di dalam container flashlight (use case resmi "Validate a module with the PrestaShop coding standard").
- **Composer** — untuk scaffold (`composer dump-autoload`).
- **WebReader / web search** — agent riset devdocs untuk memperbarui knowledge base (gunakan WebReader, bukan WebFetch — lebih lengkap untuk devdocs).

## UI and Visualization

- **Laporan HTML validasi** (psm-validate) — ringkasan lolos/gagal per versi (1.7/8/9), temuan statis, hasil instalasi, temuan adversarial e-commerce. Disimpan di `psm_reports_dir`.
- **Laporan HTML profil/optimasi** (psm-optimize) — sebelum/sesudah, rekomendasi diterapkan.

## Setup Extensions

- Setup skill (psm-setup) selain config: buat folder knowledge base & seed `tech/*.md` + `ecommerce/function-catalog.md` dari knowledge plan ini; buat `psm_reports_dir`; siapkan `docker-compose.yml` contoh untuk flashlight; cek Docker.

## Integration

**Standalone** — memberi nilai mandiri penuh (bikin/cross-version/validasi/optimasi module PrestaShop) tanpa module BMad lain. Mengadopsi *teknik* dari bmad-advanced-elicitation & bmad-review-adversarial-general (di-embed/dikhususkan e-commerce), bukan ketergantungan keras. Calon kerabat masa depan: module **PrestaShop Server Optimizer** (lihat Ideas Captured) yang bisa berbagi knowledge base PrestaShop inti.

## Creative Use Cases

- **Audit borongan store:** jalankan psm-validate headless atas semua module di `psm_modules_dir`, hasilkan satu dasbor HTML "module mana siap 9.0".
- **CI gate:** psm-validate di pipeline — module tak boleh rilis sebelum lolos 3 versi.
- **Idea-to-module:** brainstorm fungsi e-commerce dengan agent → psm-scaffold (baru) atau psm-develop (existing) dengan fungsi terpilih → psm-validate.
- **Knowledge yang tumbuh:** tiap rilis PrestaShop baru, minta agent riset devdocs & perbarui `tech/breaking-changes-*.md` — module makin pintar seiring waktu.
- **Belajar:** tanya agent "kenapa hook X hilang di 9 dan apa gantinya" — knowledge base jadi bahan ajar lintas versi.

## Ideas Captured

<!-- Raw ideas from brainstorming — preserved for context even if not all made it into the plan -->

### Spark (sesi awal, 2026-06-25)

- **Inti:** module BMad yang mendefinisikan alur jelas + standar baku untuk membuat module PrestaShop, supaya Budi tidak perlu menjelaskan kebutuhan yang sama berulang-ulang setiap kali bikin module.
- **Kebutuhan minimum sebuah module PrestaShop** harus terdokumentasi sebagai standar: struktur file, framework, testing, dll.
- **Perbedaan versi adalah masalah utama:** struktur file & konvensi berbeda antara PrestaShop **1.7.x, 8.x, dan 9.x**. Module builder harus version-aware.
- **Pengetahuan yang harus dibakukan:** framework apa yang dipakai PrestaShop (Symfony components, legacy controllers, dll), tool testing apa yang digunakan, struktur folder, hook system, dll.
- **Pengguna:** Budi sendiri, sebagai developer module PrestaShop.

### Motivasi nyata

- Budi punya **store dengan banyak module yang perlu di-upgrade**. Harapannya BMB + BMAD method membantu menyelesaikan upgrade massal ini.
- Alur kerja: **upgrade module lama dulu** → setelah terbantu BMAD, lanjut **kembangkan/develop module** tersebut lebih jauh.
- Jadi ada dua mode kerja: (1) **upgrade/migrasi** module existing antar versi, (2) **pengembangan** fitur baru.

### Standar pengecekan & lingkungan uji

- Ingin standar pengecekan pakai **Docker `prestashop/prestashop-flashlight`** (bukan image PrestaShop resmi) — alasannya lebih ringan/mudah untuk testing cepat.
- Tujuan lingkungan uji: agar **framework PrestaShop dikenali dengan baik** sehingga eksplorasi (oleh agent/workflow) maksimal.
- Contoh kasus konkret: **cache PrestaShop** — module yang dikembangkan bisa memanfaatkan/extend mekanisme cache PrestaShop. Jadi standar harus paham API internal seperti cache.

### Tema yang muncul (untuk digali lebih lanjut)

- Tegangan inti: **menangkap pengetahuan domain PrestaShop sekali**, lalu pakai berulang — ini lebih dari sekadar scaffolding.
- Kemungkinan komponen: (a) knowledge base/standar version-aware, (b) workflow scaffold module baru, (c) workflow upgrade/migrasi module antar versi, (d) lingkungan uji flashlight terstandar, (e) explorer yang memetakan API internal PrestaShop (cache, hooks, services).
- Pertanyaan terbuka: apakah ini satu agent dengan banyak capability, beberapa agent (mis. "Architect" vs "Migrator"), atau campuran agent + workflow?

### Klarifikasi tujuan (putaran 2, 2026-06-25)

- **BUKAN "naik versi", tapi "cross-version compatible"**: satu codebase module yang jalan di 1.7.x + 8.x + 9.x sekaligus, tanpa perubahan, supaya praktis dipakai orang lain.
- Sumber masalah: banyak module Budi awalnya ditulis untuk PrestaShop < 1.7, "dipaksa" jalan di 1.7.x. Target sekarang: bikin kompatibel ke atas (8.x, 9.x) tapi tetap jalan di 1.7.x.
- Penyebab kerusakan utama: **perubahan framework** (detail Budi belum kuasai → AI yang harus riset detail).
- Budi minta eksplisit: **AI yang riset detail** apa yang berubah & apa yang bisa dibakukan, lalu **tawarkan (offer)** ke Budi — bukan Budi yang harus tahu duluan.

### Temuan riset awal (sumber resmi, untuk grounding standar)

**Garis patahan framework lintas versi (yang bikin module rusak):**
- **Symfony**: 1.7 memindahkan PrestaShop ke Symfony; versi Symfony berbeda tiap rilis (8.x vs 9.x beda major Symfony) → namespace, service container, autoload berubah.
- **Hooks**: ada "Symfony bridge for hooks" + "hooks on modern pages" — perilaku hook beda di legacy vs modern controller.
- **Controllers**: Legacy Controllers vs Symfony controllers & routing hidup berdampingan; module lintas versi harus pilih jalur yang aman.
- **Persistence**: ObjectModel (legacy) vs Doctrine (modern).
- **Templating**: Smarty (legacy) vs Twig/Vue.js (modern back office).
- **Cache**: ada layer cache arsitektural yang bisa dimanfaatkan module.

**Aset resmi yang sangat relevan dengan tujuan cross-version:**
- `prestashop/module-lib-service-container` — library RESMI PrestaShop untuk service container yang kompatibel lintas versi module. (kandidat standar baku!)
- **PrestaShop Validator** (validator.prestashop.com) — tool validasi resmi; `ps_versions_compliancy` kini WAJIB. Ini deklarasi rentang versi yang didukung module → langsung relevan "compatible 1.7/8/9".
- **prestashop-flashlight** — resmi diposisikan sebagai dev environment + CI/CD asset untuk testing module cepat. (sesuai keinginan Budi)
- `composer.json` + autoload jadi mekanisme utama dependency/namespace sejak 1.7.

**Implikasi untuk standar baku yang bisa di-"offer":**
1. Template `composer.json` + autoload PSR-4 standar.
2. `ps_versions_compliancy` + deklarasi versi di main module file.
3. Pola "version-safe": deteksi versi PrestaShop saat runtime, pilih jalur legacy/modern (hook, controller, template, persistence).
4. Adopsi `module-lib-service-container` untuk service injection lintas versi.
5. Pipeline test standar di flashlight (versi 1.7.x, 8.x, 9.x).
6. Checklist lolos PrestaShop Validator.

**Sumber:** devdocs.prestashop-project.org (concepts, composer, flashlight, testing), validator.prestashop.com/changelog, github.com/PrestaShop/prestashop-flashlight, github.com/PrestaShopCorp/module-lib-service-container.

### Fokus eksplorasi yang dikonfirmasi Budi

- Manfaatkan framework PrestaShop (Symfony, cache, services) untuk **performa lebih baik & integrasi lebih baik** pada module yang dikembangkan.
- Penggunaan utama module ini: (a) **membuat** module PrestaShop baru, (b) **upgrade/cross-version** module existing, (c) **menambah fungsi** ke module, (d) **optimasi performa** module.
- Flashlight dipakai terutama untuk **validasi module** (bukan sekadar eksplorasi source).

### Ide ditahan untuk nanti (diputuskan kemudian)

- **Agent "PrestaShop Server Optimizer"** — agent terpisah untuk optimasi server PrestaShop (infra: PHP-FPM, MySQL/MariaDB, OPcache, Nginx, Redis, CDN), BUKAN kode module. Budi ragu antara project terpisah vs include. Keputusan: **catat dulu, putuskan setelah Module Builder selesai**. Pertimbangan: objek kerja & knowledge berbeda jauh dari module builder; base knowledge PrestaShop beririsan tipis. Opsi BMad: jadikan module terpisah yang bisa berbagi/expand knowledge base PrestaShop inti bila perlu, refaktor murah dilakukan belakangan.

### Tambahan ide (putaran 4, 2026-06-25) — agent sebagai partner ide e-commerce

- Saat **membuat & mengembangkan** module, agent harus bisa **brainstorming mendalam** dan **menawarkan fungsi-fungsi yang relevan dengan e-commerce** (bukan cuma struktur teknis). Contoh domain: konversi (upsell/cross-sell, abandoned cart), retensi (loyalty, wishlist), katalog (filter/faceted, varian), checkout (metode bayar/kirim, one-page), SEO, marketing (promo, email, segmentasi), analytics, multistore/multilang/multicurrency, GDPR/legal, performa (cache, lazy-load).
- → Agent butuh **knowledge base domain e-commerce** (selain knowledge teknis PrestaShop). Saat scaffold/develop, agent proaktif: "module-mu soal X, biasanya merchant juga butuh Y dan Z — mau dimasukkan?"

**Skill BMad yang ingin diadopsi & dikhususkan untuk e-commerce:**
- **Advanced Elicitation** (bmad-advanced-elicitation) — dipakai agent untuk menggali kebutuhan/fungsi module lebih dalam, dengan lensa e-commerce (mis. dampak ke konversi, AOV, retensi).
- **Adversarial Review** (bmad-review-adversarial-general) — review kritis/sinis terhadap module, dikhususkan e-commerce: keamanan transaksi, edge case order/cart/stock, kepatuhan, kompatibilitas lintas versi, performa di toko ramai.
- → Implementasi: bisa jadi (a) capability di agent expert yang memanggil pola dua skill ini, atau (b) referensi/teknik yang di-embed ke agent + workflow validate (adversarial sebagai bagian review). Perlu diputuskan di Fase 5.

### Riset mendalam devdocs — knowledge base cross-version (2026-06-25)

Ini bahan inti untuk "otak" standar baku. Diringkas dari devdocs resmi.

**PrestaShop 8.0 — breaking changes yang merusak module:**
- PHP min 7.2.5, +PHP 8.0/8.1. Symfony → 4.4. Twig → v3.
- Kelas di-rename: `Attribute`→`ProductAttribute`; `TranslationsController`, `StockController`, `ActionsBarButtonInterface` pindah namespace.
- Kelas/method dihapus: `HookDispatcher`, `Tools::jsonEncode/jsonDecode`, `Hook::getHookAliasList/getRetroHookName`, `Validate::isPasswd`, namespace PrestaTrust, `ModuleZip`.
- Hook alias → deprecation notice; di dev mode, daftar hook tanpa implement method = exception.
- Konstanta dihapus: `_PS_SMARTY_DIR_`, `_PS_TCPDF_DIR_`, `_PS_SWIFT_DIR_`, cache trusted-modules.
- Translation pindah `/app/Resources/translations/` → `/translations/`.
- Service syntax Symfony: `bundle:path:file` → `@bundle/path/file.html.twig`; form ext pakai `getExtendedTypes(): iterable`.
- Semua module di folder `modules` install by default; pakai `Module::postInstall()`.

**PrestaShop 9.0 — breaking changes yang merusak module:**
- **Symfony 4.4 → 6.4**, PHP min **8.1**, Node min 20.
- Dependency dihapus dari core (harus bundle sendiri): `guzzlehttp/guzzle`→Symfony HTTP Client, `swiftmailer`→Symfony Mailer, `tactician`→Symfony Messenger.
- Controller harus didefinisikan sebagai **service**; `FrameworkBundleAdminController` deprecated→`PrestaShopAdminController`.
- `PrestaShopAutoload` dihapus → pakai `prestashop/autoload`.
- `Context` singleton dipecah jadi service: `EmployeeContext`, `ShopContext`, `LanguageContext`, `CurrencyContext`, dll. Tulis auth via Symfony Session.
- `trans()` tidak lagi escape string (params `htmlspecialchars`/`addslashes` dihapus) — pengaruh ke Smarty `l` juga.
- Banyak hook legacy dihapus (Product activate/deactivate/delete/sort, Login*); diganti hook baru (`actionBackOfficeLoginForm`, `actionPresentCategory/Store/Manufacturer`).
- Override legacy controller method (`run`, `initContent`, dll) putus.
- Banyak BO page kini Twig + Symfony Forms/Grid (bukan Smarty + HelperForm/HelperList). `.php` module tak bisa dipanggil langsung.

**Sumbu legacy vs modern (yang harus dijembatani module cross-version):**
- Controllers: legacy `controllers/admin/Admin*.php` ↔ modern Symfony controller service + routing yml.
- Templates: Smarty ↔ Twig (`views/**/*.html.twig`).
- Persistence: ObjectModel ↔ Doctrine.
- Hooks: legacy ↔ "hooks on modern pages" + Symfony bridge.
- Services: akses langsung ↔ service container (FQCN autowired).

**Strategi cross-version (kandidat standar yang akan ditawarkan):**
1. Deteksi versi runtime via `_PS_VERSION_` / `version_compare()` → cabang jalur legacy vs modern.
2. Pakai `prestashop/module-lib-service-container` untuk akses service yang aman lintas versi.
3. `ps_versions_compliancy` WAJIB diisi (range min/max) — divalidasi PrestaShop Validator.
4. Hindari API yang dihapus per versi; sediakan shim/polyfill bila perlu (mis. JSON, autoload).
5. composer.json + `prestashop/autoload` untuk namespace yang konsisten.
6. Bundle dependency yang dihapus core di 9 (HTTP client, mailer) bila dipakai.

**Catatan:** halaman devdocs lain perlu di-riset lebih lanjut saat build (hooks-on-modern-pages, services, doctrine, admin-views override, composer). Disimpan sebagai pekerjaan riset lanjutan untuk skill knowledge-base.

**Sumber:** devdocs.prestashop-project.org/9/modules/core-updates/9.0, /8/modules/core-updates/8.0, /9/development/architecture/migration-guide.

### Riset mendalam putaran 2 — detail konkret (2026-06-25)

**Hooks (mekanisme persis, lintas versi):**
- Registrasi: `$this->registerHook('displayHeader')` di `install()`.
- Eksekusi: method publik non-static `hookDisplayHeader(array $params)`.
- Trigger legacy controller: `Hook::exec($name, $args)`. Symfony controller: `$this->dispatchHook($name, $params)`. Smarty: `{hook h='name' mod='modulename'}`. Twig: `{{ renderHook('name', { params }) }}`.
- Bikin hook sendiri: `registerHook` auto-create kalau belum ada (Hook extends ObjectModel).
- → Standar cross-version: pakai naming hook yang sama, tapi pemicu beda jalur legacy vs modern.

**Services / DI (kunci performa & integrasi modern):**
- Module bisa definisikan service sendiri di `config/services.yml`; load `services.php`/xml via imports.
- Bisa **override** (ganti) atau **decorate** (bungkus, simpan `.inner`) service core — alternatif aman pengganti override class legacy.
- Container terpisah per konteks — tabel definisi penting:
  - `config/services.yml` → Symfony container (semua komponen + PrestaShopBundle)
  - `config/admin/services.yml` → admin legacy + Doctrine
  - `config/front/services.yml` → front legacy + Doctrine
  - `config/webservice/services.yml` → webservice
- Akses dari legacy controller/hook: `$this->get('service.id')` (front vs admin context berbeda).
- Wildcard resource WAJIB exclude `index.php` (kalau tidak, redirect ke FO).
- Trik service di front & admin: bikin `config/common.yml` lalu import di tiap env.
- → Standar: `module-lib-service-container` untuk akses seragam lintas versi; decorate > override.

**Cache (untuk workflow Optimize):**
- `Cache::clean('key')` untuk invalidasi; pola key mis. `Module::isInstalled<name>`, `Module::getModuleIdByName_<name>`.
- ObjectModel punya lazy loading + caching bawaan; `clearCache()` granular per objek/kelas; auto-clear saat add/update/delete.
- `Configuration` class: penyimpanan config multilayer DENGAN caching internal + batch mode untuk update banyak nilai (optimasi query).
- PS9: kernel cache adapter pakai `$kernel` global, di-cache lokal; `CacheClearLocker::waitUntilUnlocked()` cegah akses cache saat clear.
- → Standar Optimize: manfaatkan Configuration cache + batch, Cache::clean granular, hindari query berulang, decorate service untuk caching.

**prestashop-flashlight (lingkungan uji baku):**
- Image pre-built di Docker Hub; tag per versi: `latest`, `nightly`, `1.7.8.11`, `8.x`, `php-8.1`, varian `-debian`/PHP spesifik.
- Embeds nginx + php-fpm; **MySQL harus disediakan terpisah** → pakai docker-compose (contoh tersedia).
- Resmi mendukung use case: "Auto installation of modules", "Develop a PrestaShop module", **"Validate a module with the PrestaShop coding standard"**, Xdebug, Blackfire profiling.
- ENV penting untuk otomasi uji:
  - `INSTALL_MODULES_DIR` (mis. `/ps-modules`) → auto-install zip module via PrestaShop CLI.
  - `INIT_SCRIPTS_DIR` / `POST_SCRIPTS_DIR` → script sebelum/sesudah boot.
  - `PS_DOMAIN`, `DEBUG_MODE`, `XDEBUG_ENABLED`, `BLACKFIRE_ENABLED`, `ON_INSTALL_MODULES_FAILURE=continue`.
- Matriks kompatibilitas versi PS↔PHP ada di `prestashop-version.json`.
- → Workflow Validate: spin flashlight per versi target (1.7.8, 8.x, nightly/9), mount module ke `INSTALL_MODULES_DIR`, jalankan coding-standard + cek instalasi, kumpulkan hasil per versi.

**Catatan:** WebReader (mcp) jauh lebih lengkap dari WebFetch untuk devdocs — pakai itu saat riset lanjutan di skill knowledge-base. Halaman cache devdocs 404; sumber cache dari source PrestaShop (zread).

**Sumber tambahan:** devdocs /9/modules/concepts/hooks, /9/modules/concepts/services; github.com/PrestaShop/prestashop-flashlight (README); source PrestaShop (ObjectModel, Configuration, Hook, kernel cache).

### Riset mendalam putaran 3 — composer, Doctrine, Validator (2026-06-25)

**composer.json module (template baku):**
- Field: `name`, `description`, `authors`, `require` (`php: >=5.6.0` untuk dukung 1.6/1.7 lama — sesuaikan target), `autoload` (psr-4 + classmap), `config`, `type: "prestashop-module"`.
- Konvensi namespace PrestaShop: `PrestaShop\Module\ModuleName` atau `YourCompany\YourModuleName`. psr-4 map ke `src/`.
- **WAJIB** `config.prepend-autoloader: false` — kalau true, dependency module override core → rusak. Ini aturan keras.
- Build rilis: `composer dump-autoload -o --no-dev`, sertakan folder `vendor/`, JANGAN sertakan dev deps (PHPUnit dll) — risiko keamanan produksi.
- `composer dump-autoload` bikin `vendor/autoload.php`.
- → Standar scaffold: generate composer.json + jalankan dump-autoload; checklist rilis no-dev.

**Doctrine (persistence modern, sejak 1.7.6):**
- PrestaShop pakai Doctrine **2.15**. Entity di `src/Entity/`, auto-scan untuk module terinstall. Butuh namespace via composer.
- Mapping pakai annotation (`@ORM\Entity`, `@ORM\Table`, `@ORM\Column`). PS9 Symfony 6.4 → cek apakah attribute PHP 8 didukung (annotation tetap jalan tapi cek deprecation).
- **JANGAN pakai doctrine schema tool untuk bikin tabel** (bikin FK tak kompatibel struktur PrestaShop). Bikin tabel via SQL install seperti biasa. Boleh pakai `doctrine:schema:update --dump-sql` untuk generate SQL saja.
- Konvensi nama tabel: CamelCase class → snake_case + prefix `ps_` (ProductComment → ps_product_comment).
- Akses: `$this->container->get('doctrine.orm.entity_manager')` → `persist()` + `flush()`; repository via `getRepository()` (magic `findByX`).
- → Pola cross-version data: ObjectModel aman semua versi (1.7/8/9); Doctrine modern 1.7.6+. Standar: default ObjectModel untuk maksimal kompatibilitas, Doctrine bila butuh ORM & target ≥1.7.6.

**PrestaShop Validator — aturan konkret (dari changelog publik v5.x):**
- `ps_versions_compliancy` **WAJIB** (sejak v5.2.0). Sintaks baru dideteksi (v5.3.x). Generator dukung range hingga 9.0.x (v5.13.3).
- Cek **breaking changes PS8/PS9** otomatis (v5.5.0): service salah di controller, refaktor context Symfony, hook dihapus PS9 (v5.10/5.11).
- Deteksi dependency terlarang di PS9: **GuzzleHttp, SwiftMailer, league/tactician-bundle, anotasi PrestaShopBundle, Symfony FrameworkExtraBundle** (v5.11.0). → harus dihindari/bundle sendiri.
- Deteksi var Smarty yang dihapus PS9, `PS_LEGACY_IMAGES`, `PS_HIGHT_DPI` (v5.12.0); hard-coded theme name & `displaySearch` deprecated, handling `displayOrderDetail` untuk PS9.1+ (v5.14.0).
- **PHPStan** level 5 untuk cek kompatibilitas (v5.12.0); jalan terhadap PS 1.7.8.7, 8.0.0, 9 (v5.5/5.9).
- Cek statis lain: HTML dalam PHP, `serialize`, Smarty escaped (error bila tak di-escape, v5.14.1), `.htaccess`, kondisi `PS_VERSION`, komentar berbahasa Inggris, `index.php` wajib ada tiap folder, deteksi `eval`, fungsi sistem terlarang (`passthru`, `shell_exec`, `system`), encoding UTF-8, BOM marker, file terlarang (`Thumbs.db`, `__MACOSX`), `Readme.md` ada, nama module huruf kecil.
- Validator web butuh **login akun seller** (PrestaShop Account) → tidak bisa otomatis tanpa kredensial. Alternatif lokal: **PHPStan + php-dev-tools** + coding standard (bisa jalan di flashlight: "Validate a module with the PrestaShop coding standard").
- → Workflow Validate: jalankan cek lokal (PHPStan lvl5, coding standard, index.php, escaped Smarty, dependency terlarang PS9, hook dihapus, ps_versions_compliancy ada) per versi target; web Validator opsional manual.

**Sumber:** devdocs /9/modules/concepts/composer, /9/modules/concepts/doctrine; validator.prestashop.com/changelog (publik); flashlight README (coding-standard use case).

## Build Roadmap

Urutan disusun agar tiap langkah membangun fondasi langkah berikutnya:

1. **Seed knowledge base** (`tech/*.md` + `ecommerce/function-catalog.md`) — semua skill bergantung padanya. Knowledge sudah terkumpul di plan ini; tinggal dipindahkan ke file memory. (Bisa jadi bagian init psm-agent-expert / setup.)
2. **psm-validate** (workflow) — dibangun lebih dulu karena dipanggil oleh cross-version & scaffold, dan memberi nilai langsung (audit module existing Budi). Memvalidasi flashlight + standar yang jadi tulang punggung module.
3. **psm-cross-version** (workflow) — prioritas #1 Budi; bergantung pada psm-validate sebagai sub-langkah.
4. **psm-scaffold** (workflow) — bergantung pada knowledge composer/struktur + function-catalog + psm-validate.
5. **psm-develop** (workflow) — menambah fungsi ke module existing; bergantung pada function-catalog + psm-validate. Dibangun setelah scaffold (berbagi banyak pola).
6. **psm-agent-expert** (agent) — hub percakapan; paling baik dibangun setelah workflow ada agar bisa me-route ke sesuatu yang nyata + merawat knowledge base.
7. **psm-optimize** (workflow) — fitur penyempurna; dibangun terakhir setelah inti jalan.

**Next steps:**

1. Build each skill using **Build an Agent (BA)** or **Build a Workflow (BW)** — share this plan document as context
2. When all skills are built, return to **Create Module (CM)** to scaffold the module infrastructure
