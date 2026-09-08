{*
* Bankwire — detail rekening bank terpilih.
* @license http://opensource.org/licenses/afl-3.0.php Academic Free License (AFL 3.0)
*}
<dl>
    <dt>{l s='Amount' mod='bankwire' d='Shop'}</dt>
    <dd>{$bankwire_total|escape:'html':'UTF-8'}</dd>
    <dt>{l s='Bank' mod='bankwire' d='Shop'}</dt>
    <dd>{$bankwire_bank_name|escape:'html':'UTF-8'}</dd>
    <dt>{l s='Name of account owner' mod='bankwire' d='Shop'}</dt>
    <dd>{$bankwire_owner|escape:'html':'UTF-8'}</dd>
    <dt>{l s='Account details' mod='bankwire' d='Shop'}</dt>
    <dd>{$bankwire_details nofilter}</dd>
    {if $bankwire_address}
        <dt>{l s='Bank address' mod='bankwire' d='Shop'}</dt>
        <dd>{$bankwire_address nofilter}</dd>
    {/if}
</dl>
