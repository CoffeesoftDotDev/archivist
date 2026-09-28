---
prd_id: PRD-001
title: Image inventory and dynamic file workflows
description: Draft product specification for image listing, ZIP-aware previews, and human-approved move or source-preserving copy workflows
status: draft
version: 0.5.0
owners: []
reviewers: []
created_date: 2026-09-28
last_updated: 2026-09-28
product_goal_ids: [GOAL-001, GOAL-002, GOAL-003]
product_goal_smart_status: deferred
fr_to_ac_coverage_threshold_pct: 100.0
fr_to_goal_coverage_threshold_pct: 100.0
diagram_format: none
source_brd_id: BRD-2026-Q3-001
lineage:
  supersedes: []
  superseded_by: []
requirement_id_prefixes:
  fr: FR
  ac: AC
  nfr: NFR
  con: CON
  goal: GOAL
---

> **PRD-001 | Draft | Implemented in the working tree.** The user authorized
> implementation on September 28, 2026 and settled the material workflow policies.
> This document records that implementation, not a release or formal PRD approval.

Business authority: [BRD-2026-Q3-001, approved version 1.0.0](image-collection-consolidation-brd.md).
The user approved the business scope with an explicit measurement waiver.
This PRD remains draft. Implementation authorization does not approve proposed
performance targets, business measurements or release readiness.

## Executive Summary

Extend Archivist with image inventory and relocation capabilities that compose
with ZIP extraction in its existing pipeline. Users should be able to inspect a
folder tree, discover matching pictures inside ZIPs, review a report, and approve
extraction and relocation without manually unpacking each archive first.

The defining move sequence is **list pictures, obtain human confirmation, extract
ZIPs, then move pictures**. A move request supplies those prerequisites even when
the caller does not explicitly select listing or extraction. Dry-run stops at the
inventory/report boundary and performs no extraction or movement.
Adding `--copy` to `--move-pictures` changes the final action to duplication:
source pictures and ZIPs remain unchanged, including during prerequisite extraction.
The subsequent user request also requires unchanged EXIF/date-taken data and
preservation of original available filesystem creation/modification dates.

The immediate scope is a deterministic CLI and dynamic workflow builder. The
conversational agent and AG-UI proposal is deferred to [future-spec.md](future-spec.md).
No model, agent framework, web interface, or hosted service is needed for this scope.
Release date, delivery ownership and representative performance targets remain open.

## Product Context

### Problem and current baseline

Pictures can be scattered across folders and ZIP archives. The requested outcome
is one inspectable, filterable inventory followed by an explicitly approved
extraction-and-move operation.

At source revision `42666b2`, Archivist has a sequence-based workflow builder,
recursive ZIP extraction, configurable metadata cleanup, and console/file reports.
It does not have the proposed image actions, extension filter, or destination option.
That baseline workflow always includes ZIP extraction; cleanup is enabled unless
disabled by `--leave-*` flags. The implementation preserves it when no explicit
action flags are selected, and adds image-specific inventory/approval/extraction/
transfer steps using the existing builder and integer-counter Step contract.

Current runs preview by default, with `--apply` enabling mutations. The legacy
`--dry-run` flag overrides `ARCHIVIST_APPLY=true`. Successful extraction deletes
the original ZIP unless `--leave-zip` is set. Existing-folder conflicts can prompt
for merging during interactive application. These are compatibility constraints
preserved by the new action selection. New image moves have the separately
approved delayed-disposal policy below.

### Evidence and precedence

| Source | Product evidence |
|--------|------------------|
| Conversation: initial request | Name/type/full-path listing, `pictures.log`, absolute or relative destinations, move dry-run equivalence, aggregate confirmation, and extension filtering |
| Conversation: ZIP clarification | Inspect ZIP contents and report the number of images inside archives |
| Conversation: dynamic workflow clarification | Combine `--list-images`, `--extract-zip`, `--dry-run`, and `--filter` in one pipeline |
| Conversation: final move-order clarification | List, confirm, extract, then move; extraction is an implicit move prerequisite |
| Conversation: specification request | Document the CLI scope now and keep the agent/AG-UI route in a separate future specification |
| [Current usage](../usage.md), [configuration](../configuration.md), and [contributor guide](../contributing.md) | Existing command behavior and implementation conventions |

The dynamic-workflow clarification supersedes the earlier interpretation of a
separate, mutually exclusive image command. Unanswered questions and assistant
recommendations are not treated as user-approved decisions. The subsequently
approved business scope is recorded in BRD-2026-Q3-001; no feasibility handoff
was supplied.

## Users and Personas

| User | Job to be done | Success outcome |
|------|----------------|-----------------|
| Archivist operator managing a local or mounted folder tree | Find and collect pictures across ordinary folders and archives | Review one inventory and approve the intended file operations |
| Existing CLI user | Continue using extraction and cleanup | Understand any new mode rules without accidentally enabling unrelated actions |

The first role comes from the request; the second is a compatibility stakeholder
inferred from the existing product. No broader user research or adoption estimates
are claimed.

## Design Decisions

**Confirmed** means explicitly selected by the user. **Implemented** denotes
engineering policy consistent with the approved intent. **Open** means unresolved.

| ID | Status | Decision |
|----|--------|----------|
| DD-001 | Confirmed | Actions compose in the existing pipeline rather than selecting isolated image and ZIP modes |
| DD-002 | Confirmed | A move requires listing, human confirmation, ZIP extraction, and movement in that order |
| DD-003 | Confirmed | Listing and move dry-run have the same inventory/report behavior; archives are inspected without extracting images |
| DD-004 | Confirmed | The inventory is `pictures.log` at the parent-folder root and its location is returned to the user |
| DD-005 | Confirmed | Agent/AG-UI work is deferred and must not become a dependency of the CLI scope |
| DD-006 | Implemented | Canonical `--list-images` and `--move-images` also accept `--list-pictures` and `--move-pictures` |
| DD-007 | Implemented | Preserve no-action legacy behavior; explicit actions include only selected stages and prerequisites, never implicit metadata cleanup |
| DD-008 | Implemented | Retain `--apply` plus human confirmation and global dry-run precedence |
| DD-009 | Confirmed | Filters select pictures, while applicable ZIPs are extracted completely; nonselected contents remain in sibling extraction folders for moves |
| DD-010 | Confirmed | Number collisions oldest-first using original creation time, explicitly reported original-mtime fallback, and full-source-location ties |
| DD-011 | Confirmed | `--move-pictures --copy` duplicates selected pictures without altering their originals; preserve ZIP sources and apply the same oldest-first collision naming |
| DD-012 | Confirmed | Flatten destination layout |
| DD-013 | Confirmed | Delete original physical ZIPs only after complete extraction and successful transfer; copy and `--leave-zip` retain them |
| DD-014 | Confirmed | Recursively inspect nested ZIPs with bounded resources and visible errors |
| DD-015 | Confirmed | Stop on failure, retain not-yet-removed ZIPs, and report partial outcomes without promising rollback |
| DD-016 | Confirmed | Append clearly separated runs to an existing `pictures.log` |
| DD-017 | Confirmed | Number every colliding incoming file from `(001)`, even if the unsuffixed name is free |
| DD-018 | Confirmed | List-plus-applied-extraction without transfer follows list, approval, extraction |
| DD-019 | Implemented | Resolve relative destinations against process cwd; require a destination only when applying transfers |
| DD-020 | Implemented | Reject overlapping roots, unsafe paths, source-mutating copy modifiers and existing extraction targets; never overwrite destination pictures |

### Implemented command surface

These commands are implemented in the working tree. `JPG,PNG,ARW` is a concrete
filter example; the conversational `etc.` is not an extension or wildcard.

```powershell
# Inventory files and matching ZIP entries; return the pictures.log location.
archivist --list-images --parent-folder "C:\Photos" --filter JPG,Png,ARW

# Compose actions while previewing only; do not extract.
archivist --list-images --extract-zip --parent-folder "C:\Photos" --dry-run --filter JPG,Png,ARW

# Same inventory/report behavior as listing; do not prompt or create the destination.
archivist --move-pictures --parent-folder "C:\Photos" --destination "D:\Collected" --dry-run --filter JPG,Png,ARW

# Apply: inventory -> human approval -> extract -> move.
archivist --move-pictures --parent-folder "C:\Photos" --destination "D:\Collected" --apply --filter JPG,Png,ARW

# Apply: inventory -> human approval -> safe extraction -> copy.
archivist --move-pictures --copy --parent-folder "C:\Photos" --destination "D:\Collected" --apply --filter JPG,Png,ARW

# Copy preview: inventory only, with no copies, extraction, or destination creation.
archivist --move-pictures --copy --parent-folder "C:\Photos" --destination "D:\Collected" --dry-run --filter JPG,Png,ARW
```

Relative destinations resolve against the current working directory. A destination
is required for an applied transfer, but optional for inventory-only preview.

## Product Goals

These are proposed acceptance targets for the first image-workflow release, not
measured business improvements or a delivery commitment.

| Goal | Priority | Target and measurement |
|------|----------|------------------------|
| GOAL-001 | MUST | On the agreed readable test corpus, inventory 100% of supported matching on-disk files and archive entries, with exact per-archive counts |
| GOAL-002 | MUST | Across dry-run and declined-confirmation scenarios, make zero source/destination content changes other than the requested report |
| GOAL-003 | MUST | Every supported transfer follows list -> confirmation -> extraction -> movement or source-preserving copying, including omitted prerequisite flags and permuted flag order |

SMART assessment is deferred: the outcomes and acceptance measurements are
specific, but corpus limits, resources, ownership, and a release date are unresolved.

## Functional Requirements

All actors below are the Archivist operator. Priorities follow MUST/SHOULD/COULD/
WON'T terminology. Acceptance and goal links are in the traceability matrix.

| ID | Priority / basis | Trigger and expected outcome |
|----|------------------|------------------------------|
| FR-001 | MUST / Confirmed | When multiple actions are selected, execute a dependency-ordered workflow containing those actions and their prerequisites once, regardless of argument order |
| FR-002 | MUST / Confirmed | When listing pictures, recursively identify matching files beneath the selected parent folder |
| FR-003 | MUST / Confirmed | When listing pictures, also inspect ZIPs found beneath the parent folder and report matching image-entry counts for each archive and in total |
| FR-004 | MUST / Confirmed | When listing completes, write each matching image's name, type, and full source location to `pictures.log` at the parent-folder root and print the absolute report path |
| FR-005 | MUST / Implemented clarification | When `--filter` supplies comma-separated extensions, select image extensions case-insensitively, normalize whitespace/leading dots/duplicates, and reject empty or unsupported tokens; the supported catalog is in Usage |
| FR-006 | MUST / Confirmed | When moving pictures is requested, include listing, confirmation, and ZIP extraction before transfer even if those actions were not explicitly requested; `--copy` substitutes copying for the final move |
| FR-007 | MUST / Confirmed | Before ZIP extraction or transfer, present the matching file count, affected extensions, source-folder impact, destination, and move/copy mode, then wait for explicit human approval |
| FR-008 | MUST / Confirmed | After approval, extract applicable ZIPs discovered beneath the parent tree before picture transfer; copy mode must stage extraction without changing the source tree or original ZIPs |
| FR-009 | MUST / Confirmed | Without `--copy`, relocate selected pictures to the specified absolute or relative destination; this is relocation, not image-format conversion |
| FR-010 | MUST / Confirmed | When dry-run is active, inspect and report without extracting, moving, copying pictures, deleting, overwriting source files, or creating destination folders; only the inventory/report write is permitted |
| FR-011 | MUST / Confirmed | For the same root, filter, and unchanged inputs, listing, move dry-run, and copy dry-run produce the same inventory entries, counts, report location, and no approval prompt |
| FR-012 | MUST / Approved business scope | When discovery or execution is incomplete, report failed/skipped items and distinguish planned, completed, and remaining operations rather than declaring all selected pictures moved |
| FR-013 | MUST / Confirmed | When destination filenames collide, append numbered suffixes before the extension, such as `photo (001).jpg`, assigning lower available numbers to older-created incoming files before newer-created files without replacing existing destination files |
| FR-014 | MUST / Confirmed | When `--copy` accompanies `--move-pictures`, duplicate the approved pictures at the destination while retaining original source images and ZIPs unchanged throughout the workflow |
| FR-015 | MUST / Confirmed follow-up | When image extraction or transfer succeeds, preserve original picture bytes/EXIF and available original creation/modification dates; if a known filesystem date cannot be restored exactly, report failure before removing the affected source or original ZIP |

### Copy mode

`--copy` is a modifier of the picture-transfer action, not a separate stage
appended after movement and not a command to copy the ZIP itself. It replaces
the final move with a copy. It retains filter selection, archive inventory,
human approval, and collision-numbering rules. Both image aliases select the same
copy behavior.

| Effect | Move without `--copy` | With `--copy` |
|--------|----------------------|---------------|
| Selected ordinary pictures | Relocated | Duplicated; original paths and contents retained |
| Selected archived pictures | Extracted before moving | Extracted outside the source tree, then duplicated to the destination |
| Original ZIPs | Deleted only after complete extraction and successful transfer, unless `--leave-zip` | Always retained byte-for-byte; no deletion or rewrite |
| Collision names | Oldest-first available numbered suffix | Same policy, applied only to destination copies |
| Human approval | Before extraction or movement | Before extraction or copying; label mode as COPY |
| Dry-run | Inventory/report only | Same inventory/report only |

The existing extractor deletes ZIPs by default and extracts beside the source
archive. Those behaviors cannot be reused unchanged for copy mode. Extraction
output and temporary staging must be outside the source tree, with no metadata
cleanup of the source. The destination must be disjoint from the source tree;
reject an overlapping source/destination before any mutation. This prevents a
copy from overwriting a source, introducing files into the source tree, or
recursively discovering its own output.

"Source unchanged" means no application-initiated changes to source file paths,
bytes, or metadata; filesystem-managed read-access bookkeeping is excluded.
The previously requested `pictures.log` remains the explicit local-report write
exception. If the chosen report path is an existing source image or archive,
reject it rather than overwrite source data.

Copy mode must preserve sources even if `--extract-zip` is explicitly selected:
use the same source-preserving prerequisite once, not a separate destructive
extraction stage. Reject requested combinations that would mutate sources,
including explicitly selected source cleanup, rather than silently overriding
the promise. Report successful transfers as **copied**, not **moved**.
`--copy` without a picture-transfer action is an argument error.
`ARCHIVIST_COPY` maps to the same modifier; it does not grant approval.

### Original picture metadata and dates

The user's September 28 follow-up explicitly requests initial EXIF, picture-taken
dates and original file creation/modification dates. Embedded metadata remains
byte-identical; no EXIF parsing/re-encoding or substitution of date categories is
required. Capture original filesystem dates during inventory, before reading
picture payloads; retain integer precision through extraction and final transfer.

Read ZIP local and central NTFS/extended Unix timestamp extras, preferring NTFS
precision, then extended Unix, then DOS modification time interpreted in the local
timezone. If creation was not recorded or exposed by the source OS, report it as
unavailable; the output's OS-assigned creation time is not presented as original.
Do not infer creation from EXIF, modification or staging-file metadata.

Restore and verify original modification and known creation dates before source
removal. Native creation restoration exists for Windows and macOS; unsupported
platforms/volumes or timestamp rounding produce explicit failure, retaining the
affected source and not-yet-removed ZIPs. Earlier successful transfers are not
rolled back. Access-time bookkeeping and POSIX metadata-change `ctime` are excluded
from the exact-date guarantee. The legacy extraction-only workflow is unchanged.

### Filename collision handling

The user selected **oldest to newest** creation-date order for collisions; this
applies to both moves and copies. Existing destination
files are not renamed or overwritten to make room for incoming pictures.
Noncolliding files retain their names. Within a collision group, lower available
numbers go to earlier-created incoming files. Already occupied numbered names
must not be reused; numbers use at least three digits and do not wrap after 999.
These numbering safeguards elaborate the requested `(001, 002, etc.)` behavior.

For example, if `photo.jpg` already exists and two incoming `photo.jpg` files were
created in 2020 and 2023, respectively, the older becomes `photo (001).jpg` and the
newer `photo (002).jpg` when those names are free. If `(001)` is already occupied,
it is preserved and numbering uses the next available names.

Creation time means original source metadata, not the time a copy or extracted
file is newly written. Standard ZIP timestamps generally describe modification
time, not creation time, and creation metadata is not portable across filesystems.
Use original modification time only as an explicitly reported fallback; never
substitute POSIX metadata-change time, image capture time or extraction time.
Full source location breaks ties. Every incoming duplicate receives a suffix,
including when the unsuffixed name is unused. Source-to-final-name mapping is reviewable
before movement and recorded in execution results without changing the standalone
listing versus move-dry-run inventory contract.

### Inventory and filter semantics

Implemented report interpretation:

* A filesystem image has its original filename, normalized extension as its type,
  and absolute filesystem path. Extension matching is not image-content validation.
* An archive image has its filename, type, and an archive-qualified location such
  as `C:\Photos\holiday.zip :: day-1\IMG_001.JPG`. It must not be represented as an
  already-existing extracted file.
* Counts distinguish on-disk images from archive entries, including nested ZIPs.
  Each archive's count covers its direct selected entries; aggregate ZIP totals
  include nested matches. Source-folder impact counts physical parent directories.
* A single extraction result is not counted twice as both an archive image and a
  new file in the same projected inventory. A file already on disk and a separate
  archived copy are separate occurrences; content deduplication is not requested.
* Filter normalization removes whitespace, optional leading dots and repeated
  extensions after case normalization. Empty or unsupported entries are errors.

The report appends separated runs with JSON inventory rows and text counts/outcomes.
Image workflows use `pictures.log`, not a second `report.log`, and honor
`--log-file`/`--no-log-file`. FR-011 requires identical inventory semantics.
If projected extraction or destination paths are included, standalone listing
must retain the same inventory contract rather than claim those files exist.

## Non-Functional Requirements

The following quality requirements are **proposed engineering safeguards**, not
additional user-approved feature decisions.

### Performance and Capacity

**NFR-001:** Listing ordinary ZIP entries shall not decompress image payloads or
write extracted image files. Nested-archive inspection, if selected, shall have
explicit depth and decompressed-byte limits. Implemented limits are ten archive
levels including the outer ZIP, 100,000 aggregate entries, 64 MiB per nested ZIP
and 256 MiB aggregate nested payload reads. Latency targets remain open in Q-015;
no throughput claim is made.

### Reliability and Resilience

**NFR-002:** For a failed transfer, the original source shall remain available
unless a complete destination copy has been established in move mode; copy mode
retains it even after successful transfer. Rejection, cancellation,
and extraction failures shall never be reported as successful moves. Partial
application is possible; automatic rollback is not promised (Q-012).

### Security

**NFR-003:** A workflow shall not write outside its approved source/extraction/
destination/report scope through ZIP member paths, symlinks, or Windows junctions.
Collision and archive-deletion effects shall be disclosed before approval. Link
policy rejects links/junctions and existing extraction targets; no implicit merge
or additional overwrite approval is supported.

### Privacy

**NFR-004:** Inventory and file operations shall require zero network calls or
uploads. Full paths are intentionally present in the local operator-requested
report; image contents, credentials, and personal paths shall not be exported as
service telemetry. Sharing and retaining the report remain the operator's concern.

### Scalability and Elasticity

No server, autoscaling, concurrency, or multi-user capacity target is in scope.
Representative folder sizes and large/nested ZIP budgets must be agreed under
Q-015 before performance acceptance.

### Maintainability and Operability

**NFR-005:** CLI-selected and automatically required actions shall use one shared
set of workflow rules. Each required stage appears once; the agent proposal shall
not add a second execution engine or a dependency to this release.

### Observability

**NFR-006:** The local report and console shall distinguish previews, approval
outcomes, extraction outcomes, moved files, and failures. Report location and
unreadable archives must remain visible. These are local user-facing reports,
not a new telemetry service; no custom metric or span names, exporter, or SLO
is specified.

### Usability and Accessibility

**NFR-007:** Confirmation shall name the root, destination, selected extensions,
image counts, affected source folders, and archive effects in text, without
requiring color to understand approval. Empty input, EOF, or no terminal shall
not implicitly authorize a move (Q-013).

### Compatibility and Interoperability

**NFR-008:** Existing extraction/cleanup invocations and CLI-over-environment
precedence shall retain their documented behavior unless a reviewed migration
explicitly changes it. Default action selection, log overrides and error exit
codes follow the resolution register below.

### Portability

**NFR-009:** The feature shall remain usable through the existing Python CLI on
Windows, macOS, and Linux without an agent service. Absolute and relative path
cases, mixed-case extensions, and cross-volume movement require platform-specific
acceptance. Raising the current Python 3.10 minimum is not proposed.

## Constraints

| ID | Source / category | Boundary and impact |
|----|-------------------|---------------------|
| CON-001 | User / technical scope | Extend Archivist's existing multi-step pipeline; do not create a competing standalone image utility |
| CON-002 | User / operational | List and obtain human approval before extraction and movement in every move workflow |
| CON-003 | User / scope | Agent Framework, AG-UI, model integration, and chat UI are future considerations only |
| CON-004 | User / delivery | The subsequent explicit implementation request authorizes source, tests and related docs, not operations on actual user collections, releases or remote tracker writes |

These boundaries can change only through an explicit product-scope revision.

## Process Models

### Move workflow

1. Validate inputs and resolve the proposed root, destination, and filter.
2. List on-disk and archived pictures; write the inventory and display its location.
3. If dry-run applies, stop here without requesting mutation approval.
4. Otherwise display the proposed effects and wait for human confirmation.
5. If approved, perform the required ZIP extraction stage, using source-preserving
   extraction outside the source tree for copy mode.
6. Reconcile available files with the approved selection, then move the selected
   pictures or duplicate them when `--copy` is selected.
7. Report actual outcomes, including incomplete extraction and movement.

Steps 2 -> 4 -> 5 -> 6 are the confirmed ordering. Validation, reconciliation,
and failure policies are implemented safeguards. The workflow builder must not
interpret the order of command-line flags as permission to reorder prerequisites.

Declining confirmation stops before any extraction or movement; the previously
requested inventory log remains. If extraction finds additional candidates or
changes the plan, they must not be silently added to the approved move scope.
Nested inspection limits and incomplete-inventory errors prevent approval from
claiming an unverified complete total.

### Listing and other combinations

Standalone listing and move dry-run use the same inventory behavior. Selecting
listing plus extraction in a dry-run still does not extract. For real
listing-plus-extraction without movement, the user explicitly selected listing,
approval, then extraction, preserving inventory provenance before ZIP disposal.

Cleanup inclusion is intentionally not inferred from `--extract-zip` or a move
request. Without explicit action flags, legacy extraction and cleanup remain.

## Acceptance Criteria

The criteria are implemented and covered by focused filesystem/CLI fixtures in
`tests/test_image_inventory.py` and `tests/test_image_workflow.py`, alongside the
existing suite. Local Windows execution is evidence for the implementation,
not formal product approval or cross-platform release acceptance. Link scenarios
requiring unavailable host symlink privileges are explicitly skipped; CI owns
the remaining platform coverage.

| ID | Given / When / Then |
|----|---------------------|
| AC-001 | Given a move request with listing and extraction also selected, when the workflow is prepared with any argument order, then each prerequisite appears once and listing precedes confirmation, extraction, and movement |
| AC-002 | Given a root containing `a.JPG`, a subfolder containing `b.png`, and a text file, when listing with `JPG,Png`, then exactly the two images appear with name, type, and absolute source location |
| AC-003 | Given a ZIP in a subfolder containing `c.JPEG`, `day-1\d.ARW`, a directory entry, and a text file, when listing with `Jpeg,ARW`, then the archive count is two, both image locations identify their archive membership, and nothing is extracted |
| AC-004 | Given a writable report location and matching files, when listing completes, then `pictures.log` exists at the parent-folder root and the console prints its absolute path; given no matches, the report records zero images |
| AC-005 | Given JPG, JPEG, PNG, ARW, and TXT files, when filtering with `JPG,Png,Jpeg,ARW`, then all four image types are selected and TXT is not; extension case does not alter selection |
| AC-006 | Given a move request without explicit listing or extraction flags, when prepared, then the workflow includes listing, human confirmation, extraction, and movement in that order |
| AC-007 | Given a prepared move inventory, when approval is requested, then file count, extension breakdown, and affected source-folder count are displayed before extraction or movement; declining changes neither source nor destination contents |
| AC-008 | Given a root with an ordinary picture and a ZIP in a subfolder containing another selected picture, when the complete plan is approved and extraction succeeds, then no picture movement starts until extraction finishes and both selected pictures reach the destination |
| AC-009 | Given valid absolute and relative destinations under the approved resolution policy, when relocation succeeds, then each selected file has the same contents at its destination and is no longer at its original on-disk location |
| AC-010 | Given a parent tree and a destination that does not exist, when moving with `--dry-run`, then no extraction, mutation prompt, destination creation, movement, or deletion occurs; only the permitted report is written |
| AC-011 | Given unchanged input files, the same root and filter, and the same report policy, when standalone listing and move dry-run are run, then their normalized inventory rows, counts, and report locations match |
| AC-012 | Given a malformed ZIP or a failed move, when reporting the run, then the failure is visible and neither an unknown archive count nor a failed move is represented as a successful zero-count/completed result |
| AC-013 | Given `ARCHIVIST_APPLY=true`, when `--dry-run` is explicitly supplied, then no source/destination mutation occurs; approval alone cannot override dry-run |
| AC-014 | Given a move after a successful extraction has added files, when the move selection is reconciled, then only files covered by the approved plan are moved; unexpected additions require a revised decision |
| AC-015 | Given an existing `photo.jpg` and two incoming pictures with that name and distinct known original creation times, when moving after approval with 001 and 002 free, then the older incoming picture becomes `photo (001).jpg`, the newer becomes `photo (002).jpg`, and the existing file remains unchanged |
| AC-016 | Given `photo.jpg` and `photo (001).jpg` already exist, when two incoming `photo.jpg` files are moved in oldest-to-newest order with 002 and 003 free, then they receive `(002)` and `(003)` respectively and both existing files remain unchanged |
| AC-017 | Given ordinary pictures and a disjoint destination, when `--move-pictures --copy` is approved and succeeds, then byte-identical destination copies exist, original pictures remain at their source paths, and outcomes say copied rather than moved |
| AC-018 | Given pictures inside source ZIPs, when copy mode with or without explicit `--extract-zip` succeeds, then the destination contains the selected pictures, every source ZIP remains byte-identical, and the source tree has no new extraction folders or cleanup changes except the requested report |
| AC-019 | Given copy mode, when `--dry-run` is present or approval is absent or declined, then no extraction, picture copies, or destination directories are created; copy dry-run inventory matches standalone listing |
| AC-020 | Given destination-name collisions with known distinct original creation times, when copying after approval, then available numbered names are assigned oldest first exactly as for movement while source pictures remain unchanged |
| AC-021 | Given copy mode and an overlapping source/destination, a source-mutating action combination, or a report path targeting a source image/ZIP, when inputs are validated, then the run reports the conflict before any filesystem mutation |
| AC-022 | Given an ordinary EXIF-bearing image with distinct taken, creation and modification dates, when an approved move/copy succeeds, then the destination bytes and EXIF dates are unchanged and supported original filesystem dates match exactly |
| AC-023 | Given a picture inside a nested ZIP with original timestamps in NTFS or local extended Unix metadata, when extraction/transfer succeeds, then metadata survives temporary extraction and publication without substituting staging dates; missing creation remains explicitly unavailable |
| AC-024 | Given a known creation/modification date that the destination cannot represent or restore, when applying an image workflow, then it fails visibly before removing the affected source or original ZIP and does not report the affected transfer complete |

Counts and naming fixtures follow the settled policies in Q-005 through Q-016.

## Traceability Matrix

| Requirement | Acceptance criteria | Product goals |
|-------------|---------------------|---------------|
| FR-001 | AC-001 | GOAL-003 |
| FR-002 | AC-002 | GOAL-001 |
| FR-003 | AC-003 | GOAL-001 |
| FR-004 | AC-004 | GOAL-001 |
| FR-005 | AC-005 | GOAL-001 |
| FR-006 | AC-006 | GOAL-003 |
| FR-007 | AC-007, AC-014 | GOAL-002 |
| FR-008 | AC-008 | GOAL-003 |
| FR-009 | AC-009 | GOAL-003 |
| FR-010 | AC-010, AC-013 | GOAL-002 |
| FR-011 | AC-011 | GOAL-001, GOAL-002 |
| FR-012 | AC-012 | GOAL-002 |
| FR-013 | AC-015, AC-016 | GOAL-002, GOAL-003 |
| FR-014 | AC-017, AC-018, AC-019, AC-020, AC-021 | GOAL-002, GOAL-003 |
| FR-015 | AC-022, AC-023, AC-024 | GOAL-002, GOAL-003 |

FR-to-AC coverage: 15/15 (100%). FR-to-GOAL alignment: 15/15 (100%).
These measure authored links, not passing tests or product approval. No
feasibility-candidate disposition register applies because no handoff was supplied.

## MVP and Release Framing

The CLI release targets FR-001 through FR-014, with NFR-001 through
NFR-009 proposed for safety and operability review. It covers pictures, not a
general catalog of audio, video, or document categories. Image conversion,
content-based deduplication, rewriting ZIPs to remove individual members, and
automatic rollback are not requested.

Delivery should first establish composable actions and ZIP-aware inventory,
then add approved extraction-and-move execution. Listing can be reviewed without
claiming movement is ready. Agent/AG-UI exploration is deferred to the companion
future specification and must not delay or complicate CLI installation.

### Engineering impact, not implementation mandates

The existing builder and step interfaces are a useful starting point. They
currently pass a root path and return report counters; a dry-run extraction
creates no files for the next stage to discover. Simply appending a filesystem
listing after that step would miss archived pictures.

| Existing surface | Expected specification impact |
|------------------|-------------------------------|
| CLI parser and configuration | Composable action flags, filter/destination validation, mode and environment precedence, help text |
| Workflow builder and runner | Prerequisites, stage ordering, approval boundary, inventory/results shared across relevant stages |
| ZIP service | Read-only image-member inventory distinct from extraction; preserve archive provenance and skipped outcomes |
| Image services | Classification, report generation, selection, conflict handling, and relocation |
| Prompts and logging | Aggregate approval before extraction; `pictures.log` versus existing `report.log` |
| Documentation and existing acceptance coverage | Command examples, pinned help text, step-order contracts, cross-platform and dry-run behavior |

Reuse existing layering rather than introducing a generic workflow framework.
The precise data model and functions are engineering decisions, not product
requirements. Direct ZIP entry inspection can reuse Python's standard ZIP
metadata support; no new image-decoding dependency is assumed.

## Success Metrics

| Goal | Baseline | Proposed first-release target | Evidence window / source |
|------|----------|-------------------------------|--------------------------|
| GOAL-001 | No image inventory command | 100% exact matching occurrence counts on the agreed corpus | Release acceptance: ordinary files, archive entries, filter and zero-match fixtures |
| GOAL-002 | Default preview exists; no image move workflow | Zero unauthorized source/destination content changes | Every dry-run, declined, and pre-approval fixture; compare file contents and directory entries excluding the report |
| GOAL-003 | Fixed extraction-first workflow | 100% supported move/copy combinations follow the approved stage order | Release acceptance: explicit/implicit prerequisites and argument permutations |

No adoption baseline, user time-savings estimate, throughput target, or remote
telemetry instrumentation is available. Product and engineering owners must
approve the corpus, targets, and measurement responsibility before release sign-off.

## Risks and Assumptions

### Key assumptions

| Assumption | Impact if false | Response |
|------------|-----------------|----------|
| Extension-based classification meets the need | Medium: mislabeled files will be included or missed | Document extension semantics and supported catalog; no content detection is claimed |
| Selecting an extraction stage extracts the whole archive | High: non-image files may also be created | Disclose complete extraction in the approval summary |
| The inventory captures everything a subsequent move may affect | High: nested archives, changes, or conflicts can invalidate approval | Bound inspection and reconcile against the approved selection |
| Existing CLI users expect current defaults | High: a new action model could change destructive behavior | Preserve and regression-test explicit-versus-legacy selection |

### Risk register

Likelihood has not been assessed; impact is an engineering assessment.

| Risk | Impact | Proposed mitigation |
|------|--------|---------------------|
| Default extractor deletes ZIPs after approval described only as a move | High | Explicit ZIP-retention decision and effects in the approval summary |
| Flattened destination produces duplicate filenames | High | Preflight numbered renaming by creation date; resolve metadata gaps and ties |
| Dry-run misses nested ZIP images or promises extraction that will be skipped | High | Report inspection limits and projected versus available files honestly |
| Cross-volume copy fails or the process is interrupted | High | Preserve sources until transfer completes; record partial outcomes |
| Files change after inventory or a linked path escapes the root | High | Validate approved scope again at execution; stop or request renewed approval |
| Archived copies and extracted outputs inflate counts | Medium | Separate occurrence inventory, provenance, and actual moved totals |

### Decision resolutions and remaining release question

Implementation resolutions below retain the original question identifiers.
Material policy choices were explicitly confirmed by the user; compatibility
and defensive engineering details are recorded as implemented decisions.
Q-015 retains release/performance work, not an unresolved CLI behavior choice.

| ID | Topic | Resolution or remaining work |
|----|-----------------|--------------------------|
| Q-001 | Image/picture aliases | Resolved: both vocabularies; shared `*_IMAGES` environment variables |
| Q-002 | Defaults and cleanup | Resolved: preserve no-action legacy behavior; explicit actions have no implicit cleanup |
| Q-003 | Apply and approval | Resolved: preview by default, `--apply` plus explicit human yes for image mutations |
| Q-004 | Catalog/filter/extraction | Resolved: catalog in Usage, extension-based matching, normalized validated filters; complete archive extraction |
| Q-005 | Source-folder counts | Resolved: distinct physical parent directories; archive-qualified locations and direct per-archive image counts |
| Q-006 | Layout and extraction conflicts | User confirmed flat destinations; existing extraction folders are rejected without merging |
| Q-007 | ZIP retention | User confirmed deletion only after full extraction and successful transfer; `--leave-zip` and copy retain originals |
| Q-008 | Destination resolution | Resolved: process cwd, apply-only requirement, no preview destination creation |
| Q-009 | Overlap, links and metadata | Resolved: disjoint roots, reject path links/junctions, skip filesystem links and known AppleDouble/`@eaDir` metadata; ordinary hidden pictures remain eligible |
| Q-010 | Nested ZIP limits | User confirmed bounded recursion; implemented limits in NFR-001 and Usage; unsafe/encrypted/unsupported members block application |
| Q-011 | Reports | User confirmed appended separated runs; JSON rows, logging overrides, no second report, mappings shown only for the applying approval plan |
| Q-012 | Failure behavior | User confirmed stop/retain/report partial work; nonzero image-workflow status, no rollback; legacy exit behavior unchanged |
| Q-013 | Approval input | Resolved: only yes/y; blank, EOF or no terminal declines; no auto-approval/timeout or merge prompt |
| Q-014 | List plus extraction | User confirmed list, ask for approval, then extract; standalone extraction preserves legacy behavior without cleanup |
| Q-015 | Release/performance evidence | Open: representative corpus, latency/throughput targets, delivery date, owners and approvers; implemented resource limits do not establish these claims |
| Q-016 | Timestamp and collision allocation | User confirmed reported original-mtime fallback, full-source-path ties and numbering every incoming collision |
| Q-017 | Copy modifier | Resolved: requires transfer action; `ARCHIVIST_COPY` supported, without approval bypass |

## Glossary

| Term | Meaning |
|------|---------|
| Picture / image | The same file category with interchangeable image/picture flag aliases |
| Image type | Normalized extension label, not verified MIME/content classification |
| Archive entry | A member inside a ZIP, not necessarily an existing filesystem file |
| Nested ZIP | A ZIP member inside another ZIP; different from a ZIP stored in an ordinary subfolder |
| Inventory | Observed matching occurrences with source locations and counts |
| Plan | Proposed effects and destinations awaiting approval, distinct from actual outcomes |
| Move | Relocate an on-disk file without converting it; not rewriting a ZIP to remove a member |
| Dry-run | Inspect/report only; the requested local log is the allowed write exception |

## Sign-Off

This product specification remains draft. The requesting user approved the
business baseline in BRD-2026-Q3-001 and its W-001 measurement waiver, then
authorized implementation and selected the material policies above. This is not
formal PRD or release approval. Acceptance owners, delivery estimate and the
representative performance corpus remain unassigned.

Implementation is present with local regression coverage. Formal PRD quality
review, cross-platform release acceptance and final approval remain separate
gates. No backlog upload or tracker mutation is requested.

## Disclaimer

This AI-assisted draft supports product and engineering review. It does not
constitute product approval, requirements sign-off, or engineering commitment.

## Document Metadata

* Source: Archivist product conversation, September 28, 2026.
* Baseline: repository revision `42666b2`; legacy behavior is preserved while explicit image workflows are added.
* Structure adapted from the Microsoft HVE-Core
  `requirements-author/templates/prd/prd-full.md` template, version 1.0.0,
  under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
* Future scope: [Conversational agent and AG-UI](future-spec.md).
