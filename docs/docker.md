---
title: Docker
description: Build and run Archivist with Docker or Docker Compose
---

## Container behavior

The image uses `gcr.io/distroless/python3-debian12:nonroot`. It has no shell, runs as UID `65532`,
and defaults the parent folder to `/data`.

## Build the image

```bash
docker build -t archivist .
```

## Preview a folder

The default run is a dry run:

```powershell
docker run --rm -v "C:\photos:/data" archivist
```

## Apply changes

Use command-line options or environment variables:

```powershell
# Command-line options
docker run --rm -v "C:\photos:/data" archivist --apply --max-size 4096

# Environment variables
docker run --rm -v "C:\photos:/data" `
  -e ARCHIVIST_APPLY=true `
  -e ARCHIVIST_LEAVE_ZIP=true `
  -e ARCHIVIST_SEND_TO_BIN=true `
  archivist
```

:::{important}
A container has no interactive prompt. Mount the folder at `/data` or set
`ARCHIVIST_PARENT_FOLDER`.
:::

## Docker Compose

1. Copy `.env.example` to `.env`.
2. Set `HOST_PARENT_FOLDER` to the host folder.
3. Set any `ARCHIVIST_*` variables, including `ARCHIVIST_APPLY=true` when ready.
4. Run the one-shot service:

   ```bash
   docker compose run --rm archivist
   ```

## Permissions and Trash

* Linux and NAS mounts must be writable by UID `65532`. Change ownership or run with
  `--user $(id -u):$(id -g)`.
* Docker Desktop on Windows handles mounted-folder permissions.
* The default report is written to `/data/report.log`.
* `--send-to-bin` uses a `.Trash-<uid>` folder inside the mounted filesystem because containers
  have no desktop Trash.
