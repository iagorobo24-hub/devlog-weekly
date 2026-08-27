<!-- PSM:GENERATED_ADAPTER
framework_version: 0.2.0-alpha
framework_source_commit: ee46f5bf6d8c6809621f7b4b9fcddee90037bc52
skill_id: psm-maintain
canonical_path: skills/psm-maintain/SKILL.md
canonical_sha256: c37e5b1a1d39f359115fa8035df623eca0d512f084120ca8f96a4d00b5bd68b7
-->

# psm-maintain — Post-Change Map Maintenance Skill

> Canonical PSM skill. Authoritative design: `docs/design/psm-v0.2.0-alpha-agent-skills-target-enablement-continuous-maintenance.md` (section 14).

## ID
`psm-maintain`

## Name
psm-maintain

## Purpose
Analyze the **real** product-code drift against the audited `psm.source.commit` after a code change, classify the drift, and apply the **minimum** surgical update to the System Map or its metadata. Accept the No-Op outcome when no architectural contract changed. Coordinate the optional invocation of `psm-host-docs` and the mandatory invocation of `psm-validate`.

This skill is the **primary post-change writer** for architectural changes to the System Map (`docs/system-map/**`). It is **not** the only skill that may write under that path: `psm-validate` owns a narrow Validation Correction Boundary, and `psm-host-docs` owns explicitly authorized map backlinks and canonical-document synchronization. `psm-maintain` owns the four Maintenance Decision Matrix outcomes (`NO_MAP_CHANGE`, `MAP_METADATA_ONLY`, `TARGETED_MAP_UPDATE`, `RECONCILIATION_REQUIRED`) and never touches product code.

## Trigger / Invocation Context
- Implementation phase finishes.
- Working tree (committed or staged) shows a diff versus `psm.source.commit`.
- A scheduled full re-baseline review is requested.

## Inputs & Preconditions
- Required: `psm.source.commit` from `manifest.yaml`; the **real current state** of the product tree relative to `psm.source.commit`, covering **commits after the baseline, staged (index) changes, unstaged working-tree changes, and untracked files**. The change set must reflect every architectural artifact that has been edited but not yet promoted — **not** only the commits between `source.commit` and `HEAD`.
- Optional: the `psm-before-change` contract emitted before implementation.
- Precondition: a System Map at `docs/system-map/` is present, parseable, and (preferably) `active`. If `draft`, surface the diagnostic; the maintenance action itself still applies.

## Read Scope
- **Real product diff:** `git diff <source.commit> -- <product scope>` against the *current* working tree. This single command covers **commits since the baseline, the index (staged) state, and unstaged working-tree changes** at once.
- The form `git diff <source.commit>..HEAD` is **not** equivalent: it silently hides any uncommitted state and must not be used as the sole input. It is referenced here only so the contrast is explicit.
- **Untracked product files:** `git ls-files --others --exclude-standard` filtered to the same product scope. New files that have not yet been added to the index are still part of the real change set and must be classified.
- **Tripartite drift filter:** exclude `docs/system-map/**`, `.psm/**`, skill-adapter refresh, and managed routing block refresh from **product** architectural drift, per the existing drift model.
- `docs/system-map/manifest.yaml`.
- `docs/system-map/README.md`, `domain.md`, `flow.md`, `boundaries.md`, `invariants.md` (or sharded equivalents).
- Files referenced by the diff, to verify new symbols and edges.
- `.psm/host-profile.yaml`.

## Write Scope
**Authorized write target only:**
- `docs/system-map/manifest.yaml` — for verified `source.commit` refresh and `verified_at` timestamping.
- `docs/system-map/README.md`
- `docs/system-map/domain.md` and `docs/system-map/domains/*.md`
- `docs/system-map/flow.md` and `docs/system-map/flows/*.md`
- `docs/system-map/boundaries.md`
- `docs/system-map/invariants.md`

Writes outside this set are forbidden. In particular, this skill **must not** modify:
- any product source file (`src/`, `app/`, `lib/`, etc.),
- `.psm/**`,
- any host governance file (`AGENTS.md`, `CLAUDE.md`, …),
- any adapted skill under `.agents/skills/**` or `.claude/skills/**`.

## Forbidden Actions
- Editing any product source file.
- Updating map shards whose underlying architectural contract was not changed by the diff (no churn documentation).
- Removing or weakening invariants without an explicit reconciliation outcome.
- Inventing architecture, edges or boundaries not demonstrated by the diff.
- Writing a new `source.commit` for code changes that have not yet been **committed and adequately validated**.
- Issuing `git commit`, `git push`, or any other Git mutation autonomously.

## Maintenance Decision Matrix
Per the design matrix, classify the drift as exactly one of:
- `NO_MAP_CHANGE` — internal refactor, rename, formatting or comment change; map intact.
- `MAP_METADATA_ONLY` — only `verified_at` or `source.commit` refresh; other artifacts untouched.
- `TARGETED_MAP_UPDATE` — surgical update of a specific shard (`domain.md`, `flow.md`, `boundaries.md`, `invariants.md`, `README.md`).
- `RECONCILIATION_REQUIRED` — major structural change or new domain; escalate to a Bootstrap sub-cycle (Phases 02 → 05).

The decision is emitted as a first-class result. No-Op is a valid successful result.

## Failure States
- `DIRTY_WORKTREE_CONFLICT` — diff cannot be computed cleanly because of uncommitted or untracked conflicts.
- `BASE_COMMIT_NOT_FOUND` — `source.commit` is not an ancestor of the current HEAD.
- `UNPARSEABLE_DIFF` — diff cannot be classified by path or symbol rules.
- `RECONCILIATION_REQUIRED` — drift cannot be resolved by a targeted update.
- `HUMAN_REQUIRED` — ambiguity that cannot be resolved from the diff alone.

On any failure state, apply **no writes** and escalate.

## source.commit Discipline
- `psm.source.commit` is the *audit commit of the product code*, not the map commit.
- It is **not** updated for any of:
  - changes exclusively under `docs/system-map/**`,
  - changes under `.psm/**`,
  - skill-adapter refresh,
  - managed routing block refresh.
- A product state after the baseline is `STALE_BASELINE` until it is committed and adequately validated.

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
After write (or No-Op), invoke:
- `psm-host-docs` when host-owned canonical documents must be considered for the same change;
- `psm-validate` as the final mandatory gate before any `source.commit` refresh.
