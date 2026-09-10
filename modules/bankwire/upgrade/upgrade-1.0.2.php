<?php
/**
 * 1.0.2 — catatan informatif per bank multibahasa (bankwire_account_lang) +
 * masa reservasi (kolom reservation_days per bank, default global BANKWIRE_RESERVATION_DAYS).
 *
 * Idempotent: CREATE TABLE IF NOT EXISTS, ADD COLUMN hanya bila belum ada, dan
 * Configuration default hanya bila belum diset. Instalasi lama tetap berjalan tanpa
 * data custom_text (opsional) dan reservation_days 0 (ikut default global).
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
function upgrade_module_1_0_2($module)
{
    $prefix = _DB_PREFIX_;
    $engine = _MYSQL_ENGINE_;

    $created = Db::getInstance()->execute(
        'CREATE TABLE IF NOT EXISTS `' . $prefix . 'bankwire_account_lang` (
            `id_bankwire_account` INT(10) UNSIGNED NOT NULL,
            `id_lang` INT(10) UNSIGNED NOT NULL,
            `custom_text` MEDIUMTEXT,
            PRIMARY KEY (`id_bankwire_account`, `id_lang`)
        ) ENGINE=' . $engine . ' DEFAULT CHARSET=utf8mb4;'
    );

    if (!$created) {
        return false;
    }

    // ADD COLUMN tidak idempotent lintas MySQL/MariaDB (tak ada IF NOT EXISTS portabel),
    // jadi cek dulu lewat information_schema sebelum menambah.
    $hasColumn = (bool) Db::getInstance()->getValue(
        'SELECT COUNT(*) FROM information_schema.COLUMNS
         WHERE TABLE_SCHEMA = DATABASE()
         AND TABLE_NAME = \'' . pSQL($prefix . 'bankwire_account') . '\'
         AND COLUMN_NAME = \'reservation_days\''
    );

    if (!$hasColumn) {
        $added = Db::getInstance()->execute(
            'ALTER TABLE `' . $prefix . 'bankwire_account`
             ADD `reservation_days` INT(10) UNSIGNED NOT NULL DEFAULT 0 AFTER `position`'
        );

        if (!$added) {
            return false;
        }
    }

    // Default global hanya bila belum ada — jangan timpa nilai yang mungkin sudah diubah.
    if (Configuration::get('BANKWIRE_RESERVATION_DAYS') === false) {
        Configuration::updateValue('BANKWIRE_RESERVATION_DAYS', 7);
    }

    return true;
}
