---
title: Contributing
description: Set up Archivist for development and run its test suite
---

## Development setup

Install Python 3.10 or later and [uv](https://docs.astral.sh/uv/), then clone the repository.

```powershell
git clone https://github.com/CoffeesoftDotDev/archivist.git
Set-Location archivist

# Run from the working tree
uv run archivist --parent-folder "C:\photos"

# Show module help
uv run python -m archivist --help

# Run the tests
uv run pytest
```

The first `uv run` creates `.venv` and installs the development dependency group.

## Tests and isolation

The pytest fixtures keep runs isolated by:

* Clearing `ARCHIVIST_*` variables
* Blocking the real Recycle Bin
* Closing log files before temporary folders are removed
* Providing helpers for sample ZIPs, files, listings, and reports

## Architecture

| Package | Responsibility |
|---|---|
| `cli` | Options, prompts, entry point, and exit codes |
| `workflow` | Builds and runs the ordered processing steps |
| `services` | ZIP extraction and metadata cleanup |
| `utils` | Filesystem helpers and removal strategies |
| `core` | Configuration and logging shared across layers |

Dependencies flow downward from `cli` to `workflow`, `services`, and `utils`. Every layer can use
`core`.

## Continuous integration

CI runs the locked test suite on Windows, macOS, and Linux with Python 3.10 and 3.13. It also builds
the Docker image and verifies preview and apply runs as the non-root user.

```bash
uv run --locked pytest
```

## Contributor reference

The repository guide covers adding options and workflow steps, debugging in VS Code, dependency
locking, and release versioning.

* [Read CONTRIBUTING.md](https://github.com/CoffeesoftDotDev/archivist/blob/main/CONTRIBUTING.md)
* [Browse issues](https://github.com/CoffeesoftDotDev/archivist/issues)
