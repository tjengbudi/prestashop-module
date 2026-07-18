# QUICKSTART — Lapis 4 (browser E2E) di mesin lain

Panduan menyiapkan & menjalankan **loop TDD Lapis 4 (E2E red→green)** psm-validate di
instalasi baru. Loop E2E ini **murni skrip + Docker + Playwright — TIDAK butuh API key**.
Yang butuh sesi Claude hanya Lapis 3 (adversarial); yang butuh `ANTHROPIC_API_KEY` hanya
harness eval kualitas (`bmad-eval-runner`), **bukan** loop ini.

Semua path di bawah relatif ke folder skill (`.claude/skills/psm-validate/`).

## 1. Prasyarat mesin

```bash
# uv — menjalankan skrip PEP723 (semua ps-*.py)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Docker + compose aktif (flashlight = web-tier saja, butuh DB terpisah;
# skrip membangun DB+flashlight berpasangan otomatis)
docker info && docker compose version

# Browser Playwright — sekali; terpasang ke ~/.cache/ms-playwright (dipakai lintas-env uv)
uv run --with playwright playwright install chromium firefox

# (opsional, hemat waktu first-run) pra-tarik image
docker pull mariadb:lts
for t in 1.7.8.11 8.1.6-nginx 9.1.4-nginx; do
  docker pull prestashop/prestashop-flashlight:$t
done
```

Catatan versi browser: `ps-e2e-run.py` memprovisi paket `playwright` via header PEP723
(versi terbaru). Jalankan `playwright install` dengan playwright yang sama (`uv run --with
playwright ...` di atas sudah begitu) agar build browser cocok dengan yang di-drive skrip.

## 2. Verifikasi toolchain sebelum menyentuh module

Buktikan skrip + browser + Docker siap tanpa perlu module nyata:

```bash
# unit test (tanpa Docker/browser) — semua assert harus lolos
uv run scripts/tests/test-ps-e2e-run.py

# probe cepat: jalankan atas folder module apa pun, baca JSON-nya
uv run scripts/ps-e2e-run.py <module> --versions 9.1 --browsers chromium,firefox -o e2e-probe.json
```

Baca `e2e-probe.json`:

- `browsers_available: ["chromium","firefox"]` → browser siap. Firefox absen → `browser_notes`
  menyuruh `playwright install firefox`; versi jalan dgn chromium saja (coverage tak lengkap, jujur dicatat).
- top-level `status: "skipped"` + reason Docker → Docker belum aktif.
- per-versi `skipped_image` → image belum ada lokal; tambah `--allow-image-pull` **sekali**
  (interaktif) untuk menariknya, atau pra-tarik seperti langkah 1.

## 3. Loop TDD Lapis 4

**Prinsip:** tulis skenario use-case dulu (merah) → drive → implement module sampai hijau
di Chromium **dan** Firefox.

```bash
# (a) MERAH: tulis spec use-case yang belum diimplement
mkdir -p <module>/tests/e2e
cat > <module>/tests/e2e/configure.json <<'JSON'
{"name":"configure-save","steps":[
  {"action":"goto","area":"bo","path":"/index.php?controller=AdminModules"},
  {"action":"expect_no_fatal"},
  {"action":"goto","area":"fo","path":"/"},
  {"action":"expect_visible","selector":"#mymodule-block"}
]}
JSON

# (b) drive → RED: assertion gagal → temuan → versi FAIL
uv run scripts/ps-e2e-run.py <module> --versions 9.1 --browsers chromium,firefox \
  --allow-image-pull -o e2e.json

# (c) implement fitur module, lalu ULANG (b) sampai HIJAU:
#     findings:[] , pass:true , browsers:["chromium","firefox"] di tiap versi target
```

Vonis penuh 4-lapis (via skill `psm-validate` interaktif, atau agregasi langsung):

```bash
uv run scripts/ps-aggregate.py --static static.json --e2e e2e.json --versions 9.1 -o verdict.json
```

### Format spec skenario (`<module>/tests/e2e/*.json`)

Satu file = satu skenario `{ "name", "steps":[...] }`. Aksi yang didukung:

| action | field | arti |
|---|---|---|
| `goto` | `area` (`fo`\|`bo`), `path` atau `url` | navigasi; area `bo` konklusif hanya bila login admin sukses |
| `expect_no_fatal` | — | halaman tanpa PHP fatal / white-screen / HTTP ≥ 500 |
| `expect_visible` | `selector` | elemen tampak |
| `expect_text` | `text` | teks TERLIHAT di halaman — locator teks ter-render, bukan substring HTML (teks yang cuma ada di `<script>`/atribut tak dihitung); skrip menunggu `load` settle dulu |
| `click` | `selector` | klik |
| `click_optional` | `selector` | klik bila elemen ada, lewati tanpa gagal bila tidak (interstitial yang muncul hanya di sebagian versi, mis. "Invalid security token" BO 1.7/8) |
| `fill` | `selector`, `value` | isi field |
| `expect_no_console_error` | — | tak ada error JS/console (konklusif → memblok bila ditegakkan) |
| `screenshot` | — | ambil screenshot manual (butuh `--screenshot-dir`) |

Placeholder yang disubstitusi di `path`/`url`/`text`/`value`: `{mod}` `{fo}` `{bo}` `{browser}`
(`{browser}` = nama engine aktif — pakai untuk nama data unik per-browser).

**Yang dihitung sebagai cakupan uji perilaku: aksi `expect_*` saja.** `goto`/`click`/`fill`/
`screenshot` menggerakkan browser tapi tak menyatakan benar/salah — `click` cuma membuktikan
tombolnya ada, bukan hasilnya benar. Spec tanpa satu pun `expect_*` tetap dijalankan (sebuah
`goto` yang kena HTTP ≥ 500 tetap temuan yang memblok) tapi **tak** menaikkan `ready`: vonisnya
sama dengan module yang tak punya spec sama sekali (`e2e_smoke_only`), dan pra-pass
`ps-plan-layers.py` menandainya sebelum container boot. Assertion yang hasilnya tak konklusif
(mis. area `bo` saat login admin gagal) juga tak dihitung.
Spec tak valid (JSON rusak / tanpa `steps` / aksi tak dikenal) dilewati dengan catatan, bukan crash.
Rujukan otoritatif: `uv run scripts/ps-e2e-run.py --help`.

### Pola BO lintas-versi (tanpa ini, skenario configure gagal di 1.7/8)

Verified vs flashlight `1.7.8.11`/`8.1.6-nginx`/`9.1.4-nginx`: `goto` ke configure legacy
(`index.php?controller=AdminModules&configure={mod}`) memunculkan interstitial
**"Invalid security token"** di 1.7/8 (dismiss: `a.btn-continue`) tapi tidak di 9
(route Symfony langsung render). Skenario menuju configure men-dismiss-nya secara opsional:

```json
{"action":"goto","area":"bo","path":"/index.php?controller=AdminModules&configure={mod}"},
{"action":"expect_no_fatal"},
{"action":"click_optional","selector":"a.btn-continue"},
{"action":"expect_no_fatal"}
```

Setelah di halaman configure (token sah dari interstitial atau route Symfony), link/tombol
CRUD buatan module bekerja di ketiga versi — asalkan module memakai
`getAdminLink('AdminModules', true, [], ['configure' => $name])` sebagai base link,
bukan pola manual era-1.6.

### Verifikasi visual ("cek web asli" — lihat render seperti user)

Assertion lolos ≠ tampilan benar ≠ tak ada error di browser. Tiga alat, semua **opt-in**:

```bash
# 1) Screenshot per halaman + pada kegagalan (artefak visual untuk dilihat mata)
uv run scripts/ps-e2e-run.py <module> --versions 9.1 --browsers chromium \
  --screenshot-dir ./e2e-shots -o e2e.json
#   -> ./e2e-shots/run-<YYYYMMDD-HHMMSS>/9.1/chromium-<scenario>-*.png ; path juga di JSON
#      (per-versi "screenshots"; top-level "screenshot_dir" = folder run ini). Subfolder
#      per-run: nama file deterministik, jadi tanpa pemisahan ini PNG run lama menumpuk di
#      folder yang sama & bisa terbaca sebagai bukti run sekarang.

# 2) Error JS/console: selalu ditangkap (advisory, non-blok) -> field "console_errors" +
#    browser_notes. Untuk menegakkan, taruh {"action":"expect_no_console_error"} di skenario.

# 3) --headed: browser tampil live untuk inspeksi manual langsung (butuh display/GUI)
uv run scripts/ps-e2e-run.py <module> --versions 9.1 --browsers chromium --headed
#   opt-in eksplisit; jangan di headless/CI. Tanpa display -> skipped_browser (degrade jujur).
```

### Kanal cacat visual → vonis

Screenshot yang kamu tinjau **tak punya jalan ke vonis** kecuali lewat file lapis
adversarial (`<psm_reports_dir>/<module>-adversarial.json`) — `ps-aggregate.py` tak pernah
melihat gambar. Cacat visual yang kamu yakini, tulis ke situ SEBELUM agregat jalan:

- **Tambahkan** ke `findings` yang sudah ada — jangan timpa: di file itu ada temuan
  reviewer Lapis 3, dan menimpanya membuang temuan mereka diam-diam.
- `severity: "error"` supaya memblok (`warning` tak pernah memblok).
- Pastikan `versions` top-level **memuat versi yang kamu lihat sendiri**. Agregat menandai
  versi di luar cakupan itu tak konklusif dan membuang temuannya — termasuk temuanmu.
- Bentuk esensial ada di poin di atas; `ps-aggregate.py` menegakkan skemanya (pelanggaran = exit 2 berpesan spesifik yang menyebut field yang salah).

## 4. Gotchas

- **Port bocor.** Run yang di-kill paksa bisa meninggalkan container yang memegang port
  `psm_flashlight_ps_domain` (default `localhost:8000`) → run berikut gagal bind. Bersihkan
  (satu prefix `psm-fl` menangkap kedua orkestrator — compose & manual):
  `docker ps -aq --filter name=psm-fl | xargs -r docker rm -f && docker network ls --filter name=psm-fl -q | xargs -r docker network rm`.
- **Headless / CI.** Jalankan **tanpa** `--allow-image-pull` (tak akan auto-tarik image) →
  pra-tarik dulu; browser juga wajib sudah di-`install` (tak auto-download di headless).
- **Login BO.** Default flashlight `admin@prestashop.com` / `prestashop`, folder `admin-dev`
  (override: `--admin-email` / `--admin-password` / `--admin-path`). Login gagal → assertion
  area BO ditandai tak konklusif (tak memblok), assertion FO tetap konklusif.
- **Login BO flaky di cold-container 1.7.8/8.1.** POST+redirect kadang tak selesai saat
  container dingin — skrip sudah warm-up BO sebelum men-drive dan me-retry login sekali;
  bila tetap gagal, langkah BO jatuh ke inconclusive (jujur) → ulangi run, container hangat stabil.
- **DB bersama antar-browser.** Browser-browser berbagi satu container/DB per versi →
  skenario yang membuat data menghasilkan duplikat saat browser kedua jalan. Beri nama
  data ber-placeholder `{browser}` supaya unik per-engine, atau assertion yang toleran duplikat.
- **Jangan percaya `overall pass` saja.** Cek: (1) `scenario_sources` memuat semua skenario
  yang diharapkan — tanpa spec authored, `e2e_smoke_only` true & `ready` jatuh (hanya terbukti
  "shop tak rusak"); (2) `scenario_notes` kosong (isi = spec dilewati: aksi tak dikenal/JSON
  rusak — `ps-plan-layers.py` menandainya sebelum container boot); (3) pisahkan `findings`
  konklusif vs `inconclusive` (login BO gagal → langkah BO inconclusive, bukan lolos).
- **Config keys.** `psm_e2e_enabled` (false → lewati Lapis 4) & `psm_e2e_browsers` di section
  `psm` `{project-root}/_bmad/config.yaml`; default kanonik dari resolver. Base URL memakai ulang
  `psm_flashlight_ps_domain`.
- **Dependensi psm-setup.** Resolver config dijalankan saat aktivasi dari
  `.claude/skills/psm-setup/scripts/resolve-psm-config.py` — saat menyalin ke mesin lain, sertakan
  skill `psm-setup`, bukan hanya folder `psm-validate`. Resolver absen → skill lanjut dengan
  default kanonik skrip dan mencatatnya di ringkasan.
