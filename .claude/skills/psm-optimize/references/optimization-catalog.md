# Katalog Peluang Optimasi Performa Module PrestaShop

Peluang optimasi konkret yang memanfaatkan mekanisme PrestaShop, dengan titik
deteksi dan pertimbangan lintas versi. Dipakai untuk **mengidentifikasi** apa yang
bisa dipercepat dan **merancang** perbaikannya. Tiap optimasi harus tetap
version-safe — lihat bagian Services/Cache di
`{project-root}/skills/psm-cross-version/references/version-safe-patterns.md`.

Prinsip: ukur dulu (profil), baru optimasi titik yang terbukti lambat. Jangan
optimasi spekulatif yang menambah kompleksitas tanpa bukti.

## Caching

- **Configuration batch** — banyak `Configuration::get()` berturut → `Configuration::get()` sudah cache internal, tapi untuk update banyak nilai pakai batch agar hemat query. Deteksi: banyak get/update Configuration di satu alur.
- **Cache::store / Cache::retrieve** untuk hasil query mahal yang dipanggil berulang dalam satu request. Invalidasi via `Cache::clean('key_pattern')` saat data berubah. Pola key: namespacing per module (mis. `mymodule_<id>`).
- **ObjectModel lazy + cache bawaan** — ObjectModel sudah lazy-load & cache; `clearCache()` granular per objek/kelas saat add/update/delete. Jangan instansiasi ObjectModel dalam loop bila bisa batch query.
- **Smarty template cache** — hindari logika berat di template; precompute di hook/controller. Cache fragmen via `$this->display()` bila statis.
- **Hindari cache global yang invalidasi berlebihan** — `Cache::clean('*')` mahal; targetkan key spesifik.

## Query / database

- **Query dalam loop** (N+1) — paling sering bikin lambat. Deteksi: `Db::getInstance()->...` atau `new ObjectModel(...)` di dalam `foreach` (di-surface oleh `scripts/ps-hotspot-scan.py`). Perbaikan: satu query dengan `IN(...)` / join, atau `PrestaShopCollection` dengan filter.
- **Index** — pastikan kolom yang difilter ada index (cek SQL install module).
- **DbQuery builder** untuk query yang dapat dibaca & aman lintas versi.
- Plus higiene SQL umum (ambil kolom yang dipakai, bukan `SELECT *`).

## Service container & arsitektur

- **Decorate > override** — untuk menyisipkan caching/logika ke service core, decorate (simpan `.inner`) lebih aman lintas versi daripada override. Lihat version-safe-patterns bagian Services.
- **Lazy service** — service mahal sebaiknya tak dibangun bila tak dipakai; manfaatkan lazy loading container.
- **Hook berat** — hook yang dipanggil di setiap halaman (mis. `displayHeader`) harus ringan; pindahkan kerja berat ke event yang lebih jarang atau cache hasilnya.

## Aset front (JS/CSS)

- Daftarkan aset via `registerJavascript`/`registerStylesheet` (1.7+) dengan prioritas tepat; hindari inline besar.
- Defer/async JS non-kritis. Hindari memuat aset di halaman yang tak butuh.

## Profil (ukur sebelum & sesudah)

- **Blackfire** — di flashlight, set ENV `BLACKFIRE_ENABLED=true`. Profil request yang memuat fungsi module untuk menemukan hotspot (wall-time, query count, memory).
- **Xdebug** — ENV `XDEBUG_ENABLED=true` untuk trace/profil bila Blackfire tak tersedia.
- **Query count** — bandingkan jumlah query sebelum/sesudah; target turun pada alur yang dioptimasi.
- Selalu catat baseline sebelum perubahan dan ukur ulang sesudah — optimasi tanpa pengukuran adalah tebakan.

## Pagar wajib

- Setiap optimasi tetap memakai cabang versi bila menyentuh area legacy/modern; jangan pecahkan kompatibilitas 1.7/8/9 demi kecepatan.
- Optimasi tak boleh mengubah perilaku fungsional — hasil harus identik, hanya lebih cepat.
- Verifikasi ulang lewat psm-validate setelah menerapkan.
