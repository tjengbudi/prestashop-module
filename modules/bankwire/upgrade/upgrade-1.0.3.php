<?php
/**
 * 1.0.3 — active + position pindah per-toko (kolom di bankwire_account_shop).
 *
 * Sebelumnya keduanya di baris bersama bankwire_account, sehingga toggle/urutan di
 * satu toko bocor ke semua toko yang berbagi bank. Kolom lama dipertahankan sebagai
 * fallback selama jendela upgrade (file baru melayani FO sebelum skrip ini jalan).
 *
 * Idempotent: ADD COLUMN hanya bila belum ada, backfill INSERT..SELECT aman diulang.
 * Backfill menyalin nilai global lama ke tiap baris toko, jadi perilaku identik tepat
 * setelah upgrade — admin lalu bisa mengubahnya per toko.
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
function upgrade_module_1_0_3($module)
{
    $prefix = _DB_PREFIX_;

    // Tabel asosiasi harus ada (dibuat di 1.0.1). Instalasi yang melompati langkah itu
    // tetap aman: buat bila belum ada supaya ALTER di bawah tak fatal.
    $created = Db::getInstance()->execute(
        'CREATE TABLE IF NOT EXISTS `' . $prefix . 'bankwire_account_shop` (
            `id_bankwire_account` INT(10) UNSIGNED NOT NULL,
            `id_shop` INT(10) UNSIGNED NOT NULL,
            PRIMARY KEY (`id_bankwire_account`, `id_shop`)
        ) ENGINE=' . _MYSQL_ENGINE_ . ' DEFAULT CHARSET=utf8mb4;'
    );

    if (!$created) {
        return false;
    }

    // ADD COLUMN tak punya IF NOT EXISTS portabel — cek information_schema dulu.
    $hasColumns = (bool) Db::getInstance()->getValue(
        'SELECT COUNT(*) FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE()
         AND TABLE_NAME = \'' . pSQL($prefix . 'bankwire_account_shop') . '\'
         AND COLUMN_NAME = \'position\''
    );

    if (!$hasColumns) {
        $added = Db::getInstance()->execute(
            'ALTER TABLE `' . $prefix . 'bankwire_account_shop`
             ADD `active` TINYINT(1) UNSIGNED NOT NULL DEFAULT 1,
             ADD `position` INT(10) UNSIGNED NOT NULL DEFAULT 0'
        );

        if (!$added) {
            return false;
        }
    }

    // Backfill dari baris utama: tiap toko warisi active/position global lama supaya
    // checkout/admin tampil & terurut persis seperti sebelum upgrade.
    $filled = Db::getInstance()->execute(
        'UPDATE `' . $prefix . 'bankwire_account_shop` sa
         JOIN `' . $prefix . 'bankwire_account` a
           ON a.id_bankwire_account = sa.id_bankwire_account
         SET sa.active = a.active, sa.position = a.position'
    );

    if (!$filled) {
        return false;
    }

    // Kode lain di request ini mungkin sudah menyimpulkan kolom belum ada.
    BankAccount::resetShopTableCache();

    return true;
}
