<!-- markdownlint-disable-file -->
# Changes: tests, dry run, pure Config model, nested ZIPs

* Plan: `.copilot-tracking/plans/2026-09-23/archivist-next-work-plan.instructions.md`
* Date: 2026-09-23
* Status: complete (all plan steps checked)

## Summary

Added a pytest suite, a `--dry-run` option built on removal strategies, extraction of nested ZIPs in one run, and moved the argument parser out of `Config`.

## Added

* `src/archivist/utils/removers.py`: `Remover` base class, `PermanentRemover`, `TrashRemover`, `DryRunRemover`, `make_remover()`
* `tests/conftest.py`: autouse isolation (clears `ARCHIVIST_*`, blocks the real Recycle Bin, closes log files), `logs`, `make_zip`, `write_file`, `listing` fixtures
* `tests/test_config.py`, `tests/test_cli.py`, `tests/test_fs.py`, `tests/test_zip_extractor.py`, `tests/test_metadata_cleaner.py`, `tests/test_workflow.py`

## Modified

* `src/archivist/core/config.py`: parser removed; `dry_run` field; `from_env(environ=None)`; non-numeric `ARCHIVIST_MAX_SIZE` error names the variable; summary shows the dry-run line
* `src/archivist/cli.py`: `build_parser(defaults)`, `parse_config(argv, environ)`, `--dry-run`, `prog="archivist"`
* `src/archivist/utils/fs.py`: primitives only; `make_writable` and `iter_tree` are public
* `src/archivist/utils/__init__.py`: exports the strategies
* `src/archivist/services/zip_extractor.py`: takes a `Remover`; `extract_all()` (rescans only new folders, `MAX_DEPTH = 10`); dry-run preview; archive opened before the target folder is created; a removal failure after extraction no longer marks the ZIP as failed
* `src/archivist/services/metadata_cleaner.py`: takes a `Remover`; `@eaDir` handled shallowest first so nested ones count once; logs after success
* `src/archivist/workflow.py`: builds the remover and services; returns `Report`; dry-run title in the report
* `pyproject.toml`: `dev` dependency group with pytest; `[tool.pytest.ini_options]`
* `README.md`, `.env.example`, `.gitignore`

## Removed

* `remove_file()` / `remove_tree()` functions in `utils/fs.py` (replaced by the strategies)
* `Config.build_parser()` / `Config.from_args()` (moved to `cli.py`)

## Deviations from the plan

* A corrupt ZIP no longer leaves an empty folder (found while writing tests)
* A ZIP that extracts but cannot be removed now counts as extracted, with an error line
* `--help` shows `usage: archivist` instead of the venv script path

## Validation

* `uv run pytest`: 49 passed
* `uv run archivist --help`: lists `--dry-run`
* Sample folder: dry run changed 0 files; real run extracted the nested ZIP in one run and removed the `._` file, `._` folder and `@eaDir` (exit 0)

## Review

* Request 1 (unit tests): complete
* Items 1 to 4 (tests, dry run, pure Config, nested ZIPs): complete
* `.copilot-tracking` question: answered in chat
* Known limits, documented in the README: a dry run does not count files inside archives
* Overall status: Complete

## Release summary

`archivist` gains `--dry-run` (`ARCHIVIST_DRY_RUN`), one-run extraction of nested ZIPs (10 levels), a pytest suite (`uv run pytest`), and a `Config` model with no command-line code.

## Follow-up: Command-pattern workflow (request 4, Phase 6)

### Added

* `src/archivist/workflow/steps.py`: `Step` (Command) with `ExtractArchives`, `RemoveAppleDoubleFiles`, `RemoveAppleDoubleFolders`, `RemoveEaDirFolders`
* `src/archivist/workflow/builder.py`: `WorkflowBuilder` goes through the step sequence and keeps the steps the config enables
* `src/archivist/workflow/runner.py`: `Workflow` runs the steps in order and logs the report; `Report = dict[str, int]`
* `src/archivist/workflow/__init__.py`: public names

### Modified

* `src/archivist/cli.py`: `WorkflowBuilder(config).build().run(root)`
* `tests/test_workflow.py`: step selection per config, step order, report merging; end-to-end tests use the builder
* `README.md`: `workflow/` in the project structure, how to add a step

### Removed

* `src/archivist/workflow.py` (replaced by the `workflow/` package)

### Deviations

* The removal strategies stay: steps decide which jobs run, removers decide how files are removed
* The final report lists only the steps that ran (disabled steps no longer print `0`)

### Validation

* `uv run pytest`: 54 passed
* Sample folder with every step: same titles and report as before (exit 0)
* `--leave-zip --leave-appledouble --leave-eadir`: report shows only the two ZIP lines (exit 0)

### Review

* Request 4: complete. Overall status: Complete
