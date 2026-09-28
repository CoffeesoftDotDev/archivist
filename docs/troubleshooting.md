---
title: Troubleshooting
description: Resolve common Archivist archive, permission, logging, and container issues
---

## The command did not change anything

Dry run is the default. Review the report, then add `--apply` or set
`ARCHIVIST_APPLY=true`.

```powershell
archivist --parent-folder "C:\photos" --apply
```

Image transfers additionally require an explicit yes in an interactive terminal.
Listing alone remains read-only even with `--apply`. No matching pictures is a
no-op. See [Image workflows](usage.md) for action selection and approval rules.

## An image workflow stopped partway through

New image workflows stop on incomplete discovery, changed inputs, unsafe or
occupied targets, extraction/transfer errors and report failures. They do not
roll back completed moves. Read completed/remaining counts and retained-copy
messages before retrying. Previously extracted folders may remain; original ZIPs
not yet removed are retained. Existing extraction folders are not merged in image
mode, so resolve those outputs deliberately before a new attempt.

There is no overwrite switch for destination pictures. Source and destination must
be disjoint. Source read-only flags are not cleared for picture moves; `--force`
applies to ZIP disposal and legacy cleanup, and is rejected with `--copy`.

## An archive was skipped

Common reasons include:

* The destination folder already exists and the run is non-interactive.
* The destination is a file, link, or Windows junction.
* A file in the archive conflicts with an existing folder, or the reverse.
* A replacement or archive is read-only and `--force` is not set.
* The archive needs more free space than is available after the 100 MB reserve.
* The archive exceeds the ZIP-bomb expansion thresholds.

The report records the exact reason next to the skipped archive.

## Read-only items remain

Archivist preserves read-only archives and cleanup targets by default. Pass `--force` to clear the
flag before removal.

```powershell
archivist --parent-folder "C:\photos" --apply --force
```

## Recycle Bin behavior on network shares

:::{caution}
SMB and NAS shares may not expose a Recycle Bin to Windows. In that case, `--send-to-bin` can still
result in permanent deletion. Enable the share's own recycle-bin feature when available.
:::

## Docker reports a permission error

The image runs as UID `65532`. Ensure that UID can write to the mounted folder, or run the container
with your current Linux user.

```bash
chown -R 65532 /path/to/photos

# Or
docker run --rm --user $(id -u):$(id -g) -v "/path/to/photos:/data" archivist
```

## Invalid environment configuration

Boolean variables accept `true`/`false`, `1`/`0`, `yes`/`no`, and `on`/`off`. The maximum size must
be a whole number.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | The run finished. Individual skipped items remain in the report. |
| `1` | Invalid environment configuration, cancellation, or an incomplete/unapproved image workflow. |
| `2` | Options, the parent folder, or the report destination are invalid. |

## Still blocked

Include the command, platform, Archivist version, and relevant report lines when
[opening an issue](https://github.com/CoffeesoftDotDev/archivist/issues). Remove personal paths or
filenames before posting logs publicly.
