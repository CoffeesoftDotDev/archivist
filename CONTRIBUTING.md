---
title: Contributing to Archivist
description: Development setup, tests, debugging and project structure for Archivist
---

## Development setup

You need Python 3.10 or later and [uv](https://docs.astral.sh/uv/). From a clone of the repository:

```bash
# Run the command from the working tree (a dry run until you add --apply)
uv run archivist --parent-folder "C:\photos"

# Or as a module
uv run python -m archivist --help

# Run the tests
uv run pytest
```

`uv run` creates the `.venv` folder and installs the package with its `dev` dependency group (pytest) on first use.

## Tests

Tests live in [tests/](tests), one file per module. The fixtures in [conftest.py](tests/conftest.py) keep every test isolated:

* `ARCHIVIST_*` variables are cleared, so your own environment doesn't leak into the results
* The real Recycle Bin is blocked, so `--send-to-bin` tests never touch it
* Log files are closed after each test, so Windows can delete the temporary folders
* `make_zip`, `write_file`, `listing` and `logs` build sample folders and capture the report

## Debugging in VS Code

Select the `.venv` interpreter and press F5. [launch.json](.vscode/launch.json) has two configurations, both asking for the parent folder:

* `archivist: dry run` shows what would change
* `archivist: apply (changes files)` passes `--apply` and changes the folder for real

Leave the folder empty to get the prompt in the terminal instead.

## Continuous integration

[ci.yml](.github/workflows/ci.yml) runs on every push to `main` and every pull request:

* `uv run --locked pytest` on Windows, macOS and Linux, with Python 3.10 and 3.13
* A Docker build, followed by a dry run and then an `--apply` run on a sample ZIP as the non-root user

`--locked` fails when [uv.lock](uv.lock) is out of date, so run `uv lock` after changing dependencies in [pyproject.toml](pyproject.toml).

## Project structure

```text
.github/workflows/ci.yml   Tests on Windows, macOS and Linux, plus a Docker image check
.vscode/launch.json        VS Code debug configurations (dry run, real run)
pyproject.toml             Package metadata, `archivist` command, pytest settings
Dockerfile                 Distroless image (multi-stage, uv build)
docker-compose.yml         One-shot run with a mounted folder and .env
.env.example               Sample ARCHIVIST_* configuration
src/archivist/
  __init__.py              Package version
  __main__.py              Allows `python -m archivist`
  cli/                     Command line
    parser.py              Options (defaults from ARCHIVIST_* variables) -> Config
    entrypoint.py          main(): folder prompt, logging outputs, exit codes
    prompts.py             MergePrompt: asks whether to extract into an existing folder
  workflow/                The run as a sequence of steps
    steps.py               The steps (Command pattern)
    builder.py             WorkflowBuilder: keeps the steps the config enables (Builder pattern)
    runner.py              Workflow: runs the steps in order and logs the report
  core/                    App-wide infrastructure
    config.py              Config model (defaults, ARCHIVIST_* variables, summary)
    logger.py              Logging setup (console and report file)
  services/                Business logic, one class per job
    zip_extractor.py       ZipExtractor (nested ZIPs, staging folder, space and ZIP-bomb checks, existing folders)
    metadata_cleaner.py    MetadataCleaner (._ files and folders, .DS_Store, Thumbs.db, desktop.ini, @eaDir)
  utils/                   Filesystem helpers and removal strategies, no business rules
    fs.py                  Hidden and read-only checks, any-case file search, sizes
    removers.py            Delete permanently, send to bin, or dry run (Strategy pattern)
tests/                     pytest suite, one file per module
```

Each layer only imports from the layers below it: `cli` -> `workflow` -> `services` -> `utils`, and any layer can use `core`. Each subpackage's `__init__.py` lists its public names, so other layers import from the subpackage (`from ..core import get_logger`) rather than from its modules.

## Adding an option

Declare the option once, as a field on `Config` in [config.py](src/archivist/core/config.py), with its flags, its variable (without the `ARCHIVIST_` prefix) and its help text:

```python
leave_zip: bool = option(
    False, "--leave-zip", env="LEAVE_ZIP",
    help="Keep ZIP archives after extraction (default: they are deleted).",
)
```

`Config.from_env` reads the variable and [parser.py](src/archivist/cli/parser.py) builds the flag from this declaration, both chosen by the field type:

| Type           | Flag                                             | Variable                                        |
|----------------|--------------------------------------------------|-------------------------------------------------|
| `bool`         | Plain flag, sets `True`                          | `true`/`false`, `1`/`0`, `yes`/`no`, `on`/`off` |
| `int`          | Takes a number                                   | A whole number                                  |
| `Path \| None` | Takes a path; an empty value counts as not given | A path                                          |

Fields are declared in `--help` order, and an empty or unset variable always keeps the default. Then:

1. Add a line to `Config.summary` if the option should appear at the start of the report
2. Add a row to the options and environment variable tables of [README.md](README.md), and a line to [.env.example](.env.example)
3. Update `HELP` in [test_options.py](tests/test_options.py), which pins the full `--help` text

Two rules keep options consistent:

* Name each field after its flag and variable, and give it the flag's default. A `--leave-x` flag sets `leave_x`, which defaults to `False`; code that needs the positive meaning uses `not config.leave_x`.
* An option that doesn't fit one of the types above is declared without flags and gets hand-written ones in `build_parser`, plus a `parse=` converter if its variable needs one. There are two today: `--apply`, which shares a group with the hidden `--dry-run`, and the log file (`--log-file [PATH]` / `--no-log-file`), declared in `add_log_file_options()` and converted by `parse_log_file()`.

## Adding a step

Write a `Step` subclass in [steps.py](src/archivist/workflow/steps.py), then add one `(enabled, step)` line to the sequence in `WorkflowBuilder.build()` in [builder.py](src/archivist/workflow/builder.py). File steps run before folder steps, so `._` folders emptied by an earlier step are removed in the same run.

## Releases

Versions are tagged `vX.Y` on `main`, and planned work is grouped in [milestones](https://github.com/CoffeesoftDotDev/archivist/milestones). Update `version` in [pyproject.toml](pyproject.toml) and `__version__` in [\_\_init\_\_.py](src/archivist/__init__.py) together.
