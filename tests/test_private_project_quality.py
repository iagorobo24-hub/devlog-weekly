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

if __name__=="__main__":
    unittest.main()
