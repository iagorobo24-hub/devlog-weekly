from datetime import datetime, timezone, timedelta
import os
import unittest
from unittest.mock import patch

from src import private_review as r

NOW = datetime(2026, 10, 29, 13, tzinfo=timezone.utc)


class PrivateReviewTests(unittest.TestCase):
    def selection(self):
        return {"visibility": "private-local",
                 "ranked": [{"visibility": "private", "repos": ["iagorobo24-hub/zonagemelos-clipper"]}]}

    def local(self):
        return {"visibility": "private-local", "generated_utc": NOW.isoformat(),
                "repositories": {"/home/test/clipper": {
                    "state": "inspected", "tracked_changes": 0,
                    "ahead_of_tracking_ref": 8,
                    "ahead_of_remote_verified": None,
                    "remote_check": "tracking_ref_stale_or_diverged"
                }}}

    def mapping(self):
        return {"version": 1, "mappings": [
            {"path": "/home/test/clipper",
             "repo": "iagorobo24-hub/zonagemelos-clipper"}
        ]}

    def test_stale_tracking_ref_is_not_reported_as_verified_unpushed(self):
        x=r.build_review(self.selection(),self.local(),self.mapping(),now=NOW)
        row=x["projects_to_review"][0]
        self.assertEqual(row["review"],"remote_history_diverged_or_tracking_stale")
        self.assertIsNone(row["ahead_of_remote_verified"])
        self.assertFalse(x["automatic_publication"])

    def test_dirty_files_are_flagged_without_claim_of_success(self):
        l=self.local()
        l["repositories"]["/home/test/clipper"]["tracked_changes"]=16
        row=r.build_review(self.selection(),l,self.mapping(),now=NOW)["projects_to_review"][0]
        self.assertEqual(row["review"],"local_tracked_changes_require_review")
        self.assertTrue(row["no_claim_of_validated_feature"])

    def test_stale_local_snapshot_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"desactualizadas"):
            r.build_review(self.selection(),self.local(),self.mapping(),
                           now=NOW+timedelta(days=3))

    def test_refuses_public_or_mixed_data(self):
        s=self.selection()
        s["visibility"]="public"
        with self.assertRaisesRegex(ValueError,"públicos"):
            r.build_review(s,self.local(),self.mapping(),now=NOW)

    def test_mixed_visibility_rejected(self):
        data = self.selection()
        data["ranked"][0]["visibility"] = "public"
        with self.assertRaisesRegex(ValueError, "público"):
            r.build_review(data, self.local(), self.mapping(), now=NOW)

    def test_banned_in_ci(self):
        with patch.dict(os.environ,{"CI":"true"}):
            with self.assertRaisesRegex(RuntimeError,"prohibida"):
                r.run()


if __name__=="__main__":
    unittest.main()
