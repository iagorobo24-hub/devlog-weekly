<!-- PSM:GENERATED_ADAPTER
framework_version: 0.2.0-alpha
framework_source_commit: ee46f5bf6d8c6809621f7b4b9fcddee90037bc52
skill_id: psm-before-change
canonical_path: skills/psm-before-change/SKILL.md
canonical_sha256: 7c4d951aa7a1edf28680edb9fbbc4dda4078d0c01b56b586aca16689413f8bc7
-->

# psm-before-change — Pre-Change Impact Analysis Skill

> Canonical PSM skill. Authoritative design: `docs/design/psm-v0.2.0-alpha-agent-skills-target-enablement-continuous-maintenance.md` (section 13).

## ID
`psm-before-change`

## Name
psm-before-change

## Purpose
Produce a **Pre-Change Impact Contract** before a **material product or operational change** is allowed to begin. The contract identifies which domains, flows, invariants and boundaries are affected, classifies the change, and prevents scope creep. This skill is *analytical* and *contractual* — it never touches code, the map, or Git.

## Material Change Rule

A **material change** is a requested change reasonably capable of altering an observable behavior or a contract relied on outside the edited implementation. It includes, when applicable:

- observable runtime behavior;
- public APIs, interfaces, schemas or data models;
- persistence, migrations or stored-data meaning;
- security controls or trust boundaries;
- dependencies with functional/runtime effect;
- architecture, deployment or runtime topology;
- invariants and other relevant product or integration contracts.

The following are normally non-material when they have no contract effect: formatting, comments without behavioral effect, a purely documentary typo, generated output whose contract is unchanged, and an internal rename/refactor that preserves behavior, APIs, edges, persistence, invariants and runtime/deployment assumptions.

Classify by effect, not by the fact that Git records a byte change or by the file extension. If reasonable doubt remains about materiality, classify the change as material and produce the contract. `psm-before-change` therefore does **not** mechanically block every byte edit; it is mandatory before material work, and a clearly non-material edit may proceed without a pre-change contract.

## Trigger / Invocation Context
- User requests implementation of a feature, bugfix, refactor or dependency update that may be material.
- Agent identifies a material effect, or reasonable doubt about materiality, before editing.
- A pull request or task workflow demands a stated scope boundary for material work.

## Inputs & Preconditions
- Required: a written task description; `docs/system-map/manifest.yaml`; `docs/system-map/README.md`.
- Optional: candidate paths suggested by the user; a previous `psm-before-change` contract for re-use.
- Precondition: System Map is reachable. If `status: draft`, surface the diagnostic but **do not** abort the contract; the contract is precisely what unblocks progression toward promotion.

## Read Scope
- `docs/system-map/README.md`
- `docs/system-map/domains/*.md` or `docs/system-map/domain.md`
- `docs/system-map/flows/*.md` or `docs/system-map/flow.md`
- `docs/system-map/boundaries.md`
- `docs/system-map/invariants.md`
- `.psm/host-profile.yaml`

## Write Scope
**NONE — read-only.**

This skill must not modify any source file, map artifact, lock, profile, manifest or governance document. The Pre-Change Contract is emitted as a textual response in the conversation.

## Forbidden Actions
- Beginning a material source, map, configuration or documentation change before the contract is fully stated.
- Treating every byte-level edit as material solely because it changes a file.
- Ignoring or bypassing `BLOCKER` / `CRITICAL` invariants cited in `docs/system-map/invariants.md`.
- Silently broadening scope beyond what the user authorized (scope creep).
- Comparing the user's request against a `proposed_state.commit` or any future reference; the contract operates strictly against the audited `psm.source.commit`.
- Issuing Git mutations of any kind.

## Failure States
- `INVARIANT_CONFLICT_DETECTED` — proposed change cannot satisfy a `BLOCKER` or `CRITICAL` invariant.
- `DOMAIN_AMBIGUITY` — change spans domains whose boundaries cannot be deduced from the map.
- `TARGET_NOT_COVERED` — affected code lives outside any documented domain and is not trivially host infrastructure.
- `HUMAN_REQUIRED` — invariant violation or undocumented boundary that cannot be reconciled through the read-only contract alone.

On any failure state, escalate without writing.

## Git Authority
This skill **does not self-grant any Git mutational authority**. Read-only inspection (`git status`, `git diff --stat` against `source.commit`) is permitted only insofar as it informs the contract.

The following mutational actions are **prohibited** without explicit user *Task Authorization*:
- `commit` — no autonomous `git commit`.
- `push` — no autonomous `git push`.
- `merge` — no `git merge` of any kind.
- `rebase` — no `git rebase` of any kind.
- `reset` — no `git reset`, no destructive history rewrites.
- `amend` — no `git commit --amend`.
- `force-push` — no `git push --force` or equivalent.

## Contract Output Structure
The contract must include, at minimum:
1. **Classification** — `BUGFIX | FEATURE | REFACTOR | DOCS_ONLY`.
2. **Hits** — domains, flows, boundaries and invariants materially affected.
3. **Does not hit** — domains, flows, boundaries explicitly out of scope.
4. **Invariants to preserve** — full text and severity from `docs/system-map/invariants.md`.
5. **Boundaries crossed** — interfaces, ownership lines or external dependencies touched.
6. **Affected flows** — sequence dependencies whose ordering must be preserved.
7. **Required post-change tests / checkers** — pulled from `.psm/host-profile.yaml: validation_command_references` and the affected domains' test inventory. These host entries are declarative references consumed by the agent/human; PSM does not execute arbitrary command strings automatically.
8. **Ambiguities and escalations** — items deferred to `psm-validate` or to `HUMAN_REQUIRED`.

## Handoff
On contract completion, transfer control to the material implementation step. A clearly non-material edit may proceed without this handoff. After implementation finishes, hand off to `psm-maintain`.
