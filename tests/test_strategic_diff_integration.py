"""Pinned branch diff evidence must remain a read-only, independent signal."""
import copy
import unittest

from src.strategic_selection import diff_index, enrich_branch_signal

NAME = "iagorobo24-hub/GuiaIA"
SHA = "a" * 40
URL = f"https://github.com/{NAME}/commit/{SHA}"
STAMP = "2026-10-29T16:00:00+00:00"


def inputs():
    selection = {"generated_at": STAMP}
    branch = {
        "generated_at": STAMP,
        "repos": [{"repo": NAME}],
    }
    report = {
        "schema": 1, "visibility": "public",
        "automatic_publication": False,
        "private_inputs_accessed": False,
        "only_file_category_evidence": True,
        "not_functional_or_test_execution_validation": True,
        "source_selection_generated_at": STAMP,
        "source_branch_generated_at": STAMP,
        "repos": [{
            "repo": NAME, "visibility": "public", "audited": [{
                "sha": SHA, "url": URL,
                "status": "only_docs_or_other_paths",
                "declared_kind": "test",
                "matching_declared_kind": False,
                "counts": {"code": 0, "tests": 0, "docs": 1, "other": 0},
                "scan_complete": True,
                "filename_categories_only": True,
                "not_test_execution_or_functional_validation": True,
            }],
        }],
    }
    signal = {
        "branch_evidence_status": "unmerged_not_validated_on_main",
        "branch_commit_samples": [{
            "sha": SHA, "url": URL, "kind": "test",
            "subject": "test: some claim",
            "commit_subject_only": True,
            "not_merged_or_functionally_verified": True,
        }]
    }
    return selection, branch, report, signal


class StrategicDiffTests(unittest.TestCase):
    def test_metadata_joins_exact_sha_without_promotion(self):
        sel, branch, report, signal = inputs()
        before = copy.deepcopy(signal)
        indexed = diff_index(sel, branch, report)
        enriched = enrich_branch_signal(signal, NAME, indexed)
        sample = enriched["branch_commit_samples"][0]
        self.assertFalse(sample["declared_kind_has_corresponding_path"])
        self.assertEqual(sample["path_categories"]["docs"], 1)
        self.assertTrue(sample["filename_category_is_not_runtime_or_test_execution_proof"])
        self.assertEqual(signal, before)

    def test_wrong_branch_report_or_private_data_rejected(self):
        sel, branch, report, _ = inputs()
        report["source_branch_generated_at"] = "old"
        with self.assertRaisesRegex(ValueError, "desincronizado"):
            diff_index(sel, branch, report)
        report["source_branch_generated_at"] = STAMP
        report["repos"][0]["visibility"] = "private"
        with self.assertRaisesRegex(ValueError, "privado"):
            diff_index(sel, branch, report)

    def test_foreign_commit_is_rejected(self):
        sel, branch, report, _ = inputs()
        report["repos"][0]["audited"][0]["url"] = "https://attacker.test/commit"
        with self.assertRaisesRegex(ValueError, "no fiable"):
            diff_index(sel, branch, report)

    def test_missing_or_extra_repos_are_rejected(self):
        sel, branch, report, _ = inputs()
        report["repos"] = []
        with self.assertRaisesRegex(ValueError, "incompleta"):
            diff_index(sel, branch, report)
        report["repos"] = "invalid"
        with self.assertRaisesRegex(ValueError, "inválida"):
            diff_index(sel, branch, report)

    def test_wrong_sample_sha_rejected(self):
        sel, branch, report, signal = inputs()
        report["repos"][0]["audited"][0]["sha"] = "b" * 40
        report["repos"][0]["audited"][0]["url"] = f"https://github.com/{NAME}/commit/" + "b" * 40
        with self.assertRaisesRegex(ValueError, "ajeno"):
            enrich_branch_signal(signal, NAME, diff_index(sel, branch, report))

    def test_declared_kind_disagreement_rejected(self):
        sel, branch, report, signal = inputs()
        report["repos"][0]["audited"][0]["declared_kind"] = "code"
        with self.assertRaisesRegex(ValueError, "ajeno"):
            enrich_branch_signal(signal, NAME, diff_index(sel, branch, report))

    def test_head_changed_discards_diff_evidence(self):
        sel, branch, report, signal = inputs()
        signal["branch_commit_samples"] = []
        signal["branch_evidence_status"] = "default_head_changed"
        result = enrich_branch_signal(signal, NAME, diff_index(sel, branch, report))
        self.assertEqual(result["branch_commit_samples"], [])

    def test_mismatched_count_rejected(self):
        sel, branch, report, signal = inputs()
        report["repos"][0]["audited"] = []
        with self.assertRaisesRegex(ValueError, "no coincide"):
            enrich_branch_signal(signal, NAME, diff_index(sel, branch, report))


if __name__ == "__main__":
    unittest.main()
