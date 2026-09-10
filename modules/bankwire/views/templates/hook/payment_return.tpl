{*
* Bankwire — halaman konfirmasi order.
* @license http://opensource.org/licenses/afl-3.0.php Academic Free License (AFL 3.0)
*}
{if $status == 'ok'}
    <p>
      {l s='Your order on %s is complete.' sprintf=[$shop_name] mod='bankwire' d='Shop'}<br/>
      {l s='Please send us your payment by bank transfer with the following details:' mod='bankwire' d='Shop'}
    </p>
    {include file='module:bankwire/views/templates/hook/_partials/payment_infos.tpl'}
    {if isset($bankwire_custom_text) && $bankwire_custom_text}
      <div class="bankwire-custom-text">{$bankwire_custom_text nofilter}</div>
    {/if}

    <p>
      {l s='Please specify your order reference %s in the transfer description.' sprintf=[$reference] mod='bankwire' d='Shop'}<br/>
      {l s='We have also sent you this information by email.' mod='bankwire' d='Shop'}
    </p>
    <strong>{l s='Your order will be shipped as soon as we receive your payment.' mod='bankwire' d='Shop'}</strong>
    <p>
      {l s='If you have questions, comments or concerns, please contact our %s.' mod='bankwire' d='Shop' sprintf=[$contact_anchor]}
    </p>
{else}
    <p class="warning">
      {l s='We noticed a problem with your order. If you think this is an error, feel free to contact our %s.' mod='bankwire' d='Shop' sprintf=[$contact_anchor]}
    </p>
{/if}
