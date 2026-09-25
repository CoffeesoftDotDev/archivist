---
title: Getting Started
description: Install Archivist and safely process your first folder
---

## Requirements

* Python 3.10 or later
* [uv](https://docs.astral.sh/uv/), which provides `uvx`
* Windows, macOS, or Linux

Send2Trash is the only runtime dependency. It is installed automatically and powers the optional
Recycle Bin and Trash behavior.

## Run without installing

1. Open a terminal and choose a folder whose contents you can inspect.
2. Preview the work. This command downloads Archivist and performs a dry run:

   ```powershell
   uvx --from git+https://github.com/CoffeesoftDotDev/archivist archivist --parent-folder "C:\photos"
   ```

:::{important}
Nothing is extracted or deleted without `--apply`. The preview still opens archives read-only and
performs free-space and ZIP-bomb checks.
:::

3. Review the report. Confirm the listed archives, cleanup targets, and skipped items.
4. Apply the changes. Add `--send-to-bin` if removed items should go to the Recycle Bin or Trash:

   ```powershell
   uvx --from git+https://github.com/CoffeesoftDotDev/archivist archivist --parent-folder "C:\photos" --apply --send-to-bin
   ```

## Install the command

Install Archivist as a uv tool when you want a permanent command:

```powershell
uv tool install git+https://github.com/CoffeesoftDotDev/archivist
archivist --parent-folder "C:\photos"
```

Both `uvx` and `uv tool install` accept a local clone path in place of the Git URL.

## Choose the folder interactively

Leave out `--parent-folder` to select the folder through a terminal prompt. Non-interactive
environments, including Docker, require the folder to be configured.

## Next steps

* Read [Usage](usage.md) to understand extraction, existing folders, and reports
* Review [Configuration](configuration.md) for every option and environment variable
