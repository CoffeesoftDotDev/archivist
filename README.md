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

Archivist extracts every `.zip` under a parent folder, including ZIPs found inside other ZIPs, then removes the metadata files that macOS, Windows and Synology NAS devices leave behind when folders are copied between them.

> [!WARNING]
> By default, Archivist deletes each ZIP after extracting it and deletes metadata files permanently. Preview a run with `--dry-run`, send removed items to the Recycle Bin with `--send-to-bin`, or keep the archives with `--leave-zip`.

## What it does

Archivist finds `.zip` files in any case (`photos.zip`, `PHOTOS.ZIP`) and processes each one in four steps:

1. Checks that the archive is safe to extract. It's skipped if it needs more space than is free (keeping 100 MB spare), or if it expands more than 100 times to over 1 GB, which is what a ZIP bomb does.
2. Extracts it into a sibling folder with the same name (`photos.zip` becomes `photos/`). Files go into a hidden `.photos.archivist-tmp` folder first, which is renamed once everything is extracted, so a failed or interrupted extraction leaves nothing behind. If the folder already exists, see [Existing folders](#existing-folders).
3. Restores the original file timestamps from the ZIP.
4. Deletes the ZIP, unless you pass `--leave-zip`. Read-only ZIPs are kept unless you pass `--force`.

ZIPs that come out of an archive are extracted in the same run, up to 10 levels deep.

Archivist then removes, in this order:

* AppleDouble `._*` files of 2 KB or less (macOS)
* `.DS_Store` files (macOS)
* `Thumbs.db` and `desktop.ini` files (Windows)
* `._*` folders that hold no visible files in any of their subfolders (macOS)
* `@eaDir` folders (Synology)

A file counts as hidden when its name starts with a dot or, on Windows, when it has the hidden or system attribute. Each cleanup step can be turned off with its `--leave-*` option.

### Existing folders

When the folder an archive would be extracted to already exists, Archivist skips the archive at first. After each extraction pass, it lists these archives:

```text
2 archive(s) skipped because the target already exists:
  C:\photos\2024.zip -> existing folder 2024
  C:\photos\notes.zip -> notes is a file or link, not a folder
```

When you run Archivist in a terminal, it then asks about each archive whose target is a folder:

```text
2024.zip: folder "2024" already exists. Extract into it and overwrite files with the same name? [y]es / [n]o / [a]ll / [s]kip all:
```

| Answer         | Effect                                                            |
|----------------|-------------------------------------------------------------------|
| `y`            | Extract this archive into the folder                              |
| `n` or Enter   | Skip this archive and keep the folder as it is                    |
| `a`            | Extract this archive and every remaining one without asking again |
| `s`            | Skip this archive and every remaining one without asking again    |

Extracting into an existing folder adds the archive's files and overwrites files that have the same name. Other files in the folder are kept. The replaced files are removed like any other item, so `--send-to-bin` sends them to the Recycle Bin. Timestamps are restored, and the ZIP is then deleted unless you pass `--leave-zip`.

The archive is extracted to the hidden staging folder and checked before the existing folder is touched. It's skipped, and the folder left unchanged, when:

* The folder, or a file or subfolder the archive would write to, is a link or a Windows junction
* The ZIP has a file where the folder has a subfolder, or the other way round
* A file to overwrite is read-only and you didn't pass `--force`

If moving a file fails partway through, for example because the disk is full, the files already moved stay in the folder, the file that failed keeps its old copy, and the ZIP is kept so you can run Archivist again.

Without a terminal (Docker, CI, scheduled tasks) and in a `--dry-run`, Archivist doesn't ask: the archives are listed and skipped. The report counts them in `ZIP files skipped (target exists)`, and the replaced files in `Files overwritten`.

## Requirements

* Python 3.10 or later
* [uv](https://docs.astral.sh/uv/), which provides `uvx` (recommended)
* Windows, macOS or Linux

The only dependency, [Send2Trash](https://pypi.org/project/Send2Trash/), is installed automatically and powers `--send-to-bin`.

## Getting started

Run Archivist with `uvx`, without installing it:

```bash
uvx --from git+https://github.com/CoffeesoftDotDev/archivist archivist --parent-folder "C:\photos" --dry-run
```

To get a permanent `archivist` command, install it as a uv tool:

```bash
uv tool install git+https://github.com/CoffeesoftDotDev/archivist
archivist --parent-folder "C:\photos"
```

Both commands also accept a local clone folder instead of the Git URL.

If you leave out `--parent-folder`, Archivist asks for the folder in the terminal.

## Options

| Option                                 | Default                      | Description                                                                           |
|----------------------------------------|------------------------------|---------------------------------------------------------------------------------------|
| `--parent-folder <path>`               | prompt                       | Folder to process. An empty value counts as not given                                 |
| `--leave-zip`                          | off                          | Keep ZIP archives after extraction                                                    |
| `--leave-appledouble`                  | off                          | Keep AppleDouble metadata (small `._*` files and `._*` folders with no visible files) |
| `--leave-eadir`                        | off                          | Keep Synology `@eaDir` folders                                                        |
| `--leave-ds-store`                     | off                          | Keep macOS `.DS_Store` files                                                          |
| `--leave-thumbs-db`                    | off                          | Keep Windows `Thumbs.db` thumbnail caches                                             |
| `--leave-desktop-ini`                  | off                          | Keep Windows `desktop.ini` files, which hold custom folder icons and names            |
| `--max-size <bytes>`                   | `2048`                       | Largest `._*` file to remove                                                          |
| `--force-readonly-deletion`, `--force` | off                          | Clear the read-only flag and delete read-only items, which are skipped otherwise      |
| `--send-to-bin`                        | off                          | Send removed items to the Recycle Bin or Trash instead of deleting them permanently   |
| `--dry-run`                            | off                          | Show what would be extracted and removed without changing anything                    |
| `--log-file [path]`                    | `<parent-folder>/report.log` | Where to write the report file. See [Report](#report)                                 |
| `--no-log-file`                        | off                          | Don't write a report file                                                             |
| `-h`, `--help`                         |                              | Show help                                                                             |

`--log-file` and `--no-log-file` can't be used together.

## Report

Archivist prints a report to the console: the options in use, every file it extracts, removes or skips, and a count per step. The same report, with a timestamp and level on each line, is appended to `report.log` in the parent folder, so earlier runs stay in the file.

| Value                        | Report file                  |
|------------------------------|------------------------------|
| No option                    | `<parent-folder>/report.log` |
| `--log-file` without a path  | `<parent-folder>/report.log` |
| `--log-file D:\logs\run.log` | `D:\logs\run.log`            |
| `--log-file D:\logs\`        | `D:\logs\report.log`         |
| `--no-log-file`              | None, console only           |

A folder path is any existing folder, or a path that ends with `/` or `\`. Missing parent folders are created.

## Dry run

`--dry-run` shows what a real run would do without extracting, moving or deleting anything. The report file is still written, unless you pass `--no-log-file`.

* Each archive is opened read-only to count its items and the ZIPs nested inside it.
* Files inside archives aren't on disk yet, so nested ZIPs and `._` files inside archives aren't counted.
* The free-space and ZIP-bomb checks still run, so archives that would be skipped are reported.
* Counts can be lower than in a real run when a step would remove something a later step looks at, for example a `._` folder that only holds a `Thumbs.db`.
* `--dry-run` takes priority over `--send-to-bin`.

## Examples

```bash
# Preview what would happen
archivist --parent-folder "C:\photos" --dry-run

# Extract and clean everything, writing C:\photos\report.log
archivist --parent-folder "C:\photos"

# Safe run: everything removed goes to the Recycle Bin
archivist --parent-folder "C:\photos" --send-to-bin

# Extract but keep the original ZIP archives
archivist --parent-folder "C:\photos" --leave-zip

# Extract and clean, but keep Synology @eaDir folders
archivist --parent-folder "C:\photos" --leave-eadir

# Only extract ZIPs, no cleanup
archivist --parent-folder "C:\photos" --leave-appledouble --leave-eadir --leave-ds-store --leave-thumbs-db --leave-desktop-ini

# Remove ._ files up to 4 KB, including read-only ones
archivist --parent-folder "C:\photos" --max-size 4096 --force

# Write the report elsewhere, or not at all
archivist --parent-folder "C:\photos" --log-file "D:\logs\photos-2026.log"
archivist --parent-folder "C:\photos" --no-log-file
```

## Environment variables

Every option can also be set with an `ARCHIVIST_*` environment variable. A command-line option overrides the variable, which overrides the built-in default. Unset or empty variables keep the default.

| Variable                            | Option                         | Default                                                                        |
|-------------------------------------|--------------------------------|--------------------------------------------------------------------------------|
| `ARCHIVIST_PARENT_FOLDER`           | `--parent-folder`              | prompt (`/data` in Docker)                                                     |
| `ARCHIVIST_LEAVE_ZIP`               | `--leave-zip`                  | `false`                                                                        |
| `ARCHIVIST_LEAVE_APPLEDOUBLE`       | `--leave-appledouble`          | `false`                                                                        |
| `ARCHIVIST_LEAVE_EADIR`             | `--leave-eadir`                | `false`                                                                        |
| `ARCHIVIST_LEAVE_DS_STORE`          | `--leave-ds-store`             | `false`                                                                        |
| `ARCHIVIST_LEAVE_THUMBS_DB`         | `--leave-thumbs-db`            | `false`                                                                        |
| `ARCHIVIST_LEAVE_DESKTOP_INI`       | `--leave-desktop-ini`          | `false`                                                                        |
| `ARCHIVIST_MAX_SIZE`                | `--max-size`                   | `2048`                                                                         |
| `ARCHIVIST_FORCE_READONLY_DELETION` | `--force`                      | `false`                                                                        |
| `ARCHIVIST_SEND_TO_BIN`             | `--send-to-bin`                | `false`                                                                        |
| `ARCHIVIST_DRY_RUN`                 | `--dry-run`                    | `false`                                                                        |
| `ARCHIVIST_LOG_FILE`                | `--log-file` / `--no-log-file` | `<parent-folder>/report.log`. Set a path to move it, or `false` to turn it off |

Booleans accept `true`/`false`, `1`/`0`, `yes`/`no` and `on`/`off`. An invalid value stops the run with a message naming the variable.

## Docker

The image is distroless (`gcr.io/distroless/python3-debian12:nonroot`): it has no shell, runs as a non-root user, processes the folder once and exits. Mount the folder to process at `/data`.

```bash
# Build the image
docker build -t archivist .

# Run with the defaults
docker run --rm -v "C:\photos:/data" archivist

# Configure with environment variables
docker run --rm -v "C:\photos:/data" -e ARCHIVIST_LEAVE_ZIP=true -e ARCHIVIST_SEND_TO_BIN=true archivist

# Append options, which override the environment variables
docker run --rm -v "C:\photos:/data" archivist --dry-run
```

With Docker Compose, copy [.env.example](.env.example) to `.env`, set `HOST_PARENT_FOLDER` and any `ARCHIVIST_*` values, then run:

```bash
docker compose run --rm archivist
```

Keep these container specifics in mind:

* The container runs as UID `65532` (`nonroot`), so it needs write access to the mounted folder. On Linux or a NAS, run `chown -R 65532 /path/to/photos` or add `--user $(id -u):$(id -g)`. Docker Desktop on Windows handles this for you.
* The report is written to `/data/report.log`, which is the parent folder on the host.
* There's no Trash in a container, so `--send-to-bin` moves items to a `.Trash-<uid>` folder inside the mounted folder.
* There's no prompt. If no parent folder is set, the run fails with exit code `2`, and archives whose folder already exists are skipped.

## Recycle Bin and Trash

`--send-to-bin` uses Send2Trash, which works on every platform:

| OS      | Destination                                                               |
|---------|---------------------------------------------------------------------------|
| Windows | Recycle Bin                                                               |
| macOS   | Trash                                                                     |
| Linux   | Desktop trash (`~/.local/share/Trash`, or `.Trash-<uid>` on other drives) |

> [!CAUTION]
> Network shares (SMB or NAS) may not have a Recycle Bin on Windows, in which case items are deleted permanently. Turn on the share's own recycle bin, such as the Synology one, to keep a safety net.

## Exit codes

| Code | Meaning                                                                                        |
|------|------------------------------------------------------------------------------------------------|
| `0`  | The run finished                                                                               |
| `1`  | An `ARCHIVIST_*` variable is invalid, or the run was cancelled with Ctrl+C                     |
| `2`  | Invalid options, the parent folder is missing or not given, or the report file can't be opened |

Errors on individual archives or files are logged in the report and don't change the exit code.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, tests and project structure.
