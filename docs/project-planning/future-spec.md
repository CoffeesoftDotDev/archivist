---
title: Future specification - conversational Archivist
description: Deferred exploration of an agent and AG-UI interface over the Archivist workflow
status: deferred
version: 0.1.0
created_date: 2026-09-28
last_updated: 2026-09-28
---

> **Deferred exploration, not an implementation commitment.** The user explicitly
> excluded the agent/AG-UI route from the current scope. This document preserves
> the discussion for later consideration without adding runtime dependencies.

## Relationship to the current specification

The active product-specification draft is
[Image inventory and dynamic file workflows](archivist-image-workflows.md).
Its CLI remains useful without an LLM, agent framework, server, or browser.
Nothing in this document is a prerequisite for delivering that CLI scope.

The user asked about chatting with an agent through AG-UI to decide which
operations to perform, with human approval for destructive or mutative actions.
Microsoft Agent Framework was an interpretation used during the discussion,
not a confirmed framework selection.

## Product opportunity

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
