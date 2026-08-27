<!-- PSM:GENERATED_ADAPTER
framework_version: 0.2.0-alpha
framework_source_commit: ee46f5bf6d8c6809621f7b4b9fcddee90037bc52
skill_id: psm-host-docs
canonical_path: skills/psm-host-docs/SKILL.md
canonical_sha256: c199dd22de1d9d35b5b66b754d6f229f59b36e620459e1a8d4e99d765f9879c2
-->

# psm-host-docs — Host Documentation Synchronization Skill

> Canonical PSM skill. Authoritative design: `docs/design/psm-v0.2.0-alpha-agent-skills-target-enablement-continuous-maintenance.md` (section 16).

## ID
`psm-host-docs`

## Name
psm-host-docs

## Purpose
Evaluate the interaction between a code/map change and the **host-owned canonical documentation** (ADRs, `STATUS.md`, `PLAN_ACTIVO.md`, `EVOLUCION.md`, etc.) and decide — with the **link-before-duplicate** discipline — which documents need to be updated. Emit a first-class `NO_DOCUMENTATION_CHANGE_REQUIRED` when no host document is affected.

This skill does not duplicate the content of any ADR or state document inside the System Map. Host documents remain the canonical authority for their own subject; the map links to them.

## Trigger / Invocation Context
- Invoked by `psm-maintain` whenever a code or map change has been classified.
- Detected during a maintenance cycle that introduces a new decision, a state transition, or a status update.
- Standalone invocation when host documentation drift is suspected.

## Inputs & Preconditions
- Required: `docs/system-map/manifest.yaml` (specifically `psm.canonical_docs`); `.psm/host-profile.yaml`; the nature of the change being synchronized.
- Optional: history of host documentation surrounding the affected area.
- Precondition: a System Map is reachable, and at least one canonical host document is declared. If none are declared, surface the diagnostic; sync decision may still be `NO_DOCUMENTATION_CHANGE_REQUIRED`.

## Read Scope
- All files listed under `manifest.yaml: psm.canonical_docs`.
- `AGENTS.md`, `CLAUDE.md`, `CONTRIBUTING.md`, and any host instruction file referenced from `host-profile.yaml`.
- All artifacts under `docs/system-map/**`.
- Host documentation tools and conventions discovered through the host profile.

## Write Scope
**Target-agnostic authority.** `psm-host-docs` operates on the **current target repository** in which PSM is enabled. The target **may** itself be the `project-system-map` framework repository during dogfood — being the framework repo does **not** by itself make every framework file writable.

**Authorized write targets, by sub-decision:**
- Backlinks in `docs/system-map/**` that reference a newly introduced canonical host document (e.g., a new ADR link inside `README.md`).
- The specific host canonical document authorized by the sub-decision (`UPDATE_CANONICAL_DOC_ONLY` or `UPDATE_MAP_AND_CANONICAL_DOC`).

A host canonical document is writable **only** when **all** of the following hold:
1. It is declared or discovered through the target's authority — `manifest.yaml: psm.canonical_docs`, `.psm/host-profile.yaml`, or an equivalent authoritative surface.
2. The host-doc decision explicitly authorizes that document.
3. Explicit *Task Authorization* permits the write.

Writes outside these targets are forbidden. In particular:
- The body of an ADR **must not** be duplicated inside the map.
- Historical / immutable documents must not be overwritten.
- Framework methodology files and framework source code are **not** writable simply because PSM is installed in the framework repository; they require the same authority chain above. Being the framework repo is not, on its own, a write grant.

## Host-Doc Decisions
Exactly one of:
- `UPDATE_MAP_ONLY` — change affects only the structure within `docs/system-map/**`.
- `UPDATE_CANONICAL_DOC_ONLY` — operational state or plan that does not alter architecture.
- `UPDATE_MAP_AND_CANONICAL_DOC` — structural change that accompanies a host decision or status update.
- `NO_DOC_UPDATE` — change does not warrant any documentation update.
- `HUMAN_REQUIRED` — authority conflict or precedence ambiguity that cannot be reconciled mechanically.

No-Op formal outcome: `NO_DOCUMENTATION_CHANGE_REQUIRED`.

## Forbidden Actions
- Duplicating the full content of an ADR, status document or plan file inside `docs/system-map/**`.
- Overwriting or editing historical / immutable documents.
- Inventing documentation precedence or ownership rules not derivable from the host's manifest or profile.
- Assuming universally that the host uses `AGENTS.md`, `CLAUDE.md`, `.agents/skills/` or `.claude/skills/`. Discover from `manifest.yaml` and `.psm/host-profile.yaml`.
- Issuing Git mutations of any kind.

## Failure States
- `CANONICAL_DOC_NOT_FOUND` — a host document promised by `canonical_docs` does not resolve on disk.
- `DUPLICATION_CONFLICT` — proposed write would duplicate content already inside `docs/system-map/**`.
- `AUTHORITY_AMBIGUITY` — two declared canonical documents disagree on ownership of the same subject.
- `HUMAN_REQUIRED` — escalation for unreconcilable authority conflicts.

## link-before-duplicate Rule
Any information that already exists in a canonical host document must be referenced by **relative link**, not reproduced. A new shard in the System Map can summarize a host decision **only** when the host document itself is being created in the same sub-decision (`UPDATE_MAP_AND_CANONICAL_DOC`); it must then carry an explicit cross-link in both directions.

## Git Authority
This skill **does not self-grant any Git mutational authority**. The capacity to write inside host-doc-authorized paths does not imply the capacity to commit, push, merge, rebase or otherwise mutate Git state.

The following mutational actions are **prohibited** without explicit user *Task Authorization*:
- `commit` — no autonomous `git commit`.
- `push` — no autonomous `git push`.
- `merge` — no `git merge` of any kind.
- `rebase` — no `git rebase` of any kind.
- `reset` — no `git reset`, no destructive history rewrites.
- `amend` — no `git commit --amend`.
- `force-push` — no `git push --force` or equivalent.

## Handoff
Return the deterministic decision to `psm-maintain`. Then `psm-validate` is the final gate before any `source.commit` refresh.
