# Pembersihan file sisa lewat skrip upgrade

Porting membuang dan mengganti nama file. Repo jadi bersih, tapi **toko yang sudah memasang
rilis lama tidak**: upload zip, rsync tanpa `--delete`, atau salin folder hanya menimpa dan
menambah file, tak pernah menghapus. File sisa tetap hidup:

- **front controller lama** masih bisa dirutekan (`index.php?fc=module&module=<m>&controller=<c>`)
  dan memanggil API yang sudah dihapus core → fatal di PS8/9;
- **override lama** tetap terpasang di `override/` root dan membayangi kelas core;
- **kelas/template lama** bisa ikut termuat lewat `require` atau resolusi template.

psm-validate tak melihatnya karena selalu menguji instalasi BERSIH dari isi repo. Kasus nyata
yang memicu reference ini: `mycarrier_rj` — repo hasil cross-version bersih, server masih
menjalankan `controllers/front/AddressController.php` 1.x dengan `Tools::jsonEncode`.

Jadi: **setiap file yang dibuang saat porting wajib punya jalur penghapusan di skrip upgrade.**

## 1. Inventaris (deterministik)

```bash
uv run scripts/ps-removed-files.py <module-path> --git-history [--base-ref <ref>] [--old-dir <folder>]...
```

Jalankan **setelah** Terapkan selesai, dan juga di jalur "pindai bersih" (porting lampau bisa
sudah membuang file tanpa pernah membersihkannya). Sumber versi lama — gabungkan semua yang ada,
makin lengkap makin aman:

- `--git-history`: semua path yang **pernah** dihapus di sejarah git module, md5 dari tiap versi
  historisnya. Default yang selalu dipakai bila module di git — tak perlu tahu tag rilis lama.
- `--base-ref`: commit/tag rilis lama tertentu, bila ada.
- `--old-dir`: zip rilis yang diekstrak, folder `_backup`, atau salinan dari server. Wajib bila
  rilis lama tak pernah ada di git (umum untuk module warisan) — tanyakan ke Budi di mana
  salinannya; headless: pakai yang ada, catat di memlog bahwa sumber `--old-dir` tak tersedia.

Output per path: `category`, `md5[]`, `sources`, `override_class` (untuk override), dan
`covered_by` — skrip upgrade yang sudah **menyebut** path itu. `covered_by` hanya heuristik
teks: kosong = pasti belum tertangani; terisi = baca skrip itu sebelum menganggapnya beres.
Ringkasan: `uncovered`, `module_version`, `existing_upgrade_versions`. `uncovered` 0 → tak perlu
skrip pembersih baru; catat itu di rencana.

## 2. Perlakuan per kategori

| Kategori | Perlakuan |
| --- | --- |
| `override` | `$module->removeOverride('<Kelas>')` **selagi file override module masih ada**, lalu hapus file override module itu. |
| `front_controller`, `admin_controller`, `php`, `template` | Hapus bila md5 cocok salah satu md5 rilis lama; tak cocok → lewati + log warning. |
| `asset`, `other` | Sama seperti di atas. Risiko rendah, tapi tetap dibersihkan supaya tak menumpuk. |
| `vendor` | Sama, md5-gated. Banyak? Pertimbangkan menghapus folder paket utuh yang tak dipakai lagi — sebut di rencana. |
| `dev` (`tests/`, `.github/`, `docs/`, …) | Abaikan bila folder itu tak ikut dikapalkan di zip rilis; bila ikut, perlakukan seperti `other`. |
| `upgrade_script` | **Jangan dihapus**: core memilih skrip upgrade dari nama file versi; menghapusnya tak berefek di toko yang sudah lewat versi itu. Cukup catat. |

Kenapa **md5-gated**: file yang isinya tak cocok rilis mana pun berarti diubah tangan merchant
atau developer lain. Menghapusnya diam-diam menghancurkan kerja orang; membiarkannya tanpa
jejak mengulang masalah awal. Lewati, lalu log warning yang menyebut path-nya.

Kenapa **override lewat `removeOverride`, bukan unlink**: override root bisa memuat method dari
beberapa module sekaligus. `Module::removeOverride($classname)` (publik dengan signature sama
di 1.7.8 / 8.1 / 9.1) hanya mencabut method yang didefinisikan file override **milik module ini**,
lalu me-regenerasi class index sendiri. Ia **membaca** `<module>/override/<path>` untuk tahu
method mana yang miliknya — karena itu panggil sebelum menghapus file override module. File itu
sudah tak ada (folder module diganti utuh)? `removeOverride` tak bisa memilah lagi: jangan
sentuh override root, log error yang meminta pembersihan manual.

## 3. Template skrip upgrade

Satu file `upgrade/upgrade-<versi-baru>.php`, nama fungsi `upgrade_module_<versi_dengan_underscore>`.
**Naikkan `$this->version`** di file utama ke versi itu (juga `config.xml` / `config_*.xml` bila
dikapalkan) — core hanya menjalankan skrip upgrade yang versinya di atas versi terdaftar di DB.
Versi sudah ada skrip upgradenya? Tambahkan langkah pembersihan ke skrip itu bila versinya belum
dirilis; bila sudah dirilis, naikkan versi lagi.

Sintaks dijaga PHP 5.6-safe (PS 1.7.8 masih bisa jalan di 5.6): tanpa `??`, tanpa type hint
skalar/return, tanpa `JSON_THROW_ON_ERROR`. Idempoten — aman dijalankan ulang.

```php
<?php
if (!defined('_PS_VERSION_')) {
    exit;
}

/**
 * Bersihkan file sisa rilis lama yang dibuang saat porting cross-version.
 * Deploy di atas instalasi lama tak pernah menghapus file; tanpa langkah ini file lama
 * tetap bisa dirutekan/termuat dan memanggil API yang sudah dihapus core.
 * Inventaris: scripts/ps-removed-files.py (md5 = semua rilis lama yang dikenal).
 */
function upgrade_module_2_0_4($module)
{
    $dir = _PS_MODULE_DIR_ . $module->name . '/';
    // Closure, bukan fungsi global: dua module yang memakai template ini tak boleh bentrok nama.
    $log = function ($message, $severity) use ($module) {
        PrestaShopLogger::addLog($module->name . ': ' . $message, $severity, null, 'Module', (int) $module->id, true);
    };

    // 1) Override lama: cabut dari override/ root SELAGI file override module masih ada.
    $overrides = array(
        // 'override/classes/form/CustomerAddressFormatter.php' => 'CustomerAddressFormatter',
    );
    foreach ($overrides as $rel => $class) {
        if (!is_file($dir . $rel)) {
            continue; // sudah bersih, atau folder module diganti utuh (lihat reference)
        }
        if (!$module->removeOverride($class)) {
            $log('override gagal dicabut (izin tulis override/?): ' . $class, 3);
            return false; // gagal keras: override lama yang tetap aktif = bug senyap
        }
        @unlink($dir . $rel);
        $log('override sisa dicabut: ' . $class, 1);
    }

    // 2) File sisa: hapus hanya bila isinya persis salah satu rilis lama.
    $files = array(
        // 'controllers/front/AddressController.php' => array('<md5-1>', '<md5-2>'),
    );
    foreach ($files as $rel => $known) {
        $path = $dir . $rel;
        if (!is_file($path)) {
            continue;
        }
        if (!in_array(md5_file($path), $known, true)) {
            $log('file sisa dilewati (isi diubah, periksa manual): ' . $rel, 2);
            continue;
        }
        if (!@unlink($path) && is_file($path)) {
            $log('file sisa gagal dihapus (izin tulis?): ' . $rel, 3);
            continue;
        }
        $log('file sisa dihapus: ' . $rel, 1);
    }

    return true;
}

```

Isi kedua array dari output inventaris, apa adanya — jangan mengetik md5 dengan tangan.
`config.xml` / `config_<iso>.xml` sisa (kategori `other`) adalah cache yang ditulis core dari file
utama module — aman dihapus, dan salinan basi bisa menampilkan versi lama di daftar module.
Teks log dipakai skenario verifikasi di bawah: ubah keduanya bersamaan.

## 4. Verifikasi (psm-validate Lapis 5)

Instalasi bersih tak pernah punya file sisa, jadi yang membuktikan skrip ini jalan adalah
skenario kondisi-rusak. Simpan **salinan file lama** sebagai fixture berekstensi non-eksekusi —
md5-nya tetap sama karena isinya sama — supaya file lama tak bisa dieksekusi lewat URL bila
`tests/` ikut terkapalkan:

```
<module>/tests/fixtures/leftover/controllers/front/AddressController.php.fixture
```

Lalu `<module>/tests/scenarios/upgrade-bersihkan-file-sisa.json` (format: docstring
`ps-scenario-run.py` di psm-validate). Source module di-mount read-only di `/ps-module-src` dan
disalin ke folder `modules/<module>` PrestaShop **di dalam container** — `given` menulis ke salinan
itu, tak pernah ke repo:

```json
{
  "name": "upgrade-bersihkan-file-sisa",
  "description": "Deploy di atas rilis lama tak menghapus file yang dibuang saat porting; upgrade wajib membersihkannya.",
  "given": [
    "UPDATE `{prefix}module` SET version = '2.0.3' WHERE name = 'mycarrier_rj'",
    "UPDATE `{prefix}configuration` SET value = '1' WHERE name = 'PS_MIN_LOGGER_LEVEL_IN_DB'",
    {"sh": "cp /ps-module-src/tests/fixtures/leftover/controllers/front/AddressController.php.fixture /var/www/html/modules/mycarrier_rj/controllers/front/AddressController.php"}
  ],
  "when": "upgrade",
  "then": [
    {"query": "SELECT COUNT(*) FROM `{prefix}log` WHERE message = 'mycarrier_rj: file sisa dihapus: controllers/front/AddressController.php'",
     "expect": "1"}
  ]
}
```

- `version` di `given` = versi **sebelum** skrip pembersih; tanpanya `upgrade` no-op karena versi
  DB == versi file.
- `PS_MIN_LOGGER_LEVEL_IN_DB` disetel eksplisit: PS9 membuang log di bawah level itu, dan toko
  bisa menaikkannya — skenario tak boleh bergantung pada setelan itu.
- Tambahkan skenario kedua untuk cabang md5-tak-cocok: `given` menulis isi lain
  (`{"sh": "echo '<?php // diubah' > …"}`), `then` mengharapkan log `file sisa dilewati` = `1`.
- Ada override? Cabang pencabutan override root butuh override yang benar-benar terpasang dari
  rilis lama — `given` SQL/shell sederhana tak bisa merakitnya dengan jujur. Cukup buktikan cabang
  "file override module tak ada" tak menggagalkan upgrade, dan **tulis di rencana** bahwa pencabutan
  override root belum terbukti otomatis (uji manual di staging yang memasang rilis lama).

Skenario ini membuat Lapis 5 menggerbang `ready` untuk module itu (module yang mengapalkan
skenario wajib lolos) — memang itu tujuannya.
