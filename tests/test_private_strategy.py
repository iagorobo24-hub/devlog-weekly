import os
import unittest
from unittest.mock import patch

from src.private_strategy import build, run


class PrivateStrategyTests(unittest.TestCase):
    def setUp(self):
        self.sel = {"visibility": "private-local", "ranked": [
            {"visibility": "private", "repos": ["owner/repo"], "activity_score": 44}]}
        self.quality = {"visibility": "private-local", "records": [
            {"visibility": "private", "repo": "owner/repo",
             "ci": {"status": "failure_or_cancelled"},
             "test_path_present": True, "readiness": "ci_failure_needs_review"}]}
        self.local = {"visibility": "private-local", "projects_to_review": [
            {"repo": "owner/repo", "review": "local_tracked_changes_require_review"}]}
        self.cfg = {"version": 1, "proposals": [
            {"repo": "owner/repo", "priority": 5, "basis": "inferred_proposal",
             "rationale": "User's active development objective, awaiting explicit confirmation"}]}

    def test_high_importance_cannot_hide_ci_failure(self):
        row = build(self.sel, self.quality, self.local, self.cfg)["ranked_for_private_review"][0]
        self.assertEqual(row["priority"], 5)
        self.assertIn("diagnose_ci_at_head", row["reasons_to_review"])
        self.assertIn("strategic_priority_not_owner_confirmed", row["reasons_to_review"])
        self.assertFalse(row["publishable"])

    def test_no_priority_not_guessed_from_commit_count(self):
        x = build(self.sel, self.quality, self.local, {"version":1,"proposals":[]})
        self.assertIsNone(x["ranked_for_private_review"][0]["priority"])

    def test_refuses_public_quality(self):
        self.quality["records"][0]["visibility"] = "public"
        with self.assertRaisesRegex(ValueError, "contaminada"):
            build(self.sel, self.quality, self.local, self.cfg)

    def test_banned_under_ci(self):
        with patch.dict(os.environ, {"CI": "true"}):
            with self.assertRaisesRegex(RuntimeError, "prohibida"):
                run()

    def test_local_only_minecraft_remains_private_and_unscored(self):
        self.local["projects_to_review"].append({
            "repo": None, "local_project": "minecraft-companion",
            "review": "local_tracked_changes_require_review"})
        self.cfg["proposals"].append({
            "repo": "local:minecraft-companion", "priority": 5,
            "basis": "inferred_proposal",
            "rationale": "User's ongoing Minecraft agent development priority"})
        data = build(self.sel,self.quality,self.local,self.cfg)
        project = data["local_only_projects"][0]
        self.assertEqual(project["priority"],5)
        self.assertTrue(project["no_github_quality_equivalence"])
        self.assertFalse(project["publishable"])

    def test_duplicate_priorities_rejected(self):
        self.cfg["proposals"].append(dict(self.cfg["proposals"][0]))
        with self.assertRaisesRegex(ValueError,"ambigua"):
            build(self.sel,self.quality,self.local,self.cfg)


if __name__ == "__main__":
    unittest.main()
