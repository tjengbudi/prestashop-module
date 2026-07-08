#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = ["pyyaml"]
# ///
"""Plan a module setup run: classify install state and resolve effective defaults.

Read-only pre-pass for the psm-setup skill. It replaces the by-hand file
inspection and three-source default merge that the setup prompt would otherwise
re-derive on every run. It writes nothing and deletes nothing — merge-config.py
and cleanup-legacy.py own all mutation.

It reports:
  - module_code            derived from module.yaml (never hardcode it downstream)
  - install_state          fresh | fresh_consolidate | update | legacy_migration
  - module_section_present whether config.yaml already has this module's section
  - legacy_configs_found   legacy per-module/core config files that exist
  - core_needed            whether shared core keys still need collecting
  - defaults.core          [{key, prompt, default, target}] (only when core_needed)
  - defaults.module        [{key, prompt, default, user_setting}]

Effective defaults follow the setup priority: legacy config value (when present)
overrides the module.yaml / builtin default. Explicit user answers, collected
later, override everything — that final merge lives in merge-config.py, which
this script imports so the priority logic has a single source of truth.

Exit codes: 0=success, 1=validation error, 2=runtime error
"""

import argparse
import importlib.util
import json
import sys
import types
from pathlib import Path

try:
    import yaml  # noqa: F401  (used indirectly via the imported merge-config module)
except ImportError:
    print("Error: pyyaml is required (PEP 723 dependency)", file=sys.stderr)
    sys.exit(2)


def _load_merge_config() -> types.ModuleType:
    """Import the sibling merge-config.py module by path (hyphenated filename)."""
    mc_path = Path(__file__).parent / "merge-config.py"
    spec = importlib.util.spec_from_file_location("merge_config", mc_path)
    if spec is None or spec.loader is None:
        print(f"Error: could not load {mc_path}", file=sys.stderr)
        sys.exit(2)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mc = _load_merge_config()

# Shared core keys, and which file each is written to. Mirrors merge-config's
# _CORE_KEYS / _CORE_USER_KEYS split so targets stay consistent.
_CORE_ORDER = ("user_name", "communication_language", "document_output_language", "output_folder")
_CORE_BUILTIN = {
    "user_name": {"prompt": "Your name (how the assistant should address you)?", "default": "BMad"},
    "communication_language": {"prompt": "Language for conversation?", "default": "English"},
    "document_output_language": {"prompt": "Language for generated documents?", "default": "English"},
    "output_folder": {"prompt": "Output folder?", "default": "{project-root}/_bmad-output"},
}


def parse_args():
    parser = argparse.ArgumentParser(
        description="Plan a module setup run: classify install state and resolve effective defaults (read-only)."
    )
    parser.add_argument("--config-path", required=True, help="Path to the target _bmad/config.yaml file")
    parser.add_argument("--module-yaml", required=True, help="Path to the module.yaml definition file")
    parser.add_argument(
        "--legacy-dir",
        help="Path to _bmad/ directory to check for legacy per-module config files.",
    )
    return parser.parse_args()


def classify_state(module_section_present: bool, legacy_found: bool) -> str:
    """Map the two booleans that decide the install state to a single label."""
    if module_section_present:
        return "legacy_migration" if legacy_found else "update"
    return "fresh_consolidate" if legacy_found else "fresh"


def main():
    args = parse_args()

    module_yaml = mc.load_yaml_file(args.module_yaml)
    if not module_yaml:
        print(f"Error: Could not load module.yaml from {args.module_yaml}", file=sys.stderr)
        sys.exit(1)

    module_code = module_yaml.get("code")
    if not module_code:
        print("Error: module.yaml must have a 'code' field", file=sys.stderr)
        sys.exit(1)

    existing_config = mc.load_yaml_file(args.config_path)
    module_section_present = module_code in existing_config
    core_present = any(k in existing_config for k in mc._CORE_KEYS)

    # Legacy values (empty dicts when --legacy-dir is absent or nothing is found).
    legacy_core: dict = {}
    legacy_module: dict = {}
    legacy_files: list = []
    if args.legacy_dir:
        legacy_core, legacy_module, legacy_files = mc.load_legacy_values(
            args.legacy_dir, module_code, module_yaml
        )

    install_state = classify_state(module_section_present, bool(legacy_files))

    # Core defaults: legacy value wins over the builtin default. Only surfaced
    # when no shared core keys exist yet, matching the setup contract.
    core_defaults = []
    core_needed = not core_present
    if core_needed:
        for key in _CORE_ORDER:
            spec = _CORE_BUILTIN[key]
            default = legacy_core.get(key, spec["default"])
            target = "config.user.yaml" if key in mc._CORE_USER_KEYS else "config.yaml"
            core_defaults.append(
                {"key": key, "prompt": spec["prompt"], "default": default, "target": target}
            )

    # Module defaults: every variable definition with a prompt, legacy value
    # winning over the module.yaml default.
    module_defaults = []
    for name, var_def in module_yaml.items():
        if isinstance(var_def, dict) and "prompt" in var_def:
            default = legacy_module.get(name, var_def.get("default"))
            module_defaults.append(
                {
                    "key": name,
                    "prompt": var_def["prompt"],
                    "default": default,
                    "user_setting": var_def.get("user_setting") is True,
                }
            )

    result = {
        "status": "success",
        "module_code": module_code,
        "install_state": install_state,
        "module_section_present": module_section_present,
        "core_present": core_present,
        "core_needed": core_needed,
        "legacy_configs_found": legacy_files,
        "defaults": {"core": core_defaults, "module": module_defaults},
    }
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
