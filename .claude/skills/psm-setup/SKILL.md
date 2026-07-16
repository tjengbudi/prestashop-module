---
name: psm-setup
description: Sets up PrestaShop Module Builder module in a project. Use when the user requests to 'install psm module', 'configure PrestaShop Module Builder', or 'setup PrestaShop Module Builder'.
---

# Module Setup

## Resolution rules

- Bare paths and `{skill-root}` (e.g. `scripts/merge-config.py`, `assets/module.yaml`) resolve from this skill's installed directory.
- `{project-root}` → the project working directory.
- `{skill-name}` → the skill directory's basename.

## Overview

Installs and configures a BMad module into a project. Module identity (name, code, version) comes from `assets/module.yaml`. Collects user preferences and writes them to three files:

- **`{project-root}/_bmad/config.yaml`** — shared project config: core settings at root (e.g. `output_folder`, `document_output_language`) plus a section per module with metadata and module-specific values.
- **`{project-root}/_bmad/config.user.yaml`** — personal settings intended to be gitignored. `user_name`, `communication_language`, and any module variable marked `user_setting: true` in `assets/module.yaml` live exclusively here; the merge script routes them, so they never land in `config.yaml`.
- **`{project-root}/_bmad/module-help.csv`** — registers module capabilities for the help system.

Both config scripts use an anti-zombie pattern — existing entries for this module are removed before writing fresh ones, so stale values never persist. Values matching the current schema survive the rebuild as fallback defaults, so an update run cannot lose settings the answers file does not mention.

`{project-root}` is a **literal token** in config _values_ (the data written into the files above) — never substitute it there. It signals to the consuming LLM that the value is relative to the project root, not the skill root. **This does not apply to the filesystem path _arguments_ passed to the scripts below** (the `--*-path`, `--*-dir`, and `--target` arguments): those are real paths, so you **must** resolve `{project-root}` to the actual project root before running. The scripts reject an unresolved token with an error.

## On Activation

1. Read `assets/module.yaml` for module metadata and variable definitions (the `code` field is the module identifier)
2. Run the defaults pre-pass:

```bash
python3 scripts/merge-config.py --show-defaults --config-path "{project-root}/_bmad/config.yaml" --user-config-path "{project-root}/_bmad/config.user.yaml" --module-yaml assets/module.yaml --legacy-dir "{project-root}/_bmad"
```

Its JSON is the single source for what to ask and with which defaults: `install_type` (`fresh-install` / `update` / `legacy-migration`), `legacy_configs_found`, `ask_core`, and per-key resolved defaults with provenance (`existing` / `legacy` / `default`). Do not re-derive any of it from the YAML files. Tell the user which install type this is; when legacy configs were found, mention their values become fallback defaults and the files are cleaned up after setup.

If the user provides arguments (e.g. `accept all defaults`, `--headless`, or inline values like `user name is BMad, I speak Swahili`), map any provided values to config keys, use the pre-pass defaults for the rest, and skip interactive prompting. Still display the full confirmation summary at the end.

## Collect Configuration

Ask the user for values, showing the pre-pass defaults in brackets (name the provenance when a value came from existing or legacy config). Present all values together so the user can respond once with only the values they want to change (e.g. "change language to Swahili, rest are fine"). Never tell the user to "press enter" or "leave blank" — in a chat interface they must type something to respond.

**Core config** (only when the pre-pass says `ask_core: true`): `user_name`, `communication_language` and `document_output_language` (ask as a single language question — both keys get the same answer), and `output_folder`, with defaults from `core_defaults`.

**Module config**: ask each variable in `module_defaults` using its `prompt` field from `assets/module.yaml` with its resolved default.

## Write Files

Write a temp JSON file with the collected answers structured as `{"core": {...}, "module": {...}}` (omit `core` if `ask_core` was false). Only the values the user confirmed or changed are needed — the script preserves existing configured values and applies legacy fallbacks itself. Values inside this JSON keep the literal `{project-root}` token. Then run both scripts — they can run in parallel since they write to different files.

```bash
python3 scripts/merge-config.py --config-path "{project-root}/_bmad/config.yaml" --user-config-path "{project-root}/_bmad/config.user.yaml" --module-yaml assets/module.yaml --answers {temp-file} --legacy-dir "{project-root}/_bmad"
python3 scripts/merge-help-csv.py --target "{project-root}/_bmad/module-help.csv" --source assets/module-help.csv --legacy-dir "{project-root}/_bmad" --module-code psm
```

Both scripts output JSON to stdout with results. If either exits non-zero, surface the error and stop. `merge-config.py` also creates every configured directory (module.yaml `directories:` entries, `output_folder`, module path values) and reports them in `directories_created`. Legacy files read as fallbacks are deleted after a successful merge — `legacy_configs_deleted` and `legacy_csvs_deleted` confirm the cleanup. Run either script with `--help` for full usage.

## Cleanup Legacy Directories

After both merge scripts complete successfully, remove the installer's package directories. Skills and agents in these directories are already installed at `.claude/skills/` — the `{project-root}/_bmad/` directory should only contain config files and module runtime data.

```bash
python3 scripts/cleanup-legacy.py --bmad-dir "{project-root}/_bmad" --module-code psm --also-remove _config --skills-dir "{project-root}/.claude/skills" --preserve memory --preserve .memlog.md
```

The script verifies that every skill in the legacy directories exists at `.claude/skills/` before removing anything, and keeps the `--preserve` subtrees (the module's knowledge base and memlog) in place. Directories without skills (like `_config/`) are removed directly. If the script exits non-zero, surface the error and stop. Missing directories (already cleaned by a prior run) are not errors — the script is idempotent. Check `directories_removed`, `directories_preserved`, and `files_removed_count` in the JSON output for the confirmation step.

## Seed Knowledge Base & External Deps

After setup, the shared knowledge base at `{project-root}/_bmad/psm/memory/` (`tech/`, `ecommerce/`, `projects/`) is still empty. Do not seed it here — that is `psm-agent-expert`'s first-run job, and that skill's `references/maintain-knowledge.md` owns the sources. Tell the user to run `psm-agent-expert` once to fill it.

Also check external dependencies: **Docker** is required for the `psm-validate`/`psm-optimize` tests in `prestashop-flashlight`. Check `docker --version`; if it is missing, tell the user how to install it (do not install it automatically) and that flashlight images are pulled when the first test workflow runs.

## Confirm

Use the script JSON output to display what was written — the `install_type` (fresh install / update / legacy migration), config values set, user settings written to `config.user.yaml` (`user_keys` in the result), help entries added, and `directories_created`. If legacy files were deleted, mention the migration. If legacy directories were removed, report the count and list (e.g. "Cleaned up 106 installer package files from bmb/, core/, \_config/ — skills are installed at .claude/skills/"). Then display the `module_greeting` from `assets/module.yaml` to the user.

**Headless return**: when `--headless` was passed, append one `assumption` entry summarizing the defaulted values and any legacy carry-over — `python3 {project-root}/_bmad/scripts/memlog.py append --path "{project-root}/_bmad/psm/.memlog.md" --type assumption --text "<summary>"` — then end with a minimal JSON result (`status`, `install_type`, `config_path`, `user_config_path`, help entries, `directories_created`) instead of the prose summary.

## Outcome

Once the user's `user_name` and `communication_language` are known (from collected input, arguments, or existing config), use them consistently for the remainder of the session: address the user by their configured name and communicate in their configured `communication_language`.
