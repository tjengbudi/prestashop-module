<?php
/**
 * 1.0.6 — Berhenti menimpa template email milik core, dan pulihkan yang terlanjur.
 *
 * CACAT YANG DIPERBAIKI. Sampai 1.0.5, installOrderState() selalu early-return di toko
 * standar karena core mengirim PS_OS_BANKWIRE = OrderState 10 (module_name=ps_wirepayment,
 * template=bankwire). Module menumpang state itu, lalu copyMailTemplates() menimpa
 * _PS_MAIL_DIR_/<iso>/bankwire.html|txt — file yang dipakai order ps_wirepayment juga.
 * OrderHistory memanggil Mail::Send dengan _PS_MAIL_DIR_ sebagai basis dan module_name
 * hanya dipakai menggabung extra_mail_vars, jadi email order ps_wirepayment membaca file
 * yang sudah tertimpa lalu mengirim placeholder mentah {bankwire_bank}.
 *
 * Sejak 1.0.6 module punya OrderState sendiri (Bankwire::OS_CONFIG_KEY, ditulis GLOBAL)
 * dengan template bernama unik (Bankwire::MAIL_TEMPLATE), jadi tak ada file core disentuh.
 *
 * Order historis SENGAJA tidak dipindah state: mengubah riwayat order lebih berbahaya
 * daripada manfaatnya, dan pemulihan template core di bawah membuat email mereka benar lagi.
 *
 * Idempotent: state hanya dibuat bila kunci global belum terisi, dan pemulihan hanya
 * menyentuh file yang TERBUKTI membawa penanda module ini.
 *
 * @author Prestanesia
 * @license http://opensource.org/licenses/afl-3.0.php Academic Free License (AFL 3.0)
 */

if (!defined('_PS_VERSION_')) {
    exit;
}

/**
 * Pulihkan mails/en/bankwire.html|txt core yang ditimpa versi lama module ini.
 *
 * HANYA locale `en`. Core PrestaShop hanya mengirim template email dalam bahasa Inggris
 * (`mails/en/`), jadi itu satu-satunya isi otentik yang bisa dibundel module. Versi lama
 * menimpa SEMUA locale (ia jatuh ke sumber `en` untuk iso yang tak punya folder), tapi
 * menulis isi Inggris ke `mails/fr/` akan menukar satu kerusakan dengan kerusakan lain —
 * dan lebih buruk, ia menghapus penanda `{bankwire_bank}` sehingga kondisinya tak bisa
 * dideteksi maupun dipulihkan lagi nanti. Locale non-en yang tercemar karena itu
 * DILAPORKAN, tidak disentuh.
 *
 * Varian dipilih per MAJOR: isi core berbeda di 1.7 / 8 / 9 (khususnya .txt — md5 8.1.6
 * dan 9.1.4 tidak sama), jadi satu varian "8 dan 9" akan memulihkan toko 8.1 dengan isi 9.1.
 *
 * @param Bankwire $module
 *
 * @return array{restored: int, failed: array<int, string>, untouched: array<int, string>}
 */
function bankwire_restore_core_mail_templates($module)
{
    if (version_compare(_PS_VERSION_, '8.0.0', '<')) {
        $variant = 'core-1.7';
    } elseif (version_compare(_PS_VERSION_, '9.0.0', '<')) {
        $variant = 'core-8';
    } else {
        $variant = 'core-9';
    }

    $srcDir = dirname(dirname(__FILE__)) . '/mails/_core_restore/';
    $result = array('restored' => 0, 'failed' => array(), 'untouched' => array());

    foreach (Language::getLanguages(false) as $lang) {
        $iso = strtolower($lang['iso_code']);
        foreach (array('html', 'txt') as $ext) {
            $target = _PS_MAIL_DIR_ . $iso . '/bankwire.' . $ext;
            if (!is_file($target)) {
                continue;
            }

            $current = (string) @file_get_contents($target);
            // Penanda module ini; tak pernah ada di template core.
            if (strpos($current, '{bankwire_bank}') === false
                && strpos($current, '{bankwire_custom_text}') === false
            ) {
                continue; // bukan kita yang menimpa — jangan sentuh
            }

            if ($iso !== 'en') {
                // Tercemar, tapi kita tak punya isi otentik untuk bahasa ini.
                $result['untouched'][] = $iso . '/bankwire.' . $ext;
                continue;
            }

            $source = $srcDir . $variant . '.' . $ext;
            if (!is_file($source) || !is_writable($target) || !@copy($source, $target)) {
                $result['failed'][] = $iso . '/bankwire.' . $ext;
                continue;
            }

            ++$result['restored'];
        }
    }

    return $result;
}

/**
 * @param Bankwire $module
 *
 * @return bool
 */
function upgrade_module_1_0_6($module)
{
    // 1. Pulihkan file core DULU: bila langkah berikutnya gagal, kerusakan pada module LAIN
    //    tetap sudah diperbaiki.
    $restore = bankwire_restore_core_mail_templates($module);

    // Kegagalan IO tak boleh senyap. Di 1.7.8/8.1 tak ada fallback pindai modules/*/mails/,
    // jadi "Update succeeded" sambil nol file tersentuh berarti email pertama tak terkirim
    // dan tak seorang pun tahu sebabnya.
    if (!empty($restore['failed'])) {
        PrestaShopLogger::addLog(
            '[bankwire 1.0.6] gagal memulihkan template email core: '
            . implode(', ', $restore['failed'])
            . ' — pulihkan manual dari paket PrestaShop.',
            3,
            null,
            'Bankwire'
        );
    }
    if (!empty($restore['untouched'])) {
        PrestaShopLogger::addLog(
            '[bankwire 1.0.6] template email core untuk locale non-en masih tercemar versi lama '
            . 'dan TIDAK dipulihkan otomatis (core hanya mengirim bahasa Inggris): '
            . implode(', ', $restore['untouched'])
            . ' — pulihkan manual dari paket PrestaShop.',
            2,
            null,
            'Bankwire'
        );
    }

    // 2. OrderState milik module — SATU pemilik logikanya: Bankwire::ensureOrderState().
    //    Menyalin blok pembuatan state ke sini adalah cara build 1.0.6 pertama mendrift:
    //    install memakai updateGlobalValue sementara salinan di upgrade tidak, lalu toko
    //    yang terlanjur upgrade mendapat OrderState KEDUA. ensureOrderState() juga yang
    //    mengadopsi baris shop-scoped peninggalan build itu alih-alih menambah state baru.
    if (!$module->ensureOrderState()) {
        return false;
    }

    // 3. Template milik module, di bawah nama yang tak dimiliki siapa pun.
    $module->copyMailTemplates();

    return true;
}
