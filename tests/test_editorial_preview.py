import unittest
from src.editorial_preview import render


class EditorialPreviewTests(unittest.TestCase):
    def setUp(self):
        self.s={"visibility":"public","automatic_publication":False,
                "proposed_slate":[{"visibility":"public","publishable":False,
                                  "repo":"owner/foo","title":"Foo",
                                  "strategic_priority":5,"ci_status":"unknown",
                                  "editorial_tier":"strategic_high_requires_verification"}]}
        self.d={"visibility":"public","automatic_publication":False,"drafts":[]}

    def test_proposal_not_publication(self):
        md=render(self.s,self.d)
        self.assertIn("NO PUBLICAR",md)
        self.assertIn("Foo",md)
        self.assertIn("No se ha consultado ni exportado ningún repositorio privado.", md)
        self.assertIn("prioridades editoriales", md)
        self.assertIn("sin definir" if False else "5/5", md)

    def test_references_unmerged_commits_only_as_subjects(self):
        sha="a"*40
        self.s["proposed_slate"][0].update({
            "unmerged_code_7d": 1, "unmerged_tests_7d": 0,
            "branch_scan_complete": True,
            "branch_commit_samples": [{
                "sha": sha, "kind": "code",
                "subject": "<script>alert(1)</script>",
                "url": f"https://github.com/owner/foo/commit/{sha}",
                "commit_subject_only": True,
                "not_merged_or_functionally_verified": True,
            }],
        })
        result=render(self.s,self.d)
        self.assertIn("Muestras de commits públicos", result)
        self.assertIn("sin verificar ejecución", result)
        self.assertIn(sha, result)
        self.assertNotIn("<script>", result)
        self.assertIn("&lt;script&gt;", result)

    def test_feature_tip_ci_not_promoted_to_main(self):
        row=self.s["proposed_slate"][0]
        row.update({
            "unmerged_code_7d":2,"unmerged_tests_7d":1,
            "branch_scan_complete":True,
            "feature_branch_ci":[{
                "branch":"feature/b","tip_sha":"a"*40,
                "status":"all_observed_runs_successful",
                "observed_workflow_count":2,
                "sample_run_urls":[
                    "https://github.com/owner/foo/actions/runs/123"],
                "not_main_or_runtime_evidence":True,
            }],
        })
        report=render(self.s,self.d)
        self.assertIn("Ejecuciones CI en puntas", report)
        self.assertIn("feature/b", report)
        self.assertIn("https://github.com/owner/foo/actions/runs/123",report)
        self.assertIn("independientes de main",report)

    def test_rejects_private_injections(self):
        self.s["proposed_slate"][0]["visibility"]="private"
        with self.assertRaisesRegex(ValueError,"privado"):
            render(self.s,self.d)

    def test_rejects_any_autopublish(self):
        self.s["proposed_slate"][0]["publishable"]=True
        with self.assertRaisesRegex(ValueError,"indebidamente"):
            render(self.s,self.d)



    def test_historical_candidate_is_reported_but_not_published(self):
        self.s["historical_watchlist"] = [{
            "visibility": "public", "publishable": False,
            "title": "Historic", "strategic_priority": 2,
            "watch_reason": "no_substantive_activity_30d"}]
        text = render(self.s, self.d)
        self.assertIn("Proyectos históricos", text)
        self.assertIn("Historic", text)
        self.assertIn("evidencia nueva", text)

    def test_private_historical_entry_is_refused(self):
        self.s["historical_watchlist"] = [{
            "visibility": "private", "publishable": False,
            "title": "Hidden", "strategic_priority": 4}]
        with self.assertRaisesRegex(ValueError, "privado"):
            render(self.s, self.d)


if __name__ == "__main__":
    unittest.main()
