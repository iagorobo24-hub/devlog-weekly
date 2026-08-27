<!-- PSM:GENERATED_ADAPTER
framework_version: 0.2.0-alpha
framework_source_commit: ee46f5bf6d8c6809621f7b4b9fcddee90037bc52
skill_id: psm-validate
canonical_path: skills/psm-validate/SKILL.md
canonical_sha256: 45c7afcfdfbf1b4fe4d49997a7623fae14dc19f5dc6bc479bd360bfcf4aa9c68
-->

# psm-validate — Architectural Validation Skill

> Canonical PSM skill. Authoritative design: `docs/design/psm-v0.2.0-alpha-agent-skills-target-enablement-continuous-maintenance.md` (section 15).

## ID
`psm-validate`

## Name
psm-validate

## Purpose
Coordinate two explicitly separate validation planes for the joint state of the product tree, the System Map and the host's canonical documentation. This skill is the **gatekeeper** that authorizes `psm.source.commit` refresh only after the deterministic mechanical gate and the required semantic review have both completed. It can correct trivial defects inside the *Validation Correction Boundary* and explicitly **cannot** modify product source files.

## Validation Planes

### `MECHANICAL_GATE`

The mechanical gate contains checks that tooling can execute and repeat deterministically, including YAML/schema parsing, physical paths and reference existence, structural fields, hashes, skill-lock and framework provenance, managed blocks, lifecycle state, and syntax/structural checks. Static tooling may enumerate candidate universal terms or verify that an edge is physically present, but those facts are evidence only; they do not settle the meaning, scope or correctness of the claim.

A mechanical result is reported as `MECHANICAL_GATE: PASS`, `MECHANICAL_GATE: FAIL`, or `MECHANICAL_GATE: UNAVAILABLE`. A mechanical failure is a tooling/check failure with its mechanical diagnostic. `MECHANICAL_GATE: PASS` certifies only the listed deterministic checks and **never** certifies `SEMANTIC_AGENT_REVIEW: PASS`.

### `SEMANTIC_AGENT_REVIEW`

The semantic review requires an agent or human to interpret evidence and make or confirm judgment. It covers architectural meaning, severity, conceptual completeness, the truth and scope of universal claims, material edge direction/scope/exceptions/order, architectural decisions, evidence quality, and the Cold-Agent Walk Test. Tooling can provide inputs and traces for this review, but it cannot assign its result or replace the reviewer.

The semantic plane is reported independently as `SEMANTIC_AGENT_REVIEW: PASS`, `PASS WITH WARNINGS`, `PENDING`, `FAIL`, or `HUMAN_REQUIRED`. `PENDING` means the semantic review is still required; it is not a mechanical error and must not be relabeled as one. No deterministic tooling status, including a mechanical PASS or an operational `AUDIT_PASSED`/`TARGET_ENABLED`, may be presented as semantic approval.

### Combined gate

A final validation `PASS` requires `MECHANICAL_GATE: PASS` **and** a recorded semantic review of `PASS` or `PASS WITH WARNINGS`. If the mechanical gate passes while the semantic review is pending, the report must preserve both facts and must not authorize `status: active` or a `psm.source.commit` refresh. The two planes may consume common evidence, but neither result may be inferred from the other.

## Trigger / Invocation Context
- Post-maintentance cycle of `psm-maintain`.
- Phase 05 of the Bootstrap Lifecycle.
- Standalone health audit, periodic or CI-driven.

## Inputs & Preconditions
- Required: full content of `docs/system-map/**`; the product source tree at the commit being audited.
- Optional: `.psm/host-profile.yaml`, `.psm/skill-lock.yaml`.
- Precondition: every artifact referenced by the map is reachable and parseable. If PyYAML is missing in a Python-driven sub-routine, the failure is surfaced as `YAML_PARSER_UNAVAILABLE` and the verdict is forced to `FAIL` — never silently coerced.

## Read Scope
- All of `docs/system-map/**`.
- All host canonical documents listed in `manifest.yaml: canonical_docs`.
- The product source files cited by the map or by the diff under audit.
- Host linters, formatters and validation commands referenced in `.psm/host-profile.yaml: validation_command_references`; these are AGENT-CONSUMED declarative references, not commands executed automatically by PSM.

## Write Scope
**Authorized write targets only, strictly inside the *Validation Correction Boundary*:**
- Trivial syntax fixes inside `docs/system-map/**` (errata, broken relative paths confirmed against the filesystem, allowed metadata fields of `manifest.yaml`).
- Promotion of `manifest.yaml: psm.status` from `draft` to `active` only when `MECHANICAL_GATE: PASS` and `SEMANTIC_AGENT_REVIEW: PASS` or `PASS WITH WARNINGS` are recorded, including a passing Cold-Agent Walk Test.

Writes outside the *Validation Correction Boundary* are forbidden. In particular, this skill **must not** modify:
- any product source file,
- any host canonical document outside the explicit boundary above,
- `.psm/**` (the lock and profile are PSM-managed, not validator-managed),
- any adapted skill file.

## Forbidden Actions
- Weakening, skipping or disabling any host checker, linter or test to achieve a green verdict.
- Inventing architecture, symbols or edges to resolve semantic inconsistencies.
- Auto-correcting semantic contradictions inside the map. Those escalate to `HUMAN_REQUIRED`.
- Modifying product source code — no exception.
- Issuing Git mutations of any kind.

## Verdict Outputs
The report must expose both planes before any overall verdict:
- `MECHANICAL_GATE: PASS | FAIL | UNAVAILABLE` — only the deterministic checks owned by tooling.
- `SEMANTIC_AGENT_REVIEW: PASS | PASS WITH WARNINGS | PENDING | FAIL | HUMAN_REQUIRED` — only the agent/human interpretation and judgment.

The overall validation verdict remains one of:
- `PASS` — the mechanical gate passed and the semantic review recorded `PASS`.
- `PASS WITH WARNINGS` — the mechanical gate passed and the semantic review recorded `PASS WITH WARNINGS`.
- `FAIL` — a required plane failed, including mechanical reference/schema failures or a failed semantic review.

`MECHANICAL_GATE: PASS` with `SEMANTIC_AGENT_REVIEW: PENDING` is an incomplete validation, not an overall PASS and not a mechanical failure. A semantic reviewer may consume mechanical evidence, but a tooling report must never present that interpretation as deterministic tooling output.

## Failure States
- `REFERENCE_INTEGRITY_FAIL` — a path, symbol or canonical document cited by the map does not resolve.
- `UNIVERSAL_AUDIT_FAIL` — the `SEMANTIC_AGENT_REVIEW` cannot accept a universal claim because the required exception search or interpretation is missing/failed.
- `WALK_TEST_FAIL` — the `SEMANTIC_AGENT_REVIEW` Cold-Agent Walk Test cannot be performed or fails.
- `YAML_PARSER_UNAVAILABLE` — the `MECHANICAL_GATE` cannot run because the required parser is missing; the overall verdict is forced to `FAIL`.
- `HUMAN_REQUIRED` — semantic contradiction that cannot be coerced by mechanical correction.

## Universal Quantifier Discipline
Deterministic tooling may scan for candidate universal quantifiers and report the searched scope. The exception search, interpretation of whether the claim is actually universal, decision about adequate evidence, and any bounding or evidence-status change belong to `SEMANTIC_AGENT_REVIEW`. If the search cannot be performed or an undeclared exception is found, the semantic plane becomes `FAIL` or `HUMAN_REQUIRED` as appropriate; the mechanical scan must not masquerade as that judgment.

## Git Authority
This skill **does not self-grant any Git mutational authority**. The capacity to write inside `docs/system-map/**` does not imply the capacity to commit, push, merge, rebase or otherwise mutate Git state.

The following mutational actions are **prohibited** without explicit user *Task Authorization*:
- `commit` — no autonomous `git commit`.
- `push` — no autonomous `git push`.
- `merge` — no `git merge` of any kind.
- `rebase` — no `git rebase` of any kind.
- `reset` — no `git reset`, no destructive history rewrites.
- `amend` — no `git commit --amend`.
- `force-push` — no `git push --force` or equivalent.

## Handoff
- Only after both planes produce an eligible overall `PASS` / `PASS WITH WARNINGS` may `psm-maintain` refresh `source.commit`.
- After a mechanical failure, return the mechanical diagnostics for correction.
- After a semantic `PENDING`, `FAIL`, or `HUMAN_REQUIRED`, return control to the agent/human review path; do not report a tooling failure unless the mechanical gate itself failed.

## Host-Profile Field Semantics
- `framework_compatibility.min_version` is a declarative/reserved note in v0.2. Tooling validates its basic shape but does not resolve semver ranges, select a framework, update a checkout, or negotiate compatibility automatically.
- `validation_command_references` is an `AGENT-CONSUMED / DECLARATIVE REFERENCE` map. PSM may surface or recommend entries, but never executes arbitrary host command strings automatically.
- `skill_overrides` has no general v0.2 semantics. `{}` is allowed; a non-empty mapping is rejected fail-closed as `UNSUPPORTED_SKILL_OVERRIDES`.
