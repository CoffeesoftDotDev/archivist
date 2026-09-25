---
title: Archivist
description: Recursive ZIP extraction and metadata cleanup for macOS, Windows, and Synology files
---

:::{image} assets/Archivist.png
:alt: Archivist logo
:width: 240px
:align: center
:::

Archivist recursively extracts ZIP files, restores timestamps, and removes the metadata left
behind by macOS, Windows, and Synology devices.

::::{grid} 1 2 3 3
:gutter: 3

:::{grid-item-card} 🚀 Getting Started
:link: getting-started
:link-type: doc

Install with uv, preview your first folder, and safely apply the changes.
:::

:::{grid-item-card} 🗂️ Usage
:link: usage
:link-type: doc

Learn how recursive extraction, existing folders, dry runs, and reports work.
:::

:::{grid-item-card} ⚙️ Configuration
:link: configuration
:link-type: doc

Review every command-line option and its matching environment variable.
:::

:::{grid-item-card} 🐳 Docker
:link: docker
:link-type: doc

Run the distroless image as a non-root user with Docker or Compose.
:::

:::{grid-item-card} 🩺 Troubleshooting
:link: troubleshooting
:link-type: doc

Understand skipped archives, permissions, reports, and exit codes.
:::

:::{grid-item-card} 🧰 Contributing
:link: contributing
:link-type: doc

Set up a development environment, run tests, and understand the project.
:::

::::

## What Archivist does

::::{grid} 1 2 3 3
:gutter: 3

:::{grid-item-card} 📦 Extracts recursively
ZIPs found inside other ZIPs are processed in the same run, up to ten levels deep.
:::

:::{grid-item-card} 🧹 Cleans metadata
Remove AppleDouble, `.DS_Store`, `Thumbs.db`, `desktop.ini`, and `@eaDir` artifacts.
:::

:::{grid-item-card} 🛡️ Starts safely
Every run is a preview until you explicitly pass `--apply`.
:::

:::{grid-item-card} 💣 Checks archives
Free-space and expansion-ratio checks guard against oversized archives and ZIP bombs.
:::

:::{grid-item-card} ♻️ Supports recovery
Use `--send-to-bin` to move removed items to the Recycle Bin or Trash.
:::

:::{grid-item-card} 📝 Reports every action
See extracted, removed, overwritten, and skipped items in the console and log file.
:::

::::

## Preview before anything changes

Run Archivist without `--apply` to inspect every planned extraction and cleanup. When the report
looks right, run the same command with `--apply`.

```powershell
archivist --parent-folder "C:\photos"
archivist --parent-folder "C:\photos" --apply --send-to-bin
```

:::{toctree}
:hidden:

getting-started
usage
configuration
docker
troubleshooting
contributing
:::
