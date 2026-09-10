{*
* Bankwire — info singkat per bank di widget pilihan pembayaran.
* @license http://opensource.org/licenses/afl-3.0.php Academic Free License (AFL 3.0)
*}
<section>
  <p>
    {l s='Please transfer the invoice amount to the account below. You will receive our order confirmation by email with the bank details and your order number.' mod='bankwire' d='Shop'}
    {if isset($bankwire_reservation_days) && $bankwire_reservation_days > 0}
      {if $bankwire_reservation_days > 1}
        {l s='Goods will be reserved for %d days and the order processed as soon as we receive your payment.' sprintf=[$bankwire_reservation_days] mod='bankwire' d='Shop'}
      {else}
        {l s='Goods will be reserved for %d day and the order processed as soon as we receive your payment.' sprintf=[$bankwire_reservation_days] mod='bankwire' d='Shop'}
      {/if}
    {/if}
  </p>
  {include file='module:bankwire/views/templates/hook/_partials/payment_infos.tpl'}
  {if isset($bankwire_custom_text) && $bankwire_custom_text}
    <div class="bankwire-custom-text">{$bankwire_custom_text nofilter}</div>
  {/if}
</section>
