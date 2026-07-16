# Katalog Peluang Optimasi Performa Module PrestaShop

Peluang optimasi konkret yang memanfaatkan mekanisme PrestaShop, dengan titik
deteksi dan pertimbangan lintas versi. Dipakai untuk **mengidentifikasi** apa yang
bisa dipercepat dan **merancang** perbaikannya. Tiap optimasi harus tetap
version-safe — lihat bagian Services/Cache di
`<skills-dir>/psm-cross-version/references/version-safe-patterns.md`
(`<skills-dir>` = direktori yang memuat skill psm-*, bukan mirror `skills/` di
root project).

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

## Service container & arsitektur

- **Decorate > override** — untuk menyisipkan caching/logika ke service core, decorate (simpan `.inner`) lebih aman lintas versi daripada override. Lihat version-safe-patterns bagian Services.
- **Hook berat** — hook yang dipanggil di setiap halaman (mis. `displayHeader`) harus ringan; pindahkan kerja berat ke event yang lebih jarang atau cache hasilnya.

## Aset front (JS/CSS)

- Daftarkan aset via `registerJavascript`/`registerStylesheet` (1.7+) dengan prioritas tepat; hindari inline besar.

## Bukti performa per kelas (dipakai gerbang Verifikasi)

Bukti harus semetode dengan baseline — angka runtime dari `scripts/ps-profile-summary.py`, patokan statis dari `scripts/ps-hotspot-scan.py` — dan dibandingkan dengan blok baseline di `<module-path>/.psm-optimize-plan.md`, bukan dari ingatan.

- **Baseline punya angka profiler** — ukur ulang dengan profiler yang sama, ringkas via `ps-profile-summary.py` yang sama, bandingkan JSON-nya dengan baseline. Syarat lolos: metrik membaik.
- **Statis, kelas N+1 / hook berat** — jalankan ulang `ps-hotspot-scan.py`. Syarat lolos: jumlah kandidat (query-in-loop / hook berat) turun terhadap baseline.
- **Statis, kelas cache/service/aset** — tak tampak di scan (scan hanya melihat query-in-loop & hook berat). Buktinya: mekanisme terpasang & jalur-pakainya terkonfirmasi dari diff (cache benar di-hit, service ter-decorate, aset ter-defer). Laporkan jujur: "kompatibilitas terverifikasi, mekanisme optimasi terpasang, performa runtime tak terukur (bukan kelas N+1) — perlu profiler untuk angka".
