# PrestaShop Module Builder — Panduan Instalasi & Penggunaan

Module BMad untuk membuat, mengembangkan, meng-cross-version-kan, memvalidasi, dan mengoptimasi module PrestaShop — satu codebase yang jalan di 1.7.x, 8.x, dan 9.x sekaligus.

> Sudah terpasang? Konfigurasi, alur kerja, dan detail skill ada di [README module](README.md).

---

## Prasyarat

Sebelum install, pastikan:

- **Satu harness yang membaca Agent Skills** — pilih salah satu (bisa berdampingan, satu pohon skill dipakai bersama):
  - **Claude Code** terpasang dan sudah login ([claude.ai/code](https://claude.ai/code)) — jalur kanonik
  - **pi** — `pi --help`; butuh satu baris konfigurasi (langkah 4)
  - **opencode** — `opencode --version`; nol konfigurasi, discovery `.claude/skills/` native
- **Python 3** tersedia — `python3 --version`
- **uv** tersedia — `uv --version` (dipakai oleh skill workflow; install: `pip install uv`)
- **Docker** — opsional, tapi diperlukan untuk uji flashlight & E2E browser (`psm-validate`, `psm-optimize`). Bisa dipasang belakangan, tidak memblok instalasi

---

## Instalasi

### 1. Buka project PrestaShop kamu di harness pilihanmu

```bash
cd /path/ke/project-kamu
claude .      # Claude Code
# atau: pi    # pi
# atau: opencode
```

> Project ini adalah folder tempat kamu mengembangkan module PrestaShop — bukan folder instalasi PrestaShop-nya.

### 2. Pastikan BMad sudah terpasang di project

Jika belum ada BMad, install dulu:

```bash
npx bmad-method install
```

Ikuti prompt interaktif — pilih modul yang kamu butuhkan (minimal `core`). Jika BMad sudah ada, lewati langkah ini.

### 3. Tambahkan module PSM

Pilih salah satu cara:

**Opsi A — via BMad installer (direkomendasikan jika BMad sudah terpasang)**

```bash
npx bmad-method install --action update --custom-source https://github.com/<owner>/prestashop-module
```

BMad akan mengunduh module dari GitHub, menyalin skills ke `.claude/skills/`, dan mendaftarkannya ke instalasi yang sudah ada.

**Opsi B — manual**

```bash
git clone https://github.com/<owner>/prestashop-module /tmp/psm-installer
cp -r /tmp/psm-installer/.claude/skills/psm-* /path/ke/project-kamu/.claude/skills/
rm -rf /tmp/psm-installer
```

> Bila `.claude/skills/` belum ada: `mkdir -p /path/ke/project-kamu/.claude/skills/`

### 4. Sambungkan harness ke pohon skill

Skill `psm-*` hidup di **satu** pohon: `.claude/skills/`. Tak ada yang perlu disalin per harness — yang berbeda cuma cara tiap harness menemukannya.

| Harness | Yang perlu dikerjakan |
|---|---|
| **Claude Code** | Tak ada. `.claude/skills/` memang pohon nativenya. |
| **opencode** | Tak ada. Membaca `.claude/skills/*/SKILL.md` secara native (project + `~/.claude/skills/`). |
| **pi** | Satu baris di `.pi/settings.json` (di bawah) + konfirmasi trust. |

**pi** tidak memindai `.claude/skills/` sendiri; ia harus ditunjuk:

```json
// .pi/settings.json  — dibuat di root project, di samping .claude/
{
  "skills": ["../.claude/skills"]
}
```

Path **relatif**, bukan absolut: pi me-resolve path di `.pi/settings.json` relatif terhadap folder `.pi` itu sendiri, jadi `../.claude/skills` benar di mesin mana pun dan file ini aman di-commit. (Path absolut juga didukung, tapi membuatnya machine-specific: repo pindah folder atau di-clone orang lain → path mati.)

Lalu jalankan `pi` di root project. pi akan **menanyakan trust** untuk project yang punya settings project-level; setujui, atau simpan keputusannya dengan `/trust` supaya tak ditanya lagi. Tanpa trust, `.pi/settings.json` diabaikan dan skill `psm-*` tak akan muncul. Mode non-interaktif (`-p`, `--mode json/rpc`) tak pernah menampilkan prompt trust — pakai `--approve` atau simpan keputusan trust lebih dulu.

> Menunjuk seluruh folder berarti pi juga melihat skill BMad lain di pohon itu, bukan cuma sepuluh `psm-*`.

### 5. Jalankan setup

Panggil skill setup — sintaksnya berbeda per harness:

```
/psm-setup          # Claude Code
/skill:psm-setup    # pi (skill terdaftar sebagai command /skill:<nama>)
```

Di harness yang tak punya command eksplisit, sebut saja maksudnya (mis. "jalankan psm-setup") — skill dipilih model dari `description`-nya. Contoh perintah di sisa dokumen ini memakai sintaks Claude Code; padankan dengan harness-mu.

Skill akan:
- Menanyakan nama kamu, bahasa komunikasi, dan preferensi folder
- Menulis config ke `_bmad/config.yaml` dan `_bmad/config.user.yaml`
- Mendaftarkan skill ke help system (`_bmad/module-help.csv`)
- Membuat folder output yang diperlukan
- Membersihkan file installer sementara

Terima default dengan mengetik "semua default oke" — atau sebutkan hanya nilai yang ingin diubah. Daftar key config & default-nya ada di [README module](README.md#konfigurasi-config-section-psm).

---

## Mulai pakai

Setelah setup selesai, jalankan sekali:

```
/psm-agent-expert
```

Ini akan menyeed knowledge base bersama (`_bmad/psm/memory/`) dari referensi yang sudah ada di dalam skill, lalu membuka pintu masuk konsultasi. Langkah ini wajib dilakukan sekali sebelum workflow lain dipakai.

---

## Cara pakai

### Skenario 1 — Bikin module baru dari nol

```
/psm-scaffold
```

Interaktif: tanya nama module, author, & maksud module, bangkitkan kerangka cross-version, tawarkan fungsi pemantik, lalu validasi otomatis.

### Skenario 2 — Module sudah ada, mau cross-version ke 1.7/8/9

Letakkan module di folder yang dikonfigurasi saat setup (default: `modules/<nama-module>/`), lalu:

```
/psm-cross-version
```

Alur: analisis risiko per versi → rencana perubahan → konfirmasi → terapkan → validasi.

### Skenario 3 — Tambah fitur ke module existing

```
/psm-develop
```

Alur: pahami existing → rancang → konfirmasi → terapkan → verifikasi.

### Skenario 4 — Audit kompatibilitas

```
/psm-validate
```

Empat lapis: pindai statis (selalu), uji flashlight Docker (bila Docker ada), review adversarial e-commerce (selalu), dan uji perilaku browser E2E Chromium+Firefox (bila Docker + Playwright ada). Output: laporan JSON per versi di `_bmad-output/psm-validate/`.

### Skenario 5 — Optimasi performa

```
/psm-optimize
```

Tambahkan cache/service tanpa memecah kompatibilitas lintas versi.

### Konsultasi umum

```
/psm-agent-expert
```

Tanya apa saja soal PrestaShop cross-version, brainstorm fungsi e-commerce, atau minta arahan ke workflow yang tepat. Contoh alur kerja lengkap: lihat [Alur kerja umum](README.md#alur-kerja-umum).

---

## Sepuluh skill

| Skill | Perintah | Fungsi |
|---|---|---|
| psm-agent-expert | `/psm-agent-expert` | Konsultasi + kurator KB + routing workflow |
| psm-scaffold | `/psm-scaffold` | Buat module baru dari nol |
| psm-ideate | `/psm-ideate` | Gali & rawat backlog ide untuk memperdalam module (dilanjutkan psm-plan) |
| psm-plan | `/psm-plan` | Rencanakan fitur tanpa menerapkan (dilanjutkan psm-develop) |
| psm-develop | `/psm-develop` | Tambah fitur ke module existing |
| psm-cross-version | `/psm-cross-version` | Jadikan satu codebase kompatibel 1.7/8/9 |
| psm-validate | `/psm-validate` | Validasi & audit kompatibilitas (4 lapis) |
| psm-optimize | `/psm-optimize` | Optimasi performa module |
| psm-module-context | `/psm-module-context` | Rawat konteks per-module lintas sesi + rekonsiliasi |
| psm-setup | `/psm-setup` | Install & konfigurasi module ini |

Tabel ini sengaja ringkas. Deskripsi lengkap, kapan memanggil, contoh invokasi, dan artefak yang dihasilkan tiap skill ada di [Referensi per skill](README.md#referensi-per-skill).

---

## Knowledge base

KB bersama hidup di `_bmad/psm/memory/` dan di-seed otomatis oleh `psm-agent-expert` saat pertama kali dijalankan:

```
_bmad/psm/memory/
  tech/           # breaking-changes-8.md, breaking-changes-9.md, cross-version-patterns.md,
                  # hooks.md, services-di.md, persistence.md, composer-structure.md,
                  # validator-rules.md, flashlight.md
  ecommerce/      # function-catalog.md, elicitation-lenses.md, adversarial-checks.md
  projects/       # <module>.md (profil per module)
```

KB diperbarui otomatis saat psm-agent-expert menemukan info baru. Tidak perlu dikelola manual. Kecuali `projects/`: isinya **tak** di-seed di first run — tiap `<module>.md` lahir lewat `psm-module-context` saat module itu dikerjakan, dan direkonsiliasi terhadap kode oleh workflow yang menyentuhnya.

---

## Troubleshooting

**`/psm-setup` tidak dikenali (Claude Code)**
→ Pastikan `npx bmad-method install --action update --custom-source ...` sudah selesai dan restart Claude Code. Skill harus ada di `.claude/skills/psm-setup/`.

**Skill `psm-*` tak muncul di pi**
→ Tersangka pertama bukan path, tapi **trust**: pi mengabaikan `.pi/settings.json` untuk project yang belum dipercaya. Jalankan `pi` interaktif dan setujui promptnya, atau `/trust` untuk menyimpannya. Sesudah itu baru cek `skills` di `.pi/settings.json` benar-benar menunjuk pohonnya (`../.claude/skills` dari `.pi/`). Ingat commandnya `/skill:psm-setup`, bukan `/psm-setup`.

**Skill `psm-*` tak muncul di opencode**
→ Discovery-nya native, jadi biasanya soal izin: cek `permission.skill` di `opencode.json` (default bisa `ask`/`deny`) dan pastikan `tools.skill` tak dimatikan untuk agent yang kamu pakai.

**`npx bmad-method` tidak ditemukan**
→ Pastikan Node.js dan npm terpasang: `node --version`. Install Node.js dari [nodejs.org](https://nodejs.org) jika belum ada.

**`python3` not found**
→ Install Python 3: `brew install python3` (Mac) atau `apt install python3` (Linux).

**`uv` not found**
→ `pip install uv` atau `curl -LsSf https://astral.sh/uv/install.sh | sh`

**Setup gagal di tengah jalan**
→ Aman untuk dijalankan ulang dari awal — script merge bersifat idempoten dan tidak membuat entri duplikat.

**Docker tidak ada — psm-validate/psm-optimize tidak bisa uji flashlight**
→ Install Docker Desktop, lalu jalankan ulang skill. Image flashlight diunduh otomatis saat pertama kali dipakai (ukuran besar — tunggu sebentar).

**Folder `modules/` belum ada**
→ `mkdir -p modules` di root project, lalu letakkan atau clone module kamu di sana.

Troubleshooting pemakaian sehari-hari (Docker/image/E2E/versi target): lihat [README module](README.md#troubleshooting).
