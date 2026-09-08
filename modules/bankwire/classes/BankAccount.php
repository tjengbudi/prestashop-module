<?php
/**
 * BankAccount ObjectModel — satu rekening bank untuk pembayaran transfer.
 * Aman lintas PrestaShop 1.7.x / 8.x / 9.x (ObjectModel + Db).
 *
 * @author Prestanesia
 * @license http://opensource.org/licenses/afl-3.0.php Academic Free License (AFL 3.0)
 */

if (!defined('_PS_VERSION_')) {
    exit;
}

class BankAccount extends ObjectModel
{
    /** @var int */
    public $id_bankwire_account;

    /** @var string Nama bank yang ditampilkan (mis. "Bank BCA", "Bank Niaga") */
    public $bank_name;

    /** @var string Nama pemilik rekening */
    public $owner;

    /** @var string Detail rekening (no. rekening, cabang, dll) */
    public $details;

    /** @var string Alamat / nama bank tambahan */
    public $address;

    /** @var string|array Catatan informatif per bank (multibahasa: array keyed id_lang) */
    public $custom_text;

    /** @var int Masa reservasi barang (hari); 0 = ikut default global BANKWIRE_RESERVATION_DAYS */
    public $reservation_days = 0;

    /** @var string Nama file icon di views/img/banks/ (kosong = tanpa icon) */
    public $icon;

    /** @var bool Aktif / tampil di checkout */
    public $active = true;

    /** @var int Urutan tampil */
    public $position = 0;

    /** @var string */
    public $date_add;

    /** @var string */
    public $date_upd;

    /**
     * @see ObjectModel::$definition
     */
    public static $definition = array(
        'table' => 'bankwire_account',
        'primary' => 'id_bankwire_account',
        'multilang' => true,
        'fields' => array(
            'bank_name' => array('type' => self::TYPE_STRING, 'validate' => 'isGenericName', 'required' => true, 'size' => 128),
            'owner' => array('type' => self::TYPE_STRING, 'validate' => 'isGenericName', 'size' => 128),
            'details' => array('type' => self::TYPE_STRING, 'validate' => 'isCleanHtml', 'size' => 1024),
            'address' => array('type' => self::TYPE_STRING, 'validate' => 'isCleanHtml', 'size' => 1024),
            'icon' => array('type' => self::TYPE_STRING, 'validate' => 'isFileName', 'size' => 128),
            'active' => array('type' => self::TYPE_BOOL, 'validate' => 'isBool'),
            'position' => array('type' => self::TYPE_INT, 'validate' => 'isUnsignedInt'),
            'reservation_days' => array('type' => self::TYPE_INT, 'validate' => 'isUnsignedInt'),
            'date_add' => array('type' => self::TYPE_DATE, 'validate' => 'isDate'),
            'date_upd' => array('type' => self::TYPE_DATE, 'validate' => 'isDate'),
            // Multibahasa: catatan informatif per bank, dirender apa adanya (isCleanHtml).
            'custom_text' => array('type' => self::TYPE_HTML, 'lang' => true, 'validate' => 'isCleanHtml', 'size' => 65535),
        ),
    );

    /**
     * Ambil semua bank aktif, terurut posisi — untuk checkout.
     *
     * @return array<int, array<string, mixed>>
     */
    public static function getActiveBanks()
    {
        // custom_text lewat subquery skalar berkorelasi, BUKAN JOIN: restrictToCurrentShop
        // menambah groupBy hanya pada konteks semua-toko, jadi JOIN+agregasi tak konsisten
        // (di jendela pra-upgrade tanpa groupBy, MAX akan meruntuhkan semua bank jadi satu
        // baris). Subquery berkorelasi pada a.id_bankwire_account (kunci group) valid di
        // ONLY_FULL_GROUP_BY baik ter-group maupun tidak, dan tak pernah menggandakan baris.
        $sql = new DbQuery();
        $sql->select('a.*, ' . self::customTextSubquery() . ' AS custom_text');
        $sql->from(self::$definition['table'], 'a');
        if (self::shopColumnsExist()) {
            // active/position kini milik baris sa (per toko). FO selalu konteks satu toko,
            // jadi join sa (dari restrictToCurrentShop) menghasilkan satu baris per bank;
            // MIN() menjaga ORDER BY tetap sah di bawah ONLY_FULL_GROUP_BY (groupBy aktif).
            $sql->where('sa.active = 1');
            $sql->orderBy('MIN(sa.position) ASC, a.id_bankwire_account ASC');
        } else {
            $sql->where('a.active = 1');
            $sql->orderBy('a.position ASC, a.id_bankwire_account ASC');
        }
        self::restrictToCurrentShop($sql);

        $result = Db::getInstance()->executeS($sql);

        return is_array($result) ? $result : array();
    }

    /**
     * Subquery skalar custom_text pada bahasa konteks aktif, untuk disisipkan ke SELECT
     * query yang beralias 'a' pada tabel bankwire_account. Aman lintas ONLY_FULL_GROUP_BY.
     *
     * @return string
     */
    private static function customTextSubquery()
    {
        $idLang = (int) Context::getContext()->language->id;

        return '(SELECT bl.custom_text FROM `' . _DB_PREFIX_ . 'bankwire_account_lang` bl'
            . ' WHERE bl.id_bankwire_account = a.id_bankwire_account AND bl.id_lang = ' . $idLang . ')';
    }

    /**
     * Ambil semua bank (aktif + nonaktif) untuk daftar admin.
     *
     * @return array<int, array<string, mixed>>
     */
    public static function getAllBanks()
    {
        // Sengaja TANPA custom_text: daftar admin tak menampilkannya, dan form edit
        // memuatnya sendiri lewat ObjectModel multilang (new BankAccount($id)). Menyambung
        // lang di sini akan bentrok dengan groupBy konteks semua-toko (ONLY_FULL_GROUP_BY).
        $sql = new DbQuery();
        if (self::shopColumnsExist()) {
            // active/position dari sa (per toko), menimpa nilai baris utama di a.*.
            // Konteks "semua toko" mencocokkan banyak baris sa per bank (groupBy aktif):
            // MAX(active) = tampil bila aktif di salah satu toko, MIN(position) = urutan
            // paling awal — cukup untuk daftar admin lintas-toko. Konteks satu toko:
            // hanya satu baris sa, jadi agregat = nilainya sendiri.
            $sql->select('a.*, MAX(sa.active) AS active, MIN(sa.position) AS position');
            $sql->from(self::$definition['table'], 'a');
            $sql->orderBy('MIN(sa.position) ASC, a.id_bankwire_account ASC');
        } else {
            $sql->select('a.*');
            $sql->from(self::$definition['table'], 'a');
            $sql->orderBy('a.position ASC, a.id_bankwire_account ASC');
        }
        self::restrictToCurrentShop($sql);

        $result = Db::getInstance()->executeS($sql);

        return is_array($result) ? $result : array();
    }

    /**
     * Apakah sudah ada bank bernama ini (case-insensitive) dalam lingkup toko aktif?
     *
     * Menolak duplikat mencegah dua opsi "Pay by X" identik di checkout yang tak bisa
     * dibedakan pelanggan. $excludeId untuk cabang edit: baris sendiri tak dihitung.
     * Lingkup = toko konteks aktif (sama seperti getActiveBanks/getAllBanks): dua toko
     * multistore boleh punya nama sama karena FO selalu satu toko dan opsinya tak pernah
     * tampil bersama.
     *
     * @param string $name
     * @param int $excludeId
     *
     * @return bool
     */
    public static function existsByName($name, $excludeId = 0)
    {
        $name = trim((string) $name);
        if ($name === '') {
            return false;
        }

        $sql = new DbQuery();
        // COUNT(DISTINCT ...) agar konteks "semua toko" (beberapa baris asosiasi per
        // bank lewat JOIN restrictToCurrentShop) tetap menghitung satu bank sekali.
        $sql->select('COUNT(DISTINCT a.id_bankwire_account)');
        $sql->from(self::$definition['table'], 'a');
        // LOWER() eksplisit: kepekaan kasus kolasi MySQL bergantung instalasi; tabel
        // kecil sehingga biaya fungsi kolom tak berarti. Nilai DIKUTIP manual — pSQL()
        // di semua versi hanya escape, TIDAK menambah kutip (konvensi modul: lihat
        // shopColumnsExist()/withPositionLock()). Tanpa kutip, nama ber-spasi dibaca
        // sebagai deretan identifier: fatal sintaks di MariaDB baru, diam-diam tak
        // pernah match di server lama.
        $sql->where('LOWER(a.bank_name) = LOWER(\'' . pSQL($name) . '\')');
        if ($excludeId) {
            $sql->where('a.id_bankwire_account != ' . (int) $excludeId);
        }
        self::restrictToCurrentShop($sql, false);

        return (int) Db::getInstance()->getValue($sql) > 0;
    }

    /**
     * Batasi query ke toko aktif. Tanpa ini rekening milik satu toko bocor ke
     * checkout dan halaman admin toko lain pada instalasi multistore.
     *
     * @param DbQuery $sql
     *
     * @return void
     */
    private static function restrictToCurrentShop(DbQuery $sql, $groupBy = true)
    {
        // File module baru sudah melayani Front Office sebelum upgrade script sempat
        // jalan. Selama jendela itu tabel asosiasi belum ada: JOIN akan fatal di
        // checkout, jadi lebih baik berperilaku seperti 1.0.0 sampai upgrade selesai.
        if (!self::shopTableExists()) {
            return;
        }

        $sql->innerJoin(
            'bankwire_account_shop',
            'sa',
            'sa.id_bankwire_account = a.id_bankwire_account AND sa.id_shop IN (' . self::currentShopIds() . ')'
        );

        // Konteks "semua toko" mencocokkan beberapa baris asosiasi per bank; tanpa
        // group by, satu bank tampil berkali-kali. MAX() tidak butuh ini.
        if ($groupBy) {
            $sql->groupBy('a.id_bankwire_account');
        }
    }

    /** @var bool|null Cache per-request; invalidasi lewat resetShopTableCache() */
    private static $shopTableExists = null;

    /** @var bool|null Cache per-request; kolom active/position per-toko di tabel _shop */
    private static $shopColumnsExist = null;

    /**
     * Panggil setelah tabel/kolom asosiasi dibuat dalam request yang sama (installDb,
     * upgrade). Tanpa ini cache terkunci di false dan penyaringan toko / kolom per-toko
     * dilewati diam-diam untuk sisa request.
     *
     * @return void
     */
    public static function resetShopTableCache()
    {
        self::$shopTableExists = null;
        self::$shopColumnsExist = null;
    }

    /**
     * @return bool
     */
    private static function shopTableExists()
    {
        if (self::$shopTableExists === null) {
            $rows = Db::getInstance()->executeS(
                "SHOW TABLES LIKE '" . _DB_PREFIX_ . "bankwire_account_shop'",
                true,
                false
            );
            self::$shopTableExists = is_array($rows) && count($rows) > 0;
        }

        return self::$shopTableExists;
    }

    /**
     * Apakah active/position sudah pindah ke bankwire_account_shop (per toko)?
     *
     * Instalasi lama (pra-1.0.3) menyimpan keduanya di baris bersama bankwire_account.
     * Selama jendela upgrade file baru sudah melayani FO sebelum kolom ada — jatuh ke
     * perilaku lama (baca/tulis baris utama) supaya checkout tak fatal.
     *
     * @return bool
     */
    private static function shopColumnsExist()
    {
        if (self::$shopColumnsExist === null) {
            if (!self::shopTableExists()) {
                self::$shopColumnsExist = false;
            } else {
                self::$shopColumnsExist = (bool) Db::getInstance()->getValue(
                    'SELECT COUNT(*) FROM information_schema.COLUMNS
                     WHERE TABLE_SCHEMA = DATABASE()
                     AND TABLE_NAME = \'' . pSQL(_DB_PREFIX_ . 'bankwire_account_shop') . '\'
                     AND COLUMN_NAME = \'position\''
                );
            }
        }

        return self::$shopColumnsExist;
    }

    /**
     * Daftar id toko pada konteks aktif, siap dipakai di klausa IN.
     *
     * @return string
     */
    private static function currentShopIds()
    {
        $ids = array_map('intval', (array) Shop::getContextListShopID());

        return count($ids) ? implode(',', $ids) : '0';
    }

    /**
     * Apakah bank terkait toko pada konteks aktif?
     *
     * Menyaring daftar saja tidak cukup: id bank datang dari POST checkout dan dari
     * URL admin, jadi tanpa cek ini rekening toko lain masih bisa dijangkau langsung.
     *
     * @param int $idBank
     *
     * @return bool
     */
    public static function isAssociatedToCurrentShop($idBank)
    {
        // Sama seperti restrictToCurrentShop(): sebelum upgrade sempat jalan, tidak ada
        // asosiasi untuk dicek — jangan tolak semua bank, dan jangan fatal.
        if (!self::shopTableExists()) {
            return true;
        }

        $sql = new DbQuery();
        $sql->select('1');
        $sql->from('bankwire_account_shop', 'sa');
        $sql->where('sa.id_bankwire_account = ' . (int) $idBank);
        $sql->where('sa.id_shop IN (' . self::currentShopIds() . ')');

        return (bool) Db::getInstance()->getValue($sql);
    }

    /**
     * Apakah bank aktif pada toko konteks aktif?
     *
     * Sumber kebenaran status aktif kini per-toko (sa.active). loadActiveBank() memakai
     * ini sebagai re-check keamanan untuk id_bank yang di-POST ke checkout: tanpa ini,
     * POST langsung ke validation.php untuk bank yang dinonaktifkan di toko ini masih
     * lolos (baris utama a.active bisa tertinggal 1 setelah toggle per-toko).
     *
     * Saat kolom per-toko belum ada (pra-1.0.3), kembalikan null → pemanggil jatuh ke
     * cek baris utama a.active seperti perilaku lama.
     *
     * @param int $idBank
     *
     * @return bool|null true/false bila kolom per-toko ada; null bila belum
     */
    public static function isActiveInCurrentShop($idBank)
    {
        if (!self::shopColumnsExist()) {
            return null;
        }

        return (bool) Db::getInstance()->getValue(
            'SELECT 1 FROM `' . _DB_PREFIX_ . 'bankwire_account_shop`
             WHERE id_bankwire_account = ' . (int) $idBank . '
             AND id_shop IN (' . self::currentShopIds() . ')
             AND active = 1'
        );
    }

    /**
     * Kaitkan bank ke toko-toko pada konteks aktif. Dipanggil setelah add().
     *
     * @param int $idBank
     *
     * @return void
     */
    public static function associateToCurrentShops($idBank)
    {
        if (!self::shopTableExists()) {
            return;
        }

        $withColumns = self::shopColumnsExist();

        foreach (array_map('intval', (array) Shop::getContextListShopID()) as $idShop) {
            if ($withColumns) {
                // Posisi dihitung per toko (MAX+1 dalam toko itu) supaya urutan checkout
                // tiap toko independen. active default 1, seperti kolom lama.
                $next = 1 + (int) Db::getInstance()->getValue(
                    'SELECT MAX(position) FROM `' . _DB_PREFIX_ . 'bankwire_account_shop`
                     WHERE id_shop = ' . (int) $idShop
                );
                Db::getInstance()->execute(
                    'INSERT IGNORE INTO `' . _DB_PREFIX_ . 'bankwire_account_shop`
                     (id_bankwire_account, id_shop, active, position)
                     VALUES (' . (int) $idBank . ', ' . (int) $idShop . ', 1, ' . (int) $next . ')'
                );
            } else {
                Db::getInstance()->execute(
                    'INSERT IGNORE INTO `' . _DB_PREFIX_ . 'bankwire_account_shop` (id_bankwire_account, id_shop)
                     VALUES (' . (int) $idBank . ', ' . (int) $idShop . ')'
                );
            }
        }
    }

    /**
     * Posisi tertinggi + 1 untuk bank baru, dalam lingkup toko aktif.
     *
     * @return int
     */
    public static function getNextPosition()
    {
        if (self::shopColumnsExist()) {
            // Posisi per toko: MAX di antara baris sa milik toko konteks aktif.
            $max = (int) Db::getInstance()->getValue(
                'SELECT MAX(position) FROM `' . _DB_PREFIX_ . 'bankwire_account_shop`
                 WHERE id_shop IN (' . self::currentShopIds() . ')'
            );

            return $max + 1;
        }

        $sql = new DbQuery();
        $sql->select('MAX(a.position)');
        $sql->from(self::$definition['table'], 'a');
        self::restrictToCurrentShop($sql, false);

        $max = (int) Db::getInstance()->getValue($sql);

        return $max + 1;
    }

    /**
     * Serialize baca-lalu-tulis posisi (getNextPosition + add, atau swap posisi)
     * lewat named lock MySQL per toko. Tanpa ini dua admin (atau dua tab) yang
     * submit hampir bersamaan bisa membaca MAX(position)/posisi yang sama sebelum
     * salah satu UPDATE ter-commit — race TOCTOU, karena tak ada transaksi eksplisit
     * di sekitar pasangan baca-tulis tsb.
     *
     * @param callable $fn dijalankan setelah lock didapat; hasilnya diteruskan apa adanya
     *
     * @return mixed hasil $fn(), atau false bila lock tak didapat dalam waktu wajar
     */
    public static function withPositionLock(callable $fn)
    {
        $lockName = 'bankwire_position_' . (int) Context::getContext()->shop->id;
        $db = Db::getInstance();

        if (!$db->getValue('SELECT GET_LOCK(\'' . pSQL($lockName) . '\', 3)')) {
            return false;
        }

        try {
            return $fn();
        } finally {
            $db->execute('SELECT RELEASE_LOCK(\'' . pSQL($lockName) . '\')');
        }
    }

    /**
     * Tukar posisi dua bank dalam lingkup toko konteks aktif. Dipanggil di dalam
     * withPositionLock(). Saat kolom per-toko ada, swap terjadi di baris sa milik
     * tiap toko konteks — urutan toko lain tak tersentuh. Fallback: swap posisi
     * pada baris utama (perilaku pra-1.0.3).
     *
     * @param int $idBank
     * @param int $idOther
     *
     * @return bool
     */
    public static function swapPositionInCurrentShops($idBank, $idOther)
    {
        if (self::shopColumnsExist()) {
            $db = Db::getInstance();

            // Per toko konteks: baca lalu tukar. Satu UPDATE self-join tak dipakai karena
            // MySQL tak menjamin urutan assignment pada multi-table update (a=b, b=a bisa
            // korup). withPositionLock() sudah men-serialize pasangan baca-tulis ini.
            foreach (array_map('intval', (array) Shop::getContextListShopID()) as $idShop) {
                $posBank = $db->getValue(
                    'SELECT position FROM `' . _DB_PREFIX_ . 'bankwire_account_shop`
                     WHERE id_bankwire_account = ' . (int) $idBank . ' AND id_shop = ' . (int) $idShop
                );
                $posOther = $db->getValue(
                    'SELECT position FROM `' . _DB_PREFIX_ . 'bankwire_account_shop`
                     WHERE id_bankwire_account = ' . (int) $idOther . ' AND id_shop = ' . (int) $idShop
                );

                // Salah satu bank tak terkait toko ini — lewati, tak ada yang ditukar.
                if ($posBank === false || $posOther === false) {
                    continue;
                }

                $ok = $db->execute(
                    'UPDATE `' . _DB_PREFIX_ . 'bankwire_account_shop` SET position = ' . (int) $posOther . '
                     WHERE id_bankwire_account = ' . (int) $idBank . ' AND id_shop = ' . (int) $idShop
                ) && $db->execute(
                    'UPDATE `' . _DB_PREFIX_ . 'bankwire_account_shop` SET position = ' . (int) $posBank . '
                     WHERE id_bankwire_account = ' . (int) $idOther . ' AND id_shop = ' . (int) $idShop
                );

                if (!$ok) {
                    return false;
                }
            }

            return true;
        }

        $bank = new BankAccount((int) $idBank);
        $other = new BankAccount((int) $idOther);
        if (!Validate::isLoadedObject($bank) || !Validate::isLoadedObject($other)) {
            return false;
        }

        $tmp = (int) $bank->position;
        $bank->position = (int) $other->position;
        $other->position = $tmp;

        return $bank->update() && $other->update();
    }

    /**
     * Toggle status aktif.
     *
     * @return bool
     */
    public function toggleStatus()
    {
        if (self::shopColumnsExist()) {
            // Toggle hanya pada toko konteks aktif: mengubah baris utama akan mengganti
            // status di semua toko yang berbagi bank ini.
            return (bool) Db::getInstance()->execute(
                'UPDATE `' . _DB_PREFIX_ . 'bankwire_account_shop`
                 SET active = 1 - active
                 WHERE id_bankwire_account = ' . (int) $this->id . '
                 AND id_shop IN (' . self::currentShopIds() . ')'
            );
        }

        $this->active = !(bool) $this->active;

        return $this->update();
    }

    /**
     * Set status aktif per toko konteks aktif (dipakai form edit). Baris utama
     * dibiarkan sebagai fallback; sumber kebenaran ada di bankwire_account_shop.
     *
     * @param int $idBank
     * @param bool $active
     *
     * @return bool
     */
    public static function setActiveForCurrentShops($idBank, $active)
    {
        if (!self::shopColumnsExist()) {
            return false;
        }

        return (bool) Db::getInstance()->execute(
            'UPDATE `' . _DB_PREFIX_ . 'bankwire_account_shop`
             SET active = ' . ((bool) $active ? '1' : '0') . '
             WHERE id_bankwire_account = ' . (int) $idBank . '
             AND id_shop IN (' . self::currentShopIds() . ')'
        );
    }

    /**
     * Hapus baris + asosiasi + file icon terkait.
     *
     * Tetap berarti "objek ini hilang", sesuai kontrak ObjectModel::delete().
     * Untuk melepas dari satu toko saja, pakai detachFromCurrentShop().
     *
     * @return bool
     */
    public function delete()
    {
        if (self::shopTableExists()) {
            Db::getInstance()->execute(
                'DELETE FROM `' . _DB_PREFIX_ . 'bankwire_account_shop`
                 WHERE id_bankwire_account = ' . (int) $this->id
            );
        }

        Db::getInstance()->execute(
            'DELETE FROM `' . _DB_PREFIX_ . 'bankwire_order`
             WHERE id_bankwire_account = ' . (int) $this->id
        );

        $icon = $this->icon;

        if (!parent::delete()) {
            return false;
        }

        // Hapus file icon HANYA setelah baris DB terbukti terhapus
        if ($icon) {
            $file = _PS_MODULE_DIR_ . 'bankwire/views/img/banks/' . $icon;
            if (is_file($file)) {
                @unlink($file);
            }
        }

        return true;
    }

    /**
     * Lepas dari toko pada konteks aktif; hapus total hanya bila tak ada toko lain
     * yang masih memakainya DAN belum pernah dipakai order. Menghapus dari toko B
     * tidak boleh mematikan rekening yang sama di toko A.
     *
     * @return string 'deleted' | 'detached' | 'archived' | 'failed'
     */
    public function detachFromCurrentShop()
    {
        if (self::shopTableExists()) {
            $detached = Db::getInstance()->execute(
                'DELETE FROM `' . _DB_PREFIX_ . 'bankwire_account_shop`
                 WHERE id_bankwire_account = ' . (int) $this->id . '
                 AND id_shop IN (' . self::currentShopIds() . ')'
            );

            if (!$detached) {
                return 'failed';
            }

            if (self::hasRemainingShops((int) $this->id)) {
                return 'detached';
            }
        }

        // Rekening yang pernah dipakai order tidak boleh hilang: order lama yang belum
        // dibayar membaca tujuan transfernya lewat map ini. Nonaktifkan saja — ia sudah
        // lepas dari semua toko, jadi tak muncul di mana pun.
        if (self::isUsedByOrder((int) $this->id)) {
            $this->active = false;

            return $this->update() ? 'archived' : 'failed';
        }

        return $this->delete() ? 'deleted' : 'failed';
    }

    /**
     * @param int $idBank
     *
     * @return bool
     */
    private static function isUsedByOrder($idBank)
    {
        $sql = new DbQuery();
        $sql->select('1');
        $sql->from('bankwire_order', 'o');
        $sql->where('o.id_bankwire_account = ' . (int) $idBank);

        return (bool) Db::getInstance()->getValue($sql);
    }

    /**
     * Apakah bank masih terkait toko lain di luar konteks aktif?
     *
     * @param int $idBank
     *
     * @return bool
     */
    private static function hasRemainingShops($idBank)
    {
        $sql = new DbQuery();
        $sql->select('1');
        $sql->from('bankwire_account_shop', 'sa');
        $sql->where('sa.id_bankwire_account = ' . (int) $idBank);

        return (bool) Db::getInstance()->getValue($sql);
    }
}
