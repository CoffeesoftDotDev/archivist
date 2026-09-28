---
brd_id: BRD-2026-Q3-001
title: Controlled discovery and consolidation of distributed image collections
description: Business requirements for controlled image discovery, selection, approval, and consolidation in Archivist
status: approved
version: 1.0.0
owners: ["Requesting user (business scope approver)"]
reviewers: ["Requesting user", "BRD Quality Reviewer (AI-assisted quality assessment)"]
created_date: 2026-09-28
last_updated: 2026-09-28
business_goal_ids: [BG-001, BG-002, BG-003, BG-004]
business_goal_smart_status: deferred
fr_to_ac_coverage_threshold_pct: 100.0
diagram_format: ascii
lineage:
  supersedes: []
  superseded_by: []
  last_brd_id: null
requirement_id_prefixes:
  fr: FR
  ac: AC
  nfr: NFR
  con: CON
  br: BR
---

> **BRD-2026-Q3-001 | Approved with measurement waiver | Version 1.0.0**
> Business scope approved by the requesting user on September 28, 2026.
> Measurement gaps are explicitly waived until release approval under W-001.
> Approval is not evidence of implementation, quantified benefits, or release readiness.

## Executive Summary

Enable an Archivist operator to understand and consolidate a picture collection
distributed across folders and ZIP archives, while retaining control over
changes to the collection.

The approved business need is a unified inventory, format-based selection, a
preview of the proposed impact, explicit human authorization, and controlled
consolidation into a selected destination. The required operating sequence is
**list pictures -> human confirmation -> extract ZIPs -> move pictures**.
The operator must not have to remember prerequisite extraction as a separate task.
When the operator selects copy mode, the final action duplicates the pictures
instead of relocating them, and all original source pictures and ZIPs remain
unchanged. Prerequisite extraction must also respect that source-preservation rule.

The expected benefits are improved visibility, less manual consolidation effort,
controlled changes, and understandable outcomes. Reduced operator time is the
primary efficiency measure, but no baseline, numeric improvement target, delivery
date, or return on investment has been established. W-001 permits approval of
the business baseline without asserting those measurements are complete.

This BRD is the business authority for the
[draft product specification](archivist-image-workflows.md).
The [agent/AG-UI proposal](future-spec.md) remains deferred. This approval does not
approve every proposed CLI policy, authorize production file operations, or
replace subsequent product, engineering, and release decisions.

## Business Context

Archivist already extracts ZIPs and cleans metadata. At repository revision
`42666b2`, it lacks the proposed image inventory and relocation capabilities.
Its existing extraction workflow may delete a successfully extracted ZIP unless
configured to keep it; this is a material effect requiring an explicit policy
in the proposed consolidation workflow.

The requested collection may contain ordinary pictures, archives in subfolders,
and image formats such as JPG, JPEG, PNG, and ARW. Users need to see relevant
images without first changing the collection.

Manual effort and missed-image risk are plausible business drivers, not measured
facts. No customer population, commercial market, regulatory obligation, savings
estimate, or current manual procedure has been established. The approved baseline
therefore concerns the requesting operator's needs, not an enterprise-wide mandate.

### Evidence

| Source | Authority |
|--------|-----------|
| September 28, 2026 product conversation | Image inventory, archive visibility, format selection, report, preview, and destination requirements |
| Final workflow clarification | Listing and human confirmation precede extraction and movement; actions compose in Archivist |
| Business outline accepted by the user | Four business outcomes and the initial seven business-level functional requirements below |
| Subsequent collision instruction and ordering answer | Add numbered suffixes based on creation date; user selected "Oldest to newest (Recommended)" |
| Subsequent copy instruction | "`--copy` (while using the move-pictures command)" duplicates pictures and leaves the source untouched |
| User approval at `2026-09-28T17:02:33.230+02:00` | "I like that, add it as an approved BRD" |
| Subsequent explicit waiver decision | "Approve the BRD with that measurement waiver (Recommended)" |
| [Current usage](../usage.md) and [configuration](../configuration.md) | Existing behavior, not approval of proposed behavior |

The latest workflow clarification supersedes the earlier interpretation of an
isolated image command. The existing PRD records proposed details; this BRD does
not retroactively approve all of them. Identifiers are document-scoped: BRD
`FR-001` and PRD `FR-001` are not the same requirement.

## Stakeholders

The requesting user is the identified business decision authority through their
explicit approval. No legal name, organizational title, engineering role, or
ownership of particular files is inferred from that approval.

| Stakeholder | Evidence / responsibility | Power / interest | Engagement |
|-------------|---------------------------|------------------|------------|
| Requesting user, business scope approver | Accountable for this scope, W-001, and disposition or assignment of open business decisions | High / High | Approve revisions and release prerequisites |
| Collection operator | Primary beneficiary; responsible for selecting a collection and approving each actual run; not a separately named person yet | High for their run / High | Review inventory and proposed effects |
| File owner, if different from the operator | Conditional affected party; authority over actual data must be established before use | High / High | Obtain authorization before processing their files |
| Archivist maintainer / implementation reviewer | Role not assigned by this approval; responsible for feasibility and compatibility review when appointed | High / High | Review downstream implementation before release |
| BRD Quality Reviewer | AI-assisted advisory evidence, not a substitute business approver | Advisory / High | Assess requirement quality and traceability |

For this BRD's decisions, the requesting user is the single accountable approver.
The drafting assistant is responsible only for documenting that decision; it
cannot grant business waivers or authorize file mutations. Engineering and
acceptance owners must be assigned under OQ-006 before release approval.

## Design Decisions

| ID | Approved business decision | Boundary |
|----|----------------------------|----------|
| DD-001 | Document outcomes and observable obligations, not Python classes or command aliases | Implementation choices remain with the PRD and engineering |
| DD-002 | Combine discovery and consolidation within Archivist | Do not require an unrelated image utility |
| DD-003 | Enforce list -> confirmation -> extraction -> movement for a move | Required extraction is included before relocation |
| DD-004 | Retain the local inventory report as the preview's permitted write | Preview does not extract, move, delete, or overwrite collection files |
| DD-005 | Defer the agent/AG-UI route | No agent dependency in the current scope |
| DD-006 | Approve the qualitative business baseline with W-001 | Do not claim complete SMART goals, quantified benefits, or an approved release |
| DD-007 | Resolve filename collisions by numbered suffixes ordered by source creation date, oldest first | Missing/equal timestamps and archive date provenance remain downstream details; do not overwrite to resolve a move collision |
| DD-008 | Allow source-preserving duplication as an alternative final action in the same workflow | Copying retains the listing, approval, prerequisite extraction, filtering, and collision controls |

## Business Goals

The requesting user is accountable for obtaining measurements or assigning their
owner. All targets are acceptance intent, not observed results. SMART assessment
remains deferred under W-001; missing values are not replaced with invented data.

| ID | Approved outcome statement | Priority | KPI and measurement source | Baseline / target / timeframe |
|----|----------------------------|----------|----------------------------|-------------------------------|
| BG-001 | Improve collection visibility so the operator can identify relevant images, including those inside supported archives. | MUST | Matching occurrences identified versus a known reference collection, with inspection gaps disclosed; reference inventory and run report | Baseline unmeasured; corpus and coverage target to be agreed; before release approval under W-001 |
| BG-002 | Reduce manual consolidation effort so the operator needs fewer separate discovery, extraction, and relocation actions. | MUST | Operator minutes and manual interventions per representative collection; before/after task observations | Baseline and numeric improvement target unmeasured; benefit window and release date to be agreed under W-001 |
| BG-003 | Maintain control over file changes so the operator understands and approves the scope before extraction, relocation, or copying begins. | MUST | Number of pre-approval or rejected-run extraction/transfer actions; observed action sequence and resulting file state | New workflow has no measured baseline; zero unauthorized actions is the required control for every run; release date not set |
| BG-004 | Make outcomes understandable so the operator can distinguish completed work from failures and remaining work. | MUST | Selected inventory entries reconciled to reported outcomes; inventory and execution records | Baseline unmeasured; target is no falsely reported successful operation; timing/corpus to be agreed under W-001 |

Specific outcomes and measurement definitions exist. Numeric efficiency targets,
complete baseline evidence, feasibility of targets, and calendar commitments do
not. Business approval accepts these gaps only through W-001; it does not mark
the goals as SMART-passing.

No outcome-hypothesis handoff was supplied. There are no imported external goals
or claimed business-case measurements.

## Business Rules

All rules are mandatory operational rules, applying to the operator and collection
owner. They are not claims of a legal or regulatory obligation.
The approval and reporting controls cover both relocation and copy mode.

| ID | Rule | Rationale / goals | Enforcing requirements |
|----|------|-------------------|------------------------|
| BR-001 | Extraction, relocation, or copying in a consolidation run require explicit human approval of the presented operation. | Preserve operator control; BG-003 | FR-003, FR-004, FR-005, FR-010 |
| BR-002 | Preview permits the requested inventory report but no extraction, relocation, copying, deletion, or overwrite of collection files. | Enable inspection without applying changes; BG-003 | FR-006 |
| BR-003 | Reported completion must reflect actual outcomes; a failed or skipped operation must not be described as a successful move. | Make results reconcilable; BG-004 | FR-007 |
| BR-004 | A picture-move or copy filename collision is resolved by an available numbered name, not by replacing another file. | Preserve the collection; BG-003 | FR-008 |
| BR-005 | Copy mode must retain original source pictures and ZIPs unchanged throughout the workflow, including prerequisite extraction. | Permit duplication without relocation or source loss; BG-002, BG-003 | FR-010 |

Approval of this BRD is not approval of any actual run. Archive deletion and
overwrite policies remain unresolved in OQ-002; they cannot be inferred from
approval to consolidate pictures.

## Functional Requirements

All ten requirements are **MUST** for the approved business scope. The actor is
the collection operator, with file-owner interests protected through approval.
Expected behavior is independent of specific flag names.

| ID | Trigger and required outcome | Goal links | Acceptance |
|----|------------------------------|------------|------------|
| FR-001 | When the operator requests discovery within a selected collection, Archivist shall provide an inventory of relevant on-disk images and supported archive images with identifiable source locations. | BG-001 | AC-001 |
| FR-002 | When the operator specifies relevant image formats, Archivist shall restrict the selected images to those formats. | BG-001, BG-002 | AC-002 |
| FR-003 | Before seeking approval for consolidation, Archivist shall present the selected file count, affected formats, and source-folder impact. | BG-003 | AC-003 |
| FR-004 | Before starting extraction, relocation, or copying in a consolidation run, Archivist shall require explicit human authorization of the presented operation. | BG-003 | AC-004, AC-005, AC-013 |
| FR-005 | After authorization, Archivist shall consolidate selected images into the operator-selected destination, completing applicable prerequisite extraction before any picture movement begins. | BG-002, BG-003 | AC-006 |
| FR-006 | When the operator requests a preview, Archivist shall provide the inventory report without applying extraction, relocation, or copying. | BG-003 | AC-007, AC-013 |
| FR-007 | After execution, Archivist shall provide a record distinguishing completed, skipped, failed, and remaining work. | BG-004 | AC-009 |
| FR-008 | When selected pictures would collide by destination filename, Archivist shall add numbered suffixes such as `(001)` and `(002)`, assigning lower available numbers to older-created incoming pictures before newer-created ones, instead of overwriting another file. | BG-002, BG-003 | AC-010 |
| FR-009 | For unchanged inputs and the same format selection, Archivist shall produce equivalent inventories for standalone listing and move/copy previews. | BG-001, BG-003 | AC-008 |
| FR-010 | When the operator selects copy mode and approves the operation, Archivist shall duplicate the selected pictures at the destination while retaining original source pictures and ZIPs unchanged, including through prerequisite extraction. | BG-002, BG-003 | AC-011, AC-012 |

Supported archive depth, format catalog, destination-layout rules, and the precise
counting convention are resolved downstream, not assumed here. An unsupported
or unreadable scope must not be presented as fully inspected.

Collision examples in the PRD place the suffix before the extension, such as
`photo (001).jpg`. Numbering uses creation metadata from before the workflow,
not the new creation time of a file just extracted or copied. Original creation
metadata can be missing, particularly for ZIP members; the fallback must be
decided explicitly under OQ-008 rather than silently using another timestamp.

## Non-Functional Requirements

These express the approved outline's control and outcome obligations, rather than
new infrastructure or performance commitments. All four are MUST.

### Functional Suitability

**NFR-001:** No failed or skipped extraction, relocation, or copy operation may be reported
as successfully completed. Goal: BG-004. Stakeholders: operator and file owner.
Verify through AC-009 using both successful and failing operations.

### Performance Efficiency

No numeric throughput, memory, or latency requirement is approved. Representative
volume and target selection are deferred to OQ-001 and OQ-003, not claimed as
accepted engineering performance.

### Compatibility

Existing-user compatibility needs product and engineering review (OQ-005).
Approving this business scope does not approve breaking existing commands.

### Usability

**NFR-002:** Every consolidation approval request shall show file count, affected
formats, and source-folder impact before any extraction or relocation. Goal:
BG-003. Stakeholder: operator. Verify through AC-003; the same pre-operation
boundary applies before copying.
For copy mode, the same summary must explicitly identify copying rather than moving.

### Reliability

**NFR-004:** Copy mode shall perform zero application-initiated writes, renames,
or deletions to original source pictures and ZIPs; operating-system read-access
bookkeeping is outside this guarantee. Goals: BG-002, BG-003. Stakeholders:
operator and file owner. Verify original paths, contents, and application-controlled
metadata remain unchanged in AC-011 and AC-012. The requested inventory report
is the existing explicit write exception, not permission to modify an image.

The outcome record must expose partial application, but this BRD does not promise
automatic rollback or atomic multi-file movement. Failure continuation and
recovery policy remain OQ-004.

### Security

**NFR-003:** A consolidation run shall perform zero extraction, relocation, or copying
operations before human approval or after that approval is declined. Goal:
BG-003. Stakeholders: operator and file owner. Verify through AC-004, AC-005, and AC-013.

### Maintainability

No independent maintainability metric is approved. The existing Archivist
pipeline is the imposed integration boundary, not a prescription for a new
framework or class hierarchy.

### Portability

Target platforms and installation compatibility remain product/engineering
decisions. No new hosting environment or agent runtime is required.

## Constraints

| ID | Imposing source / category | Boundary | Goal / acceptance impact |
|----|----------------------------|----------|--------------------------|
| CON-001 | Requesting user / technical | Deliver discovery and consolidation within the existing Archivist solution. | BG-001, BG-002; review product scope and AC-006 |
| CON-002 | Requesting user / operational | Transfer follows listing, human confirmation, ZIP extraction, then movement or source-preserving duplication when copy mode is selected. | BG-003; AC-003 through AC-006, AC-011, AC-012 |
| CON-003 | Requesting user / scope | Exclude agent/AG-UI implementation from this initiative; retain it for future consideration. | BG-002; scope inspection against the future specification |

Only the business approver can change these boundaries. They do not specify
budget, staffing, schedule, or legal obligations that were never supplied.

## Process Models

### Current state

Archivist offers extraction and metadata cleanup, but not the requested integrated
image inventory and consolidation. The operator's present manual process has not
been observed; measuring it is an open task, not an assumed baseline.

### Approved future state

```text
Select collection and formats
              |
              v
List pictures on disk and in supported archives; retain inventory report
              |
              +-- Preview only ----------------------> Return report; stop
              |
              v
Present impact and request human approval
              |
              +-- Declined / no approval -------------> Stop; report remains
              |
              v
Extract applicable ZIPs
              |
              v
Move approved pictures, or copy them while preserving sources
              |
              v
Report actual outcomes and remaining work
```

Unexpected conflicts and incomplete extraction require the downstream failure
policy, not silent expansion of approved effects. Images in ZIPs must be visible
before approval without already performing the extraction being approved.
In copy mode, prerequisite extraction cannot delete original ZIPs or create
extraction output among the source files. Destination or isolated staging output
must stay outside the source tree; its placement is an engineering choice.
The chosen destination must not overlap the source tree in this mode, apart from
the explicitly requested inventory report.

## Acceptance Criteria

These are approved acceptance obligations, **not executed tests**. All are
**Not Started**. Archive support boundaries and unresolved date/failure policies must
be agreed before preparing final release fixtures.

| ID | Given / When / Then | Covers |
|----|---------------------|--------|
| AC-001 | Given a reference collection containing on-disk images and readable supported ZIP entries, when discovery runs, then the inventory identifies matching occurrences and their source locations, distinguishing archive entries from existing files. | FR-001 |
| AC-002 | Given images in selected and unselected formats, when format selection is applied, then only selected formats appear in the selected inventory. | FR-002 |
| AC-003 | Given a completed inventory, when consolidation approval is requested, then the displayed summary includes file count, affected formats, source-folder impact, and move/copy mode before extraction or transfer begins. | FR-003 |
| AC-004 | Given a consolidation request awaiting approval, when approval has not been granted, then no extraction, relocation, or copying occurs. | FR-004 |
| AC-005 | Given a presented consolidation plan, when the operator declines approval, then the workflow stops without extraction, relocation, or copying; the requested inventory report remains. | FR-004 |
| AC-006 | Given an approved selection containing ordinary images and images in supported ZIPs, when extraction and transfer succeed, then prerequisite extraction finishes before the first move and the selected images reach the chosen destination without format conversion. | FR-005 |
| AC-007 | Given a collection and a proposed destination, when preview runs, then only the requested report is written and no source/destination collection contents are extracted, relocated, copied, deleted, or overwritten. | FR-006 |
| AC-008 | Given unchanged inputs and the same selection, when standalone listing, move preview, and copy preview are compared, then matching inventory entries and counts agree. | FR-009 |
| AC-009 | Given an execution with successful, skipped, and failing items, when results are reported, then each outcome and remaining work are distinguishable and no unsuccessful action is labeled successful. | FR-007 |
| AC-010 | Given an existing `photo.jpg` and two incoming pictures with that name and distinct known source creation times, when moving after approval with suffixes 001 and 002 available, then the older incoming picture becomes `photo (001).jpg`, the newer becomes `photo (002).jpg`, and the existing file is unchanged. | FR-008 |
| AC-011 | Given selected on-disk pictures and a disjoint destination, when approved copy mode succeeds, then the destination contains byte-identical duplicates under the approved collision names and the original pictures retain their source paths and contents. | FR-010 |
| AC-012 | Given selected pictures in a source ZIP and a disjoint destination, when approved copy mode extracts and duplicates them, then original ZIP bytes and source-tree entries remain unchanged except for the requested report, with no extracted sibling folder created in the source tree. | FR-010 |
| AC-013 | Given a copy-mode request, when preview is active or human approval is absent or declined, then no extraction, destination creation, or picture copying occurs; only the requested inventory report may be written. | FR-004, FR-006 |

## Traceability Matrix

### FR-to-AC Coverage

| Requirement | Acceptance criteria |
|-------------|---------------------|
| FR-001 | AC-001 |
| FR-002 | AC-002 |
| FR-003 | AC-003 |
| FR-004 | AC-004, AC-005, AC-013 |
| FR-005 | AC-006 |
| FR-006 | AC-007, AC-013 |
| FR-007 | AC-009 |
| FR-008 | AC-010 |
| FR-009 | AC-008 |
| FR-010 | AC-011, AC-012 |

Coverage: 10/10 = **100.0%**, meeting the 100.0% threshold.

### FR-to-BG Alignment

| Requirement | Business goals |
|-------------|----------------|
| FR-001 | BG-001 |
| FR-002 | BG-001, BG-002 |
| FR-003 | BG-003 |
| FR-004 | BG-003 |
| FR-005 | BG-002, BG-003 |
| FR-006 | BG-003 |
| FR-007 | BG-004 |
| FR-008 | BG-002, BG-003 |
| FR-009 | BG-001, BG-003 |
| FR-010 | BG-002, BG-003 |

Alignment: 10/10 = **100.0%**. No traceability waiver is required.

### BR-to-FR Enforcement

| Business rule | Enforcing requirements |
|---------------|------------------------|
| BR-001 | FR-003, FR-004, FR-005, FR-010 |
| BR-002 | FR-006 |
| BR-003 | FR-007 |
| BR-004 | FR-008 |
| BR-005 | FR-010 |

### Downstream product mapping

| BRD requirement | Draft PRD requirements |
|-----------------|------------------------|
| FR-001 | PRD-001 FR-002, FR-003, FR-004 |
| FR-002 | PRD-001 FR-005 |
| FR-003 | PRD-001 FR-007 |
| FR-004 | PRD-001 FR-006, FR-007 |
| FR-005 | PRD-001 FR-008, FR-009 |
| FR-006 | PRD-001 FR-010 |
| FR-007 | PRD-001 FR-012 |
| FR-008 | PRD-001 FR-013 |
| FR-009 | PRD-001 FR-011 |
| FR-010 | PRD-001 FR-014 |

The downstream PRD remains draft. This mapping does not approve its unresolved
implementation details or candidate performance targets.

## Risks and Assumptions

### Key Assumptions

| ID | Assumption | Evidence status | Impact if false | Response |
|----|------------|-----------------|-----------------|----------|
| A-001 | A unified workflow reduces manual effort. | Untested business hypothesis | Medium | Observe representative tasks before setting benefit targets |
| A-002 | Format-based selection is sufficient for the intended collection. | Partially supported by requested extension examples | Medium | Resolve format definition and catalog in the PRD |
| A-003 | The operator is authorized to change the chosen files. | Not established for any real collection | High | Confirm actual data authority before execution |

### Risk Register

Probability is unassessed; impact below is a planning assessment, not measured risk.

| Risk | Probability | Impact | Mitigation / decision |
|------|-------------|--------|-----------------------|
| Original ZIPs deleted without informed approval | Unassessed | High | Resolve retention and disclose deletion effects before execution |
| Duplicate filenames cause unwanted replacement | Unassessed | High | Enforce numbered renaming; resolve missing/equal creation-date policy before execution |
| Archive coverage is incomplete or files change after preview | Unassessed | High | Disclose omissions and reconcile selection before mutation |
| Cross-volume movement fails or is interrupted | Unassessed | High | Define partial-outcome and recovery policy; do not promise rollback |
| Report overstates completed work | Unassessed | High | Enforce FR-007 and NFR-001 |
| Benefit claims lack evidence | Unassessed | Medium | Track W-001 and prohibit release approval until measurement gaps are resolved |

## Open Questions

All items are owned for disposition by the requesting user as business approver;
specialist execution may be assigned later. No calendar dates are invented.
Deferral permits business-scope approval, not automatic acceptance of a PRD answer.

| ID | Question or gap | Why it matters | Owner | Due gate | Status | Rationale for deferral | Target phase |
|----|-----------------|----------------|-------|----------|--------|------------------------|--------------|
| OQ-001 | Establish benefit baselines, numeric improvement targets, benefit window, and delivery dates. | Supports business-case and release decisions | Business approver | Before release approval | Deferred | Explicitly authorized measurement waiver W-001 | PRD |
| OQ-002 | Decide move-mode ZIP retention, archive-extraction conflict handling, and destination layout. | Defines permitted data changes | Business approver | Before implementation of mutative behavior | Deferred | Picture-transfer collisions use FR-008; copy mode always preserves sources; other policies remain unresolved | PRD |
| OQ-003 | Define supported image formats, archive depth, inspection limits, and source-folder counting. | Makes inventory and approval totals interpretable | Business approver | Before inventory acceptance | Deferred | Detailed supported scope belongs in the PRD | PRD |
| OQ-004 | Decide stop/continue behavior, cancellation, recovery, and partial-result exit status. | Prevents ambiguous partial execution | Business approver | Before execution acceptance | Deferred | Failure behavior needs product and engineering agreement | PRD |
| OQ-005 | Resolve action defaults, apply/preview flags, report overrides, relative paths, and noninteractive behavior. | Preserves compatibility and operator control | Business approver | Before CLI contract acceptance | Deferred | Implementation-facing choices remain in the draft PRD | PRD |
| OQ-006 | Assign engineering and acceptance owners; establish authority for actual collections. | Separates business approval from feasibility and data authorization | Business approver | Before release approval; data authority before each run | Deferred | This sign-off does not appoint other people or approve actual file operations | PRD |
| OQ-007 | Revisit agent/AG-UI scope, hosting, provider, and approval interface. | Avoids unapproved expansion | Business approver | Before any future-agent initiative | Deferred | User explicitly deferred this direction | Future-Release |
| OQ-008 | Decide creation-date provenance, fallback when missing, tie-breaking, and whether one incoming file retains an unused unsuffixed name. | Keeps collision numbering deterministic without inventing original dates | Business approver | Before collision handling acceptance | Deferred | Oldest-first numbering is approved; filesystem and archive metadata limitations require a product decision | PRD |

## Glossary

| Term | Meaning |
|------|---------|
| Collection | Operator-selected folder tree and its supported archive contents |
| Consolidation | Controlled relocation or source-preserving duplication of selected images into a chosen destination |
| Inventory | Record of matching occurrences and source locations before execution |
| Preview | Inspection/reporting without applying source/destination changes |
| Approval | Explicit permission for a defined operation, not blanket authority |
| Business baseline | Approved needs and constraints; not a claim that the software exists |
| Measurement waiver | Temporary permission to approve business scope without complete benefit measurements |

## Sign-Off

### Approval record

| Item | Record |
|------|--------|
| Business approver | Requesting user in this project conversation |
| Decision | APPROVED_WITH_COMMENTS: approve the presented business outline and its documented limitations |
| Approval date | September 28, 2026 |
| Approval evidence | "I like that, add it as an approved BRD" at `2026-09-28T17:02:33.230+02:00` |
| Scope | Business outcomes, initial seven functional requirements (preview equivalence now split for clarity), confirmed collision handling and copy mode, control rules, and current/future scope boundary |
| Additional approval evidence | User requested `(001, 002, etc.)` suffixes based on creation date and explicitly selected oldest-to-newest order; captured before `2026-09-28T17:09:24.4414012+02:00` |
| Copy-mode instruction | "Create the specs accordingly. I also want to have the ability to --copy (while using the move-pictures command) that will duplicate the pictures (and leave the source untouched)" |
| Exclusions | No technical feasibility certification, release approval, budget commitment, file-operation approval, or agent implementation |
| Other signatories | None asserted; implementation and acceptance roles require assignment under OQ-006 |
| Quality evidence | Define approved with comments on version 0.2.0; final Govern assessment linked below; neither substitutes for human approval |

### Waivers

#### W-001 - Business measurement completeness

* Granted by: requesting user, business scope approver.
* Granted on: September 28, 2026; decision captured before `2026-09-28T17:04:43.1316113+02:00`.
* Approval evidence: "Approve the BRD with that measurement waiver (Recommended)".
* Scope: missing benefit baselines, numeric improvement targets, and delivery
  dates, including the resulting incomplete SMART assessment for BG-001 through BG-004.
* Rationale: approve the qualitative business need now without fabricating
  measurements or committing to an unagreed schedule.
* Condition: resolve and obtain approval of the missing measurements before
  release approval. No release date is invented as a waiver expiry.
* Owner and follow-up: business approver; OQ-001, with measurement ownership
  assigned through OQ-006.
* Exclusions: no waiver of human run approval, safe preview, truthful reporting,
  FR-to-AC coverage, or FR-to-BG alignment. This waiver does not select unresolved
  data-loss, retention, or remaining collision-date policies.

### Quality finding dispositions

The Define assessment approved exit with comments after separating preview safety
(FR-006) from inventory equivalence (FR-009). Copy mode introduced no blocking
finding. The following cautions remain explicit downstream obligations, not
evidence of implementation readiness.

| Finding | Disposition | Follow-up |
|---------|-------------|-----------|
| rq-006 | Resolved by FR-006/FR-009 separation and corresponding traceability | Retain both behaviors in the PRD |
| rq-007 | Deferred feasibility assessment, including source-preserving archive extraction | OQ-006; assign engineering and acceptance owners before implementation/acceptance |
| rq-014 | Defer applicable missing quality categories to product refinement; do not invent targets | OQ-003 through OQ-006 |
| rq-015 | Accepted temporary SMART/measurement gaps under explicit W-001 | OQ-001; resolve before release approval |
| rq-024 | Defer remaining creation-date and collision policies without weakening preservation | OQ-008; resolve before collision acceptance |
| rq-026 | Carry source preservation into failed/interrupted extraction and copy acceptance fixtures | OQ-004; compare source paths, bytes, and application-controlled metadata before execution acceptance; no rollback promise |

### Handoff readiness

Business approval and W-001 are recorded for this 1.0.0 baseline. The governed
handoff records the final quality decision, exact artifact hash, sign-off, counts,
coverage, and deferred items. Publication requires a final quality report that
authorizes Govern exit. These evidence paths are local workflow records, not
published website links:

* `.copilot-tracking/brd-sessions/image-collection-consolidation.quality.yml`
* `.copilot-tracking/brd-sessions/image-collection-consolidation.findings.yml`
* `.copilot-tracking/brd-sessions/image-collection-consolidation.handoff.yml`

Identifier counts: 4 business goals, 10 functional requirements, 13 acceptance
criteria, 4 non-functional requirements, 3 constraints, and 5 business rules.
Both functional traceability measures are 100.0%. Authored coverage is not
evidence of implemented or passing behavior.

## Disclaimer

> [!CAUTION]
> **Disclaimer:** This agent is an assistive tool only. It does not provide business approval, regulatory compliance validation, or executive sign-off and does not replace business analysts, stakeholder representatives, compliance teams, or other qualified human reviewers. The output consists of suggested business requirements, objectives, and scope definitions to support a user's own business analysis and decision-making. All Business Requirements Documents, business objectives, stakeholder analysis, and requirement traceability generated by this tool must be independently reviewed and validated by appropriate business and compliance reviewers before adoption. Outputs from this tool do not constitute business approval, requirements sign-off, or stakeholder commitment.

The human approval recorded above is distinct from AI-generated content and
quality assessment. It is the source of this document's business approval.

## Document Metadata

* BRD identity: `BRD-2026-Q3-001`; new baseline, superseding no prior BRD.
* Source: September 28, 2026 Archivist conversation and explicit user decisions.
* Related product specification: [PRD-001](archivist-image-workflows.md), still draft.
* Deferred scope: [Future agent specification](future-spec.md).
* Structure adapted from Microsoft HVE-Core's
  `requirements-author/templates/brd/brd-full.md`, version 1.0.0,
  under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/).
