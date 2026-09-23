---
title: Archivist
description: Recursively extract ZIP archives and clean macOS, Windows and Synology metadata
---

<p align="center">
  <img
    src="https://raw.githubusercontent.com/CoffeesoftDotDev/archivist/main/Archivist.png"
    alt="Archivist logo"
    width="320"
  >
</p>

Recursively extracts every `.zip` under a parent folder (in any case, such as `PHOTOS.ZIP`), then cleans up macOS, Windows and Synology metadata.

For each archive, the script:
1. Checks that it is safe to extract. It is skipped if it needs more space than is free (keeping 100 MB spare), or if it expands more than 100x to over 1 GB, which is what a ZIP bomb does.
2. Extracts it into a sibling folder with the same name (`photos.zip` becomes `photos\`). If that folder already exists, the archive is skipped. Files go into a hidden `.photos.archivist-tmp` folder first, which is renamed once everything is extracted, so a failed or interrupted extraction leaves nothing behind.
3. Restores the original file timestamps from the ZIP.
4. Deletes the ZIP (unless `--leave-zip` is given).

ZIPs that come out of an archive are extracted in the same run, up to 10 levels deep.

It then optionally removes:
- small `._*` AppleDouble files (2 KB or less by default)
- macOS `.DS_Store` files, and Windows `Thumbs.db` and `desktop.ini` files
- `._*` folders that contain no visible files, checking all their subfolders
- Synology `@eaDir` folders

## Requirements

- **Python 3.10+**
- [uv](https://docs.astral.sh/uv/) (recommended), which provides `uvx`
- One dependency, [`send2trash`](https://pypi.org/project/Send2Trash/) (installed automatically by uv), used for `--send-to-bin`
- Windows, macOS or Linux (Windows hidden/system attributes are also detected)

## Usage

Run it directly with `uvx`, no install needed:

```bash
# From a local checkout
uvx --from <local-clone-folder> archivist [options]

# From a Git repository
uvx --from git+https://github.com/CoffeesoftDotDev/archivist archivist [options]
```

Or install it once as a global command:

```bash
uv tool install C:\Laboratoire\dezipper
archivist [options]
```

During development:

```bash
uv run archivist [options]

# Run the tests
uv run pytest
```

To debug in VS Code, select the `.venv` interpreter and press F5. The `archivist: dry run` configuration in [`.vscode/launch.json`](.vscode/launch.json) asks for the parent folder; leave it empty to be asked in the terminal instead.

GitHub Actions ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs the tests on Windows, macOS and Linux with Python 3.10 and 3.13. It also builds the Docker image and runs it on a sample ZIP.

If `--parent-folder` is not given, the script asks for the parent folder path.

## Arguments

| Argument | Default | Description |
|---|---|---|
| `--parent-folder <path>` | prompt | Folder to process (skips the prompt). An empty value counts as not given |
| `--leave-zip` | off | Keep ZIP archives after extraction |
| `--leave-appledouble` | off | Keep macOS AppleDouble metadata (small `._*` files and `._*` folders with no visible files) |
| `--leave-eadir` | off | Keep Synology `@eaDir` folders |
| `--leave-ds-store` | off | Keep macOS `.DS_Store` files |
| `--leave-thumbs-db` | off | Keep Windows `Thumbs.db` thumbnail caches |
| `--leave-desktop-ini` | off | Keep Windows `desktop.ini` files (they hold custom folder icons and names) |
| `--max-size <bytes>` | `2048` | Maximum size of `._*` files to remove |
| `--force-readonly-deletion`, `--force` | off | Clear the read-only flag and delete read-only items (otherwise they are skipped) |
| `--send-to-bin` | off | Send removed items to the Recycle Bin / Trash instead of deleting them permanently |
| `--dry-run` | off | Show what would be extracted and removed without changing anything |
| `--log-file [path]` | off | Also write the report to a file (appended, timestamped). No path: `<parent-folder>/report.log`. A folder path: `<folder>/report.log`. A file path: that file. |
| `-h`, `--help` | | Show help |

The report always appears in the console. `--log-file` writes the same report to a file as well.

### Dry run

`--dry-run` shows what a real run would do without extracting, moving or deleting anything. A requested log file is still written.

- Each archive is opened read-only to count its items and the ZIPs nested inside it.
- Files inside archives are not on disk yet, so nested ZIPs and `._` files inside archives are not counted.
- The free-space and ZIP-bomb checks still run, so archives that would be skipped are reported.
- Counts can be lower than in a real run when a step would remove something a later step looks at, for example a `._` folder that only holds a `Thumbs.db`.
- `--dry-run` takes priority over `--send-to-bin`.

## Examples

```bash
# Everything on (default)
archivist

# Non-interactive run on a given folder
archivist --parent-folder "C:\photos"

# Extract but keep the original ZIP archives
archivist --leave-zip

# Extract and clean, but keep Synology @eaDir folders
archivist --leave-eadir

# Only extract ZIPs, no cleanup
archivist --leave-appledouble --leave-eadir --leave-ds-store --leave-thumbs-db --leave-desktop-ini

# Remove ._ files up to 4 KB, including read-only ones
archivist --max-size 4096 --force

# Preview what would happen, without changing anything
archivist --parent-folder "C:\photos" --dry-run

# Safe run: everything removed goes to the Recycle Bin
archivist --parent-folder "C:\photos" --send-to-bin

# Also write the report to C:\photos\report.log
archivist --parent-folder "C:\photos" --log-file

# Custom report location
archivist --parent-folder "C:\photos" --log-file "D:\logs\photos-2026.log"
archivist --parent-folder "C:\photos" --log-file "D:\logs\"   # -> D:\logs\report.log
```

(Prefix with `uvx --from <path-or-git-url>` if the tool is not installed.)

## Environment variables

Every option can also be set with an `ARCHIVIST_*` environment variable. **Precedence: CLI flag > env var > built-in default.** Unset or empty variables keep the default.

| Variable | Equivalent flag | Default |
|---|---|---|
| `ARCHIVIST_PARENT_FOLDER` | `--parent-folder` | prompt (`/data` in Docker) |
| `ARCHIVIST_LEAVE_ZIP` | `--leave-zip` | `false` |
| `ARCHIVIST_LEAVE_APPLEDOUBLE` | `--leave-appledouble` | `false` |
| `ARCHIVIST_LEAVE_EADIR` | `--leave-eadir` | `false` |
| `ARCHIVIST_LEAVE_DS_STORE` | `--leave-ds-store` | `false` |
| `ARCHIVIST_LEAVE_THUMBS_DB` | `--leave-thumbs-db` | `false` |
| `ARCHIVIST_LEAVE_DESKTOP_INI` | `--leave-desktop-ini` | `false` |
| `ARCHIVIST_MAX_SIZE` | `--max-size` | `2048` |
| `ARCHIVIST_FORCE_READONLY_DELETION` | `--force` | `false` |
| `ARCHIVIST_SEND_TO_BIN` | `--send-to-bin` | `false` |
| `ARCHIVIST_DRY_RUN` | `--dry-run` | `false` |
| `ARCHIVIST_LOG_FILE` | `--log-file [path]` | unset. `true` means `<parent>/report.log`, or give a path |

Booleans accept `true/false`, `1/0`, `yes/no` and `on/off`.

## Docker

The image is **distroless** (`gcr.io/distroless/python3-debian12:nonroot`), so it has no shell and runs as a non-root user. It runs once and exits. Mount the folder to process at **`/data`**.

```bash
# Build
docker build -t archivist .

# Run with defaults
docker run --rm -v "C:\photos:/data" archivist

# Configure via env vars
docker run --rm -v "C:\photos:/data" \
  -e ARCHIVIST_LEAVE_ZIP=true \
  -e ARCHIVIST_LOG_FILE=true \
  archivist

# CLI flags can still be appended (they override env vars)
docker run --rm -v "C:\photos:/data" archivist --max-size 4096
```

With Docker Compose, copy `.env.example` to `.env`, set `HOST_PARENT_FOLDER` and any `ARCHIVIST_*` values, then run:

```bash
docker compose run --rm archivist
```

Notes:
- The container runs as UID `65532` (`nonroot`), so the mounted folder must be writable by that user. On Linux or a NAS, run `chown -R 65532 /path/to/photos` or add `--user $(id -u):$(id -g)`. Docker Desktop on Windows handles this automatically.
- `--send-to-bin` has no effect in a container, because there is no desktop Trash. `send2trash` falls back to a `.Trash-<uid>` folder inside the mounted volume.
- There is no interactive prompt: if no parent folder is set, the run fails with exit code `2`.

## Project structure

```text
.github/workflows/ci.yml         GitHub Actions: tests on Windows, macOS, Linux + Docker image check
.vscode/launch.json              VS Code debug configurations (dry run, real run)
pyproject.toml                   Package metadata, `archivist` command, pytest settings
Dockerfile                       Distroless image (multi-stage, uv build)
docker-compose.yml               One-shot run with a mounted folder + .env
.env.example                     Sample ARCHIVIST_* configuration
src/archivist/
  __init__.py                    Package version
  __main__.py                    Allows `python -m archivist`
  cli/                           Command line
    parser.py                    Flags (defaults from ARCHIVIST_* variables) -> Config
    entrypoint.py                main(): folder prompt, logging outputs, exit codes
  workflow/                      The algorithm as a sequence of steps
    steps.py                     The steps (Command pattern)
    builder.py                   WorkflowBuilder: keeps the steps the config enables (Builder pattern)
    runner.py                    Workflow: runs the steps in order and logs the report
  core/                          App-wide infrastructure
    config.py                    Config options model (defaults, ARCHIVIST_* env vars)
    logger.py                    Logging setup (console / report file)
  services/                      Business logic, one class per job
    zip_extractor.py             ZipExtractor (nested ZIPs, staging folder, space and ZIP-bomb checks)
    metadata_cleaner.py          MetadataCleaner (._ files/folders, .DS_Store, Thumbs.db, desktop.ini, @eaDir)
  utils/                         Filesystem helpers and removal strategies, no business rules
    fs.py                        Hidden and read-only checks, any-case file search, sizes
    removers.py                  Delete permanently, send to bin, or dry run (Strategy pattern)
tests/                           pytest suite, one file per module
```

Each layer only imports from the layers below it: `cli` -> `workflow` -> `services` -> `utils`, and any layer can use `core`. Each subpackage's `__init__.py` lists its public names, so other layers import from the subpackage (`from ..core import get_logger`) rather than from its modules.

To add a step, write a `Step` subclass in `workflow/steps.py` and add one line to the sequence in `WorkflowBuilder.build()`.

### Recycle Bin / Trash support

`--send-to-bin` uses `send2trash`, which works on every platform:

| OS | Destination |
|---|---|
| Windows | Recycle Bin |
| macOS | Trash |
| Linux | Desktop trash (`~/.local/share/Trash`, or `.Trash-<uid>` on other drives) |

On network shares (SMB/NAS), Windows may not provide a Recycle Bin, and the item may be deleted permanently instead. Enable the Synology share's own recycle bin to keep a safety net.

> ⚠️ By default, removed items are deleted permanently. Use `--send-to-bin` to recover them if needed, and `--leave-zip` to keep the archives.
