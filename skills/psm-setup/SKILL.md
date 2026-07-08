---
name: psm-setup
description: Sets up PrestaShop Module Builder module in a project. Use when the user requests to 'install psm module', 'configure PrestaShop Module Builder', or 'setup PrestaShop Module Builder'.
---

# Module Setup

## Overview

Installs and configures a BMad module into a project. Module identity (name, code, version) comes from `assets/module.yaml`. Collects user preferences and writes them to three files:

- **`{project-root}/_bmad/config.yaml`** — shared project config: core settings at root (e.g. `output_folder`, `document_output_language`) plus a section per module with metadata and module-specific values.
- **`{project-root}/_bmad/config.user.yaml`** — personal settings intended to be gitignored: `user_name`, `communication_language`, and any module variable marked `user_setting: true` in `assets/module.yaml`.
- **`{project-root}/_bmad/module-help.csv`** — registers module capabilities for the help system.

`{project-root}` is a **literal token** in config _values_ (the data written into the files above) — never substitute it there. It signals to the consuming LLM that the value is relative to the project root, not the skill root. **This does not apply to the filesystem path _arguments_ passed to the scripts below** (the `--*-path`, `--*-dir`, `--project-root`, and `--target` arguments): those are real paths, so you **must** resolve `{project-root}` to the actual project root before running, or the scripts reject the unresolved token with an error.

## On Activation

Confirm `python3` is available (`python3 --version`) — every script below requires it. If it is missing, tell the user how to install it and stop before prompting.

Run the planner to classify the install and resolve effective defaults in one read-only pass (resolve `{project-root}` in the path arguments first):

```bash
python3 scripts/plan-setup.py --config-path "{project-root}/_bmad/config.yaml" --module-yaml assets/module.yaml --legacy-dir "{project-root}/_bmad"
```

If the planner exits non-zero, surface the error and stop before prompting — the run yields no defaults, so continuing is unsafe.

It returns `module_code` (use this everywhere below — never hardcode it), `install_state`, `core_needed`, `legacy_configs_found`, and `defaults` (the effective default for every core and module key, with legacy values already applied over the `module.yaml` defaults). Read state from this JSON instead of inspecting config files by hand. Inform the user based on `install_state`:

- **`fresh`** — new install, no prior config.
- **`fresh_consolidate`** — installer config was detected; values will be consolidated into the new format.
- **`update`** — this module already has a section; you are updating it.
- **`legacy_migration`** — legacy per-module config found alongside existing config; legacy values are used as fallback defaults.

In every state, legacy per-module config files and directories are cleaned up after setup.

If the user provides arguments (e.g. `accept all defaults`, `--headless`, or inline values like `user name is BMad, I speak Swahili`), map any provided values to config keys, use the planner's defaults for the rest, and skip interactive prompting. Still display the full confirmation summary at the end.

## Collect Configuration

Present the planner's `defaults` and ask the user for values, showing each default in brackets. Present all values together so the user can respond once with only the values they want to change (e.g. "change language to Swahili, rest are fine"). Never tell the user to "press enter" or "leave blank" — in a chat interface they must type something to respond.

When `install_state` is `update` and no arguments were supplied, note the module is already configured and offer a keep-all exit: tell me only what to change, or say nothing to keep everything. Either way the run stays safe — the anti-zombie merge rewrites this module's section cleanly.

**Core config** appears only when `core_needed` is true. Ask `communication_language` and `document_output_language` as a single language question (both keys get the same answer) — but if the user's answer implies they want to converse in one language and generate documents in another, collect the two separately. The planner marks each key's `target` (`config.yaml` at root, shared across modules, or `config.user.yaml` for `user_name`/`communication_language`).

**Module config** is every entry in `defaults.module`; ask using each `prompt` with its resolved `default`.

## Write Files

Write a temp JSON file with the collected answers structured as `{"core": {...}, "module": {...}}` (omit `core` when `core_needed` is false). Give it a run-unique name under the OS temp dir (e.g. `$(mktemp)`), overwrite rather than reuse so a stale file from a failed run can't feed a re-run, and delete it after both merge scripts complete. Values inside this JSON keep the literal `{project-root}` token. Then run both scripts — they can run in parallel since they write to different files. Pass the `module_code` from the planner and resolve `{project-root}` in every path argument to the actual project root first (these are filesystem paths, not config values). `--project-root` makes merge-config create the configured output directories in the same pass.

```bash
python3 scripts/merge-config.py --config-path "{project-root}/_bmad/config.yaml" --user-config-path "{project-root}/_bmad/config.user.yaml" --module-yaml assets/module.yaml --answers {temp-file} --legacy-dir "{project-root}/_bmad" --project-root "{project-root}"
python3 scripts/merge-help-csv.py --target "{project-root}/_bmad/module-help.csv" --source assets/module-help.csv --legacy-dir "{project-root}/_bmad" --module-code {module_code}
```

Both scripts output JSON to stdout. If either exits non-zero, surface the error and stop — then tell the user the setup is safe to re-run from the top once the cause is fixed: the merge scripts overwrite this module's entries cleanly (anti-zombie), so a re-run leaves no duplicate or stale values. The scripts read legacy config values as fallback defaults, then delete the legacy files after a successful merge; check `legacy_configs_deleted` and `legacy_csvs_deleted` to confirm cleanup, and `output_dirs_created` for the directories made. Run `scripts/merge-config.py --help` or `scripts/merge-help-csv.py --help` for full usage.

## Cleanup Legacy Directories

After both merge scripts complete successfully, remove the installer's package directories. Skills and agents in these directories are already installed at `.claude/skills/` — the `{project-root}/_bmad/` directory should only contain config files.

As with the merge scripts, replace `{project-root}` in the `--bmad-dir` and `--skills-dir` path arguments with the actual project root, and pass the planner's `module_code`.

```bash
python3 scripts/cleanup-legacy.py --bmad-dir "{project-root}/_bmad" --module-code {module_code} --also-remove _config --skills-dir "{project-root}/.claude/skills"
```

The script verifies that every skill in the legacy directories exists at `.claude/skills/` before removing anything. Directories without skills (like `_config/`) are removed directly. If the script exits non-zero, surface the error and stop. Missing directories (already cleaned by a prior run) are not errors — the script is idempotent.

Check `directories_removed` and `files_removed_count` in the JSON output for the confirmation step. Run `scripts/cleanup-legacy.py --help` for full usage.

## Seed Knowledge Base & External Deps (psm-specific)

After the directories are created, the shared knowledge base at `{project-root}/_bmad/psm/memory/` (`tech/`, `ecommerce/`, `projects/`) is still empty. Do not seed it here — that is `psm-agent-expert`'s job, which has first-run seed logic (see that skill's `references/maintain-knowledge.md`: it seeds from the research in `{project-root}/skills/reports/prestashop-module-builder-plan.md` plus the catalogs in `{project-root}/skills/psm-cross-version/references/version-safe-patterns.md` and `{project-root}/skills/psm-develop/references/ecommerce-function-catalog.md`, falling back to devdocs when absent). Tell the user to run `psm-agent-expert` once to populate the knowledge base.

Also flag a forward-looking dependency — this is not a setup blocker, only a heads-up for later workflows: **Docker** is required to run the `psm-validate`/`psm-optimize` tests inside `prestashop-flashlight`. Check `docker --version`; if it is missing, tell the user how to install it (do not install automatically) and that the flashlight image is pulled when the first test workflow runs. Setup itself does not need Docker, so a missing Docker never blocks this install.

## Confirm

Use the script JSON output to display what was written — config values set (written to `config.yaml` at root for core, module section for module values), user settings written to `config.user.yaml` (`user_keys` in result), help entries added, fresh install vs update, and the output directories created. If legacy files were deleted, mention the migration. If legacy directories were removed, report the count and list (e.g. "Cleaned up 106 installer package files from bmb/, core/, \_config/ — skills are installed at .claude/skills/").

Then give the user one clear next action: run `psm-agent-expert` once — that single invocation both seeds the shared knowledge base (per the Seed step above) and opens the consultation entry point. Display the `module_greeting` from `assets/module.yaml` alongside this, so the seed and consult prompts land as one next step rather than two.

When the skill was invoked headless or with arguments, also emit a compact machine-readable result the caller can gate on — a single JSON object aggregating the script outputs, e.g.:

```json
{"status": "success", "install_state": "fresh", "module_code": "psm", "user_keys": ["user_name", "communication_language"], "output_dirs_created": ["..."], "legacy_configs_deleted": [], "legacy_dirs_removed": []}
```

## Outcome

Once the user's `user_name` and `communication_language` are known (from collected input, arguments, or existing config), use them consistently for the remainder of the session: address the user by their configured name and communicate in their configured `communication_language`.
