<!-- markdownlint-disable-file -->
# Plan: tests, dry run, pure Config model, nested ZIPs

## User Requests

1. "add the python unit tests as well" (Suggested Next Work item 1)
2. "You can go from 1 to 4 in fact, i like the ideas": items 1 to 4 of the last Suggested Next Work list
   1. Add a pytest suite
   2. Add `--dry-run` (with the Strategy pattern suggested in chat)
   3. Make `Config` a pure options model (argument parser moves to `cli.py`)
   4. Extract nested ZIPs in one run
3. "what is the .copilot-tracking made for ?" (answered in chat)
4. "I actually like the Command approach better, with a workflow builder that would go through the sequence of steps you describe based on the config state, Apply that instead"

## Decisions (research summary)

* Dry run: Strategy pattern. `Remover` base class with `PermanentRemover`, `TrashRemover`, `DryRunRemover` in `utils/removers.py`. Services receive a remover instead of `force_readonly`/`to_trash` flags. Rejected: a third boolean threaded through every call.
* `--dry-run` wins over `--send-to-bin`. A dry run opens archives read-only to count items and nested ZIPs, and still writes a requested log file.
* Nested ZIPs: `ZipExtractor.extract_all()` rescans only the folders created by the previous pass (fast on big trees, never re-extracts kept ZIPs) and stops at depth 10 (ZIPs that contain themselves). Rejected: rescanning the whole tree each pass.
* Corrupt ZIPs: open the archive before creating the target folder, so a failure leaves no empty folder that would make later runs skip the ZIP.
* `Config` keeps fields, derived values, `summary()` and `from_env(environ)`. `cli.build_parser()` / `cli.parse_config()` own argparse.
* `workflow.run()` returns a `Report` dataclass so tests assert counts instead of parsing logs.
* Tests: flat `tests/` at the project root, pytest in a uv `dev` dependency group. Autouse fixtures clear `ARCHIVIST_*` variables, block the real Recycle Bin and close log files.
* Workflow (request 4): Command pattern. Each step is a `Step` subclass in `workflow/steps.py`; `WorkflowBuilder` goes through the step sequence and keeps the steps the config enables; `Workflow` runs them in order and merges their report lines. The removal strategies stay: steps decide which jobs run, removers decide how files are removed. The report lists only the steps that ran.

## Context

* Instructions: hve-core `markdown.instructions.md` and `writing-style.instructions.md` (README), `commit-message.instructions.md` (commit message)
* Dependencies: `pytest>=8` (dev group only). Skills: none

## Implementation Checklist

### Phase 1: Config model and CLI <!-- parallelizable: false -->

* [x] `dry_run` field, `ARCHIVIST_DRY_RUN`, `environ` parameter on `Config.from_env`
* [x] Parser moves to `cli.py` (`build_parser`, `parse_config`), new `--dry-run` flag

### Phase 2: Removal strategies <!-- parallelizable: false -->

* [x] `utils/removers.py`; `utils/fs.py` keeps the primitives
* [x] Services take a `Remover`; dry-run path in `ZipExtractor.extract()`

### Phase 3: Nested ZIPs and report <!-- parallelizable: false -->

* [x] `ZipExtractor.extract_all()` with depth limit
* [x] `workflow.run()` builds services with `make_remover()` and returns `Report`

### Phase 4: Tests <!-- parallelizable: false -->

* [x] pytest dev group and settings in `pyproject.toml`
* [x] `tests/` for config, cli, fs and removers (`test_fs.py`), zip extractor, metadata cleaner, workflow

### Phase 5: Docs <!-- parallelizable: false -->

* [x] README (dry run, nested ZIPs, env var, tests, structure), `.env.example`, `.gitignore`

### Phase 6: Command-pattern workflow (request 4) <!-- parallelizable: false -->

* [x] `workflow/` package: `steps.py` (Command), `builder.py` (Builder), `runner.py` (Workflow)
* [x] `cli.py` uses `WorkflowBuilder(config).build().run(root)`; old `workflow.py` removed
* [x] Tests for step selection, step order and report merging; README structure

## Success Criteria

* `uv run pytest` passes
* A dry run on a sample folder leaves it unchanged
* A real run extracts nested ZIPs in one go and keeps the previous cleanup behaviour
* `uv run archivist --help` lists `--dry-run`

Changes log: `.copilot-tracking/changes/2026-09-23/archivist-next-work-changes.md`
