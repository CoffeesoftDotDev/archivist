<!-- markdownlint-disable-file -->
# Plan: safe extraction, more cleanup steps, any-case .zip, space and ZIP-bomb checks, CI

## User Requests

1. "Go for 1 to 5": items 1 to 5 of the last Suggested Next Work list
   1. Safe extraction: extract into a temporary folder, rename it when complete
   2. More cleanup steps: `.DS_Store`, `Thumbs.db`, `desktop.ini`, each with its own `--leave-...` option
   3. Match `.ZIP` in any case (Linux and the Docker image)
   4. Disk-space and ZIP-bomb check before extracting
   5. GitHub Actions: tests on Windows and Linux, Docker image build

## Decisions (research summary)

* Safe extraction: staging folder `.<name>.archivist-tmp` next to the target, renamed on success and removed in `finally` (errors and Ctrl+C). A staging folder left by a killed run is replaced. Timestamps use the path returned by `archive.extract()`, so a member named `../x` can never touch a file outside the target (the old code could).
* Any case: `utils.find_files(root, pattern)` matches lowercased names with `fnmatchcase`. `rglob(case_sensitive=False)` needs Python 3.12 and the project supports 3.10. Also skips folders named `*.zip` and symlinks.
* Checks: skip when declared uncompressed size + 100 MB reserve > free space, or when size > 1 GB and the ratio is over 100:1. Declared sizes are safe to trust: `zipfile` stops writing at the declared size and fails the CRC check otherwise. Both checks also run in a dry run.
* Cleanup steps: one parameterised `RemoveFilesNamed(cleaner, filename)` step rather than three identical classes. Runs after `._` files and before `._` folders, so a `._` folder emptied of `Thumbs.db` goes too. Names match in any case.
* CI: `.github/workflows/ci.yml`, `permissions: contents: read`. Test matrix ubuntu/windows/macos x Python 3.10/3.13 with `astral-sh/setup-uv` and `uv run --locked pytest`. Docker job builds the image and extracts a sample ZIP as the non-root user.

## Context

* Instructions: hve-core `markdown.instructions.md`, `writing-style.instructions.md` (README), `commit-message.instructions.md`
* Previous work: `.copilot-tracking/plans/2026-09-23/archivist-next-work-plan.instructions.md`

## Implementation Checklist

### Phase 1: Filesystem helpers <!-- parallelizable: false -->

* [x] `find_files()` and `format_size()` in `utils/fs.py`

### Phase 2: ZipExtractor <!-- parallelizable: false -->

* [x] Any-case `find_archives()` (item 3)
* [x] Staging folder + rename, safe timestamp paths (item 1)
* [x] Space and ZIP-bomb checks, also in dry runs (item 4)

### Phase 3: Named-file cleanup (item 2) <!-- parallelizable: false -->

* [x] `MetadataCleaner.remove_files_named()`, `RemoveFilesNamed` step, builder sequence
* [x] `ds_store`, `thumbs_db`, `desktop_ini` config fields, `ARCHIVIST_LEAVE_*` variables, `--leave-*` flags

### Phase 4: CI (item 5) <!-- parallelizable: true -->

* [x] `.github/workflows/ci.yml`

### Phase 5: Tests and docs <!-- parallelizable: false -->

* [x] Tests for every item
* [x] README, `.env.example`

## Success Criteria

* `uv run pytest` passes
* A ZIP that fails halfway leaves only the ZIP; `PHOTOS.ZIP` is extracted; low space and ZIP bombs are skipped with a clear message
* `ci.yml` parses as YAML
* A sample folder run removes `.DS_Store`, `Thumbs.db` and `desktop.ini`

Changes log: `.copilot-tracking/changes/2026-09-23/archivist-hardening-changes.md`
