<?php
/**
 * 1.0.7 — Pulihkan asosiasi bank ke toko yang belum punya baris asosiasi.
 *
 * CACAT YANG DIPERBAIKI. Core PrestaShop TIDAK punya hook pembuatan toko di
 * 1.7.8/8.1/9.1 (diverifikasi terhadap source ketiga versi: tak ada actionAddShop
 * maupun event setara saat Shop::add()), jadi ketika merchant menambah toko baru ke
 * instalasi multistore, bank existing tak pernah mendapat baris di
 * bankwire_account_shop untuk toko itu — dan getActiveBanks() INNER JOIN asosiasi
 * per toko, sehingga bank tak muncul di checkout toko baru. Menyimpan ulang bank pun
 * tak membantu (asosiasi hanya dibuat saat bank DIBUAT), dan tak ada UI untuk
 * mengaitkannya.
 *
 * Pemulihan memakai backfill penuh: setiap pasangan (bank, toko) tanpa baris di
 * bankwire_account_shop diisi. Aturan tanggal TIDAK dipakai karena kolom date_add pada
 * ps_shop dihapus di PS 8.x/9.x (fatal di 8/9, jalan di 1.7.8 — drift skema lintas
 * versi). Ke-lebihan asosiasi aman: merchant bisa menonaktifkan bank per-toko lewat
 * toggle aktif, sedangkan celah semula tak bisa diperbaiki sama sekali (tanpa baris,
 * bank tak muncul di daftar mana pun).
 *
 * Idempoten (INSERT IGNORE). Self-heal yang sama (Bankwire::ensureShopAssociations)
 * juga jalan setiap kali halaman admin module dibuka, jadi upgrade ini terutama
 * menjamin pemulihan deterministik saat update tanpa menunggu kunjungan admin.
 *
 * @author PrestaShop
 * @license http://opensource.org/licenses/afl-3.0.php Academic Free License (AFL 3.0)
 */
/**
 * @param Bankwire $module
 *
 * @return bool
 */
function upgrade_module_1_0_7($module)
{
    $module->ensureShopAssociations();

    return true;
}
