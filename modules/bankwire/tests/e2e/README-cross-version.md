# Uji E2E lintas-versi PrestaShop (1.7.x / 8.x / 9.x)

Catatan lengkap perubahan harness `psm-validate` Lapis 4 (`ps-e2e-run.py`) dan fakta
per-versi yang diperlukan untuk menulis skenario yang lolos di ketiga versi sekaligus.
Semua fakta di sini diverifikasi langsung terhadap image `prestashop/prestashop-flashlight`
(tag `1.7.8.11`, `8.1.6-nginx`, `9.1.4-nginx`) pada 2026-07-16/17 — bukan asumsi.

---

## 1. Perubahan harness (`ps-e2e-run.py`) — 4 titik

### 1.1 `DEFAULT_NAV_TIMEOUT_S`: 20 → 60 detik
**Kenapa:** container flashlight *dingin* butuh 13–22 detik untuk hit HTTP pertama
(kompilasi Smarty di 1.7, cache Symfony di 8/9) — terukur langsung. Dengan 20s,
`page.goto()` melempar `Timeout` walau halaman sebenarnya ter-render utuh (dibuktikan
lewat screenshot cart yang sempurna). Ini membuat Lapis 4 **merah palsu** untuk toko
yang sehat. Override per-run: `--nav-timeout <detik>`.

### 1.2 `SUPPORTED_ACTIONS`: tambah `click_optional`
Daftar aksi valid yang dipakai `discover_scenarios()` untuk memvalidasi spec. **Aksi
yang tak terdaftar di sini membuat SELURUH skenario dilewati diam-diam** (dengan catatan
di `scenario_notes`, tapi `overall pass` tetap bisa `True`). Menambah aksi baru WAJIB di
dua tempat: tuple ini DAN loop eksekusi `run_steps()`.

### 1.3 Aksi baru `click_optional`
Klik bila selector ada; lewati tanpa gagal bila tidak. Untuk elemen yang muncul di
sebagian versi saja — terutama interstitial "Invalid security token" BO legacy (1.7/8).

### 1.4 `_bo_login()` — selector tombol & cek keberhasilan
- Tombol submit: `button[name=submitLogin]` → **`#submit_login`** (id stabil ketiga versi).
- Cek keberhasilan: `"submitLogin" not in html` → **`'name="passwd"' not in html`**
  (hilangnya field password = keluar dari form login; stabil lintas versi, nama tombol tidak).
- `wait_for_load_state("networkidle")` dibungkus try/except dengan timeout 15s lalu
  fallback ke `"load"` — BO punya polling XHR yang bisa membuat networkidle tak pernah
  tercapai.

---

## 2. Fakta per-versi (verified)

| Aspek | PS 1.7.8 | PS 8.1 | PS 9.1 |
|---|---|---|---|
| **Login BO — `name` tombol** | `submitLogin` | `submitLogin` | `submit_login` |
| **Login BO — `id` tombol** | `submit_login` | `submit_login` | `submit_login` |
| **Login BO — field** | `email`, `passwd` | `email`, `passwd` | `email`, `passwd` |
| **Login form** | legacy | legacy | Symfony |
| **Module-configure URL** | legacy `index.php?controller=AdminModules&configure=<mod>&token=` | legacy | Symfony `index.php/improve/modules/manage/action/configure/<mod>?_token=` |
| **Interstitial "Invalid security token"** saat goto configure tanpa token | YA (`a.btn-continue`) | YA (`a.btn-continue`) | TIDAK (langsung render) |
| **Kredensial admin flashlight** | `admin@prestashop.com` / `prestashop` | sama | sama |
| **BO folder** | `admin-dev` | `admin-dev` | `admin-dev` |
| **Smarty** | 3.1.48 | (4.x) | 4.5.5 |

Catatan penting:
- **`#submit_login` adalah satu-satunya selector tombol login yang jalan di ketiganya.**
  `name=submitLogin` di 1.7/8 cocok ke DUA tombol (login + "Send reset link").
- Login BO di 1.7.8/8.1 **flaky pada cold-container** (POST+redirect kadang tak selesai
  dalam batas tunggu). Pertimbangkan warm-up (hit BO sekali via curl) sebelum run, atau
  retry login.

---

## 3. Kosakata aksi skenario (`tests/e2e/*.json`)

Spec: `{"name": "...", "description": "...", "steps": [ {...}, ... ]}`

| Aksi | Field | Perilaku |
|---|---|---|
| `goto` | `area` (`fo`\|`bo`, default `fo`), `path` | Navigasi. `area=bo` memicu login admin best-effort sekali. |
| `click` | `selector` | Klik; GAGAL bila selector tak ada. |
| `click_optional` | `selector` | Klik bila ada; LEWATI bila tak ada (tak gagal). |
| `fill` | `selector`, `value` | Isi input; `value` disubstitusi placeholder. |
| `expect_no_fatal` | — | Gagal bila HTTP ≥500 atau ada tanda fatal PHP di HTML. |
| `expect_visible` | `selector` | Gagal bila elemen tak terlihat. |
| `expect_text` | `text` | Gagal bila `text` tak ada di HTML. **Peka timing** — jalankan setelah `expect_visible` pada elemen penanda, atau setelah redirect settle. |
| `expect_no_console_error` | — | Gagal bila ada error console/JS sejak langkah sebelumnya. |
| `screenshot` | — | Simpan screenshot (bila `--screenshot-dir` diset). |

Placeholder di `path`/`text`/`value`: `{mod}` (nama module), `{fo}` (base URL FO),
`{bo}` (base URL BO). Langkah BO jadi **konklusif** hanya bila login BO berhasil; bila
gagal, langkah BO masuk kanal `inconclusive` (tak memblok vonis).

---

## 4. Pola skenario BO lintas-versi (WAJIB)

Karena 1.7/8 memunculkan interstitial token tapi 9 tidak, setiap skenario yang menuju
halaman configure module HARUS men-dismiss interstitial secara opsional:

```json
{"action": "goto", "area": "bo", "path": "/index.php?controller=AdminModules&configure={mod}"},
{"action": "expect_no_fatal"},
{"action": "click_optional", "selector": "a.btn-continue"},
{"action": "expect_no_fatal"},
{"action": "expect_text", "text": "..."}
```

Setelah berada di halaman configure (dengan token sah dari interstitial atau route
Symfony), tautan CRUD yang dibangun module (`a[href*='action=addbank']`, tombol
`button[name=submitBank]`, dst) bekerja di ketiga versi — asalkan module memakai
`getAdminLink('AdminModules', true, [], ['configure' => $name])` sebagai base link
(lihat `bankwire.php::moduleAdminLink()`), bukan pola manual era-1.6.

---

## 5. Keterbatasan yang diketahui (kandidat perbaikan harness berikutnya)

1. **Login BO flaky di cold-container 1.7.8/8.1** → tambah retry di `_bo_login`, atau
   warm-up BO sebelum run.
2. **DB bersama antar-browser** → chromium & firefox berbagi satu container/DB, jadi
   skenario yang MEMBUAT data (mis. add bank) menghasilkan duplikat saat browser kedua
   jalan. Pakai nama unik per-browser, atau isolasi DB per-browser.
3. **`expect_text` peka timing** setelah submit+redirect → dahului dengan
   `expect_visible` pada elemen penanda daftar agar auto-wait Playwright settle.

---

## 6. Perintah run referensi

```bash
uv run .claude/skills/psm-validate/scripts/ps-e2e-run.py modules/bankwire \
  --versions 1.7.8,8.1,9.1 --browsers chromium,firefox \
  --db-image mariadb:lts --ps-domain localhost:8000 \
  --orchestrator auto --startup-timeout 180 \
  --screenshot-dir _bmad-output/psm-validate/e2e-shots \
  -o _bmad-output/psm-validate/bankwire-e2e.json
```

**Verifikasi hasil — JANGAN percaya `overall pass` saja:**
1. `scenario_sources` memuat semua skenario yang diharapkan (bukan terlewat).
2. `scenario_notes` kosong (catatan = skenario dilewati karena aksi tak dikenal / JSON rusak).
3. Screenshot BERTANGGAL run ini (folder e2e-shots menumpuk file lama; screenshot basi menipu).
4. `findings` conclusive vs `inconclusive` (login BO gagal → langkah BO inconclusive, bukan lolos).
