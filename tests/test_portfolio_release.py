import unittest
from unittest.mock import patch
from src import run_portfolio_v2 as release


class ReleaseContracts(unittest.TestCase):
    def test_skip_without_showcase_events(self):
        with patch.object(release,"had_showcase_activity_this_week",return_value=False):
            self.assertFalse(release.should_build())
        with patch.object(release,"had_showcase_activity_this_week",return_value=False):
            with patch.object(release,"write_preview") as renderer:
                self.assertFalse(release.prepare())
                renderer.assert_not_called()

    def test_force_is_explicit_opt_in(self):
        self.assertTrue(release.should_build(force=True))


if __name__ == "__main__":
    unittest.main()
