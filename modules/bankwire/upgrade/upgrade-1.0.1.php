<?php
/**
 * 1.0.1 — rekening kini terkait per toko (bankwire_account_shop).
 *
 * Instalasi lama tidak punya tabel asosiasi, sehingga query yang sudah difilter toko
 * tidak akan menemukan satu bank pun: seluruh rekening lenyap dari admin dan metode
 * pembayaran hilang dari checkout. Backfill mengaitkan setiap bank yang sudah ada ke
 * setiap toko hidup, mempertahankan perilaku lama (semua bank tampil di semua toko).
 *
 * @author Prestanesia
 * @license http://opensource.org/licenses/afl-3.0.php Academic Free License (AFL 3.0)
 */

if (!defined('_PS_VERSION_')) {
    exit;
}

/**
 * @param Bankwire $module
 *
 * @return bool
 */
function upgrade_module_1_0_1($module)
{
    $prefix = _DB_PREFIX_;
    $engine = _MYSQL_ENGINE_;

    $created = Db::getInstance()->execute(
        'CREATE TABLE IF NOT EXISTS `' . $prefix . 'bankwire_account_shop` (
            `id_bankwire_account` INT(10) UNSIGNED NOT NULL,
            `id_shop` INT(10) UNSIGNED NOT NULL,
            PRIMARY KEY (`id_bankwire_account`, `id_shop`)
        ) ENGINE=' . $engine . ' DEFAULT CHARSET=utf8mb4;'
    );

    if (!$created) {
        return false;
    }

    // Kode lain di request ini mungkin sudah menyimpulkan tabel belum ada.
    BankAccount::resetShopTableCache();

    // Hanya toko hidup: toko yang sudah dibuang tidak boleh meninggalkan baris yatim.
    $filled = Db::getInstance()->execute(
        'INSERT IGNORE INTO `' . $prefix . 'bankwire_account_shop` (id_bankwire_account, id_shop)
         SELECT a.`id_bankwire_account`, s.`id_shop`
         FROM `' . $prefix . 'bankwire_account` a
         CROSS JOIN `' . $prefix . 'shop` s
         WHERE s.`deleted` = 0'
    );

    if (!$filled) {
        return false;
    }

    // Email dikirim dari _PS_MAIL_DIR_, bukan dari folder module: tanpa penyalinan ulang
    // ini toko lama tetap memakai template lama yang menyebut satu bank secara hardcode.
    $module->copyMailTemplates();

    // Mengisi placeholder bank pada email status non-inisial. Instalasi lama belum
    // punya hook ini, jadi tanpa pendaftaran di sini email mereka tetap rusak.
    if (!$module->isRegisteredInHook('actionEmailSendBefore')) {
        $module->registerHook('actionEmailSendBefore');
    }

    return true;
}
