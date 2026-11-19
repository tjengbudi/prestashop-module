# Breaking Changes PrestaShop 8.x

Hal yang pecah saat module 1.7 dibawa ke PS8. Diseed 2026-06-29 dari riset devdocs (core-updates 8.0) + ruleset psm-validate.

## Kelas / Method dihapus
- `Tools::jsonEncode` / `Tools::jsonDecode` → `json_encode` / `json_decode` native.
- `Tools::addonsRequest` → dihapus, integrasi addons lama tak didukung.
- Kelas `Attribute` → di-rename `ProductAttribute`.
- `HookDispatcher` → dihapus (deprecated sejak 1.7.5). Pakai `Hook::exec` / dispatchHook Symfony.
- `Validate::isPasswd` → `Validate::isPlaintextPassword` / `isHashedPassword`.
- Hook alias API (`Hook::getHookAliasList`, `Hook::getRetroHookName`) → deprecated/dihapus. Pakai nama hook kanonik.

## Konstanta dihapus
- `_PS_SMARTY_DIR_`, `_PS_TCPDF_DIR_`, `_PS_TCPDF_PATH_`, `_PS_SWIFT_DIR_` → hapus, pakai service/path modern.

## Perilaku
- Dev mode: daftar hook tanpa implementasi method-nya → exception (bukan diam).
- Hook alias → deprecation notice.

Lihat juga [[breaking-changes-9]], [[cross-version-patterns]], [[validator-rules]].

Sumber: devdocs.prestashop-project.org/8/modules, validator.prestashop.com/changelog.

## Verified additions 2026-11-18 `[core]`

Verified inside the pinned flashlight images (1.7.8.11 / 8.1.6-nginx); adds to and corrects the list above.
- Line 9 is over-broad: the class deleted in 8.0 is `PrestaShopBundle\Service\Hook\HookDispatcher`. `PrestaShop\PrestaShop\Core\Hook\HookDispatcher` and its interface still exist at 9.1.4, so the bare name is not a break. `cls-hookdispatcher` was narrowed accordingly. → [[validator-rules]]
- Line 10's suggested replacement is wrong for 9 targets: `Validate::isPlaintextPassword` survives 8.1.6 but is gone in 9; 8.1.6 keeps only `isPasswdAdmin`, which is itself removed in 9. On 9 use `Core\Security\PasswordPolicyConfiguration` or `password_verify`.
- Line 11/18: the alias API is **removed** in 8 (zero matches at 8.1.6 and 9.1.4), so this is an error class, not a deprecation notice.
- `Validate::isAnything` also disappears — but only in 9 (present at 8.1.6).
- `vendor/` at 8.1.6 still ships `pear/archive_tar` and `soundasleep/html2text`. The four packages that break in 9 (`guzzlehttp/guzzle`, `swiftmailer/swiftmailer`, `league/tactician-bundle`, `sensio/framework-extra-bundle`) were all verified present at 1.7.8.11 and 8.1.6-nginx and absent at 9.1.4 — they are 8→9 breaks, not 1.7→8 ones, which is why their rules affect only `9`.
- 1.7→8 vendor reality: nothing was pulled from `vendor/` between 1.7.8.11 and 8.1.6-nginx in this set; the 1.7→8 surface is code/API removals, not dependencies.
- `_PS_TCPDF_PATH_` is documented for 8.0; `_PS_TCPDF_DIR_` is claimed by the ruleset but appears in no 8.0 doc — unverified, kept flagged rather than asserted.
- The `8.1.6-nginx` image runs PHP 8.1.
