from copy import deepcopy
import tempfile
import unittest
from pathlib import Path

from src.candidate_profiles import validate, build

SHA = "a" * 40
PROFILE = {
    "version": 1, "id": "candidate", "title": "Example", "repo": "owner/project",
    "revision": SHA, "visibility": "public", "editorial_status": "draft_only",
    "statements": [{"text": "La CI se ejecutó en el HEAD del repositorio.",
                    "kind": "ci_at_head", "source_path": ".github/workflows/ci.yml"},
                   {"text": "Existen pruebas bajo la carpeta tests.",
                    "kind": "repository_directory", "source_path": "30-tools/tests"}],
    "images": [{"path": "docs/img/banner.svg", "kind": "conceptual_illustration"}],
    "publication_gate": {
        "independent_functional_check_required": True,
        "runtime_evidence_required": True, "explicit_editorial_approval_required": True}
}
QUALITY = {
    "repo":"owner/project", "head": SHA, "visibility": "public",
    "readiness": "ci_head_passed_tests_exist", "ci": {
        "status": "success_at_head", "run_count_at_head": 1,
        "run_url": "https://github.com/owner/project/actions/runs/123"}}


class CandidateProfilesTests(unittest.TestCase):
    def test_verified_ci_but_publication_still_blocked(self):
        x = validate(PROFILE, QUALITY)
        self.assertFalse(x["publication_allowed"])
        self.assertEqual(x["warnings"],[])
        # The workflow definition is a source file, not evidence it executed.
        self.assertFalse(x["sources"][0]["is_independently_verified"])
        self.assertFalse(x["sources"][1]["is_independently_verified"])
        self.assertEqual(x["sources"][0]["ci_run_url_at_head"],
                         "https://github.com/owner/project/actions/runs/123")
        self.assertIsNone(x["sources"][1]["ci_run_url_at_head"])
        self.assertTrue(x["sources"][0]["source_semantics_not_verified"])
        self.assertIn("/tree/",x["sources"][1]["url"])
        self.assertIn("/blob/",x["sources"][0]["url"])

    def test_stale_revision_blocks_ci_claim(self):
        q = dict(QUALITY, head="b"*40)
        x=validate(PROFILE,q)
        self.assertIn("editorial_revision_outdated",x["warnings"])
        self.assertIn("ci_statement_needs_recheck",x["warnings"])
        self.assertFalse(x["sources"][0]["is_independently_verified"])

    def test_green_ci_without_valid_run_is_not_verified(self):
        for run_url in (None, "https://attacker.test/123",
                        "https://github.com/other/repo/actions/runs/123",
                        "https://github.com/owner/project/actions/runs/nope",
                        "https://github.com/owner/project/actions/runs/0",
                        "https://github.com/owner/project/actions/runs/123?x=1"):
            with self.subTest(url=run_url):
                q = deepcopy(QUALITY)
                q["ci"]["run_url"] = run_url
                result = validate(PROFILE, q)
                self.assertFalse(result["publication_allowed"])
                self.assertFalse(result["sources"][0]["is_independently_verified"])
                self.assertIsNone(result["sources"][0]["ci_run_url_at_head"])
                self.assertIn("ci_run_url_missing_or_invalid_at_head",
                              result["warnings"])

    def test_forged_green_ci_without_run_count_rejected(self):
        q = deepcopy(QUALITY)
        q["ci"]["run_count_at_head"] = 0
        result = validate(PROFILE, q)
        self.assertIn("ci_statement_needs_recheck", result["warnings"])
        self.assertIsNone(result["sources"][0]["ci_run_url_at_head"])

    def test_foreign_or_private_quality_does_not_support_ci(self):
        for mismatch in ({"repo": "attacker/repo"}, {"visibility": "private"}):
            q = deepcopy(QUALITY)
            q.update(mismatch)
            result = validate(PROFILE, q)
            self.assertIsNone(result["sources"][0]["ci_run_url_at_head"])
            self.assertFalse(result["sources"][0]["is_independently_verified"])
            self.assertIn("ci_statement_needs_recheck", result["warnings"])

    def test_non_ci_sources_have_no_execution_evidence(self):
        profile = deepcopy(PROFILE)
        profile["statements"] = [profile["statements"][1]]
        result = validate(profile, QUALITY)
        self.assertIsNone(result["sources"][0]["ci_run_url_at_head"])
        self.assertFalse(result["sources"][0]["is_independently_verified"])

    def test_never_autopromotes_or_disables_gate(self):
        p=deepcopy(PROFILE)
        p["editorial_status"]="approved"
        with self.assertRaisesRegex(ValueError,"autopromoverse"):
            validate(p,QUALITY)
        p=deepcopy(PROFILE)
        p["publication_gate"]["explicit_editorial_approval_required"]=False
        with self.assertRaisesRegex(ValueError,"puertas editoriales"):
            validate(p,QUALITY)

    def test_rejects_unversioned_external_source(self):
        p=deepcopy(PROFILE)
        p["statements"][0]["source_path"]="../../private"
        with self.assertRaisesRegex(ValueError,"fuente"):
            validate(p,QUALITY)

    def test_private_quality_not_accepted(self):
        q=dict(QUALITY,visibility="private")
        x=validate(PROFILE,q)
        self.assertIn("quality_probe_missing",x["warnings"])
        with self.assertRaisesRegex(ValueError,"privados"):
            build({"visibility":"private-local","records":[]})

    def test_directory_ignored_when_empty(self):
        with tempfile.TemporaryDirectory() as tmp:
            q={"visibility":"public","records":[]}
            x=build(q,folder=Path(tmp))
            self.assertEqual(x["drafts"],[])


if __name__=="__main__":
    unittest.main()
