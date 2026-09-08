<?php
/**
 * 1.0.4 — Cutover hook konfirmasi order: paymentReturn -> displayPaymentReturn.
 *
 * Core 1.7/8/9 memanggil hook displayPaymentReturn dari OrderConfirmationController;
 * paymentReturn tak dipanggil lagi oleh core manapun (diverifikasi terhadap source
 * 1.7.8.11/8.1.6/9.1.4). Tanpa pendaftaran ini, instalasi lama tidak menampilkan
 * detail bank di halaman konfirmasi order setelah checkout — pelanggan hanya
 * mendapatkannya lewat email.
 *
 * Idempotent: register/unregister hanya dijalankan bila kondisi belum terpenuhi.
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
function upgrade_module_1_0_4($module)
{
    if (!$module->isRegisteredInHook('displayPaymentReturn')) {
        // install() mengecek hasil registerHook(); upgrade harus konsisten — tanpa cek,
        // kegagalan DB dilaporkan sukses padahal halaman konfirmasi kehilangan blok bank.
        if (!$module->registerHook('displayPaymentReturn')) {
            return false;
        }
    }

    // Cutover bersih: hapus pendaftaran hook lama yang sudah tak dipanggil core,
    // supaya ps_hook_module tidak menumpuk dua baris untuk satu perilaku.
    if ($module->isRegisteredInHook('paymentReturn')) {
        $module->unregisterHook('paymentReturn');
    }

    return true;
}
