<!-- PSM:GENERATED_ADAPTER
framework_version: 0.2.0-alpha
framework_source_commit: ee46f5bf6d8c6809621f7b4b9fcddee90037bc52
skill_id: psm-orient
canonical_path: skills/psm-orient/SKILL.md
canonical_sha256: a6424e848bf11fcfe5b7966da363fdc0777edf1202a23a8adb5603e41d44a01d
-->

# psm-orient — Cold-Start Orientation Skill

> Canonical PSM skill. Authoritative design: `docs/design/psm-v0.2.0-alpha-agent-skills-target-enablement-continuous-maintenance.md` (section 12).

## ID
`psm-orient`

## Name
psm-orient

## Purpose
Provide fast, *read-only* orientation to a coding agent that enters the repository or starts a session with no prior architectural context. The goal is to route the agent to the smallest sufficient subset of the System Map in **≤ 2 file reads**, then hand off to the appropriate next skill. This skill never absorbs architectural payload — it routes.

## Trigger / Invocation Context
- Cold entry into the repository by a coding agent.
- New session without prior architectural state.
- User asks for an overview of the project structure or where a given concern lives.

## Inputs & Preconditions
- Required: `docs/system-map/manifest.yaml`, `docs/system-map/README.md`.
- Optional: `.psm/host-profile.yaml` (for host-aware routing signals only).
- Precondition: The repository is readable. PSM status is **not** enforced here — orient responds to any reachable manifest and surfaces the lifecycle state it finds.

## Read Scope
- `docs/system-map/manifest.yaml`
- `docs/system-map/README.md`
- `.psm/host-profile.yaml` (optional)
- Domain / flow / boundary / invariants files **only when a single sharded file is referenced by the user's question**.

## Write Scope
**NONE — read-only.**

This skill must not modify any file under any path. It performs no writes: not to `docs/system-map/**`, not to `.psm/**`, not to source code, not to governance files.

## Forbidden Actions
- Reading the full source-code tree or any sharded domain map exhaustively.
- Dumping the entire content of any System Map file into the context.
- Modifying any file (code, map, governance, lock, profile, manifest).
- Issuing Git mutations, executing diffs, or proposing commits.
- Treating `MAP_NOT_FOUND`, `MAP_STATUS_DRAFT` or `PSM_NOT_ENABLED` as synonyms. They are distinct lifecycle diagnostics and must be reported with the canonical state naming.

## Failure States
- `PSM_NOT_ENABLED` — no `docs/system-map/manifest.yaml`.
- `MAP_NOT_FOUND` — manifest path resolves but the file is absent.
- `MAP_STATUS_DRAFT` — manifest declares `status: draft`.
- `MANIFEST_INVALID` — manifest is present but unparseable or schema-invalid.
- `HUMAN_REQUIRED` — agent cannot reconcile orientation request with the read-only scope.

On any failure state, escalate without writing.

## Git Authority
This skill **does not self-grant any Git mutational authority**. Read-only Git inspection (`git rev-parse`, `git status`, `git diff` without commit metadata) is permitted only as needed to confirm baseline identity at the cold-start boundary.

The following mutational actions are **prohibited** without explicit user *Task Authorization*:
- `commit` — no autonomous `git commit`.
- `push` — no autonomous `git push`.
- `merge` — no `git merge` of any kind.
- `rebase` — no `git rebase` of any kind.
- `reset` — no `git reset`, no destructive history rewrites.
- `amend` — no `git commit --amend`.
- `force-push` — no `git push --force` or equivalent.

Writing files inside this skill's scope (none, in this case) does not imply Git authority.

## Handoff
After orientation completes, transfer control only to:

- `psm-before-change` — when a code modification is about to begin.
- `psm-validate` — when the user explicitly asks for an **independent** map audit. A host-routed audit request does **not** pass through here.

`psm-orient` does **not** route to `psm-host-docs` and does **not** route to `psm-maintain` directly. Maintenance, host-doc synchronization, and the eventual validation gate are coordinated by `psm-maintain` *after* a modification completes. `psm-orient` is a cold-start router, not a general dispatcher.
