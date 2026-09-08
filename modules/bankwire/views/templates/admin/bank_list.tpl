{*
* Bankwire — daftar bank di admin (custom, tanpa HelperList).
* @license http://opensource.org/licenses/afl-3.0.php Academic Free License (AFL 3.0)
*}
<div class="alert alert-info">
  <p><strong>{l s='This module lets you accept payments by bank transfer to several accounts.' mod='bankwire' d='Admin'}</strong></p>
  <p>{l s="When a customer pays by bank transfer, the order status changes to 'Awaiting bank wire payment'." mod='bankwire' d='Admin'}</p>
  <p>{l s='You must manually confirm the order once you receive the transfer.' mod='bankwire' d='Admin'}</p>
</div>

<div class="panel">
  <div class="panel-heading">
    <i class="icon-cogs"></i> {l s='Settings' mod='bankwire' d='Admin'}
  </div>
  <form action="{$bankwire_settings_url|escape:'html':'UTF-8'}" method="post" class="form-horizontal">
    <div class="form-group">
      <label class="control-label col-lg-3">{l s='Default reservation period' mod='bankwire' d='Admin'}</label>
      <div class="col-lg-3">
        <input type="text" name="BANKWIRE_RESERVATION_DAYS" value="{$bankwire_reservation_global|intval}" class="form-control" />
      </div>
      <div class="col-lg-6">
        <p class="help-block">{l s='Number of days items stay reserved, used by any bank set to 0. Enter 0 to show no reservation notice.' mod='bankwire' d='Admin'}</p>
      </div>
    </div>
    <div class="panel-footer">
      <button type="submit" name="submitBankwireSettings" class="btn btn-default pull-right">
        <i class="process-icon-save"></i> {l s='Save' mod='bankwire' d='Admin'}
      </button>
    </div>
  </form>
</div>

<div class="panel">
  <div class="panel-heading">
    <i class="icon-bank"></i> {l s='Bank accounts' mod='bankwire' d='Admin'}
    <span class="panel-heading-action">
      <a href="{$bankwire_add_url|escape:'html':'UTF-8'}" class="btn btn-primary">
        <i class="icon-plus"></i> {l s='Add a bank account' mod='bankwire' d='Admin'}
      </a>
    </span>
  </div>

  {if $bankwire_banks|@count == 0}
    <p class="alert alert-info">
      {l s='No bank account yet. Click "Add a bank account" to create the first one. Payment will appear at checkout once at least one bank is enabled.' mod='bankwire' d='Admin'}
    </p>
  {else}
    <table class="table">
      <thead>
        <tr>
          <th>{l s='Icon' mod='bankwire' d='Admin'}</th>
          <th>{l s='Bank name' mod='bankwire' d='Admin'}</th>
          <th>{l s='Account owner' mod='bankwire' d='Admin'}</th>
          <th class="text-center">{l s='Enabled' mod='bankwire' d='Admin'}</th>
          <th class="text-center">{l s='Position' mod='bankwire' d='Admin'}</th>
          <th class="text-right">{l s='Actions' mod='bankwire' d='Admin'}</th>
        </tr>
      </thead>
      <tbody>
        {foreach from=$bankwire_banks item=bank}
          <tr>
            <td>
              {if $bank.icon_url}
                <img src="{$bank.icon_url|escape:'html':'UTF-8'}" alt="" style="max-height:32px" />
              {else}
                <span class="text-muted">&mdash;</span>
              {/if}
            </td>
            <td>{$bank.bank_name|escape:'html':'UTF-8'}</td>
            <td>{$bank.owner|escape:'html':'UTF-8'}</td>
            <td class="text-center">
              <a href="{$bank.toggle_url|escape:'html':'UTF-8'}" title="{l s='Toggle' mod='bankwire' d='Admin'}">
                {if $bank.active}
                  <i class="icon-check text-success"></i>
                {else}
                  <i class="icon-remove text-danger"></i>
                {/if}
              </a>
            </td>
            <td class="text-center">
              <a href="{$bank.up_url|escape:'html':'UTF-8'}" title="{l s='Up' mod='bankwire' d='Admin'}"><i class="icon-arrow-up"></i></a>
              <span>{$bank.position|intval}</span>
              <a href="{$bank.down_url|escape:'html':'UTF-8'}" title="{l s='Down' mod='bankwire' d='Admin'}"><i class="icon-arrow-down"></i></a>
            </td>
            <td class="text-right">
              <a href="{$bank.edit_url|escape:'html':'UTF-8'}" class="btn btn-default">
                <i class="icon-edit"></i> {l s='Edit' mod='bankwire' d='Admin'}
              </a>
              <a href="{$bank.delete_url|escape:'html':'UTF-8'}" class="btn btn-default"
                 onclick="return confirm('{l s='Delete this bank account?' mod='bankwire' d='Admin' js=1}');">
                <i class="icon-trash"></i> {l s='Delete' mod='bankwire' d='Admin'}
              </a>
            </td>
          </tr>
        {/foreach}
      </tbody>
    </table>
  {/if}
</div>
