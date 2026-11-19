# Cek Adversarial Fungsi E-commerce

Pertanyaan tajam untuk mengkritik module sebelum dianggap matang (teknik dari review-adversarial, dikhususkan e-commerce). Diseed 2026-06-29; tambah saat menemukan kelemahan baru.

## Keamanan & integritas
- Harga/diskon dihitung server-side? CartRule API, bukan JS klien (risiko manipulasi)?
- Input front controller divalidasi & di-escape? CSRF token pada aksi tulis?
- Smarty variabel di-escape? → [[validator-rules]].

## Cross-version
- Tiap area legacy/modern punya cabang `_PS_VERSION_`? Tak ada API dihapus tanpa cabang? → [[breaking-changes-8]], [[breaking-changes-9]].
- Hook yang dipakai masih ada di semua versi target?
- Lolos psm-validate di 1.7/8/9?

## Data & skala
- Tabel pakai ObjectModel + SQL install (bukan doctrine schema)? Migrasi via upgrade script? → [[persistence]].
- `id_shop` disimpan (multistore)? Field lang (multilang)?
- Query efisien? Index di kolom yang difilter? N+1 di loop hook display?

## E-commerce / UX
- Fungsi menangani edge: cart kosong, stok 0, produk dihapus, customer tamu vs login?
- Multicurrency: harga diformat via `Tools::displayPrice` / context currency?
- Gagal anggun bila dependency/config belum diset?

## Kepatuhan & operasional
- Simpan data pelanggan → support GDPR export/hapus/anonimisasi?
- Merchant bisa kelola dari BO? Aksi berat pakai cron/CLI, bukan request front?
- Uninstall bersih (hapus tabel/config/hook)?

Pakai sebelum module dianggap selesai; temuan jadi backlog perbaikan.

## Verified additions 2026-11-18 `[core]`

Extra domain checks earned while seeding project `whatsappchat`; they add to the four lens groups above and never replace the `psm-validate` Lapis 3 contract. Finding ids keep the prefixes the aggregator enforces (`adv-sec-`, `adv-cart-`, `adv-xver-`, `adv-perf-`) and every finding needs a `file:line` the reviewer actually read.
- **Anonymous AJAX / front controllers (sec):** `Controller::run()` calls `init()` **before** `checkAccess()`, so a legacy controller that bootstraps core itself answers anonymous callers even when its version branch is dead — BO AJAX endpoints need an explicit `isBoLogged` gate plus an `employee->id` check, and a token-compared cron endpoint must not echo configuration or personal rows.
- **PII into client state (sec):** phone/e-mail serialized into JS for an anonymous widget — check whether the JSON endpoint requires a session and whether the page is cacheable; anything stored per customer must answer `actionExportGDPRData` / `actionDeleteGDPRCustomer`.
- **State changes (cart):** notifications firing on cancelled/refunded/retour states or re-sending on a status regression; verify which `id_order_status` the handler acts on. Schedule windows must be checked against app timezone vs server clock, DST and overnight windows.
- **Cross-shop data (cart):** amounts persisted without `id_currency`, or `Configuration::get` read without `id_shop`, leak across shops; render prices only through the context currency.
- **Cross-version (xver):** a hook registered but never dispatched on modern pages of a target — verify dispatch on BOTH the legacy and the Symfony layout, and never treat markup ids (`table#order_grid_table`, theme classes) as a core contract. A BO probe without a valid token returns an "Invalid token" interstitial at HTTP 200: false negative, not a defect.
- **Performance (perf):** cheap eligibility checks must run before any query inside `displayHeader` / `displayFooter` / `displayBackOfficeHeader`; per-block context re-resolution and per-row queries in BO grids are the usual N+1; per-request external fetches need a cache; `Mail::send` loops inside a hook need batching/queue.
