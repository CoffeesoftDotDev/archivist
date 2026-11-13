# TouteMonAnnee journal export

The optional `toutemonannee` extra adds an authenticated browser workflow without
changing Archivist's base installation:

```powershell
uv sync --extra toutemonannee
uv run playwright install chromium
archivist --export-journal --journal-destination "C:\school-photos"
archivist --export-journal --journal-destination "C:\school-photos" --apply
```

The first invocation is a configuration-only preview. It does not import the
browser service, open a browser, sign in, create a report, or touch the destination.
Only `--apply` runs the exporter. Journal selection takes place in its dedicated
browser, so `--parent-folder` is neither needed nor accepted for this workflow.

## Settings

Archivist accepts `--journal-config PATH` to select an exporter JSON file; without
it, the exporter reads an optional `appsettings.json` in the current directory.
`--journal-destination` overrides only the configured destination. TMA environment
variables keep their existing names and override JSON settings. Nested settings use
double underscores, such as `TMA_Immich__ApiKey`.

| Setting | Default | Description |
|---|---|---|
| `Destination` / `TMA_Destination` | `.` | Local photo destination |
| `JournalId` / `TMA_JournalId` | unset | Optional journal UUID; otherwise choose in browser |
| `BrowserChannel` / `TMA_BrowserChannel` | `msedge` | `msedge` or Playwright `chromium` |
| `ReuseSession` / `TMA_ReuseSession` | `true` | Reuse the dedicated private browser profile |
| `ScreenshotRestricted` / `TMA_ScreenshotRestricted` | `false` | Separate permission for restricted-photo screenshots |
| `Immich:Enabled` / `TMA_Immich__Enabled` | `false` | Add Immich as a destination |
| `Immich:Url` / `TMA_Immich__Url` | unset | Immich server URL |
| `Immich:ApiKey` / `TMA_Immich__ApiKey` | unset | Immich API key; keep private |
| `Immich:Album` / `TMA_Immich__Album` | unset | Required album when Immich is enabled |
| `Resolution` / `TMA_Resolution` | `1920x1080` | Supported browser viewport preset |
| `LoginTimeoutSeconds` / `TMA_LoginTimeoutSeconds` | `300` | Sign-in timeout (1–3600 seconds) |
| `RequestTimeoutSeconds` / `TMA_RequestTimeoutSeconds` | `120` | Per-request timeout (1–3600 seconds) |
| `PageSize` / `TMA_PageSize` | `100` | Journal page size (1–100) |
| `NoLocal` / `TMA_NoLocal` | `false` | Disable local output; requires Immich |

`--journal-config` can point at a private copy of
[the example settings](../examples/toutemonannee/appsettings.example.json). The
standalone compatibility command `tma` retains its exporter-specific CLI options.
In Archivist mode, operation logs use Archivist's `--log-file`/`--no-log-file`;
the export-specific `LogPath` and `LogLevel` settings apply only to `tma`.

## Privacy and output

The exporter uses only a dedicated TouteMonAnnee browser profile, never the user's
normal Edge profile. Reused authentication state is stored under
`%LOCALAPPDATA%\TouteMonAnnee.Cli\browser\...` on Windows or
`$XDG_DATA_HOME/TouteMonAnnee.Cli/browser/...` on Unix. Set
`TMA_ReuseSession=false` to use a temporary profile. API keys belong in private
settings or environment variables, not source control or shell history.

Restricted-photo screenshots are disabled by default and require an independent
explicit `TMA_ScreenshotRestricted=true` opt-in. `--apply` alone does not grant
that permission. The workflow never exposes browser login, screenshots, or uploads
through Archivist's read-only MCP interface.

An applied export appends its photo outcomes to `pictures.log` in the destination.
Reports include photo IDs, activity dates, statuses, and local paths; redact them
before sharing. Completed files are retained if later work fails. Export exit codes
are `0` for complete, `1` for incomplete/operation failure, `2` for invalid
configuration or unavailable optional dependencies, and `130` for cancellation.
