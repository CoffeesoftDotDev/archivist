---
title: Future specification - file categories and conversational workflows
description: Deferred exploration of general-purpose file collection, mixed ZIP handling, and an agent and AG-UI interface
status: deferred
version: 0.2.0
created_date: 2026-09-28
last_updated: 2026-09-28
---

> **Deferred exploration, not an implementation commitment.** General-purpose
> file categories and the agent/AG-UI route are future capabilities, not implemented
> commands. This document preserves both discussions without changing runtime
> behavior, adding dependencies, or expanding the approved image-workflow scope.

## Relationship to the current specification

The active product-specification draft is
[Image inventory and dynamic file workflows](archivist-image-workflows.md).
Its CLI remains useful without an LLM, agent framework, server, or browser.
Nothing in this document is a prerequisite for delivering that CLI scope.

There are two independent future directions: collecting file categories beyond
pictures, and conversational operation. Generic file collection does not require
an agent, model, AG-UI frontend, or server.

## General-purpose file collection

### User need and proposed command model

The user wants to collect other file types into a destination, initially `.stl`
and `.3mf` 3D-printing files, with the same discovery, ZIP inspection, approval,
copy/move and preservation safeguards as pictures.

Separate the **action** from the **category** rather than adding one pair of flags
per category. This scales better than `--list-pictures`, `--list-3d-files`,
`--move-videos`, and a growing set of category-specific actions.

The following syntax is a proposal only and is not accepted by the current CLI:

```powershell
# Inventory ordinary and archived pictures; write an inventory report.
archivist --list-files --type pictures --parent-folder "C:\Collection"

# Preview collection of STL and 3MF files, without mutation.
archivist --move-files --type 3d --parent-folder "C:\Collection" --destination "D:\Models" --dry-run

# List, request approval, extract relevant ZIPs, then move matching files.
archivist --move-files --type 3d --parent-folder "C:\Collection" --destination "D:\Models" --apply

# The same plan, but preserve source files and original ZIPs.
archivist --move-files --type 3d --copy --parent-folder "C:\Collection" --destination "D:\Models" --apply

# Narrow a category to a subset of its supported extensions.
archivist --list-files --type 3d --filter STL --parent-folder "C:\Collection"
```

Use a shell-safe category token such as `3d`, not unquoted `3d files`: the latter
is two command-line arguments. A quoted label such as `--type "3d files"` could
be an alias later, but is not proposed as the canonical spelling.

| Proposed category | Initial extension set | Meaning |
|-------------------|-----------------------|---------|
| `pictures` | Current supported image catalog | Preserve existing image selection semantics |
| `3d` | `stl`, `3mf` | Collect whole model files; no conversion or model repair |

Further categories, custom category definitions and multi-category selection are
not part of this initial proposal. File classification is extension-based and
case-insensitive, not a claim that a file's contents are valid for that format.
Requiring `--type` on generic actions is recommended to avoid accidentally selecting
every file. Unknown categories, empty filters and extensions outside the selected
category should fail explicitly rather than silently broadening selection.

### Proposed behavior and compatibility

* Keep current picture/image flags supported. They should select the same
  `pictures` category, not a separate implementation with different safety rules.
* Treat `--filter` as a narrowing intersection with the category's extension set.
  It must not implicitly add unrelated formats or select files inside a model
  package.
* Reuse the ordered workflow: **inventory -> human approval -> complete relevant
  ZIP extraction -> move/copy**. Repeated actions and prerequisites execute once;
  flag order must not change effects. Dry-run stops at inventory/report generation.
* Report name, extension, category and full physical/archive-qualified source
  location, plus counts by category, extension and archive. Show selected and
  unselected archive-file counts separately; do not describe every archive entry
  as transferred.
* Preserve `pictures.log` for picture workflows. Category-based report naming,
  such as `3d.log`, is a candidate requiring a compatibility decision before
  implementation; retain an explicit `--log-file` override.
* Keep flat, disjoint destinations, exclusive creation, oldest-first collision
  suffixes, original-byte/date preservation, source snapshots, ZIP resource
  limits and honest partial-failure outcomes.
* Preserve each `.3mf` as an opaque file. Although 3MF is ZIP-based, it is a model
  package, not an ordinary extraction archive: do not unpack its internals, collect
  its thumbnail as a separate picture, or discard package relationships. An outer
  `.zip` may contain a `.3mf`; collect that entire member unchanged. Apply the same
  byte-preserving treatment to ASCII and binary STL.
* Do not infer related assets or repair project references. Associated unselected
  files remain at their source or in the safely extracted remainder; collecting
  arbitrary future project formats may require a separate dependency policy.

### Mixed ZIPs: selected files versus extraction scope

**Current behavior:** `--filter` selects which pictures are inventoried and
transferred; it does not filter the contents of a ZIP extraction. A relevant ZIP
and its nested ZIPs are fully extracted before any selected picture moves.

For `album.zip` containing `photo.jpeg` and `clip.mp4`, with JPEG selected:

| Current operation | JPEG outcome | MP4 outcome | Original ZIP |
|-------------------|--------------|-------------|--------------|
| Listing or move/copy dry-run | Report the matching picture; no transfer | Not selected; remains in archive | Retained, no extraction |
| Approved move | Move to the destination after full extraction | Remains in the sibling `album` extraction folder | Deleted only after complete extraction and successful transfers, unless `--leave-zip` |
| Approved copy | Copy from private temporary extraction to the destination | Remains in the original archive; temporary extracted copy is cleaned up | Always retained unchanged |

Unselected files are not deleted merely because they fail the filter. In move
mode, deleting the original ZIP removes the container after **all** its contents
have been materialized; it is not proof that all contents went to the requested
destination. Use `--leave-zip` to retain the original container as well.
Archive deletion is not archive rewriting: Archivist does not remove just the
selected members from the original ZIP.

For a move/copy request, an archive containing no matching files is not selected
for extraction or deletion; an entirely empty selection performs neither transfer
nor extraction. Separately requesting list-plus-extraction can extract inventoried
ZIPs even without matching pictures, so its explicitly approved extraction effects
must not be confused with transfer selection.

**Recommended initial generic behavior:** retain this full-extraction policy and
make the remainder visible before approval. Show selected files, unselected file
counts/extensions, extraction locations, destination mappings and exact archive
retention/deletion effects. For a ZIP containing an STL, a 3MF and a PDF, collecting
`3d` sends only the STL/3MF to the destination and retains the PDF in the extracted
remainder (move) or unchanged original ZIP (copy).

**Possible later optimization:** selectively decompress only matching members,
and nested ZIP containers needed to discover them. This is a separate policy
decision, not an alternate implementation with identical side effects:

* If unselected members have not been safely materialized elsewhere, the original
  ZIP **must remain intact**, even after every selected file was transferred.
* A source ZIP containing retained members cannot be reported as deleted or fully
  moved. Report selected-member copies/transfers and archive retention separately.
* Do not rewrite a ZIP to remove selected entries under ordinary move approval.
  Such archive editing would need separate authorization, integrity checks and a
  recovery design.
* Preserve nested containers needed to retain unselected descendants. A filter,
  partial extraction, CRC failure, cancellation or metadata-restoration failure
  must never authorize disposal of their only remaining copy.

Selective extraction could reduce temporary space and I/O for mixed archives,
but cannot inherit the current full-extraction ZIP-deletion rule.

### Implementation impact and acceptance candidates

Generalize the current image-specific inventory/transfer selection around a small
category-to-extension catalog. Reuse the planner, approval boundary, archive
manifests, timestamp utility and executor; adapt CLI/environment configuration,
report labels and counters, and compatibility tests. Do not add an agent or a
plugin framework merely to support two categories. Existing CLI tests remain
regression requirements, not candidates for replacement.

These scenarios are future criteria, not claims of current support:

| Scenario | Expected future result |
|----------|------------------------|
| List `3d` across folders and nested ordinary ZIPs | Return STL/3MF names, types, full locations and archive counts without extraction |
| Approve a generic `3d` move | Extract relevant ZIPs first, then collect only approved models in the destination |
| Copy a 3MF nested inside an ordinary ZIP | Destination 3MF bytes and supported original dates match; source ZIP remains unchanged |
| Encounter a 3MF while listing pictures | Do not traverse model-package internals for thumbnails or textures |
| Narrow `3d` with `--filter STL` | Select STL only; 3MF remains unselected and safely retained |
| Select JPEG from a ZIP also containing MP4 | Show the MP4 remainder and archive disposition before approval; preserve the MP4 after execution |
| Select models from a ZIP containing PDF notes | Transfer models only; retain the notes according to the explicit full/partial extraction policy |
| Selectively extract JPEG while leaving MP4 compressed | Keep the original mixed ZIP intact; do not apply full-extraction deletion semantics |
| Find no models during a generic transfer preview/apply | Report zero matches, without creating a destination or extracting/deleting archives |
| Reject approval or fail extraction/transfer/date restoration | Preserve affected sources and not-yet-removed ZIPs; report completed versus remaining work |
| Use existing picture aliases | Preserve established inventory, approval, report naming and transfer behavior |

Before implementation, confirm the final category names/catalog, generic
configuration/environment names and report filenames. Confirm full versus
selective extraction and the corresponding archive-retention defaults explicitly.
Selective extraction and archive rewriting must not be smuggled into the category
refactor. This proposal does not amend the approved BRD or implement these flags.

## Conversational product opportunity

The user also asked about chatting with an agent through AG-UI to decide which
operations to perform, with human approval for destructive or mutative actions.
Microsoft Agent Framework was an interpretation used during the discussion,
not a confirmed framework selection.

Let an operator discover files, discuss filters and destinations, review a proposed
workflow, and authorize its execution through conversation. The agent would help
choose actions; ordinary application code would enforce dependencies, permissions,
and approved filesystem effects.

The intended distinction is **conversational planning, deterministic execution**.
The agent must not replace the CLI's workflow rules or gain an unrestricted shell.

## Candidate experience

1. The operator selects a folder and asks to collect particular picture formats.
2. The agent requests a read-only inventory of ordinary files and ZIP entries.
3. The interface displays counts, source locations, archive coverage, and omissions.
4. The operator revises the filter, destination, exclusions, or archive policy.
5. The backend produces a concrete plan and the interface displays explicit
   approval controls alongside its effects.
6. After approval, the executor extracts ZIPs before moving the approved pictures.
7. Progress and actual outcomes are streamed back, including partial failures.

For a move, the current specification's order remains: **list -> human
confirmation -> extract -> move**. "Decide on the go" allows changing a proposal;
it does not grant permission to silently expand an approved execution.

## Candidate responsibilities

| Component | Responsibility |
|-----------|----------------|
| Chat frontend | Conversation, inventory views, approval/rejection controls, progress, and results |
| AG-UI adapter | Carry messages, tool events, approval requests/responses, and UI state between frontend and backend |
| Agent runtime | Interpret user requests, clarify ambiguity, and propose structured actions |
| Shared Archivist planner | Validate inputs, resolve dependencies and effects, and prepare reviewable plans |
| Approval boundary | Verify who approved which plan version and which filesystem effects |
| Shared Archivist executor | Execute authorized operations and return factual per-operation outcomes |

AG-UI is a protocol, not a ready-made chat product or a filesystem permission
system. A frontend and an agent/backend integration would still be required.
CLI and chat adapters should share the same underlying operation rules.

## Proposed capability boundaries

The following are candidate tool capabilities, not committed API names or schemas.

| Capability | Approval treatment |
|------------|--------------------|
| Inspect authorized folders and ZIP metadata | Read-only, subject to access and resource limits |
| Preview or revise a workflow | No filesystem mutation; invalidate obsolete approval |
| Export an inventory report | A filesystem write; requires explicit permission or a narrowly defined report-write policy |
| Execute an approved plan | Requires backend-verified human approval for the exact effects |
| Read execution status | Read-only; do not execute work again to recreate the display |
| Request cancellation | Stop future work at safe boundaries; do not imply rollback |

Do not expose arbitrary shell execution, unconstrained path access, or an
unrestricted "run anything" action.

## Proposed approval and execution safeguards

These are review candidates, not claims that the chosen framework supplies them
automatically.

* Enforce approval in backend code. A prompt telling the model to ask permission
  is not an authorization boundary.
* Bind each approval to an immutable plan identifier/version, operator identity,
  source scope, destination, filter, and operation set.
* Show file counts, extensions, affected folders, archive counts, collisions,
  and all mutative effects before asking for approval.
* Treat extraction, directory creation, report writing, movement, overwrite,
  metadata cleanup, and ZIP deletion as writes. Approval to move pictures must
  not silently authorize deleting original ZIPs or unrelated metadata.
* A single approval may cover an explicitly itemized extraction-and-move plan
  only if that approval model is chosen. Per-stage approval is an alternative.
  Neither model grants blanket permission for later changes.
* Changed destinations, filters, discovered files, conflicts, or relevant
  filesystem state require revalidation and, when effects change, fresh approval.
* Reject missing, stale, cancelled, or replayed approvals. Reconnects and retried
  requests must not repeat completed mutations.
* Persist enough execution state to distinguish approved, running, completed,
  skipped, failed, and cancelled work. Conversation history alone is not a job ledger.
* Report cancellation and partial application honestly. Do not promise atomic
  multi-file transactions or automatic recovery of deleted files.

## Hosting, access, and privacy

The executor must run where the files are accessible. A hosted agent cannot
directly operate on a user's `C:\Photos` folder without a local connector, mount,
or separate upload flow.

| Deployment option | Additional considerations |
|-------------------|---------------------------|
| Local single-user application | Local folder permissions, loopback endpoint protection, model credentials, process lifecycle |
| Hosted service with mounted storage | Authentication, per-user roots, authorization, concurrent operations, job ownership, storage access |
| Hosted conversation with local executor | Authenticated connector, remote-to-local trust, approved path boundaries, disconnected operation |

Filenames, archive entries, and file contents are untrusted data, never agent
instructions. Bound root access and ZIP inspection, reject path escapes, and do
not allow UI-supplied state to override server-side permissions.

Decide what the model provider may receive. Full paths, filenames, and image
contents can disclose private information; minimize or redact metadata and keep
contents local unless separately authorized. Operational telemetry should avoid
raw paths, credentials, and conversation contents. Retention and report-sharing
policies remain open; no new telemetry vocabulary is specified here.

## Dependencies and product impact

This would add a frontend, agent/API adapter, model configuration, approval and
job persistence, streamed progress, cancellation, and recovery behavior. A
multi-user version would also need identity, isolation, and concurrent-operation
controls.

Keep those dependencies optional and separate from the CLI. Do not raise the
CLI's Python minimum or introduce model-provider configuration merely to prepare
for this possible direction.

The documentation consulted during the conversation described a Python
Microsoft Agent Framework AG-UI integration using a FastAPI endpoint and
approval-required tools. It used a prerelease installation path at the time of
review. Package versions, supported Python versions, protocol compatibility, and
approval semantics must be rechecked before adoption.

## Future acceptance candidates

These scenarios are deferred, not current release criteria.

| Scenario | Expected result |
|----------|-----------------|
| Request an inventory | Return observed matches and archive coverage without unauthorized filesystem writes |
| Change a destination before approval | Show an updated plan; the old plan cannot be executed as newly approved |
| Reject the extraction-and-move plan | Neither extraction nor movement starts |
| Supply approval for a different plan or user | Backend rejects execution |
| Repeat an approval response or reconnect | Restore status without repeating completed file operations |
| Cancel during execution | Stop subsequent work safely and show completed versus remaining operations |
| Archive filename contains instruction-like text | Treat it as a filename, not a request to invoke tools |
| Run existing CLI workflows without the agent stack | Continue to function without model credentials or a running service |

## Decisions required before revisiting

| Topic | Open decision |
|-------|---------------|
| Product scope | Local personal tool, hosted shared service, or hybrid connector? |
| Agent runtime | Microsoft Agent Framework or another framework? |
| Model | Local or hosted model, provider, cost limits, and permitted metadata? |
| UI | Frontend technology and inventory/approval interaction design? |
| Approval | One itemized plan or separate stage approvals; expiration and changed-file policy? |
| Report permission | Explicit export approval or a narrowly scoped automatic local-report exception? |
| Access | Authorized roots, destinations, identities, and concurrent-operation rules? |
| State and recovery | Storage, retention, resumability, idempotency, and cancellation guarantees? |
| Delivery | Sponsor, owner, timeline, support burden, and measurable benefit? |

The prerequisite for revisiting this proposal is a reviewed deterministic CLI
workflow and its resolved safety policies, not implementation of an agent now.

## References

Consulted during the September 28, 2026 discussion; sources are background evidence,
not approval to adopt their dependencies or examples.

* [Microsoft Agent Framework: AG-UI integration](https://learn.microsoft.com/en-us/agent-framework/integrations/ag-ui/)
* [Microsoft Agent Framework: human-in-the-loop with AG-UI](https://learn.microsoft.com/en-us/agent-framework/integrations/ag-ui/human-in-the-loop)
* [AG-UI: tools and human-in-the-loop workflows](https://docs.ag-ui.com/concepts/tools)
* [Current CLI and pipeline specification](archivist-image-workflows.md)
