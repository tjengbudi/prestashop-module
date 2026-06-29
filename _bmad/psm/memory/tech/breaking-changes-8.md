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
