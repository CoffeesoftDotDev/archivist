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
| `--list-images`, `--list-pictures` | Off | List image files and ZIP entries |
| `--move-images`, `--move-pictures` | Off | List, approve, extract, then transfer pictures |
| `--extract-zip` | Off | Explicit extraction without implicit cleanup |
| `--destination <path>` | Unset | Flat, source-disjoint transfer destination; relative to current directory |
| `--copy` | Off | Copy rather than move; requires a picture-transfer action |
| `--filter <extensions>` | Image catalog | Comma-separated case-insensitive image extensions |
| `--leave-zip` | Off | Keep ZIP archives after extraction |
| `--leave-appledouble` | Off | Keep AppleDouble files and folders |
| `--leave-eadir` | Off | Keep Synology `@eaDir` folders |
| `--leave-ds-store` | Off | Keep `.DS_Store` files |
| `--leave-thumbs-db` | Off | Keep Windows `Thumbs.db` files |
| `--leave-desktop-ini` | Off | Keep Windows `desktop.ini` files |
| `--max-size <bytes>` | `2048` | Largest AppleDouble file to remove |
| `--force-readonly-deletion`, `--force` | Off | Clear read-only flags before removal |
| `--send-to-bin` | Off | Use the Recycle Bin or Trash |
| `--apply` | Off | Extract, move, and remove files |
| `--dry-run` | On without apply | Preview only; overrides `ARCHIVIST_APPLY=true` |
| `--log-file [path]` | `report.log` / `pictures.log` | Choose the report file or folder; image workflows use `pictures.log` |
| `--no-log-file` | Off | Disable file logging |

## Environment variables

| Variable | Option | Default |
|---|---|---|
| `ARCHIVIST_PARENT_FOLDER` | `--parent-folder` | Prompt, or `/data` in Docker |
| `ARCHIVIST_LIST_IMAGES` | `--list-images` / `--list-pictures` | `false` |
| `ARCHIVIST_MOVE_IMAGES` | `--move-images` / `--move-pictures` | `false` |
| `ARCHIVIST_EXTRACT_ZIP` | `--extract-zip` | `false` |
| `ARCHIVIST_DESTINATION` | `--destination` | Unset |
| `ARCHIVIST_COPY` | `--copy` | `false` |
| `ARCHIVIST_FILTER` | `--filter` | All supported image extensions |
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
| `ARCHIVIST_LOG_FILE` | Logging options | `report.log` (`pictures.log` for images) in the parent folder |

Boolean variables accept `true`/`false`, `1`/`0`, `yes`/`no`, and `on`/`off`.
Both flag vocabularies share the `*_IMAGES` variables; there are no `*_PICTURES`
variables. `--copy` and `--destination` require a move action, and `--filter`
requires an image action. Applying a transfer requires a destination; preview
does not. Copy mode rejects `--force`/`--send-to-bin`. No variable grants human
approval. See [Usage](usage.md) for the extension catalog and workflow rules.

## Logging values

`ARCHIVIST_LOG_FILE` supports three modes:

* Set a file or folder path to choose the destination
* Use `true` to keep the workflow's default `report.log` or `pictures.log`
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
