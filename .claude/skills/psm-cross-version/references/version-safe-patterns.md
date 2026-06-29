# Pola Version-Safe Module PrestaShop (1.7.x / 8.x / 9.x)

Katalog pola konkret untuk membuat satu codebase module jalan di ketiga versi
mayor sekaligus. Sumber: devdocs.prestashop-project.org (core-updates 8.0/9.0,
concepts hooks/services/doctrine/composer), validator.prestashop.com.

Prinsip: **deteksi versi saat runtime, pilih jalur aman.** Jangan pakai API yang
hilang di versi target tanpa cabang. Aturan pelanggaran konkret (kelas/hook/dep
yang dihapus) ada di ruleset skill psm-validate (`{project-root}/skills/psm-validate/assets/ps-rules.json`)
— pakai itu untuk deteksi, file ini untuk *perbaikannya*.

## Deteksi versi (fondasi semua pola)

```php
// _PS_VERSION_ tersedia sejak module di-load. Bandingkan dengan version_compare.
if (version_compare(_PS_VERSION_, '8.0.0', '>=')) {
    // jalur PS8/9 (modern)
} else {
    // jalur 1.7.x (legacy)
}
// Untuk PS9 spesifik: version_compare(_PS_VERSION_, '9.0.0', '>=')
```

Simpan hasil sebagai helper privat (`private function isPs8Plus()`) agar cabang
konsisten dan terbaca. Hindari pengecekan versi tersebar tak beraturan.

## composer.json & autoload

- WAJIB `"config": {"prepend-autoloader": false}` — kalau true, dependency module
  override core dan merusak PrestaShop.
- `require.php`: set serendah versi target terendah yang didukung (mis. `>=7.2`
  bila masih dukung 1.7.x lawas; PS9 butuh PHP 8.1 — pisahkan lewat compliancy).
- PSR-4 map ke `src/`. Build rilis: `composer dump-autoload -o --no-dev`,
  sertakan `vendor/`, jangan sertakan dev-deps.
- `ps_versions_compliancy` di constructor main file (WAJIB, divalidasi Validator):
  ```php
  $this->ps_versions_compliancy = ['min' => '1.7.0.0', 'max' => _PS_VERSION_];
  ```

## Dependency yang dihapus core di PS9 (bundle atau ganti)

- `guzzlehttp/guzzle` → Symfony HTTP Client, atau bundle guzzle di vendor module.
- `swiftmailer/swiftmailer` → Symfony Mailer (`Mail::send` core tetap aman lintas versi untuk email module sederhana — prefer ini bila cukup).
- `league/tactician-bundle` → Symfony Messenger.
- Anotasi `PrestaShopBundle\Security` & `sensio/framework-extra-bundle` → atribut Symfony 6.4 native.
- Pola aman: jika butuh HTTP client lintas versi, deteksi & pilih, atau bundle satu lib di module dan pakai itu konsisten.

## Hooks

- Registrasi tetap sama lintas versi: `$this->registerHook('displayHeader')` di `install()`; method `hookDisplayHeader(array $params)`.
- Hook legacy yang DIHAPUS di PS9 (login admin, produk legacy: `actionAdminLoginControllerBefore`, `actionAdminProductsController*`, dll) → daftarkan hook pengganti modern **dengan cabang versi**:
  ```php
  public function install() {
      $hooks = ['displayHeader', 'actionFrontControllerSetMedia'];
      if (version_compare(_PS_VERSION_, '9.0.0', '>=')) {
          $hooks[] = 'actionBackOfficeLoginForm'; // pengganti PS9
      } else {
          $hooks[] = 'actionAdminLoginControllerBefore'; // legacy
      }
      foreach ($hooks as $h) { $this->registerHook($h); }
  }
  ```
- Implementasikan KEDUA method hook (legacy & modern) bila perlu; yang tak terdaftar di suatu versi cukup tak dipanggil.
- Jangan daftarkan hook tanpa mengimplementasi method-nya (PS8+ dev mode lempar exception).
- Jangan pakai hook alias (deprecated PS8).

## Controllers

- **Front controller** (`ModuleFrontController`) aman lintas versi — prefer untuk logika front.
- **Admin**: legacy `ModuleAdminController` (`controllers/admin/`) masih jalan di 1.7/8/9 untuk module — paling portable. Symfony controller butuh service + routing yml dan berubah signifikan di PS9 (`FrameworkBundleAdminController` deprecated → `PrestaShopAdminController`).
- Pola aman cross-version: tetap di `ModuleAdminController` / `getContent()` legacy config kecuali butuh fitur modern. Jangan override method legacy controller core (`initContent`/`run`) — putus di PS9 untuk halaman termigrasi.

## Templates

- **Smarty (.tpl)** lewat `$this->display(__FILE__, 'views/templates/hook/x.tpl')` aman lintas versi untuk output hook module — prefer ini.
- Twig hanya untuk controller Symfony modern. Hindari mencampur kecuali perlu.
- Escape variabel Smarty: `{$var|escape:'html':'UTF-8'}` (Validator error bila tak di-escape sejak v5.14.1); `{$var nofilter}` bila memang sengaja mentah.
- Jangan pakai `_PS_SMARTY_DIR_` (dihapus PS8). Jangan hardcode nama theme (Validator error PS9.1+).

## Persistence (data)

- **ObjectModel** aman SEMUA versi (1.7/8/9) — pilihan default untuk maksimal kompatibilitas. Definisikan `$definition`, buat tabel via SQL di `install()`.
- **Doctrine** hanya untuk target ≥1.7.6 dan konteks modern. Entity di `src/Entity/`, tabel TETAP dibuat via SQL (jangan pakai doctrine schema tool — bikin FK tak kompatibel). Akses: `$this->container->get('doctrine.orm.entity_manager')`.
- Pola aman: bila module sederhana, pakai ObjectModel. Bila butuh ORM & target tak menyertakan 1.7 lawas, Doctrine boleh — tapi tetap satu jalur, jangan campur untuk entity yang sama.
- `Db::getInstance()` + `DbQuery` aman lintas versi untuk query langsung.

## Services / Dependency Injection

- Akses service core berbeda antar versi & konteks. Untuk portabilitas, pakai
  `prestashop/module-lib-service-container` (library resmi) — akses service seragam lintas versi.
- Definisi service module: `config/services.yml` (Symfony), `config/admin/services.yml` & `config/front/services.yml` (legacy container per konteks + Doctrine). Wildcard resource WAJIB exclude `index.php`.
- Override service core berisiko lintas versi (nama service berubah). Prefer **decorate** daripada override; pakai sehemat mungkin.
- `Context` singleton dipecah jadi service di PS9 (`EmployeeContext`, `ShopContext`, dll). Untuk baca masih aman via `Context::getContext()` lintas versi; untuk tulis auth gunakan jalur modern di PS9 (cabang versi).

## Konstanta / API yang dihapus (ganti lintas versi)

- `Tools::jsonEncode/jsonDecode` (dihapus PS8) → `json_encode/json_decode` native.
- `Attribute` (PS8) → `ProductAttribute`.
- `Validate::isPasswd` (PS8) → `isPlaintextPassword`/`isHashedPassword`.
- `PrestaShopAutoload` (PS9) → composer autoload + `prestashop/autoload`.
- `PS_LEGACY_IMAGES`, `PS_HIGHT_DPI` (PS9) → hapus.
- Untuk API yang berbeda total antar versi, sediakan shim privat di module yang mencabangkan implementasi.

## Checklist keluaran cross-version

Sebuah module dianggap cross-version-safe bila:
- [ ] `ps_versions_compliancy` terisi range yang benar
- [ ] Tak ada dependency terlarang PS9 (atau dibundel)
- [ ] Tak ada kelas/method/konstanta/hook yang dihapus tanpa cabang versi
- [ ] Semua cabang versi pakai `_PS_VERSION_`/`version_compare`, bukan tebak
- [ ] composer `prepend-autoloader: false`, autoload benar
- [ ] index.php di tiap folder, variabel Smarty di-escape
- [ ] Lolos psm-validate di 1.7.x, 8.x, dan 9.x
