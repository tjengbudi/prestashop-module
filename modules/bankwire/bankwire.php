<?php
/**
 * Bankwire — pembayaran transfer bank multi-rekening dinamis.
 * Kelola banyak bank (BCA, Niaga, Jenius, dll): tambah/hapus, aktif/nonaktif,
 * dengan icon per bank. Aman lintas PrestaShop 1.7.x / 8.x / 9.x.
 *
 * @author Prestanesia
 * @license http://opensource.org/licenses/afl-3.0.php Academic Free License (AFL 3.0)
 */

use PrestaShop\PrestaShop\Core\Payment\PaymentOption;

if (!defined('_PS_VERSION_')) {
    exit;
}

require_once dirname(__FILE__) . '/classes/BankAccount.php';

class Bankwire extends PaymentModule
{
    /**
     * Kunci Configuration untuk OrderState MILIK module ini.
     *
     * Sengaja BUKAN `PS_OS_BANKWIRE`: kunci itu milik core dan sudah terisi OrderState 10
     * (module_name=ps_wirepayment, template=bankwire) di tiap toko standar. Memakainya
     * ulang membuat module menumpang state orang lain dan memaksa nama template `bankwire`.
     */
    const OS_CONFIG_KEY = 'BANKWIRE_OS_AWAITING';

    /**
     * Nama template email milik module ini, tanpa ekstensi.
     *
     * Harus TIDAK dimiliki core: file disalin ke _PS_ROOT_DIR_/mails/<iso>/ (wajib untuk
     * 1.7.8/8.1 yang belum punya fallback pindai modules/*\/mails/), jadi nama yang
     * menabrak akan menimpa template core dan merusak email module lain.
     */
    const MAIL_TEMPLATE = 'bankwire_multibank';

    /**
     * Nama template yang dipakai module ini SEBELUM 1.0.6, dan yang juga dimiliki core
     * untuk OrderState 10 (ps_wirepayment).
     *
     * Order yang lahir sebelum 1.0.6 tetap duduk di OrderState lama dengan template ini —
     * upgrade sengaja tak memindahkan riwayat order. hookActionEmailSendBefore WAJIB tetap
     * melayani nama ini, kalau tidak email mereka jatuh ke extra_mail_vars ps_wirepayment
     * dan pelanggan menerima nomor rekening MODULE LAIN (atau placeholder mentah bila
     * module itu dihapus).
     *
     * Aman terhadap order milik ps_wirepayment: hook hanya mengisi bila getBankForOrder()
     * menemukan baris peta bankwire_order, yang hanya ada untuk order kita sendiri.
     */
    const LEGACY_MAIL_TEMPLATE = 'bankwire';

    /** @var string */
    private $_html = '';

    /** @var array<int, string> */
    private $_postErrors = array();

    /** @var string Folder icon absolut */
    private $iconDir;

    /** @var array<int, string> Ekstensi icon diizinkan */
    private $iconExtensions = array('jpg', 'jpeg', 'png', 'gif');

    /** @var int Ukuran maksimum icon (byte) */
    private $iconMaxSize = 1048576; // 1 MB

    /** @var bool|string false bila icon aman, pesan error bila upload gagal */
    private $iconError = false;

    public function __construct()
    {
        $this->name = 'bankwire';
        $this->tab = 'payments_gateways';
        $this->version = '1.0.6';
        // 1.7.7 — versi pertama yang punya hook actionEmailSendBefore (dipakai mengisi
        // placeholder bank pada email non-inisial). Context::$currentLocale yang dipakai
        // formatPrice() ada sejak 1.7.6, jadi 1.7.7 adalah batas yang mengikat.
        $this->ps_versions_compliancy = array('min' => '1.7.7.0', 'max' => _PS_VERSION_);
        $this->author = 'Prestanesia';
        $this->controllers = array('validation');

        $this->currencies = true;
        $this->currencies_mode = 'checkbox';

        $this->bootstrap = true;
        parent::__construct();

        $this->displayName = $this->trans('Bankwire (multi-bank)', array(), 'Modules.Bankwire.Admin');
        $this->description = $this->trans('Accept payments via transfer to several bank accounts that you can add, remove, enable or disable dynamically.', array(), 'Modules.Bankwire.Admin');
        $this->confirmUninstall = $this->trans('Are you sure you want to uninstall? All configured bank accounts will be deleted.', array(), 'Modules.Bankwire.Admin');

        $this->iconDir = dirname(__FILE__) . '/views/img/banks/';

        if (!count(Currency::checkPaymentCurrencies($this->id))) {
            $this->warning = $this->trans('No currency has been set for this module.', array(), 'Modules.Bankwire.Admin');
        }
    }

    /**
     * @return bool
     */
    public function install()
    {
        if (!parent::install()) {
            return false;
        }

        // PrestaShop tidak me-rollback install yang gagal separuh jalan: tanpa
        // pembersihan ini, module tercatat terpasang & aktif dengan hook tak lengkap
        // atau tabel yatim, sementara UI melaporkan gagal.
        if (!$this->registerHook('paymentOptions')
            || !$this->registerHook('displayPaymentReturn')
            || !$this->registerHook('actionEmailSendBefore')
            || !$this->installDb()
            || !$this->ensureOrderState()
        ) {
            $this->uninstallDb();
            parent::uninstall();

            return false;
        }

        // Default reservasi global (hari); bank yang tak set (0) mengikuti nilai ini.
        // 7 = sama seperti default ps_wirepayment.
        Configuration::updateValue('BANKWIRE_RESERVATION_DAYS', 7);
        // Kunci tanda tangan pilihan bank (signBankOption): milik module, independen dari
        // konstanta core — _PS_PASSWD_KEY_ tak terdefinisi di PS 8/9 dan PHP 8 fatal pada
        // konstanta tak dikenal. Lihat getSigningKey().
        if (!Configuration::get('BANKWIRE_SIGNING_KEY')) {
            Configuration::updateValue('BANKWIRE_SIGNING_KEY', bin2hex(random_bytes(32)));
        }

        $this->copyMailTemplates();
        $this->ensureIconDir();

        return true;
    }

    /**
     * @return bool
     */
    public function uninstall()
    {
        // parent::uninstall() dulu: bila gagal, module tetap terpasang dan aktif, jadi
        // tabel serta icon harus masih utuh — hookPaymentOptions akan tetap dipanggil.
        if (!parent::uninstall()) {
            return false;
        }

        Configuration::deleteByName('BANKWIRE_RESERVATION_DAYS');

        $this->uninstallDb();
        $this->removeIconDir();
        $this->removeMailTemplates();
        $this->retireOrderState();

        return true;
    }

    /**
     * Buat tabel: bankwire_account (data bank) + bankwire_order (map order→bank).
     *
     * @return bool
     */
    private function installDb()
    {
        $prefix = _DB_PREFIX_;
        $engine = _MYSQL_ENGINE_;

        $sql = array();
        $sql[] = 'CREATE TABLE IF NOT EXISTS `' . $prefix . 'bankwire_account` (
            `id_bankwire_account` INT(10) UNSIGNED NOT NULL AUTO_INCREMENT,
            `bank_name` VARCHAR(128) NOT NULL,
            `owner` VARCHAR(128) DEFAULT NULL,
            `details` VARCHAR(1024) DEFAULT NULL,
            `address` VARCHAR(1024) DEFAULT NULL,
            `icon` VARCHAR(128) DEFAULT NULL,
            `active` TINYINT(1) UNSIGNED NOT NULL DEFAULT 1,
            `position` INT(10) UNSIGNED NOT NULL DEFAULT 0,
            `reservation_days` INT(10) UNSIGNED NOT NULL DEFAULT 0,
            `date_add` DATETIME NOT NULL,
            `date_upd` DATETIME NOT NULL,
            PRIMARY KEY (`id_bankwire_account`)
        ) ENGINE=' . $engine . ' DEFAULT CHARSET=utf8mb4;';

        // Tabel multibahasa: catatan informatif per bank per bahasa (custom_text).
        $sql[] = 'CREATE TABLE IF NOT EXISTS `' . $prefix . 'bankwire_account_lang` (
            `id_bankwire_account` INT(10) UNSIGNED NOT NULL,
            `id_lang` INT(10) UNSIGNED NOT NULL,
            `custom_text` MEDIUMTEXT,
            PRIMARY KEY (`id_bankwire_account`, `id_lang`)
        ) ENGINE=' . $engine . ' DEFAULT CHARSET=utf8mb4;';

        // active + position hidup di sini (per toko), bukan di bankwire_account: toggle
        // dan urutan checkout harus independen tiap toko yang berbagi bank yang sama.
        // Kolom senama di bankwire_account dipertahankan sebagai fallback saat jendela
        // upgrade (file baru melayani FO sebelum upgrade 1.0.3 jalan).
        $sql[] = 'CREATE TABLE IF NOT EXISTS `' . $prefix . 'bankwire_account_shop` (
            `id_bankwire_account` INT(10) UNSIGNED NOT NULL,
            `id_shop` INT(10) UNSIGNED NOT NULL,
            `active` TINYINT(1) UNSIGNED NOT NULL DEFAULT 1,
            `position` INT(10) UNSIGNED NOT NULL DEFAULT 0,
            PRIMARY KEY (`id_bankwire_account`, `id_shop`)
        ) ENGINE=' . $engine . ' DEFAULT CHARSET=utf8mb4;';

        $sql[] = 'CREATE TABLE IF NOT EXISTS `' . $prefix . 'bankwire_order` (
            `id_order` INT(10) UNSIGNED NOT NULL,
            `id_bankwire_account` INT(10) UNSIGNED NOT NULL,
            PRIMARY KEY (`id_order`)
        ) ENGINE=' . $engine . ' DEFAULT CHARSET=utf8mb4;';

        foreach ($sql as $query) {
            if (!Db::getInstance()->execute($query)) {
                return false;
            }
        }

        // Tabel asosiasi baru saja lahir dalam request ini — cache keberadaannya
        // mungkin sudah terisi false sebelum ini.
        BankAccount::resetShopTableCache();

        return true;
    }

    /**
     * @return bool
     */
    private function uninstallDb()
    {
        $prefix = _DB_PREFIX_;
        Db::getInstance()->execute('DROP TABLE IF EXISTS `' . $prefix . 'bankwire_account`');
        Db::getInstance()->execute('DROP TABLE IF EXISTS `' . $prefix . 'bankwire_account_lang`');
        Db::getInstance()->execute('DROP TABLE IF EXISTS `' . $prefix . 'bankwire_account_shop`');
        Db::getInstance()->execute('DROP TABLE IF EXISTS `' . $prefix . 'bankwire_order`');

        return true;
    }

    /**
     * Buat OrderState "menunggu pembayaran" bila belum ada. Idempotent via Configuration.
     *
     * @return bool
     */
    /**
     * Id OrderState hidup milik module ini — SUMBER KEBENARAN, dari `ps_order_state`.
     *
     * Kolom `module_name` yang menentukan kepemilikan, bukan baris `ps_configuration`:
     * ia otoritatif, tak berdimensi toko (sama seperti tabelnya), dan tetap benar setelah
     * baris config tersapu atau uninstall gagal separuh. Urut menaik agar deterministik.
     *
     * @return array<int, int>
     */
    private function findOwnedOrderStates()
    {
        $rows = Db::getInstance()->executeS(
            'SELECT `id_order_state` FROM `' . _DB_PREFIX_ . 'order_state`'
            . ' WHERE `module_name` = "' . pSQL($this->name) . '" AND `deleted` = 0'
            . ' ORDER BY `id_order_state` ASC'
        );

        $ids = array();
        foreach ((array) $rows as $row) {
            $id = (int) $row['id_order_state'];
            if ($id > 0) {
                $ids[] = $id;
            }
        }

        return $ids;
    }

    /**
     * Pilih state yang dipertahankan saat ada duplikat: yang PALING BANYAK dirujuk order.
     *
     * Diukur ke `ps_orders`, bukan ditebak dari urutan id. Seri (termasuk semuanya nol
     * order) diputus id terkecil supaya hasilnya deterministik. Yang dipertahankan adalah
     * yang paling sedikit menuntut pemindahan order, jadi jendela di mana riwayat order
     * tersentuh sekecil mungkin.
     *
     * @param array<int, int> $ids
     *
     * @return int
     */
    private function pickCanonicalOrderState($ids)
    {
        $best = (int) $ids[0];
        $bestCount = -1;

        foreach ($ids as $id) {
            $count = (int) Db::getInstance()->getValue(
                'SELECT COUNT(*) FROM `' . _DB_PREFIX_ . 'orders`'
                . ' WHERE `current_state` = ' . (int) $id,
                false // jangan dari cache: hitungan ini memutuskan riwayat order mana yang dipindah
            );
            if ($count > $bestCount) {
                $best = (int) $id;
                $bestCount = $count;
            }
        }

        return $best;
    }

    /**
     * Pindahkan order dan riwayatnya dari satu OrderState ke OrderState lain.
     *
     * Tanpa ini, mempensiunkan duplikat menelantarkan setiap order yang lahir di sana:
     * statusnya hilang dari dropdown BO sehingga merchant tak bisa memindahkannya balik,
     * dan `hookDisplayPaymentReturn` jatuh ke cabang gagal — pelanggan membaca "We noticed
     * a problem with your order" dan tak pernah melihat rekening tujuan.
     *
     * `order_history` ikut diperbarui supaya riwayat menunjuk status yang masih hidup;
     * baris riwayat yang menggantung ke status pensiun tampil kosong di BO.
     *
     * @param int $from
     * @param int $to
     *
     * @return void
     */
    private function migrateOrdersBetweenStates($from, $to)
    {
        if ((int) $from === (int) $to) {
            return;
        }

        Db::getInstance()->execute(
            'UPDATE `' . _DB_PREFIX_ . 'orders` SET `current_state` = ' . (int) $to
            . ' WHERE `current_state` = ' . (int) $from
        );
        Db::getInstance()->execute(
            'UPDATE `' . _DB_PREFIX_ . 'order_history` SET `id_order_state` = ' . (int) $to
            . ' WHERE `id_order_state` = ' . (int) $from
        );
    }

    /**
     * Tulis ulang cache penunjuk state jadi TEPAT satu baris global.
     *
     * Seluruh baris dibuang dulu: baris shop-scoped peninggalan build lama membayangi baris
     * global untuk `Configuration::get()`, dan perbedaan jawaban antara dua API itulah yang
     * dulu melahirkan OrderState kedua. Kehilangan nilai per-toko di sini bukan kehilangan
     * data — nilainya menunjuk state yang baru saja dikonsolidasikan, dan sumber kebenaran
     * tetap `ps_order_state`.
     *
     * @param int $id
     *
     * @return void
     */
    private function syncOrderStateCache($id)
    {
        Configuration::deleteByName(self::OS_CONFIG_KEY);
        Configuration::updateGlobalValue(self::OS_CONFIG_KEY, (int) $id);
    }

    /**
     * Id OrderState module untuk jalur RUNTIME (checkout, hook). Read-only.
     *
     * Cache dibaca dulu karena murah, tapi divalidasi terhadap sumber kebenaran sebelum
     * dipakai: cache yang menunjuk state pensiun, state module lain, atau state yang sudah
     * hilang tak boleh membuat order baru lahir di status yang salah. Bila cache tak sahih,
     * jawabannya diambil dari `ps_order_state` — TANPA menulis apa pun, karena jalur
     * checkout bukan tempat memperbaiki state instalasi; `ensureOrderState()` yang menulis.
     *
     * @return int 0 bila module tak punya OrderState hidup
     */
    public function getOrderStateId()
    {
        $cached = (int) Configuration::getGlobalValue(self::OS_CONFIG_KEY);
        if ($cached > 0) {
            $state = new OrderState($cached);
            if (Validate::isLoadedObject($state)
                && !$state->deleted
                && $state->module_name === $this->name
            ) {
                return $cached;
            }
        }

        $owned = $this->findOwnedOrderStates();

        return empty($owned) ? 0 : (int) $owned[0];
    }

    public function ensureOrderState()
    {
        // JANGAN memakai ulang PS_OS_BANKWIRE: di toko standar itu OrderState 10 milik
        // ps_wirepayment (module_name=ps_wirepayment, template=bankwire). Menumpanginya
        // memaksa kita memakai nama template `bankwire` milik core, dan penyalinan template
        // lalu menimpa file yang dipakai order ps_wirepayment juga.
        //
        // SUMBER KEBENARAN = `ps_order_state.module_name`, BUKAN ps_configuration.
        // Empat ronde perbaikan sebelumnya semua gagal di akar yang sama: penunjuk config
        // dipakai sebagai otoritas. Itu model yang salah — `ps_order_state` tak berdimensi
        // toko sementara `ps_configuration` berdimensi toko, jadi keduanya tak bisa
        // didamaikan; dan state yang kehilangan penunjuknya (uninstall yang gagal separuh,
        // baris config tersapu) jadi TAK TERLIHAT, sehingga install berikutnya membuat state
        // kedua. Kolom `module_name` otoritatif, lintas-toko, dan selamat dari kedua kelas itu.
        // Baris config turun pangkat jadi CACHE yang selalu boleh dibangun ulang dari sini.
        $owned = $this->findOwnedOrderStates();

        if (count($owned) > 1) {
            // Konsolidasi WAJIB memindahkan order. Versi sebelumnya memilih "id tertua"
            // dengan komentar "paling mungkin dirujuk order" — tebakan yang tak pernah
            // diverifikasi, dan order di state non-kanonik tertinggal di status yang
            // `deleted=1` sehingga halaman konfirmasi pelanggan jatuh ke cabang gagal.
            $canonical = $this->pickCanonicalOrderState($owned);
            foreach ($owned as $id) {
                if ((int) $id === $canonical) {
                    continue;
                }
                $this->migrateOrdersBetweenStates((int) $id, $canonical);
                $dup = new OrderState((int) $id);
                if (Validate::isLoadedObject($dup)) {
                    $dup->deleted = true;
                    $dup->send_email = false;
                    $dup->update();
                }
            }
            $this->syncOrderStateCache($canonical);

            return true;
        }

        if (count($owned) === 1) {
            $this->syncOrderStateCache((int) $owned[0]);

            return true;
        }

        // Nol state milik kita — buang penunjuk basi supaya tak membayangi cache baru.
        Configuration::deleteByName(self::OS_CONFIG_KEY);

        $newState = new OrderState();
        $newState->send_email = true;
        $newState->module_name = $this->name;
        $newState->invoice = false;
        $newState->color = '#002F95';
        $newState->unremovable = false;
        $newState->logable = false;
        $newState->delivery = false;
        $newState->hidden = false;
        $newState->shipped = false;
        $newState->paid = false;

        $languages = Language::getLanguages(true);
        foreach ($languages as $lang) {
            if ($lang['iso_code'] == 'id') {
                $newState->name[(int) $lang['id_lang']] = 'Menunggu transfer bank (multi-bank)';
            } else {
                $newState->name[(int) $lang['id_lang']] = 'Awaiting bank wire payment (multi-bank)';
            }
            $newState->template[(int) $lang['id_lang']] = self::MAIL_TEMPLATE;
        }

        if (!$newState->add()) {
            return false;
        }

        // GLOBAL, bukan shop-scoped: PS_OS_BANKWIRE yang digantikan kunci ini ditulis core
        // sebagai baris id_shop NULL. updateValue() menulis per-shop, jadi di multistore
        // toko lain membaca false -> state 0 -> checkout mati.
        $this->syncOrderStateCache((int) $newState->id);
        $logo = dirname(__FILE__) . '/logo.gif';
        if (is_file($logo)) {
            @copy($logo, _PS_IMG_DIR_ . 'tmp/order_state_mini_' . (int) $newState->id . '_1.gif');
        }

        return true;
    }

    /**
     * Salin template email module ke _PS_MAIL_DIR_ — dari sanalah email benar-benar
     * dikirim, bukan dari folder module. Dipanggil dari install() (bukan dari
     * installOrderState(), yang early-return saat OrderState lama masih ada sehingga
     * install ulang tak pernah menyalin) dan dari upgrade.
     *
     * Penyalinan ini TAK BISA dihapus: OrderHistory memanggil Mail::Send dengan
     * _PS_MAIL_DIR_ sebagai basis, dan Mail::getTemplateBasePath() baru memindai
     * modules/<x>/mails/ sebagai fallback SEJAK 9.1 — di 1.7.8 dan 8.1 fallback itu tak
     * ada, jadi template wajib hadir di _PS_ROOT_DIR_/mails/<iso>/.
     *
     * Yang diperbaiki adalah NAMANYA: self::MAIL_TEMPLATE milik module ini sendiri, jadi
     * tak ada file core yang tertimpa. Versi lama memakai nama `bankwire`, yang dimiliki
     * template OrderState 10 core dan dipakai order ps_wirepayment juga.
     *
     * @return void
     */
    public function copyMailTemplates()
    {
        foreach (Language::getLanguages(false) as $lang) {
            $iso = strtolower($lang['iso_code']);
            $src = is_dir(dirname(__FILE__) . '/mails/' . $iso) ? $iso : 'en';
            foreach (array('html', 'txt') as $ext) {
                $mail = dirname(__FILE__) . '/mails/' . $src . '/' . self::MAIL_TEMPLATE . '.' . $ext;
                if (is_file($mail) && is_dir(_PS_MAIL_DIR_ . $iso)) {
                    @copy($mail, _PS_MAIL_DIR_ . $iso . '/' . self::MAIL_TEMPLATE . '.' . $ext);
                }
            }
        }
    }

    /**
     * Hapus salinan template email module dari _PS_MAIL_DIR_ saat uninstall.
     *
     * Aman JUSTRU karena namanya milik kita (self::MAIL_TEMPLATE): tak ada template core
     * maupun module lain yang bernama begitu. Versi lama tak punya pembersihan sama sekali,
     * dan karena ia menimpa nama milik core, memulihkannya memang mustahil dari sini —
     * itulah yang diperbaiki upgrade-1.0.6.
     *
     * @return void
     */
    private function removeMailTemplates()
    {
        foreach (Language::getLanguages(false) as $lang) {
            $iso = strtolower($lang['iso_code']);
            foreach (array('html', 'txt') as $ext) {
                $path = _PS_MAIL_DIR_ . $iso . '/' . self::MAIL_TEMPLATE . '.' . $ext;
                if (is_file($path)) {
                    @unlink($path);
                }
            }
        }
    }

    /**
     * Pensiunkan OrderState milik module saat uninstall — SOFT delete, bukan hapus baris.
     *
     * Menghapus barisnya akan memutus riwayat order yang pernah memakai status ini
     * (`orders.current_state` dan `order_history` menyimpan id-nya). `deleted = true` adalah
     * mekanisme core untuk menyembunyikannya dari daftar BO sambil menjaga riwayat utuh.
     *
     * Tanpa ini, state tertinggal hidup dengan `send_email = 1` dan template yang filenya
     * sudah dihapus removeMailTemplates(): di 1.7.8/8.1 resolusi template menghasilkan ''
     * sehingga BO gagal mengubah status, dan di 9.1 email tetap terkirim dengan placeholder
     * mentah lewat fallback pindai modules/*\/mails/.
     *
     * @return void
     */
    private function retireOrderState()
    {
        // Dari SUMBER KEBENARAN, bukan dari penunjuk config. Versi sebelumnya membaca satu
        // baris global; pada instalasi yang penunjuknya hanya shop-scoped, uninstall lapor
        // sukses dan menghapus template email sementara OrderState tetap `deleted=0` dan
        // `send_email=1` — status BO gagal berubah di 1.7.8/8.1, dan di 9.1 email tetap
        // terkirim membawa placeholder mentah lewat fallback pindai modules/*/mails/.
        foreach ($this->findOwnedOrderStates() as $id) {
            $state = new OrderState((int) $id);
            if (Validate::isLoadedObject($state)) {
                $state->deleted = true;
                $state->send_email = false;
                $state->update();
            }
        }

        Configuration::deleteByName(self::OS_CONFIG_KEY);
        Configuration::deleteByName('BANKWIRE_SIGNING_KEY');
    }

    /**
     * Hapus seluruh file icon saat uninstall. Tanpa ini, icon basi bank_<id>.<ext>
     * akan dipungut ulang oleh rekening baru yang kebetulan mendapat id yang sama.
     *
     * @return void
     */
    private function removeIconDir()
    {
        if (!is_dir($this->iconDir)) {
            return;
        }

        foreach ((array) scandir($this->iconDir) as $file) {
            if ($file === '.' || $file === '..' || $file === 'index.php') {
                continue;
            }
            $path = $this->iconDir . $file;
            if (is_file($path)) {
                @unlink($path);
            }
        }

        // index.php dihapus terakhir: bila rmdir gagal (permission, sisa file), folder
        // tidak boleh tertinggal tanpa pelindung directory listing.
        $index = $this->iconDir . 'index.php';
        @unlink($index);

        if (!@rmdir($this->iconDir) && is_dir($this->iconDir)) {
            @copy(dirname(__FILE__) . '/index.php', $index);
        }
    }

    /**
     * @return void
     */
    private function ensureIconDir()
    {
        if (!is_dir($this->iconDir)) {
            @mkdir($this->iconDir, 0755, true);
        }
        $index = $this->iconDir . 'index.php';
        if (!is_file($index)) {
            @copy(dirname(__FILE__) . '/index.php', $index);
        }
        $this->cleanIconDir();
    }

    // ------------------------------------------------------------------
    // Admin (getContent) — CRUD bank
    // ------------------------------------------------------------------

    /**
     * @return string
     */
    public function getContent()
    {
        $this->ensureIconDir();

        $showForm = false;

        if (Tools::isSubmit('submitBankwireSettings')) {
            // Setting global (masa reservasi default). Redirect setelah simpan agar
            // refresh tidak mengirim ulang.
            $this->redirectAfterAction($this->processSaveSettings());
        } elseif (Tools::isSubmit('submitBank')) {
            // Redirect saat sukses: tanpa ini F5/Back mengirim ulang form dan membuat
            // rekening duplikat (id 0 selalu masuk cabang add()). Bila gagal, tetap di
            // form supaya pesan error dan input admin tidak hilang.
            if ($this->processSaveBank()) {
                $this->redirectAfterSave($this->iconError);
            }
            $showForm = true;
        } elseif (Tools::isSubmit('deletebank')) {
            // Redirect setelah aksi: tanpa ini, refresh/back mengeksekusi ulang aksi
            // dari URL — togglebank jadi bolak-balik dan posisi bergeser lagi.
            $this->redirectAfterAction($this->processDeleteBank());
        } elseif (Tools::isSubmit('togglebank')) {
            $this->redirectAfterAction($this->processToggleBank());
        } elseif (Tools::isSubmit('positionbank')) {
            $this->redirectAfterAction($this->processPositionBank());
        } else {
            $action = Tools::getValue('action');
            $showForm = ($action === 'addbank' || $action === 'editbank');
        }

        if (Tools::getValue('bankwire_error')) {
            $this->_html .= $this->displayError($this->trans('The action could not be completed.', array(), 'Modules.Bankwire.Admin'));
        }

        if (Tools::getValue('bankwire_icon_error')) {
            $this->_html .= $this->displayWarning($this->trans('The bank account was saved, but the icon could not be uploaded.', array(), 'Modules.Bankwire.Admin'));
        }

        $this->_html .= $showForm ? $this->renderBankForm() : $this->renderBankList();

        return $this->_html;
    }

    /**
     * Kembali ke daftar bank dengan URL bersih setelah aksi GET, agar refresh/back
     * tidak menjalankan ulang aksi tersebut.
     *
     * @return void
     */
    /**
     * Redirect setelah simpan sukses. Kegagalan icon ikut lewat URL supaya tidak
     * tertelan redirect dan terbaca sebagai sukses penuh.
     *
     * @param bool|string $iconError
     *
     * @return void
     */
    private function redirectAfterSave($iconError)
    {
        $params = array('conf' => 4);
        if ($iconError !== false) {
            $params['bankwire_icon_error'] = 1;
        }

        Tools::redirect($this->moduleAdminLink($params));
    }

    private function redirectAfterAction($success)
    {
        // Redirect membuang $this->_html, termasuk pesan error — jadi kegagalan harus
        // ikut lewat URL, kalau tidak admin melihat konfirmasi sukses palsu.
        Tools::redirect($this->moduleAdminLink(
            $success ? array('conf' => 4) : array('bankwire_error' => 1)
        ));
    }

    /**
     * URL admin module ini (dengan token). Aman lintas versi.
     *
     * @param array<string, mixed> $params
     *
     * @return string
     */
    private function moduleAdminLink(array $params = array())
    {
        // Base configure SAJA -> PS memetakan ke route Symfony yang benar di 8/9
        // (improve/modules/manage/.../configure/<mod>) dan legacy di 1.7.8, lengkap
        // dengan token. Menaruh param lain (action, id) ke dalam array ini membuat
        // pemetaan route gagal dan jatuh ke URL legacy rusak, jadi tempel sendiri.
        $base = $this->context->link->getAdminLink(
            'AdminModules',
            true,
            array(),
            array('configure' => $this->name)
        );

        foreach ($params as $key => $value) {
            $base .= (strpos($base, '?') !== false ? '&' : '?')
                . $key . '=' . urlencode((string) $value);
        }

        return $base;
    }

    /**
     * Validasi + simpan (add/edit) bank. Termasuk upload icon.
     * Hanya set pesan; render diserahkan ke getContent().
     *
     * @return bool true bila tersimpan (tampilkan daftar), false bila gagal (tetap di form)
     */
    /**
     * Simpan setting global. Saat ini: masa reservasi default (hari).
     *
     * @return bool
     */
    private function processSaveSettings()
    {
        $days = Tools::getValue('BANKWIRE_RESERVATION_DAYS');

        // Tolak nilai non-integer-positif: kolom UNSIGNED, dan tampilan front memakainya
        // langsung. Kosong dibiarkan jadi 0 (tak ada reservasi).
        if ($days !== false && $days !== '' && !Validate::isUnsignedInt($days)) {
            return false;
        }

        Configuration::updateValue('BANKWIRE_RESERVATION_DAYS', (int) $days);

        return true;
    }

    private function processSaveBank()
    {
        $id = (int) Tools::getValue('id_bankwire_account');

        // Tanpa cek ini, id yang menunjuk baris terhapus (atau milik toko lain) tetap
        // masuk cabang update(): UPDATE ... WHERE id = 0 mengubah 0 baris tapi tetap
        // melaporkan sukses.
        if ($id) {
            $bank = $this->loadBankForAdmin($id);
            if ($bank === null) {
                $this->_html .= $this->displayError($this->trans('This bank account no longer exists.', array(), 'Modules.Bankwire.Admin'));

                return false;
            }
        } else {
            $bank = new BankAccount();
        }

        $bankName = trim((string) Tools::getValue('bank_name'));
        if ($bankName === '') {
            $this->_postErrors[] = $this->trans('Bank name is required.', array(), 'Modules.Bankwire.Admin');
        }
        // Duplikat nama = dua opsi "Pay by X" identik di checkout yang tak bisa
        // dibedakan pelanggan. Case-insensitive; baris sendiri dikecualikan saat edit.
        if (BankAccount::existsByName($bankName, $id)) {
            $this->_postErrors[] = $this->trans(
                'A bank account with this name already exists. Please choose a different name.',
                array(),
                'Modules.Bankwire.Admin'
            );
        }

        if (count($this->_postErrors)) {
            foreach ($this->_postErrors as $err) {
                $this->_html .= $this->displayError($err);
            }

            return false;
        }

        $bank->bank_name = $bankName;
        $bank->owner = (string) Tools::getValue('owner');
        $bank->details = (string) Tools::getValue('details');
        $bank->address = (string) Tools::getValue('address');
        $bank->active = (bool) Tools::getValue('active');
        // 0 = ikut default global BANKWIRE_RESERVATION_DAYS.
        $bank->reservation_days = (int) Tools::getValue('reservation_days');

        // custom_text multibahasa: satu textarea per bahasa (name custom_text_<id_lang>).
        $customText = array();
        foreach (Language::getLanguages(false) as $lang) {
            $customText[(int) $lang['id_lang']] = (string) Tools::getValue('custom_text_' . (int) $lang['id_lang']);
        }
        $bank->custom_text = $customText;

        // validateFields()/validateFieldsLang() melempar PrestaShopException, bukan
        // mengembalikan false — tangkap di sini supaya admin dapat pesan, bukan halaman fatal.
        $fieldErrors = $bank->validateFields(false, true);
        if ($fieldErrors !== true) {
            $this->_html .= $this->displayError(is_string($fieldErrors) ? $fieldErrors : $this->trans('Could not save bank account.', array(), 'Modules.Bankwire.Admin'));

            return false;
        }
        $langErrors = $bank->validateFieldsLang(false, true);
        if ($langErrors !== true) {
            $this->_html .= $this->displayError(is_string($langErrors) ? $langErrors : $this->trans('Could not save bank account.', array(), 'Modules.Bankwire.Admin'));

            return false;
        }

        $isNew = !Validate::isLoadedObject($bank);

        if ($isNew) {
            // getNextPosition() (baca) + add() (tulis) dibungkus lock supaya dua admin
            // yang submit hampir bersamaan tak berebut posisi yang sama.
            $saved = BankAccount::withPositionLock(function () use ($bank) {
                $bank->position = BankAccount::getNextPosition();

                return $bank->add();
            });
        } else {
            $saved = $bank->update();
        }

        if (!$saved) {
            $this->_html .= $this->displayError($this->trans('Could not save bank account.', array(), 'Modules.Bankwire.Admin'));

            return false;
        }

        // Hanya saat dibuat. Mengaitkan ulang tiap simpan akan melebarkan bank milik
        // satu toko ke semua toko begitu di-edit dari konteks "semua toko" — dan
        // pelebaran itu tidak bisa dibatalkan lewat admin.
        if ($isNew) {
            BankAccount::associateToCurrentShops((int) $bank->id);
        }

        // active kini milik baris per-toko: tulis nilai form ke toko konteks aktif.
        // ($bank->update()/add() menyimpannya di baris utama sbg fallback; per-shop
        // adalah sumber kebenaran saat kolom sudah ada.) Toko lain tak tersentuh.
        BankAccount::setActiveForCurrentShops((int) $bank->id, (bool) Tools::getValue('active'));

        // Bank tersimpan; icon boleh gagal sendiri. Kegagalan itu harus ikut lewat URL
        // karena redirect setelahnya membuang $this->_html — kalau tidak, admin melihat
        // konfirmasi hijau padahal icon-nya tidak pernah terpasang.
        $this->iconError = $this->handleIconUpload($bank);

        return true;
    }

    /**
     * Proses upload icon bila ada file. Return false bila sukses / tak ada file, string error bila gagal.
     *
     * @param BankAccount $bank
     *
     * @return bool|string
     */
    private function handleIconUpload(BankAccount $bank)
    {
        if (!isset($_FILES['icon']) || !isset($_FILES['icon']['tmp_name']) || !is_uploaded_file($_FILES['icon']['tmp_name'])) {
            return false;
        }

        $file = $_FILES['icon'];

        $validation = ImageManager::validateUpload($file, $this->iconMaxSize, $this->iconExtensions);
        if ($validation !== false) {
            return $validation;
        }

        $ext = strtolower(pathinfo($file['name'], PATHINFO_EXTENSION));
        if (!in_array($ext, $this->iconExtensions, true)) {
            $ext = 'png';
        }

        $this->ensureIconDir();

        $fileName = 'bank_' . (int) $bank->id . '.' . $ext;
        $dest = $this->iconDir . $fileName;
        $oldIcon = $bank->icon;

        if (!ImageManager::resize($file['tmp_name'], $dest, null, null, $ext)) {
            return $this->trans('Could not save the icon image.', array(), 'Modules.Bankwire.Admin');
        }

        // Hapus icon lama HANYA setelah icon baru terbukti tersimpan
        if ($oldIcon && $oldIcon !== $fileName && is_file($this->iconDir . $oldIcon)) {
            @unlink($this->iconDir . $oldIcon);
        }

        $bank->icon = $fileName;
        // Hanya kolom icon yang ditulis: update penuh baris akan menimpa field lain
        // (bank_name, owner, dst.) dengan nilai objek yang dimuat di awal request —
        // perubahan admin lain di antara load dan simpan ikut tertimpa (TOCTOU).
        $bank->update(array('icon'));

        $this->cleanIconDir();

        return false;
    }

    /**
     * Buang file asing di folder icon (mis. artefak 'fileType' dari render field file).
     * Hanya menyimpan index.php dan icon bernama bank_<id>.<ext> — folder eksklusif module.
     *
     * @return void
     */
    private function cleanIconDir()
    {
        if (!is_dir($this->iconDir)) {
            return;
        }

        foreach ((array) scandir($this->iconDir) as $entry) {
            if ($entry === '.' || $entry === '..' || $entry === 'index.php') {
                continue;
            }
            if (preg_match('/^bank_\d+\.(jpg|jpeg|png|gif)$/i', $entry)) {
                continue;
            }
            $path = $this->iconDir . $entry;
            if (is_file($path)) {
                @unlink($path);
            }
        }
    }

    /**
     * @return void
     */
    /**
     * Muat bank dari id URL/POST, hanya bila terkait toko pada konteks aktif.
     * Tanpa cek ini admin toko B bisa mengubah rekening milik toko A.
     *
     * @param int $id
     *
     * @return BankAccount|null
     */
    private function loadBankForAdmin($id)
    {
        $id = (int) $id;
        if (!$id || !BankAccount::isAssociatedToCurrentShop($id)) {
            return null;
        }

        $bank = new BankAccount($id);

        return Validate::isLoadedObject($bank) ? $bank : null;
    }

    private function processDeleteBank()
    {
        $bank = $this->loadBankForAdmin(Tools::getValue('id_bankwire_account'));
        if ($bank === null) {
            return false;
        }

        return $bank->detachFromCurrentShop() !== 'failed';
    }

    /**
     * @return bool
     */
    private function processToggleBank()
    {
        $bank = $this->loadBankForAdmin(Tools::getValue('id_bankwire_account'));

        return $bank !== null && $bank->toggleStatus();
    }

    /**
     * @return bool
     */
    private function processPositionBank()
    {
        $way = (int) Tools::getValue('way'); // 1 = turun (posisi+1), 0 = naik (posisi-1)
        $idBank = (int) Tools::getValue('id_bankwire_account');

        // Baca urutan + tukar posisi dibungkus lock supaya dua admin yang submit
        // hampir bersamaan tak berebut baca MAX/posisi yang sama sebelum salah satu
        // UPDATE ter-commit.
        return (bool) BankAccount::withPositionLock(function () use ($way, $idBank) {
            $bank = $this->loadBankForAdmin($idBank);
            if ($bank === null) {
                return false;
            }

            $banks = BankAccount::getAllBanks();
            $ids = array();
            foreach ($banks as $row) {
                $ids[] = (int) $row['id_bankwire_account'];
            }
            $index = array_search((int) $bank->id, $ids, true);
            if ($index === false) {
                return false;
            }

            $swapIndex = $way ? $index + 1 : $index - 1;
            if ($swapIndex < 0 || $swapIndex >= count($ids)) {
                // Sudah di batas urutan (paling atas/bawah) — bukan kegagalan, tak
                // ada yang perlu ditukar.
                return true;
            }

            $otherId = (int) $ids[$swapIndex];

            return BankAccount::swapPositionInCurrentShops((int) $bank->id, $otherId);
        });
    }

    /**
     * Daftar bank (Smarty custom — bukan HelperList).
     *
     * @return string
     */
    private function renderBankList()
    {
        $banks = BankAccount::getAllBanks();
        $rows = array();
        foreach ($banks as $row) {
            $iconUrl = '';
            if (!empty($row['icon']) && is_file($this->iconDir . $row['icon'])) {
                $iconUrl = $this->_path . 'views/img/banks/' . $row['icon'];
            }
            $rows[] = array(
                'id' => (int) $row['id_bankwire_account'],
                'bank_name' => $row['bank_name'],
                'owner' => $row['owner'],
                'active' => (bool) $row['active'],
                'position' => (int) $row['position'],
                'icon_url' => $iconUrl,
                'edit_url' => $this->moduleAdminLink(array('action' => 'editbank', 'id_bankwire_account' => (int) $row['id_bankwire_account'])),
                'delete_url' => $this->moduleAdminLink(array('deletebank' => 1, 'id_bankwire_account' => (int) $row['id_bankwire_account'])),
                'toggle_url' => $this->moduleAdminLink(array('togglebank' => 1, 'id_bankwire_account' => (int) $row['id_bankwire_account'])),
                'up_url' => $this->moduleAdminLink(array('positionbank' => 1, 'way' => 0, 'id_bankwire_account' => (int) $row['id_bankwire_account'])),
                'down_url' => $this->moduleAdminLink(array('positionbank' => 1, 'way' => 1, 'id_bankwire_account' => (int) $row['id_bankwire_account'])),
            );
        }

        $this->context->smarty->assign(array(
            'bankwire_banks' => $rows,
            'bankwire_add_url' => $this->moduleAdminLink(array('action' => 'addbank')),
            'bankwire_settings_url' => $this->moduleAdminLink(),
            'bankwire_reservation_global' => (int) Configuration::get('BANKWIRE_RESERVATION_DAYS'),
        ));

        return $this->display(__FILE__, 'views/templates/admin/bank_list.tpl');
    }

    /**
     * Nilai field custom_text untuk HelperForm — array keyed id_lang (kosong untuk bank
     * baru). Repopulasi dari POST saat validasi gagal supaya input admin tak hilang.
     *
     * @param BankAccount $bank
     *
     * @return array<int, string>
     */
    private function customTextFieldValue(BankAccount $bank)
    {
        $values = array();
        $posted = Tools::isSubmit('submitBank');
        foreach (Language::getLanguages(false) as $lang) {
            $idLang = (int) $lang['id_lang'];
            if ($posted) {
                $values[$idLang] = (string) Tools::getValue('custom_text_' . $idLang);
            } elseif (Validate::isLoadedObject($bank) && is_array($bank->custom_text) && isset($bank->custom_text[$idLang])) {
                $values[$idLang] = (string) $bank->custom_text[$idLang];
            } else {
                $values[$idLang] = '';
            }
        }

        return $values;
    }

    /**
     * Form add/edit bank (HelperForm).
     *
     * @return string
     */
    private function renderBankForm()
    {
        $id = (int) Tools::getValue('id_bankwire_account');

        // Form edit juga harus lewat cek toko: tanpa ini, membuka editbank dengan id
        // milik toko lain membocorkan nomor rekeningnya, walau simpan diblokir.
        if ($id) {
            $bank = $this->loadBankForAdmin($id);
            if ($bank === null) {
                return $this->displayError($this->trans('This bank account no longer exists.', array(), 'Modules.Bankwire.Admin'))
                    . $this->renderBankList();
            }
        } else {
            $bank = new BankAccount();
        }

        $currentIcon = '';
        if (Validate::isLoadedObject($bank) && $bank->icon && is_file($this->iconDir . $bank->icon)) {
            $currentIcon = $this->_path . 'views/img/banks/' . $bank->icon;
        }

        $fieldsForm = array(
            'form' => array(
                'legend' => array(
                    'title' => $id
                        ? $this->trans('Edit bank account', array(), 'Modules.Bankwire.Admin')
                        : $this->trans('Add a bank account', array(), 'Modules.Bankwire.Admin'),
                    'icon' => 'icon-bank',
                ),
                'input' => array(
                    // Tanpa input ini form edit tidak pernah mengirim id-nya, sehingga
                    // setiap simpan masuk cabang add() dan membuat rekening duplikat.
                    array(
                        'type' => 'hidden',
                        'name' => 'id_bankwire_account',
                    ),
                    array(
                        'type' => 'text',
                        'label' => $this->trans('Bank name', array(), 'Modules.Bankwire.Admin'),
                        'name' => 'bank_name',
                        'required' => true,
                        'desc' => $this->trans('Displayed to the customer at checkout, e.g. Bank BCA, Bank Niaga, Jenius.', array(), 'Modules.Bankwire.Admin'),
                    ),
                    array(
                        'type' => 'text',
                        'label' => $this->trans('Account owner', array(), 'Modules.Bankwire.Admin'),
                        'name' => 'owner',
                    ),
                    array(
                        'type' => 'textarea',
                        'label' => $this->trans('Details', array(), 'Modules.Bankwire.Admin'),
                        'name' => 'details',
                        'desc' => $this->trans('Account number, branch, IBAN, BIC, etc.', array(), 'Modules.Bankwire.Admin'),
                    ),
                    array(
                        'type' => 'textarea',
                        'label' => $this->trans('Bank address', array(), 'Modules.Bankwire.Admin'),
                        'name' => 'address',
                    ),
                    array(
                        'type' => 'textarea',
                        'label' => $this->trans('Customer information', array(), 'Modules.Bankwire.Admin'),
                        'name' => 'custom_text',
                        'lang' => true,
                        'desc' => $this->trans('Extra note shown to the customer for this bank, e.g. processing time. Leave empty to show nothing.', array(), 'Modules.Bankwire.Admin'),
                    ),
                    array(
                        'type' => 'text',
                        'label' => $this->trans('Reservation period', array(), 'Modules.Bankwire.Admin'),
                        'name' => 'reservation_days',
                        'desc' => $this->trans('Number of days items stay reserved for this bank. 0 = use the global default.', array(), 'Modules.Bankwire.Admin'),
                    ),
                    array(
                        'type' => 'file',
                        'label' => $this->trans('Icon', array(), 'Modules.Bankwire.Admin'),
                        'name' => 'icon',
                        'desc' => $this->trans('Bank logo/icon (jpg, png, gif). Leave empty to keep the current one.', array(), 'Modules.Bankwire.Admin')
                            . ($currentIcon ? ' <br /><img src="' . $currentIcon . '" style="max-height:40px;margin-top:6px" alt="" />' : ''),
                    ),
                    array(
                        'type' => 'switch',
                        'label' => $this->trans('Enabled', array(), 'Modules.Bankwire.Admin'),
                        'name' => 'active',
                        'is_bool' => true,
                        'values' => array(
                            array('id' => 'active_on', 'value' => 1, 'label' => $this->trans('Yes', array(), 'Admin.Global')),
                            array('id' => 'active_off', 'value' => 0, 'label' => $this->trans('No', array(), 'Admin.Global')),
                        ),
                    ),
                ),
                'submit' => array(
                    'title' => $this->trans('Save', array(), 'Admin.Actions'),
                ),
            ),
        );

        $helper = new HelperForm();
        $helper->show_toolbar = false;
        $helper->table = $this->table;
        $helper->module = $this;
        $lang = new Language((int) Configuration::get('PS_LANG_DEFAULT'));
        $helper->default_form_language = $lang->id;
        $helper->allow_employee_form_lang = Configuration::get('PS_BO_ALLOW_EMPLOYEE_FORM_LANG') ?: 0;
        $helper->identifier = 'id_bankwire_account';
        // $helper->id sengaja tidak di-set: form.tpl akan merender hidden identifier
        // sendiri dari {$form_id}, bentrok nama & DOM id dengan input hidden di
        // $fieldsForm yang sudah menangani add (0) maupun edit (id).
        $helper->submit_action = 'submitBank';
        // Tanpa token: HelperForm menambahkannya sendiri dari $helper->token.
        $helper->currentIndex = $this->context->link->getAdminLink(
            'AdminModules',
            false,
            array(),
            array('configure' => $this->name)
        );
        $helper->token = Tools::getAdminTokenLite('AdminModules');
        // Saat submit gagal validasi, form dirender ulang: repopulasi SEMUA field dari POST
        // supaya input admin tak hilang (bukan hanya custom_text). Selain saat submit, ambil
        // dari objek bank (edit) atau default (add).
        $posted = Tools::isSubmit('submitBank');
        $val = function ($name, $default) use ($posted) {
            return $posted ? Tools::getValue($name, $default) : $default;
        };
        $loaded = Validate::isLoadedObject($bank);

        // Status aktif per-toko (sejak 1.0.3): tampilkan nilai toko konteks, bukan baris
        // utama yang bisa basi — kalau tidak, membuka lalu menyimpan bank yang di-toggle
        // OFF akan diam-diam mengaktifkannya kembali. null = kolom belum ada → baris utama.
        $activeDefault = 1;
        if ($loaded) {
            $activeInShop = BankAccount::isActiveInCurrentShop((int) $bank->id);
            $activeDefault = ($activeInShop === null) ? (int) $bank->active : (int) $activeInShop;
        }

        $helper->tpl_vars = array(
            'fields_value' => array(
                'id_bankwire_account' => $loaded ? (int) $bank->id : 0,
                'bank_name' => $val('bank_name', $loaded ? $bank->bank_name : ''),
                'owner' => $val('owner', $loaded ? $bank->owner : ''),
                'details' => $val('details', $loaded ? $bank->details : ''),
                'address' => $val('address', $loaded ? $bank->address : ''),
                'active' => (int) $val('active', $activeDefault),
                'reservation_days' => (int) $val('reservation_days', $loaded ? (int) $bank->reservation_days : 0),
                // Field lang: HelperForm mengharap array keyed id_lang.
                'custom_text' => $this->customTextFieldValue($bank),
            ),
            'languages' => $this->context->controller->getLanguages(),
            'id_language' => $this->context->language->id,
        );

        $back = '<div class="panel-heading">'
            . '<a href="' . $this->moduleAdminLink() . '" class="btn btn-default">'
            . '<i class="icon-arrow-left"></i> ' . $this->trans('Back to list', array(), 'Modules.Bankwire.Admin')
            . '</a></div>';

        return $back . $helper->generateForm(array($fieldsForm));
    }

    // ------------------------------------------------------------------
    // Front — checkout
    // ------------------------------------------------------------------

    /**
     * @param array<string, mixed> $params
     *
     * @return array<int, PaymentOption>|void
     */
    public function hookPaymentOptions($params)
    {
        if (!$this->active) {
            return;
        }

        if (!$this->checkCurrency($params['cart'])) {
            return;
        }

        $banks = BankAccount::getActiveBanks();
        if (!count($banks)) {
            return;
        }

        // Loop-invariant: sama untuk setiap bank. Hitung sekali di luar foreach.
        // Total diformat dengan currency CART (bukan context) — context bisa divergen
        // dari cart setelah switch currency/multistore; validation.php pun pakai cart currency.
        $globalReservationDays = (int) Configuration::get('BANKWIRE_RESERVATION_DAYS');
        $total = $this->formatPrice(
            $params['cart']->getOrderTotal(true, Cart::BOTH),
            new Currency((int) $params['cart']->id_currency)
        );

        $paymentOptions = array();
        foreach ($banks as $bank) {
            $id = (int) $bank['id_bankwire_account'];

            // Reservasi efektif: nilai per-bank, atau default global bila 0/kosong.
            $reservationDays = (int) $bank['reservation_days'];
            if ($reservationDays <= 0) {
                $reservationDays = $globalReservationDays;
            }

            $this->context->smarty->assign(array(
                'bankwire_bank_name' => $bank['bank_name'],
                'bankwire_owner' => $bank['owner'] ? $bank['owner'] : '___________',
                'bankwire_details' => $bank['details'] ? Tools::nl2br($bank['details']) : '___________',
                'bankwire_address' => $bank['address'] ? Tools::nl2br($bank['address']) : '',
                'bankwire_custom_text' => isset($bank['custom_text']) ? $bank['custom_text'] : '',
                'bankwire_reservation_days' => $reservationDays,
                'bankwire_total' => $total,
            ));

            $option = new PaymentOption();
            $option->setModuleName($this->name)
                ->setCallToActionText($this->trans('Pay by %s', array($bank['bank_name']), 'Modules.Bankwire.Shop'))
                ->setAction($this->context->link->getModuleLink($this->name, 'validation', array(), true))
                ->setInputs(array(
                    'id_bank' => array(
                        'name' => 'id_bank',
                        'type' => 'hidden',
                        'value' => $id,
                    ),
                    // Tanda tangan pilihan — lihat signBankOption(); diverifikasi di
                    // controllers/front/validation.php sebelum order dibuat.
                    'bankwire_opt' => array(
                        'name' => 'bankwire_opt',
                        'type' => 'hidden',
                        'value' => $this->signBankOption($id, $params['cart']),
                    ),
                ))
                ->setAdditionalInformation($this->fetchUncached('module:bankwire/views/templates/hook/intro.tpl'));

            if (!empty($bank['icon']) && is_file($this->iconDir . $bank['icon'])) {
                $option->setLogo($this->_path . 'views/img/banks/' . $bank['icon']);
            }

            $paymentOptions[] = $option;
        }

        return $paymentOptions;
    }

    /**
     * Render template tanpa cache Smarty.
     *
     * Template pembayaran memuat data per-cart/per-order (total belanja, nomor
     * referensi). Module::getCacheId() hanya berdimensi shop/lang/currency/group/
     * country — tidak ada dimensi cart — sehingga cache apa pun akan menyajikan
     * data pelanggan sebelumnya kepada pelanggan berikutnya.
     *
     * @param string $template
     *
     * @return string
     */
    private function fetchUncached($template)
    {
        // Scope-nya $this->smarty (data anak milik module, seperti Module::fetch()),
        // bukan engine root: variabel yang di-assign lewat $this->smarty hanya terlihat
        // dari sana, sementara assign ke root tetap terjangkau lewat rantai parent.
        $tpl = $this->context->smarty->createTemplate($template, null, null, $this->smarty);

        // Caching dimatikan pada objek template, bukan pada engine bersama — mutasi
        // engine akan bocor ke seluruh request bila fetch() melempar.
        $tpl->caching = Smarty::CACHING_OFF;

        return $tpl->fetch();
    }

    /**
     * Isi placeholder bank pada email 'bankwire' yang dikirim di luar validateOrder.
     *
     * validateOrder meneruskan mailVars hanya untuk email pertama. Setiap perubahan
     * status berikutnya ke OS_CONFIG_KEY — mis. admin mengirim ulang instruksi
     * transfer — memanggil OrderHistory::sendEmail() tanpa template_vars, dan core
     * hanya menambahkan $module->extra_mail_vars. Properti itu tak bisa dipakai di
     * module multi-bank karena banknya berbeda per order, jadi isi di sini dari map
     * bankwire_order; tanpa ini pelanggan menerima literal {bankwire_bank}.
     *
     * @param array<string, mixed> $params
     *
     * @return void
     */
    public function hookActionEmailSendBefore($params)
    {
        // Dua nama diterima: milik module ini, DAN nama lama yang masih dipakai order
        // pra-1.0.6. Kepemilikan ditegakkan lebih bawah oleh getBankForOrder() — order
        // ps_wirepayment tak punya baris peta, jadi hook keluar tanpa menyentuh apa pun.
        if (!isset($params['template'])
            || ($params['template'] !== self::MAIL_TEMPLATE
                && $params['template'] !== self::LEGACY_MAIL_TEMPLATE)
        ) {
            return;
        }

        if (!isset($params['templateVars']['{id_order}'])) {
            return;
        }

        // Sudah terisi oleh validateOrder — jangan timpa.
        if (isset($params['templateVars']['{bankwire_bank}'])) {
            return;
        }

        // Bahasa order (bukan bahasa admin yang sedang memicu email) agar custom_text tampil
        // dalam bahasa pelanggan. Fallback null → konteks bila order tak termuat.
        $idOrder = (int) $params['templateVars']['{id_order}'];
        $order = new Order($idOrder);
        $orderLang = Validate::isLoadedObject($order) ? (int) $order->id_lang : null;

        $bank = $this->getBankForOrder($idOrder, $orderLang);
        if ($bank === null) {
            return;
        }

        $params['templateVars']['{bankwire_bank}'] = $bank['bank_name'];
        $params['templateVars']['{bankwire_owner}'] = (string) $bank['owner'];
        $params['templateVars']['{bankwire_details}'] = Tools::nl2br((string) $bank['details']);
        $params['templateVars']['{bankwire_address}'] = Tools::nl2br((string) $bank['address']);
        // getBankForOrder mengembalikan custom_text pada bahasa konteks; email status
        // non-inisial memakai konteks admin, jadi ini bahasa toko default admin.
        $params['templateVars']['{bankwire_custom_text}'] = isset($bank['custom_text']) ? Tools::nl2br((string) $bank['custom_text']) : '';
    }

    /**
     * Halaman konfirmasi order. Core 1.7/8/9 memanggil hook displayPaymentReturn
     * dari OrderConfirmationController; nama lama paymentReturn tak dipanggil lagi
     * oleh core manapun sejak era 1.6 (diverifikasi terhadap source 1.7.8.11/8.1.6/
     * 9.1.4) — cutover bersih di 1.0.4.
     *
     * @param array<string, mixed> $params
     *
     * @return string|void
     */
    public function hookDisplayPaymentReturn($params)
    {
        if (!$this->active) {
            return;
        }

        $order = $params['order'];
        $state = $order->getCurrentState();

        if (!in_array($state, array(
            $this->getOrderStateId(),
            Configuration::get('PS_OS_OUTOFSTOCK'),
            Configuration::get('PS_OS_OUTOFSTOCK_UNPAID'),
        ))) {
            $this->smarty->assign(array(
                'status' => 'failed',
                'contact_url' => $this->context->link->getPageLink('contact', true),
            ));

            return $this->fetchUncached('module:bankwire/views/templates/hook/payment_return.tpl');
        }

        $bank = $this->getBankForOrder((int) $order->id);

        $this->smarty->assign(array(
            'status' => 'ok',
            'shop_name' => $this->context->shop->name,
            'reference' => $order->reference,
            'contact_url' => $this->context->link->getPageLink('contact', true),
            'bankwire_bank_name' => $bank ? $bank['bank_name'] : '',
            'bankwire_owner' => ($bank && $bank['owner']) ? $bank['owner'] : '___________',
            'bankwire_details' => ($bank && $bank['details']) ? Tools::nl2br($bank['details']) : '___________',
            'bankwire_address' => ($bank && $bank['address']) ? Tools::nl2br($bank['address']) : '',
            'bankwire_custom_text' => ($bank && isset($bank['custom_text'])) ? $bank['custom_text'] : '',
            'bankwire_total' => $this->formatPrice(
                $order->getOrdersTotalPaid(),
                new Currency($order->id_currency)
            ),
        ));

        return $this->fetchUncached('module:bankwire/views/templates/hook/payment_return.tpl');
    }

    /**
     * Bank yang dipilih untuk sebuah order (via map bankwire_order).
     *
     * @param int $idOrder
     * @param int|null $idLang Bahasa untuk custom_text; null = bahasa konteks aktif.
     *                         Email ubah-status berjalan dalam bahasa admin, jadi ia harus
     *                         meneruskan bahasa order agar pelanggan menerima teks bahasanya
     *                         sendiri — bukan bahasa default admin.
     *
     * @return array<string, mixed>|null
     */
    public function getBankForOrder($idOrder, $idLang = null)
    {
        // custom_text via subquery skalar berkorelasi (pola sama BankAccount::getActiveBanks):
        // tak menggandakan baris, aman ONLY_FULL_GROUP_BY. Fallback ke bahasa default toko
        // bila tak ada baris lang untuk bahasa yang diminta.
        $idLang = $idLang === null ? (int) $this->context->language->id : (int) $idLang;
        $defaultLang = (int) Configuration::get('PS_LANG_DEFAULT');
        $sql = new DbQuery();
        $sql->select('a.*, COALESCE('
            . '(SELECT bl.custom_text FROM `' . _DB_PREFIX_ . 'bankwire_account_lang` bl'
            . ' WHERE bl.id_bankwire_account = a.id_bankwire_account AND bl.id_lang = ' . $idLang . '),'
            . '(SELECT bld.custom_text FROM `' . _DB_PREFIX_ . 'bankwire_account_lang` bld'
            . ' WHERE bld.id_bankwire_account = a.id_bankwire_account AND bld.id_lang = ' . $defaultLang . ')'
            . ') AS custom_text');
        $sql->from('bankwire_order', 'o');
        $sql->innerJoin('bankwire_account', 'a', 'a.id_bankwire_account = o.id_bankwire_account');
        $sql->where('o.id_order = ' . (int) $idOrder);

        $row = Db::getInstance()->getRow($sql);

        return $row ?: null;
    }

    /**
     * Simpan map order→bank. Dipanggil dari front controller validation.
     *
     * @param int $idOrder
     * @param int $idBank
     *
     * @return void
     */
    public function saveOrderBank($idOrder, $idBank)
    {
        Db::getInstance()->execute(
            'REPLACE INTO `' . _DB_PREFIX_ . 'bankwire_order` (id_order, id_bankwire_account) VALUES ('
            . (int) $idOrder . ', ' . (int) $idBank . ')'
        );
    }

    /**
     * @param int $idBank
     *
     * @return BankAccount|null
     */
    public function loadActiveBank($idBank)
    {
        if (!BankAccount::isAssociatedToCurrentShop((int) $idBank)) {
            return null;
        }

        $bank = new BankAccount((int) $idBank);
        if (!Validate::isLoadedObject($bank)) {
            return null;
        }

        // Status aktif adalah per-toko (sa.active) sejak 1.0.3; baris utama $bank->active
        // bisa basi setelah toggle di satu toko. Pakai status per-toko sebagai sumber
        // kebenaran; null = kolom per-toko belum ada (pra-upgrade) → jatuh ke baris utama.
        $activeInShop = BankAccount::isActiveInCurrentShop((int) $idBank);
        $isActive = ($activeInShop === null) ? (bool) $bank->active : $activeInShop;

        return $isActive ? $bank : null;
    }

    /**
     * Tanda tangan HMAC pilihan bank di langkah pembayaran: mengikat
     * (cart, customer, bank) dengan kunci milik module (lihat getSigningKey()).
     * Form checkout membawanya sebagai input tersembunyi; validation.php
     * memverifikasi ulang sebelum membuat order.
     *
     * Tanpa ini id_bank bisa dipaksa attacker lewat form lintas-situs (CSRF): order tetap
     * milik korban dan total dihitung server-side, tapi rekening tujuan transfer berubah
     * tanpa dipilih pelanggan.
     *
     * @param int $idBank
     * @param Cart $cart
     *
     * @return string
     */
    public function signBankOption($idBank, $cart)
    {
        $payload = (int) $cart->id . '|' . (int) $cart->id_customer . '|' . (int) $idBank;

        return hash_hmac('sha256', $payload, $this->getSigningKey());
    }

    /**
     * Kunci HMAC untuk signBankOption(). Dihasilkan saat install/upgrade dan disimpan
     * di ps_configuration (BANKWIRE_SIGNING_KEY).
     *
     * BUKAN _PS_PASSWD_KEY_: konstanta core itu tak terdefinisi di image PS 8/9, dan
     * PHP 8 melempar Error untuk konstanta tak dikenal (PHP 7 hanya warning lalu memakai
     * nama literal — perilaku yang tak bisa diandalkan lintas versi). Fallback berjenjang
     * menjaga instalasi yang somehow kehilangan kuncinya tetap konsisten antara render
     * dan verifikasi — itulah syarat fungsional tanda tangan ini.
     *
     * @return string
     */
    private function getSigningKey()
    {
        $key = Configuration::get('BANKWIRE_SIGNING_KEY');
        if ($key) {
            return $key;
        }
        if (defined('_PS_PASSWD_KEY_')) {
            return _PS_PASSWD_KEY_;
        }

        return sha1('bankwire|' . (string) Configuration::get('PS_SHOP_DOMAIN'));
    }

    /**
     * Verifikasi tanda tangan dari signBankOption(). Perbandingan konstan-waktu
     * (hash_equals) setelah cek panjang; penolakan memakai pesan yang sama dengan bank
     * tak dikenal supaya penyebab kegagalan tidak dibocorkan.
     *
     * @param int $idBank
     * @param Cart $cart
     * @param string $signature
     *
     * @return bool
     */
    public function verifyBankOption($idBank, $cart, $signature)
    {
        if (!is_string($signature) || strlen($signature) !== 64) {
            return false;
        }

        return hash_equals($this->signBankOption($idBank, $cart), $signature);
    }

    /**
     * @param Cart $cart
     *
     * @return bool
     */
    public function checkCurrency($cart)
    {
        $currencyOrder = new Currency($cart->id_currency);
        $currenciesModule = $this->getCurrency($cart->id_currency);

        if (is_array($currenciesModule)) {
            foreach ($currenciesModule as $currencyModule) {
                if ($currencyOrder->id == $currencyModule['id_currency']) {
                    return true;
                }
            }
        }

        return false;
    }

    /**
     * Format harga version-safe (1.7.6+/8/9). Tools::displayPrice dihapus di PS9,
     * pakai Locale (currentLocale) yang tersedia sejak 1.7.6.
     *
     * @param float $amount
     * @param Currency|null $currency
     *
     * @return string
     */
    private function formatPrice($amount, $currency = null)
    {
        if ($currency === null) {
            $currency = $this->context->currency;
        }

        return $this->context->currentLocale->formatPrice($amount, $currency->iso_code);
    }
}
