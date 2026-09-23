# syntax=docker/dockerfile:1

# ---------- build stage: install archivist + deps into a self-contained folder ----------
FROM python:3.11-slim-bookworm AS build

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never

WORKDIR /src
COPY pyproject.toml README.md ./
COPY src ./src

# Install the package (and send2trash) as plain site-packages into /app
RUN uv pip install --no-cache --target /app .

# ---------- runtime stage: distroless (no shell, no package manager) ----------
# gcr.io/distroless/python3-debian12 ships Python 3.11, matching the build stage.
FROM gcr.io/distroless/python3-debian12:nonroot

COPY --from=build /app /app

ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    # Mount the folder to process here:  -v /host/photos:/data
    ARCHIVIST_PARENT_FOLDER=/data

VOLUME ["/data"]
WORKDIR /data

# All other options come from ARCHIVIST_* env vars (defaults when unset),
# and extra CLI flags can still be appended to `docker run`.
ENTRYPOINT ["python3", "-m", "archivist"]
