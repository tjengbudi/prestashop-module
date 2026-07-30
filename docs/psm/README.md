# PrestaShop Module Builder (`psm`)

Module BMad untuk membuat, mengembangkan, meng-cross-version-kan, memvalidasi, dan mengoptimasi module PrestaShop — dengan satu prinsip inti: **satu codebase yang jalan di PrestaShop 1.7.x, 8.x, dan 9.x sekaligus**, tanpa perubahan, siap dipakai siapa pun.

> Bukan upgrade satu arah. Bukan dua codebase. Satu module yang kompatibel ke atas **dan** tetap jalan di versi lawas.

---

## Apa isinya

Satu agent konsultan + delapan workflow + satu setup skill, berbagi knowledge base PrestaShop yang hidup.

| Skill | Peran | Panggil | Menghasilkan |
|---|---|---|---|
| 🛒 **psm-agent-expert** | Agent hub: konsultan PrestaShop & e-commerce, pintu masuk + router | `/psm-agent-expert` | jawaban & arahan (+ KB tumbuh) |
| **psm-setup** | Pasang & konfigurasi module ke project | `/psm-setup` | section `psm` di `_bmad/config.yaml` |
| **psm-scaffold** | Bikin module PrestaShop baru cross-version dari nol | `/psm-scaffold <nama>` | folder module baru |
| **psm-ideate** | Gali & rawat backlog ide untuk memperdalam module dalam domainnya sendiri | `/psm-ideate <module>` | `.psm-ideas.md` |
| **psm-plan** | Rencanakan fungsi e-commerce tanpa menerapkan; dilanjutkan psm-develop | `/psm-plan <module>` | `.psm-develop-plan.md` + `.json` |
| **psm-develop** | Tambah fungsi e-commerce ke module existing tanpa regresi | `/psm-develop <module>` | module + fungsi baru |
| **psm-cross-version** | Buat module existing kompatibel 1.7/8/9 sekaligus | `/psm-cross-version <module>` | module cross-version + `.psm-cross-plan.md` |
| **psm-optimize** | Percepat module via cache/service tanpa memecah kompatibilitas | `/psm-optimize <module>` | module teroptimasi + metrik |
| **psm-validate** | Validasi module di 1.7/8/9 (4 lapis bukti) | `/psm-validate <module>` | laporan JSON per versi |
| **psm-module-context** | Rawat konteks per-module lintas sesi (konvensi, keputusan, fakta, jurnal) | `/psm-module-context <module>` | `memory/projects/<module>.md` |

Deskripsi lengkap tiap skill + contoh pemakaian: [Referensi per skill](#referensi-per-skill).

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
| `psm_flashlight_ps_domain` | `PS_DOMAIN` container flashlight; Lapis 4 pakai host-nya, port dipilih dinamis (bebas-bind) | `localhost:8000` |
| `psm_flashlight_startup_timeout` | Maks detik menunggu container `healthy` | `180` |
| `psm_e2e_enabled` | Gerbang uji browser E2E psm-validate (Lapis 4): `true`/`false` | `true` |
| `psm_e2e_browsers` | Engine Playwright untuk uji E2E, dipisah koma | `chromium,firefox` |
| `psm_modules_dir` | Folder tempat module PrestaShop kamu | `{project-root}/modules` |
| `psm_reports_dir` | Output laporan validasi/optimasi | `{project-root}/_bmad-output/psm-validate` |

> **Sumber kebenaran** daftar key & default di atas: `PSM_DEFAULTS` di `.claude/skills/psm-setup/scripts/resolve-psm-config.py` — resolver yang dibaca semua workflow psm saat runtime. Default yang juga dideklarasikan `module.yaml` psm-setup dijaga selaras oleh test anti-drift; key baru harus mendarat di resolver **dan** tabel ini.

Ubah kapan saja dengan menjalankan ulang `/psm-setup` atau menyunting `_bmad/config.yaml`.

---

## Harness lain (opencode, pi, droid)

Skill `psm-*` mengikuti **Agent Skills open standard** — frontmatter hanya `name` + `description`, tanpa dialek khusus satu harness. Jadi harness lain bisa memakainya dari pohon yang sama (`.claude/skills/`), tanpa menyalin.

| Harness | Status | Yang perlu dikerjakan |
|---|---|---|
| **Claude Code** | Kanonik | — pohon `.claude/skills/` adalah sumber kebenaran |
| **opencode** | Terpasang | **Nol konfigurasi.** opencode membaca `.claude/skills/*/SKILL.md` secara native (project + `~/.claude/skills/` global) |
| **pi** | Terpasang | Satu baris di `.pi/settings.json` + konfirmasi trust — [langkah 4 panduan instal](install.md#4-sambungkan-harness-ke-pohon-skill) |
| **droid** | Belum | Butuh symlink per-skill ke `.factory/skills/`; ada hambatan yang belum diuji (lihat di bawah) |

**pi** tidak memindai `.claude/skills/` sendiri — dia harus ditunjuk lewat array `skills` di `.pi/settings.json`, dan project-nya harus dipercaya (`/trust`) sebelum settings itu dibaca sama sekali. Perintahnya terdaftar sebagai `/skill:<nama>` (mis. `/skill:psm-validate`), bukan `/psm-validate`. Mekanik lengkapnya ada di [panduan instal](install.md#4-sambungkan-harness-ke-pohon-skill) — sengaja satu salinan supaya tak mendrift.

Menunjuk seluruh folder berarti pi juga melihat semua skill bmad di pohon itu, bukan cuma sepuluh `psm-*`.

**droid** belum disiapkan. Dia hanya memindai `<repo>/.factory/skills/`, `~/.factory/skills/`, dan folder kompat `.agent/skills/` — `.claude/skills/` tidak termasuk, jadi butuh symlink per-skill. Dua hal harus diuji lebih dulu:

- **Routing subagent BYOK** ([Factory-AI/factory#1061](https://github.com/Factory-AI/factory/issues/1061)) — subagent droid dilaporkan lari ke Anthropic alih-alih model BYOK. `psm-validate` bergantung pada subagent di dua tempat: Lapis 3 (review adversarial) dan paralelisme per-versi.
- **`droid exec --model` menolak model ID custom** ([#787](https://github.com/Factory-AI/factory/issues/787)) — `droid exec` adalah mode non-interaktif untuk run panjang.

Keduanya bisa saja sudah diperbaiki di versi yang kamu pasang; keduanya belum diverifikasi di repo ini.

> **Catatan subagent umum.** `psm-validate` sudah punya fallback bila harness tak bisa men-spawn subagent: review adversarial dikerjakan sendiri dan versi dikonvergensikan serial, dengan kontrak hasil yang sama. Paralelisme adalah optimasi, bukan syarat vonis — jadi skill tetap sah di harness tanpa subagent, hanya lebih lambat.

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

**Nama telanjang boleh di sebagian skill.** `psm-validate`, `psm-ideate`, dan `psm-module-context` me-resolve nama pendek terhadap `psm_modules_dir` — `/psm-validate ps_banner` sama dengan `/psm-validate {project-root}/modules/ps_banner`. Sisanya (`psm-plan`, `psm-develop`, `psm-cross-version`, `psm-optimize`) minta path folder; bila ambigu mereka bertanya satu pertanyaan alih-alih menebak.

**Argumen `-H` (headless).** Semua workflow menerima `-H` / `--headless` — agent hub tak, karena ia memang percakapan. Efeknya: argumen diambil apa adanya alih-alih ditanyakan, gerbang konfirmasi interaktif dilewati (pemanggil yang bertanggung jawab atas persetujuan), tiap asumsi dicatat ke memlog module, dan yang dikembalikan objek JSON kecil ber-`status` alih-alih prosa — `selesai` (= `complete` bagi pemanggil BMad), `gagal`, atau `butuh intervensi` (keduanya = `blocked`). Kamu jarang mengetiknya sendiri; ini jalur yang dipakai skill saat saling memanggil.

---

## Referensi per skill

Tiap skill di bawah: apa yang dikerjakan, kapan dipanggil, apa yang dihasilkan, dan contoh pemakaian. Sintaks perintah mengikuti harness (`/psm-x` di Claude Code & opencode, `/skill:psm-x` di pi).

### 🛒 psm-agent-expert — konsultan & pintu masuk

Agent percakapan, bukan workflow satu tembakan. Menjawab pertanyaan PrestaShop lintas versi dari knowledge base (dan riset bila KB belum tahu), membantu memikirkan fungsi e-commerce, lalu mengarahkan ke workflow yang tepat. Dia juga **kurator KB**: pengetahuan baru yang ditemukan saat menjawab diendapkan ke `_bmad/psm/memory/` supaya sesi berikutnya tak mengulang riset yang sama.

Panggil saat: bingung mulai dari mana, punya pertanyaan teknis, atau ingin brainstorm sebelum memutuskan.

```
/psm-agent-expert
> "Kelas Attribute masih ada di PS9?"
> "Module bankwire-ku mau kuperluas — kira-kira arah mana yang masuk akal?"
```

**Hasil:** jawaban + arahan; KB bertambah sebagai efek samping. Tak menyentuh source module.

---

### psm-setup — pasang & konfigurasi

Sekali di awal project. Menanyakan nilai konfigurasi (semua ada default), menulis section `psm` ke `_bmad/config.yaml`, mendaftarkan capability ke help system, dan membuat folder KB. Idempoten — aman dijalankan ulang untuk mengubah konfigurasi.

```
/psm-setup
> "pakai default semua"
```

**Hasil:** `_bmad/config.yaml` section `psm` + `_bmad/psm/memory/` kosong. Jalankan `/psm-agent-expert` sesudahnya untuk mengisinya.

---

### psm-scaffold — module baru dari nol

Membangkitkan kerangka module PrestaShop lewat generator deterministik (`ps-scaffold.py`), bukan mengarang file satu per satu — jadi struktur, `ps_versions_compliancy`, `index.php` per folder, dan composer sudah benar sejak baris pertama. Kerangkanya **tak dinyatakan siap sebelum lolos psm-validate**, yang dipanggil otomatis di akhir.

Panggil saat: belum ada module sama sekali. Bila module sudah ada, ini bukan skillnya — pakai psm-develop atau psm-cross-version.

```
/psm-scaffold ps_loyaltypoint
   → tanya nama, author, maksud module satu kalimat
   → bangkitkan kerangka → psm-validate → tawarkan fungsi e-commerce awal
```

**Hasil:** folder module baru di `psm_modules_dir` + vonis validate per versi. Menolak menimpa folder yang sudah ada (tak akan `--force` atas inisiatif sendiri).

---

### psm-ideate — gali & rawat backlog ide

Yang digali di sini **bukan** fungsi lintas domain (itu milik psm-plan dengan katalog penuh), melainkan pendalaman satu module **di dalam topiknya sendiri**: bankwire tumbuh jadi QR payment, bukti bayar, konfirmasi manual, rekonsiliasi. Digali lewat lima arah — varian, kelengkapan, otomasi, visibilitas, ketahanan.

Karena satu sesi penggalian selalu melahirkan lebih banyak ide daripada yang muat di satu siklus, hasilnya **backlog yang hidup lintas sesi**, bukan daftar sekali pakai. Ide ditandai `baru` / `dipilih` / `terwujud` / `ditolak`; yang `ditolak` tak ditawarkan ulang tanpa alasan baru.

```
/psm-ideate psbankwire
   → kenali domain dari bukti (hook terdaftar, tabel, controller)
   → gali lima arah → Budi memilih → tulis backlog
```

**Hasil:** `<module-path>/.psm-ideas.md`. Ide berstatus `dipilih` dibaca psm-plan sebagai masukan — itu jembatannya.

---

### psm-plan — rencanakan tanpa menerapkan

Tiga fase awal psm-develop (**pahami existing → rancang → konfirmasi**) lalu **berhenti**. Gunanya: perencanaan bisa jadi sesi terpisah dari eksekusi — kamu bisa mereview rencana dengan tenang, bahkan besok, tanpa satu file module pun tersentuh.

Rencananya divalidasi terhadap inventaris nyata sebelum ditampilkan: hook yang sudah terdaftar, titik sisip yang tak ada, `$definition` yang diubah tanpa folder `upgrade/` — semua ketahuan di sini, bukan saat apply.

```
/psm-plan ps_banner
   → inventaris + baseline static scan → tawarkan fungsi → rancang → validasi → konfirmasi → STOP
```

**Hasil:** pasangan artefak `<module-path>/.psm-develop-plan.md` (naratif untuk kamu) + `.psm-develop-plan.json` (terstruktur untuk skrip). psm-develop melanjutkan dari keduanya lewat mekanisme resume-nya, tanpa modifikasi.

---

### psm-develop — tambah fungsi ke module existing

Menanam fungsi e-commerce baru ke module yang **sudah ada dan berjalan**, tanpa memecah fungsi lama dan dengan kompatibilitas tetap di 1.7/8/9. Kerjanya **pahami existing → rancang → konfirmasi → terapkan → verifikasi**.

Bisa mulai dari nol (merancang sendiri) atau melanjutkan rencana psm-plan — bila artefak rencana ada, dia resume dari situ, merekonsiliasi status dulu terhadap kode (kalau kamu git-revert sesuatu, statusnya dikoreksi, bukan dipercaya buta).

```
/psm-develop ps_banner              # rancang + terapkan dalam satu sesi
/psm-develop ps_banner              # bila .psm-develop-plan.md ada → resume dari rencana
```

**Hasil:** module bertambah fungsi + artefak rencana ter-update (item jadi `diterapkan`) + vonis psm-validate. Tak ada yang disebut selesai sebelum validate hijau di ketiga versi.

---

### psm-cross-version — satu codebase, tiga versi

Mengubah module existing — sering ditulis untuk versi lawas — jadi **satu codebase yang jalan di 1.7.x, 8.x, dan 9.x sekaligus**. Bukan upgrade satu arah, bukan dua codebase. Memetakan API berisiko per versi, merancang cabang `version_compare`/shim yang aman, lalu membuktikannya.

Panggil saat: module lama mau jalan di versi baru, atau psm-validate menemukan API yang dihapus.

```
/psm-cross-version /home/budi/modules/ps_banner
   → peta risiko per versi → rencana → konfirmasi → terapkan → psm-validate
```

**Hasil:** module cross-version + `<module-path>/.psm-cross-plan.md`. Bila pindai sudah bersih, dia berhenti dengan status `sudah-aman` alih-alih mengarang perubahan.

---

### psm-optimize — percepat tanpa memecah

Mempercepat module lewat cache & service container PrestaShop, **tanpa** mengubah perilaku fungsional dan tanpa memecah kompatibilitas. Disiplinnya ukur-dulu: profil (Blackfire/Xdebug + `ps-hotspot-scan.py`) sebelum merancang, dan verifikasi **ganda** di akhir — tetap lolos validate di ketiga versi **dan** metriknya benar-benar membaik.

```
/psm-optimize /home/budi/modules/ps_banner
   → profil → rencana → konfirmasi → terapkan → validate + banding metrik
```

**Hasil:** module teroptimasi + `.psm-optimize-plan.md` + metrik sebelum/sesudah. Bila hotspot-scan tak menemukan apa pun, statusnya `sudah-ramping` — no-op sukses, bukan run rusak.

---

### psm-validate — vonis berbasis bukti

Menilai apakah module sehat di 1.7/8/9 lewat **empat lapis**, dari yang murah dan deterministik sampai yang mahal dan nyata:

| Lapis | Apa | Butuh |
|---|---|---|
| 1 | Pindai statis terhadap `ps-rules.json` (API/hook/kelas/dependency yang dihapus per versi) | — |
| 2 | Uji di PrestaShop core asli via `prestashop-flashlight` + PHPStan | Docker |
| 3 | Review adversarial e-commerce (uang, stok, pajak, multi-shop) | — |
| 4 | Uji perilaku browser E2E (Playwright) | Docker + browser |

Bacalah **`ready`**, bukan cuma `pass`. `pass` sengaja buta terhadap tuntas-tidaknya bukti; `ready` baru `true` bila tiap lapis yang diwajibkan benar-benar terevaluasi. Runner tanpa Docker menghasilkan `ready: false` — itu jujur, bukan cacat module.

```
/psm-validate ps_banner
/psm-validate ps_banner --versions 1.7.8,8.1,9.1
```

> **Sebut versi minor.** Sejak 2026-07-30 aturan bisa khas-minor (mis. theme di-hardcode = error di 9.1 karena instalasi baru 9.1 default ke Hummingbird). Aturan itu hanya menyala bila target menyebut minornya: pakai `9.1`, bukan `9`. Target telanjang melewatinya dan melaporkannya sebagai `minor_rules_skipped` → Lapis 1 tak konklusif → `ready` jatuh.

**Hasil:** JSON per versi di `psm_reports_dir` + ringkasan yang bisa ditindaklanjuti. Dipanggil otomatis sebagai gerbang mutu oleh scaffold, develop, cross-version, dan optimize.

---

### psm-module-context — memori per-module lintas sesi

Merawat lapis yang **tak bisa diturunkan dari kode**: kenapa sebuah keputusan diambil, tabel mana yang benar-benar hidup di produksi, konvensi khusus module ini, riwayat validasi. Fakta terderivasi (hook, ObjectModel, daftar file) tetap milik `ps-module-inventory.py` yang segar tiap run — skill ini tak pernah menyalinnya.

Yang membuatnya bukan sekadar catatan: **rekonsiliasi deterministik**. Fakta yang diklaim dicocokkan terhadap inventaris nyata, dan klaim yang buktinya hilang ditandai drift, bukan dibiarkan membusuk jadi dokumentasi yang berbohong.

```
/psm-module-context ps_banner
   → inventaris → rekonsiliasi klaim vs bukti → tulis/perbarui profil
```

**Hasil:** `_bmad/psm/memory/projects/<module>.md`. Dibaca psm-plan, psm-develop, psm-optimize, psm-cross-version, dan psm-agent-expert sebelum merancang apa pun — jadi tak ada workflow yang menurunkan ulang pemahaman module dari nol.

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

**Memperdalam module yang sudah jalan** — rantai penuh, tiap panah boleh jadi sesi terpisah
```
psm-module-context <module>  # (sekali) endapkan konvensi & keputusan module
        ↓
psm-ideate <module>          # gali lima arah → backlog .psm-ideas.md
        ↓ (ide berstatus `dipilih`)
psm-plan <module>            # rancang + validasi rencana → BERHENTI
        ↓ (pasangan artefak rencana)
psm-develop <module>         # resume dari rencana → terapkan
        ↓
psm-validate <module>        # vonis 4 lapis
```

> Rantai ini sengaja bisa dipotong di mana saja. Backlog dan artefak rencana bertahan lintas sesi, jadi menggali hari ini dan menerapkan minggu depan adalah alur yang didukung, bukan penyimpangan. Kalau maksudmu sudah jelas, lompat langsung ke `psm-develop` — psm-ideate dan psm-plan opsional.

> **Pola keamanan:** semua workflow yang mengubah source (cross-version, develop, optimize) bekerja **rencana → konfirmasi → terapkan → verifikasi**. Perubahan tak diterapkan tanpa persetujuanmu, dan tak ada yang dinyatakan "selesai" sebelum lolos `psm-validate` di ketiga versi. Gunakan git untuk pembatalan.

---

## Bagaimana skill saling memanggil

Sepuluh skill ini bukan sepuluh alat terpisah yang kebetulan senama. Sebagian besar pekerjaan tiap workflow justru dikerjakan **milik skill lain** — dan itu disengaja: satu kemampuan punya satu pemilik, sisanya memakai, supaya tak ada dua implementasi yang boleh berbeda jawaban.

Ada **tiga bentuk keterkaitan** yang berbeda, dan membedakannya penting saat kamu memodifikasi skill:

### 1. Delegasi skill → skill (satu skill memanggil skill lain)

Hanya ada dua arah, dan keduanya searah:

| Pemanggil | Yang dipanggil | Kapan & kenapa |
|---|---|---|
| `psm-scaffold`, `psm-develop`, `psm-cross-version`, `psm-optimize` | **`psm-validate`** | Di fase verifikasi, otomatis. Vonis lolos/gagal **bukan** penilaian mereka sendiri — mereka membaca JSON psm-validate apa adanya. Tak satu pun boleh menyatakan "selesai" tanpa vonis itu. |
| `psm-agent-expert` | semua workflow | Sebagai router. Memetakan maksud → workflow (`references/route-workflow.md`), menyiapkan konteks (path module, versi target, hasil brainstorm) lebih dulu, lalu meringkas hasilnya kembali. |

Tiga workflow juga **mengarahkan ke `psm-scaffold` lalu berhenti** bila targetnya ternyata bukan module (`looks_like_module: false`): `psm-develop`, `psm-plan`, `psm-ideate`. Itu gerbang target — mereka menolak merancang di atas ketiadaan, alih-alih menghasilkan scan kosong yang menyerupai sukses.

Di dalam dirinya sendiri, `psm-validate` juga mendelegasikan ke **subagent** (bukan skill): satu subagent per versi target saat versi > 1, plus satu subagent reviewer untuk Lapis 3 — supaya source module tak membebani konteks orkestrasi.

### 2. Skrip milik bersama (skill X menjalankan skrip milik skill Y)

Ini keterkaitan yang paling padat, dan yang paling sering luput saat menyunting. Tiap skrip punya **satu skill pemilik**; yang lain memanggilnya lewat path `<skills-dir>/<pemilik>/scripts/…`:

| Skrip | Pemilik | Dipakai juga oleh | Untuk apa |
|---|---|---|---|
| `resolve-psm-config.py` | `psm-setup` | **kesembilan skill lain** | Satu-satunya cara membaca config. Tak ada skill yang boleh mem-parse `config.yaml` sendiri. |
| `ps-module-inventory.py` | `psm-develop` | `psm-plan`, `psm-ideate`, `psm-optimize`, `psm-module-context` | Fakta module yang terderivasi dari kode: hook terdaftar, ObjectModel + tabel, controller, daftar file. Juga sumber gerbang `looks_like_module`. |
| `ps-module-context.py` | `psm-module-context` | `psm-scaffold`, `psm-plan`, `psm-develop`, `psm-cross-version`, `psm-optimize`, `psm-validate` | `init`/`note`/`reconcile` atas profil per-module. Tiap workflow mencatat **satu baris** per run. |
| `ps-static-scan.py` | `psm-validate` | `psm-plan`, `psm-develop`, `psm-cross-version` | Lapis 1. Dipakai sebagai **baseline** sebelum menyentuh file — supaya error pra-eksisting tak salah dituduhkan ke perubahan run ini. |
| `ps-idea-backlog.py` | `psm-ideate` | `psm-plan` | Membaca ide berstatus `dipilih` sebagai masukan rencana. |

Sisanya milik satu skill saja: `ps-scaffold.py` (scaffold), `ps-hotspot-scan.py` + `ps-profile-summary.py` (optimize), dan lima skrip lapis lain di psm-validate (`ps-plan-layers`, `ps-run-layer`, `ps-flashlight-run`, `ps-e2e-run`, `ps-aggregate`).

> Konsekuensi praktis: **mengubah output sebuah skrip berarti mengubah kontrak untuk setiap pemakainya.** `ps-module-inventory.py` punya empat pemakai di luar pemiliknya; `resolve-psm-config.py` punya sembilan.

### 3. Artefak sebagai jembatan (satu menulis, lain membaca)

Yang membuat rantai bisa dipotong jadi sesi terpisah. Artefak ini file biasa di disk, jadi ia bertahan setelah sesi ditutup:

| Artefak | Ditulis | Dibaca | Perannya |
|---|---|---|---|
| `<module>/.psm-ideas.md` | `psm-ideate` | `psm-plan` | Backlog ide. Hanya yang berstatus `dipilih` yang menyeberang. |
| `<module>/.psm-develop-plan.md` + `.json` | `psm-plan` *dan* `psm-develop` | keduanya + `psm-module-context` | Kontrak bersama — namanya sengaja berprefix `psm-develop` meski psm-plan yang biasanya melahirkannya. psm-plan menulis status `direncanakan`; psm-develop yang mengubahnya jadi `diterapkan`. |
| `_bmad/psm/memory/projects/<module>.md` | `psm-module-context` (+ satu baris dari tiap workflow) | **semua** workflow & agent-expert | Memori lintas sesi: konvensi, keputusan, jurnal. |
| `_bmad/psm/memory/tech/` + `ecommerce/` | `psm-agent-expert` | semua workflow | Knowledge base bersama. |
| `<module>/.psm-cross-plan.md`, `.psm-optimize-plan.md` | cross-version / optimize | pemiliknya sendiri (resume) | Bukan jembatan antar-skill — hanya negara-bagian lintas sesi bagi skill itu sendiri. |

**Aturan yang berlaku di semua jembatan:** artefak dibaca untuk **rekonsiliasi**, bukan dipercaya buta. Setiap skill yang resume menjalankan ulang inventaris/scan lebih dulu dan mengoreksi status yang tak lagi didukung bukti — kalau kamu `git revert` sesuatu, status `diterapkan`-nya dikoreksi, bukan diteruskan sebagai kebohongan.

### Membacanya sebagai satu gambar

```
                    psm-setup ──resolve-psm-config.py──> (semua skill)
                         │
                psm-agent-expert ──routing──> (semua workflow)
                         │
   psm-ideate ──.psm-ideas.md──> psm-plan ──.psm-develop-plan.*──> psm-develop
        │                            │                                 │
        └────────ps-module-inventory.py (milik psm-develop)────────────┘
                                     │
        psm-scaffold / psm-develop / psm-cross-version / psm-optimize
                                     │
                              memanggil psm-validate  ──> vonis (ready/pass)
                                     │
                    ps-module-context.py (milik psm-module-context)
                                     │
                        projects/<module>.md  ──> dibaca semua
```

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
  psm-ideate/            # + ps-idea-backlog.py (backlog ide per-module + sync ke rencana)
  psm-plan/              # perencanaan tanpa apply; artefak dilanjutkan psm-develop
  psm-develop/           # + ps-module-inventory.py, references/ecommerce-function-catalog.md
  psm-optimize/          # + ps-hotspot-scan.py, references/optimization-catalog.md
  psm-module-context/    # + ps-module-context.py (konteks per-module + rekonsiliasi)
  psm-setup/             # setup skill (module.yaml, merge scripts, resolver config runtime)

.pi/settings.json        # menunjuk pi ke pohon .claude/skills/ lewat path relatif
                         # (portabel & aman di-commit; opencode tak perlu apa pun)

skills/reports/
  prestashop-module-builder-plan.md   # rencana & riset lengkap (sumber seed knowledge base)

_bmad/psm/memory/        # knowledge base bersama (dibuat saat setup, di-seed oleh agent)
  tech/                  # breaking changes, hooks, services, persistence, dll
  ecommerce/             # katalog fungsi, lensa elicitation, checklist adversarial
  projects/              # profil per module — diproduksi psm-module-context,
                         # sengaja tak di-seed di first run
```

---

## Troubleshooting

- **"Docker tidak tersedia"** saat validasi/optimasi → uji flashlight dilewati; validasi tetap jalan dengan aturan statis saja, tapi uji perilaku di core asli butuh Docker. Pasang Docker lalu ulangi.
- **Knowledge base kosong** → jalankan `/psm-agent-expert` sekali untuk men-seed-nya.
- **Image flashlight lama diunduh** → image besar (GB); unduhan pertama per tag versi makan waktu, setelahnya di-cache lokal.
- **Mau ubah versi target** → jalankan ulang `/psm-setup` atau sunting `psm_target_versions` di `_bmad/config.yaml`.
- **Mau melewati uji browser E2E** → set `psm_e2e_enabled: 'false'` di section `psm` pada `_bmad/config.yaml` (atau batasi engine via `psm_e2e_browsers`).
- **Skill `psm-*` tak muncul di pi** → tersangka pertama bukan path, tapi trust: pi mengabaikan `.pi/settings.json` untuk project yang belum dipercaya (`/trust`). Sesudah itu cek `skills` menunjuk `../.claude/skills`, dan ingat commandnya `/skill:<nama>`. Detail: [panduan instal](install.md#4-sambungkan-harness-ke-pohon-skill).
- **Skill `psm-*` tak muncul di opencode** → discovery-nya native, jadi biasanya soal izin: cek `permission.skill` di `opencode.json` (default bisa `ask`/`deny`) dan pastikan `tools.skill` tidak dimatikan untuk agent yang kamu pakai.
