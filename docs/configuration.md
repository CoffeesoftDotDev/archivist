---
title: Configuration
description: Archivist command-line options and environment variables
---

## Precedence

A command-line option overrides its environment variable, which overrides the built-in default.
Unset and empty environment variables preserve the default.

## Command-line options

| Option | Default | Purpose |
|---|---|---|
| `--parent-folder <path>` | Prompt | Folder to process |
| `--leave-zip` | Off | Keep ZIP archives after extraction |
| `--leave-appledouble` | Off | Keep AppleDouble files and folders |
| `--leave-eadir` | Off | Keep Synology `@eaDir` folders |
| `--leave-ds-store` | Off | Keep macOS `.DS_Store` files |
| `--leave-thumbs-db` | Off | Keep Windows `Thumbs.db` files |
| `--leave-desktop-ini` | Off | Keep Windows `desktop.ini` files |
| `--max-size <bytes>` | `2048` | Largest AppleDouble file to remove |
| `--force-readonly-deletion`, `--force` | Off | Clear read-only flags before removal |
| `--send-to-bin` | Off | Use the Recycle Bin or Trash |
| `--apply` | Off | Extract, move, and remove files |
| `--log-file [path]` | `report.log` | Choose the report file or folder |
| `--no-log-file` | Off | Disable file logging |

## Environment variables

| Variable | Option | Default |
|---|---|---|
| `ARCHIVIST_PARENT_FOLDER` | `--parent-folder` | Prompt, or `/data` in Docker |
| `ARCHIVIST_LEAVE_ZIP` | `--leave-zip` | `false` |
| `ARCHIVIST_LEAVE_APPLEDOUBLE` | `--leave-appledouble` | `false` |
| `ARCHIVIST_LEAVE_EADIR` | `--leave-eadir` | `false` |
| `ARCHIVIST_LEAVE_DS_STORE` | `--leave-ds-store` | `false` |
| `ARCHIVIST_LEAVE_THUMBS_DB` | `--leave-thumbs-db` | `false` |
| `ARCHIVIST_LEAVE_DESKTOP_INI` | `--leave-desktop-ini` | `false` |
| `ARCHIVIST_MAX_SIZE` | `--max-size` | `2048` |
| `ARCHIVIST_FORCE_READONLY_DELETION` | `--force` | `false` |
| `ARCHIVIST_SEND_TO_BIN` | `--send-to-bin` | `false` |
| `ARCHIVIST_APPLY` | `--apply` | `false` |
| `ARCHIVIST_LOG_FILE` | Logging options | `report.log` in the parent folder |

Boolean variables accept `true`/`false`, `1`/`0`, `yes`/`no`, and `on`/`off`.

## Logging values

`ARCHIVIST_LOG_FILE` supports three modes:

* Set a file or folder path to choose the destination
* Use `true` to keep the default `report.log`
* Use `false` to disable file logging

## Examples

```powershell
$env:ARCHIVIST_PARENT_FOLDER = "C:\photos"
$env:ARCHIVIST_APPLY = "true"
$env:ARCHIVIST_SEND_TO_BIN = "true"
archivist
```

```bash
ARCHIVIST_PARENT_FOLDER=/mnt/photos ARCHIVIST_APPLY=true archivist
```
