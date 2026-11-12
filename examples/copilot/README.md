# Local Copilot preview example

This directory is a self-contained, **session-only** example in the Archivist
repository, not a separate plugin repository or a published release.
It uses the supported Agent Plugins 1.0 format: root `plugin.json`, root
`mcp.json`, `skills\archivist-preview\SKILL.md`, and the Copilot-specific
`com.github.copilot\agents\archivist-preview.agent.md`.

## Prerequisites

* Local Copilot CLI with `--plugin-dir` support (read-only help/version verification:
  **1.0.109** at authoring time).
* Node.js 20+ on PATH for the small launcher and its tests.
* uv/uvx, Git and compatible Python 3.10+; network/cache requirements below.
* A reviewed **full immutable 40-hex commit** containing the MCP implementation,
  accessible from `CoffeesoftDotDev/archivist`.
* Existing, narrowly scoped source and destination-root directories.

The official format reference is
[GitHub's CLI plugin reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-plugin-reference).
Help confirmed `--plugin-dir`; an authenticated Copilot/model integration
session has not been claimed as tested. The
[published MCP guide](https://coffeesoftdotdev.github.io/archivist/mcp.html#local-copilot-example)
also includes the manifests, session setup and sample request inline.

## Configure and load without installation

From the repository root in PowerShell:

```powershell
# Merged implementation from PR #30; tested on Windows and Linux.
$env:ARCHIVIST_REVIEWED_COMMIT = "d92909fccb11624c490781df2d6a4d3eac719658"
$env:ARCHIVIST_SOURCE_ROOT = "C:\photos"
$env:ARCHIVIST_DESTINATION_ROOT = "D:\collections"
copilot --plugin-dir .\examples\copilot
```

This loads only for that session, without `copilot plugin install`, user settings
changes or marketplace registration. The CLI supplies `${PLUGIN_ROOT}` to the
stdio registration's `cwd`; `node launch-mcp.mjs` therefore resolves inside this
directory on Windows and Linux. Environment variables are inherited by the
launcher; this example does not depend on arbitrary placeholder expansion in
MCP JSON. On Linux set the same three variables using your shell and supply
native absolute paths; the Node launcher uses the current host's path rules.

The sample pin is the public merge commit from
[PR #30](https://github.com/CoffeesoftDotDev/archivist/pull/30), not a mutable
branch or a released v0.3 package. Review the selected code and root policy
before using your own collections. To use a later revision, select and verify
its full immutable SHA explicitly.

The launcher rejects missing/relative roots and non-full-SHA pins, then invokes:

```text
uvx --from "archivist[mcp] @ git+https://github.com/CoffeesoftDotDev/archivist.git@<REVIEWED_FULL_SHA>" archivist-mcp --stdio --source-root <SOURCE_ROOT> --destination-root <DESTINATION_ROOT>
```

Arguments are passed without a shell. There are no broad filesystem defaults,
embedded credentials or mutable branch pins. The operator, not the model,
selects the pin and roots. The server validates existence, disjoint paths,
links/junctions and containment. A SHA's syntax alone does not prove review or
that it contains the server: the operator must establish both.

First launch can download source, Python, build dependencies and the optional MCP
SDK and populate uv's environment/cache. Offline use requires warming the exact
pin and dependencies on the target platform first and verifying startup with
uv's offline mode. Collection reads do not prohibit these installation/cache
writes outside the collection. Source pinning does not freeze all transitive
dependencies. Never replace this launch with bare `uvx archivist` or a mutable
`main` reference.

## Use

Inspect `/mcp`, `/agent` and `/skills` in that local session. Select
`archivist-preview` and request, for example:

> Inventory JPG and ARW pictures under my configured source, including nested
> ZIPs. I consent to the paths, names and dates being sent to the configured
> model service. After complete inventory, preview copying them to
> D:\collections\selected. Show collision names and all mixed-ZIP extraction
> effects. Do not execute anything.

Replace the example destination with an authorized local path. For a safe
demonstration use a disposable fixture containing both disk pictures and a ZIP
containing a nested ZIP and nonimage files; compare source/destination directory
listings and file hashes before/after. Do not use a private collection to test
metadata disclosure.

Discover `inventory` and `prepare_transfer` through MCP `tools/list`; their JSON
Schemas come from the server, not a duplicate schema in this plugin. The workflow
must drain bounded pages and reject incomplete discovery. A tool description,
read-only annotation, filename, archive member or `plan_id` cannot authorize
mutation or policy expansion. The prompt is not a sandbox: host permissions and
server access policy remain essential.

There is no apply/execution tool. For subsequent execution the example stops;
the human uses the separate CLI workflow and its interactive approval.
A GitHub-hosted coding agent cannot access your local photo folders.

## Local validation and evidence

Run without installing a plugin, contacting a model or downloading the package:

```powershell
node --test examples\copilot\launch-mcp.test.mjs
```

The tests cover immutable source selection, explicit root arguments, invalid
configuration and stderr-only failure diagnostics. They do not prove a public
SHA is available, MCP protocol compatibility, component invocation or model behavior.

Local Windows results: Node.js 24.19.0 passed all four launcher tests; both
manifests passed validation against their official Agent Plugins 1.0 JSON
Schemas; `copilot --plugin-dir .\examples\copilot plugin list --json` recognized
the enabled external plugin with CLI 1.0.109. This read-only listing is not an
authenticated agent/skill/tool invocation. The strict Sphinx 8.2.3 HTML build
also passed.

SHA validation rejects trailing newlines, and root validation rejects Windows
drive-relative/root-relative paths.
[Hosted MCP CI](https://github.com/CoffeesoftDotDev/archivist/actions/runs/43199321092)
passed SDK contracts and clean immutable-source startup on Windows/Linux with
Python 3.10/3.13 against the sample merge commit. This does not prove an
authenticated Copilot agent/skill/tool invocation.
See [MCP acceptance gates](../../docs/mcp.md#acceptance-and-release-gates)
for the hosted evidence and remaining actual Copilot integration and human
release approval. Neither this example nor passing server CI approves a release.
