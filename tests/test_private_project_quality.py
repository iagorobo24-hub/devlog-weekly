import os
import unittest
from datetime import datetime,timezone
from unittest.mock import Mock,patch
from src.private_project_quality import from_selection,run

NOW=datetime(2026,10,29,14,tzinfo=timezone.utc)

class PrivateQualityTests(unittest.TestCase):
    def test_refuses_mixed_visibility_before_probe(self):
        s={"visibility":"private-local","ranked":[
           {"visibility":"public","repos":["owner/public"]}]}
        g=Mock()
        with self.assertRaisesRegex(ValueError,"contaminación"):
            from_selection(s,g,NOW)
        g.get_repo.assert_not_called()

    def test_rejects_public_selection(self):
        with self.assertRaisesRegex(ValueError,"pública"):
            from_selection({"visibility":"public","ranked":[]},Mock(),NOW)

    def test_banned_in_ci(self):
        with patch.dict(os.environ,{"GITHUB_ACTIONS":"true"}):
            with self.assertRaisesRegex(RuntimeError,"prohibida"):
                run(selection={"visibility":"private-local","ranked":[]},github_client=Mock())


    def test_evaluates_private_overflow_without_public_access(self):
        s = {"visibility": "private-local",
             "ranked": [{"visibility": "private", "repos": ["owner/one"]}],
             "other_active": [{"visibility": "private", "repos": ["owner/two"]}]}
        with patch("src.private_project_quality.private_repo_facts",
                   side_effect=lambda _, name: {"repo": name, "visibility": "private",
                       "head": "a" * 40, "default_branch": "main", "readme": True,
                       "test_paths": False, "workflows": False, "runs": []}) as probe:
            result = from_selection(s, Mock(), NOW)
        self.assertEqual([r["repo"] for r in result["records"]],
                         ["owner/one", "owner/two"])
        self.assertEqual(probe.call_count, 2)

    def test_rejects_public_overflow_before_probing_any_repo(self):
        s = {"visibility": "private-local",
             "ranked": [{"visibility": "private", "repos": ["owner/one"]}],
             "other_active": [{"visibility": "public", "repos": ["owner/public"]}]}
        with patch("src.private_project_quality.private_repo_facts") as probe:
            with self.assertRaisesRegex(ValueError, "contaminación"):
                from_selection(s, Mock(), NOW)
        probe.assert_not_called()


if __name__=="__main__":
    unittest.main()
