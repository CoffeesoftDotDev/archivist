<!-- markdownlint-disable-file -->
# Changes: safe extraction, more cleanup steps, any-case .zip, space and ZIP-bomb checks, CI

* Plan: `.copilot-tracking/plans/2026-09-23/archivist-hardening-plan.instructions.md`
* Date: 2026-09-23
* Status: complete (all plan steps checked); CI not run yet (no GitHub remote)

## Summary

Extraction now goes through a hidden staging folder, skips archives that do not fit or look like ZIP bombs, and finds `.zip` in any case. Three cleanup steps remove `.DS_Store`, `Thumbs.db` and `desktop.ini`. A GitHub Actions workflow runs the tests on three systems and checks the Docker image.

## Added

* `.github/workflows/ci.yml`: test matrix (ubuntu, windows, macos x Python 3.10, 3.13) with `uv run --locked pytest`; Docker build plus a sample ZIP extracted as the non-root user; `permissions: contents: read`
* `src/archivist/utils/fs.py`: `find_files()` (any-case glob, files only, no symlinks), `format_size()`
* `src/archivist/workflow/steps.py`: `RemoveFilesNamed(cleaner, filename)`

## Modified

* `src/archivist/services/zip_extractor.py`: `find_archives()` uses `find_files()`; `_extract_to()` staging folder `.<name>.archivist-tmp` renamed on success, removed in `finally`, stale one replaced; timestamps use the path returned by `archive.extract()`; `_check()` for free space (100 MB reserve) and ZIP bombs (> 1 GB and > 100:1), also in dry runs; preview shows the size
* `src/archivist/services/metadata_cleaner.py`: `remove_files_named()`; shared `_remove_files()` loop for `._` files and named files
* `src/archivist/workflow/builder.py`: named-file steps after `._` files, before `._` folders
* `src/archivist/workflow/__init__.py`, `src/archivist/utils/__init__.py`: new public names
* `src/archivist/core/config.py`: `ds_store`, `thumbs_db`, `desktop_ini` fields, `ARCHIVIST_LEAVE_DS_STORE`, `ARCHIVIST_LEAVE_THUMBS_DB`, `ARCHIVIST_LEAVE_DESKTOP_INI`, summary lines
* `src/archivist/cli.py`: `--leave-ds-store`, `--leave-thumbs-db`, `--leave-desktop-ini`; description
* `src/archivist/__init__.py`, `pyproject.toml`: description mentions Windows metadata
* `README.md`, `.env.example`
* Tests: `test_fs.py`, `test_zip_extractor.py`, `test_metadata_cleaner.py`, `test_config.py`, `test_cli.py`, `test_workflow.py`

## Deviations from the plan

* Fixed while adding the staging folder: timestamps were restored on `target / member.filename`, so a member named `../x` could change the date of a file outside the target
* A folder named `something.zip` is no longer treated as an archive
* Dry run: a `._` folder that only holds a file an earlier step would remove is not counted (documented in the README)

## Validation

* `uv run pytest`: 67 passed
* `ci.yml` parses as YAML (PyYAML); jobs `test` and `docker`
* Sample folder: dry run changed 0 files and showed the archive size; real run extracted `PHOTOS.ZIP` and removed `.DS_Store` (from the ZIP), `Thumbs.db` and 2 `desktop.ini` files, with no staging folder left (exit 0)

## Review

* Item 1 (safe extraction): complete
* Item 2 (more cleanup steps): complete
* Item 3 (any-case .zip): complete
* Item 4 (space and ZIP-bomb checks): complete
* Item 5 (CI): complete, unverified until the repository is pushed to GitHub
* Overall status: Complete

## Release summary

Safer extraction (staging folder, space and ZIP-bomb checks, any-case `.zip`), `.DS_Store` / `Thumbs.db` / `desktop.ini` cleanup with `--leave-*` flags, and GitHub Actions CI.

## Follow-up: cli package and size limit

* User requests: "move the config.appledouble_max_size to the RemoveAppleDoubleFolders init" and "extract the parsers into their own cli_config.py file (or a subfile)"
* The size limit went to `RemoveAppleDoubleFiles`, the only step that checks file sizes; `RemoveAppleDoubleFolders` never did
* `MetadataCleaner(remover)` no longer takes `max_size`; `remove_appledouble_files(root, max_size)` does
* `src/archivist/cli.py` split into `cli/parser.py` (flags, `parse_config`) and `cli/entrypoint.py` (`main`, prompt, exit codes); `cli/__init__.py` keeps `archivist.cli:main` and `cli.parse_config` working
* Tests: 68 passed; `archivist --help` and `python -m archivist --help` both work

## Follow-up: console always on

* User request: "i want to have --log-console on all the time"
* Removed `--log-console`, `ARCHIVIST_LOG_CONSOLE`, `Config.log_console` and `Config.console_enabled`; the entry point always logs to the console, and `--log-file` adds the file
* `--log-console` is now rejected by argparse; an `ARCHIVIST_LOG_CONSOLE` variable is ignored
* Tests: 66 passed (the console-default cases went away); a run with only `--log-file` showed the report in the console and wrote `report.log`
