"""429/403 rate limits must not produce silent empty weekly or historical data."""
import argparse
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from github import GithubException
from src import collect, backfill

NOW = datetime(2026, 10, 29, 20, tzinfo=timezone.utc)


def error(status=429, message="API rate limit exceeded", headers=None):
    return GithubException(status, {"message": message}, headers=headers or {})


class RateLimitTests(unittest.TestCase):
    def test_retry_429_exponential_then_full_success(self):
        steps = [error(headers={"Retry-After": "1"}),
                 error(headers={"Retry-After": "1"}), "complete"]
        fn = Mock(side_effect=steps)
        with patch.object(collect.time, "sleep") as sleeper:
            self.assertEqual(collect.with_rate_limit_backoff(fn), "complete")
        self.assertEqual(fn.call_count, 3)
        self.assertEqual([call.args[0] for call in sleeper.call_args_list], [1, 2])

    def test_primary_403_rate_limit_reset_header_case_insensitive(self):
        exc = error(403, "unknown", {"x-RaTeLiMiT-ReMaInInG": "0",
                                     "X-RateLimit-Reset": "1018"})
        fn = Mock(side_effect=[exc, 12])
        with patch.object(collect.time, "sleep") as sleeper, patch.object(collect.time, "time", return_value=1000):
            self.assertEqual(collect.with_rate_limit_backoff(fn), 12)
        sleeper.assert_called_once_with(19)

    def test_retry_after_wins_and_oversized_retry_after_fails_closed(self):
        fn = Mock(side_effect=[error(headers={"Retry-After": "7"}), 2])
        with patch.object(collect.time, "sleep") as sleeper:
            self.assertEqual(collect.with_rate_limit_backoff(fn), 2)
        sleeper.assert_called_once_with(7)

        too_long = Mock(side_effect=error(headers={"Retry-After": "3600"}))
        with patch.object(collect.time, "sleep") as sleeper:
            with self.assertRaisesRegex(RuntimeError, "presupuesto"):
                collect.with_rate_limit_backoff(too_long)
            sleeper.assert_not_called()
        too_long.assert_called_once()

    def test_conflicting_headers_wait_for_later_primary_reset(self):
        both = error(403, "API rate limit exceeded", {
            "Retry-After": "2", "X-RateLimit-Remaining": "0",
            "X-RateLimit-Reset": "1018"})
        fn = Mock(side_effect=[both, "complete"])
        with patch.object(collect.time, "sleep") as sleeper, patch.object(collect.time, "time", return_value=1000):
            self.assertEqual(collect.with_rate_limit_backoff(fn), "complete")
        sleeper.assert_called_once_with(19)

    def test_invalid_retry_after_fails_closed_not_ignored(self):
        with patch.object(collect.time, "sleep") as sleeper:
            with self.assertRaisesRegex(RuntimeError, "Retry-After"):
                collect.with_rate_limit_backoff(
                    Mock(side_effect=error(headers={"Retry-After": "nan"})))
            sleeper.assert_not_called()

    def test_no_cooldown_header_waits_at_least_sixty_seconds(self):
        # GitHub forbids short retries for secondary rate limits without headers.
        fn = Mock(side_effect=[error(403, "secondary rate limit exceeded"), "complete"])
        with patch.object(collect.time, "sleep") as sleeper:
            self.assertEqual(collect.with_rate_limit_backoff(fn), "complete")
        sleeper.assert_called_once_with(60)

    def test_repeated_no_header_limit_aborts_instead_of_hammering(self):
        fn = Mock(side_effect=error())
        with patch.object(collect.time, "sleep") as sleeper:
            with self.assertRaisesRegex(RuntimeError, "presupuesto"):
                collect.with_rate_limit_backoff(fn)
        # First 60-second cooldown is budgeted; next requires 120 more.
        self.assertEqual(fn.call_count, 2)
        sleeper.assert_called_once_with(60)

    def test_secondary_403_message_retries_but_nonrate_403_does_not(self):
        self.assertTrue(collect.is_rate_limited(error(
            403, "You have exceeded a secondary rate limit")))
        for exc in (error(401, "Bad credentials"), error(
                403, "Resource not accessible by integration"), error(404, "Not found")):
            self.assertFalse(collect.is_rate_limited(exc))
            fn = Mock(side_effect=exc)
            with patch.object(collect.time, "sleep") as sleeper:
                with self.assertRaises(GithubException):
                    collect.with_rate_limit_backoff(fn)
                sleeper.assert_not_called()
            fn.assert_called_once()

    def test_exhaustion_raises_no_success(self):
        fn = Mock(side_effect=error(headers={"Retry-After": "1"}))
        with patch.object(collect.time, "sleep") as sleeper:
            with self.assertRaisesRegex(RuntimeError, "agotados"):
                collect.with_rate_limit_backoff(fn)
        self.assertEqual(fn.call_count, 4)
        self.assertEqual([c.args[0] for c in sleeper.call_args_list], [1, 2, 4])

    def test_rate_limit_never_turned_into_missing_readme(self):
        repo = Mock()
        repo.get_readme.side_effect = error(429)
        with self.assertRaises(GithubException):
            collect.collect_readme_excerpt(repo)
        repo.get_readme.side_effect = error(404, "Not Found")
        self.assertIsNone(collect.collect_readme_excerpt(repo))

    def test_rate_limit_never_turned_into_zero_diff(self):
        repo = Mock(full_name="example/repo")
        repo.compare.side_effect = error(429)
        head = SimpleNamespace(sha="b"*40, parents=[])
        with self.assertRaises(GithubException):
            collect.collect_diff_stats(repo, [head])

    def test_weekly_restart_entire_repo_after_language_limit(self):
        gh = Mock()
        repo = gh.get_repo.return_value
        repo.private = False
        repo.get_languages.side_effect = [error(headers={"Retry-After": "2"}), {"Python": 123}]
        repo.get_readme.return_value.decoded_content = b"Public README"
        with (patch.object(collect, "collect_commits", return_value=([{"sha": "a"*40}], [])) as commits,
              patch.object(collect, "collect_diff_stats", return_value={"files_changed": 0}),
              patch.object(collect, "collect_closed_issues", return_value=[]),
              patch.object(collect, "collect_closed_prs", return_value=[]),
              patch.object(collect, "collect_tags", return_value=([], [])),
              patch.object(collect.time, "sleep") as sleeper):
            result = collect.collect_repo(gh, "example/repo", {}, NOW, NOW, set())
        self.assertEqual(result["languages"], {"Python": 123})
        self.assertEqual(len(result["commits"]), 1)
        self.assertEqual(gh.get_repo.call_count, 2)
        self.assertEqual(commits.call_count, 2)
        sleeper.assert_called_once_with(2)

    def test_backfill_restarts_entire_repo_after_paginated_failure(self):
        gh = Mock()
        gh.get_repo.return_value.private = False
        with (patch.object(backfill, "collect_commits", side_effect=[
                  error(429, headers={"Retry-After": "1"}), ([{"sha": "a"*40}], [])]) as commits,
              patch.object(backfill, "collect_closed_issues", return_value=[]),
              patch.object(backfill, "collect_closed_prs", return_value=[]),
              patch.object(collect.time, "sleep") as sleeper):
            rows = backfill.collect_public_repos(
                gh, NOW, NOW, {"repos": [{"name": "example/repo"}]})
        self.assertEqual(rows[0]["commits"], [{"sha": "a"*40}])
        self.assertEqual(commits.call_count, 2)
        self.assertEqual(gh.get_repo.call_count, 2)
        sleeper.assert_called_once_with(1)

    def test_weekly_existing_output_preserved_when_limit_unresolved(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "collected.json"
            original = '{"do_not_replace": true}\n'
            target.write_text(original, encoding="utf-8")
            gh = Mock()
            gh.get_repo.side_effect = error(headers={"Retry-After": "300"})
            args = argparse.Namespace(commit_state=False, since="7d", no_state=True)
            with (patch.object(collect, "OUT_PATH", target),
                  patch.object(collect, "parse_args", return_value=args),
                  patch.object(collect, "Github", return_value=gh),
                  patch.object(collect, "load_repos_config",
                               return_value={"defaults": {}, "repos": [{"name": "example/repo"}]}),
                  patch.dict(collect.os.environ, {"GITHUB_TOKEN": "synthetic-only"}),
                  patch.object(collect.time, "sleep") as sleeper):
                with self.assertRaisesRegex(RuntimeError, "presupuesto"):
                    collect.main()
                sleeper.assert_not_called()
            self.assertEqual(target.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
