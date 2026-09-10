<?php
/**
 * 1.0.5 — Kunci tanda tangan pilihan bank (CSRF checkout).
 *
 * signBankOption() memakai kunci milik module (BANKWIRE_SIGNING_KEY di ps_configuration),
 * bukan _PS_PASSWD_KEY_: konstanta core itu tak terdefinisi di image PS 8/9, dan PHP 8
 * melempar Error untuk konstanta tak dikenal (PHP 7 hanya warning lalu memakai nama
 * literal). Instalasi 1.0.4 belum punya konfigurasi ini — tanpa langkah ini, checkout
 * jatuh ke fallback getSigningKey() yang deterministik tapi lemah.
 *
 * Idempotent: kunci hanya dibuat bila belum ada.
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
function upgrade_module_1_0_5($module)
{
    if (!Configuration::get('BANKWIRE_SIGNING_KEY')) {
        Configuration::updateValue('BANKWIRE_SIGNING_KEY', bin2hex(random_bytes(32)));
    }

    return true;
}
