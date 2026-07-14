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

# Docker + compose HARUS aktif (flashlight = web-tier saja, butuh DB terpisah;
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

## 2. Verifikasi toolchain SEBELUM menyentuh module

Buktikan skrip + browser + Docker siap tanpa perlu module nyata:

```bash
# unit test (tanpa Docker/browser) — 41 assert harus lolos
uv run scripts/tests/test-ps-e2e-run.py

# probe cepat: jalankan atas folder module apa pun, baca JSON-nya
uv run scripts/ps-e2e-run.py <module> --versions 9.1 --browsers chromium,firefox -o /tmp/e2e.json
```

Baca `/tmp/e2e.json`:

- `browsers_available: ["chromium","firefox"]` → browser siap. Firefox absen → `browser_notes`
  menyuruh `playwright install firefox`; versi jalan dgn chromium saja (coverage tak lengkap, jujur dicatat).
- top-level `status: "skipped"` + reason Docker → Docker belum aktif.
- per-versi `skipped_image` → image belum ada lokal; tambah `--allow-image-pull` **sekali**
  (interaktif) untuk menariknya, atau pra-tarik seperti langkah 1.

## 3. Loop TDD Lapis 4

**Prinsip:** tulis skenario use-case DULU (merah) → drive → implement module sampai hijau
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
| `expect_text` | `text` | teks ada di halaman |
| `click` | `selector` | klik |
| `fill` | `selector`, `value` | isi field |
| `expect_no_console_error` | — | tak ada error JS/console (konklusif → memblok bila ditegakkan) |
| `screenshot` | — | ambil screenshot manual (butuh `--screenshot-dir`) |

Placeholder yang disubstitusi di `path`/`url`/`text`/`value`: `{mod}` `{fo}` `{bo}`.
Spec tak valid (JSON rusak / tanpa `steps`) dilewati dengan catatan, bukan crash.
Rujukan otoritatif: `uv run scripts/ps-e2e-run.py --help`.

### Verifikasi visual ("cek web asli" — lihat render seperti user)

Assertion lolos ≠ tampilan benar ≠ tak ada error di browser. Tiga alat, semua **opt-in**:

```bash
# 1) Screenshot per halaman + pada kegagalan (artefak visual untuk dilihat mata)
uv run scripts/ps-e2e-run.py <module> --versions 9.1 --browsers chromium \
  --screenshot-dir ./e2e-shots -o e2e.json
#   -> ./e2e-shots/9.1/chromium-<scenario>-*.png ; path juga di JSON (per-versi "screenshots")

# 2) Error JS/console: SELALU ditangkap (advisory, non-blok) -> field "console_errors" +
#    browser_notes. Untuk MENEGAKKAN, taruh {"action":"expect_no_console_error"} di skenario.

# 3) --headed: browser TAMPIL live untuk inspeksi manual langsung (butuh display/GUI)
uv run scripts/ps-e2e-run.py <module> --versions 9.1 --browsers chromium --headed
#   opt-in eksplisit; JANGAN di headless/CI. Tanpa display -> skipped_browser (degrade jujur).
```

## 4. Gotchas

- **Port bocor.** Run yang di-kill paksa bisa meninggalkan container yang memegang port
  `psm_flashlight_ps_domain` (default `localhost:8000`) → run berikut gagal bind. Bersihkan:
  `docker ps -aq --filter name=psmfl | xargs -r docker rm -f && docker network ls --filter name=psm-fl-net -q | xargs -r docker network rm`.
- **Headless / CI.** Jalankan **tanpa** `--allow-image-pull` (tak akan auto-tarik image) →
  pra-tarik dulu; browser juga wajib sudah di-`install` (tak auto-download di headless).
- **Login BO.** Default flashlight `admin@prestashop.com` / `prestashop`, folder `admin-dev`
  (override: `--admin-email` / `--admin-password` / `--admin-path`). Login gagal → assertion
  area BO ditandai tak konklusif (tak memblok), assertion FO tetap konklusif.
- **Config keys.** `psm_e2e_enabled` (false → lewati Lapis 4) & `psm_e2e_browsers` di section
  `psm` `_bmad/config.yaml`; default kanonik dari resolver. Base URL memakai ulang
  `psm_flashlight_ps_domain`.
- **Struktur skill dua-pohon.** Resolver config di-eksekusi runtime dari
  `skills/psm-setup/scripts/resolve-psm-config.py` — pastikan file itu ada saat menyalin skill
  ke mesin lain (bukan hanya `.claude/skills/`).
