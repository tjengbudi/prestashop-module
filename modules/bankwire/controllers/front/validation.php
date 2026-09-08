<?php
/**
 * Validasi order untuk bank terpilih (id_bank dari checkout).
 *
 * @author Prestanesia
 * @license http://opensource.org/licenses/afl-3.0.php Academic Free License (AFL 3.0)
 */

if (!defined('_PS_VERSION_')) {
    exit;
}

/**
 * @property Bankwire $module
 */
class BankwireValidationModuleFrontController extends ModuleFrontController
{
    /**
     * @see FrontController::postProcess()
     */
    public function postProcess()
    {
        $cart = $this->context->cart;
        if ($cart->id_customer == 0 || $cart->id_address_delivery == 0 || $cart->id_address_invoice == 0 || !$this->module->active) {
            Tools::redirect('index.php?controller=order&step=1');
        }

        // Pastikan module masih tersedia sebagai metode pembayaran
        $authorized = false;
        foreach (Module::getPaymentModules() as $module) {
            if ($module['name'] == 'bankwire') {
                $authorized = true;
                break;
            }
        }
        if (!$authorized) {
            die($this->module->getTranslator()->trans('This payment method is not available.', array(), 'Modules.Bankwire.Shop'));
        }

        $customer = new Customer($cart->id_customer);
        if (!Validate::isLoadedObject($customer)) {
            Tools::redirect('index.php?controller=order&step=1');
        }

        // Bank yang dipilih pelanggan
        $idBank = (int) Tools::getValue('id_bank');
        // Verifikasi tanda tangan pilihan yang dirender hookPaymentOptions — lihat
        // Bankwire::signBankOption(). Tanpa ini id_bank bisa dipaksa lewat form
        // lintas-situs (CSRF): order tetap milik korban, tapi rekening tujuan berubah.
        if (!$this->module->verifyBankOption($idBank, $cart, (string) Tools::getValue('bankwire_opt'))) {
            die($this->module->getTranslator()->trans('The selected bank is not available.', array(), 'Modules.Bankwire.Shop'));
        }
        $bank = $this->module->loadActiveBank($idBank);
        if ($bank === null) {
            die($this->module->getTranslator()->trans('The selected bank is not available.', array(), 'Modules.Bankwire.Shop'));
        }

        // Total dihitung dalam mata uang cart, jadi order harus memakai mata uang cart
        // juga — bukan mata uang konteks, yang bisa berbeda setelah switcher/multistore.
        $currency = new Currency((int) $cart->id_currency);
        if (!Validate::isLoadedObject($currency)) {
            die($this->module->getTranslator()->trans('This payment method is not available.', array(), 'Modules.Bankwire.Shop'));
        }

        // hookPaymentOptions menyembunyikan tombol untuk mata uang yang tak diizinkan,
        // tapi endpoint ini bisa dipanggil langsung — jadi tegakkan ulang di sini.
        if (!$this->module->checkCurrency($cart)) {
            die($this->module->getTranslator()->trans('This payment method is not available.', array(), 'Modules.Bankwire.Shop'));
        }

        // Order tanpa state valid akan menggantung tanpa status dan tanpa email.
        $idOrderState = (int) $this->module->getOrderStateId();
        $orderState = new OrderState($idOrderState);
        // !deleted ikut diperiksa: Validate::isLoadedObject() lulus untuk status yang sudah
        // dipensiunkan (uninstall/konsolidasi duplikat), dan order baru tak boleh lahir di
        // status yang tak muncul di dropdown BO.
        if (!Validate::isLoadedObject($orderState) || $orderState->deleted) {
            die($this->module->getTranslator()->trans('This payment method is not available.', array(), 'Modules.Bankwire.Shop'));
        }

        $total = (float) $cart->getOrderTotal(true, Cart::BOTH);

        // custom_text pada bahasa cart (multilang, array keyed id_lang); fallback default lang.
        $idLang = (int) $cart->id_lang;
        $customText = '';
        if (is_array($bank->custom_text)) {
            if (isset($bank->custom_text[$idLang])) {
                $customText = (string) $bank->custom_text[$idLang];
            } else {
                $defaultLang = (int) Configuration::get('PS_LANG_DEFAULT');
                if (isset($bank->custom_text[$defaultLang])) {
                    $customText = (string) $bank->custom_text[$defaultLang];
                }
            }
        }

        $mailVars = array(
            '{bankwire_bank}' => $bank->bank_name,
            '{bankwire_owner}' => (string) $bank->owner,
            '{bankwire_details}' => nl2br((string) $bank->details),
            '{bankwire_address}' => nl2br((string) $bank->address),
            '{bankwire_custom_text}' => nl2br($customText),
        );

        // Resubmit POST bayar (back-button / klik ganda): core melempar saat cart sudah
        // punya order (Cart::orderExists) atau secure_key tak cocok. Arahkan ke konfirmasi
        // order yang sudah ada, jangan biarkan exception jatuh ke halaman fatal generik.
        $existingOrderId = (int) Order::getIdByCartId((int) $cart->id);
        if ($existingOrderId > 0) {
            Tools::redirect('index.php?controller=order-confirmation&id_cart=' . (int) $cart->id
                . '&id_module=' . (int) $this->module->id
                . '&id_order=' . $existingOrderId
                . '&key=' . $customer->secure_key);
        }

        try {
            $this->module->validateOrder(
                (int) $cart->id,
                $idOrderState,
                $total,
                $this->module->displayName,
                null,
                $mailVars,
                (int) $currency->id,
                false,
                $customer->secure_key
            );
        } catch (PrestaShopException $e) {
            // Order mungkin lahir di request paralel antara cek di atas dan validateOrder.
            $retryId = (int) Order::getIdByCartId((int) $cart->id);
            if ($retryId > 0) {
                Tools::redirect('index.php?controller=order-confirmation&id_cart=' . (int) $cart->id
                    . '&id_module=' . (int) $this->module->id
                    . '&id_order=' . $retryId
                    . '&key=' . $customer->secure_key);
            }

            Tools::redirect('index.php?controller=order&step=1');
        }

        // Satu cart bisa menghasilkan beberapa order (multi-gudang/multi-carrier);
        // currentOrder hanya menyimpan yang terakhir, jadi petakan semuanya.
        $orders = Order::getByReference($this->module->currentOrderReference);
        if (count($orders)) {
            foreach ($orders as $order) {
                $this->module->saveOrderBank((int) $order->id, (int) $bank->id);
            }
        } else {
            $this->module->saveOrderBank((int) $this->module->currentOrder, (int) $bank->id);
        }

        Tools::redirect('index.php?controller=order-confirmation&id_cart=' . (int) $cart->id
            . '&id_module=' . (int) $this->module->id
            . '&id_order=' . (int) $this->module->currentOrder
            . '&key=' . $customer->secure_key);
    }
}
