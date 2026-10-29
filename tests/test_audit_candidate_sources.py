from copy import deepcopy
from datetime import datetime, timezone
import unittest

from github.GithubException import GithubException

from src.audit_candidate_sources import _parse_source, build, _get_public_repo

NAME = "iagorobo24-hub/example"
SHA = "a" * 40
NOW = datetime(2026, 10, 29, 15, tzinfo=timezone.utc)
FILE_URL = f"https://github.com/{NAME}/blob/{SHA}/README.md"
DIR_URL = f"https://github.com/{NAME}/tree/{SHA}/tests"


class FakeContent:
    type = "file"


class FakeRepo:
    private = False
    def __init__(self, answers=None):
        self.answers = answers or {}
        self.calls = []
    def get_contents(self, path, ref):
        self.calls.append((path, ref))
        response = self.answers.get(path)
        if isinstance(response, Exception):
            raise response
        return response if response is not None else FakeContent()


class FakeClient:
    def __init__(self, repo=None):
        self.repo = repo or FakeRepo()
        self.calls = []
    def get_repo(self, name):
        self.calls.append(name)
        return self.repo


def source(kind, url):
    return {"statement": "Documented source at immutable commit",
            "evidence_kind": kind, "url": url}


class SourceAuditTests(unittest.TestCase):
    def setUp(self):
        self.drafts = {"schema": 1, "visibility": "public",
                       "automatic_publication": False,
                       "drafts": [{
                           "repo": NAME, "revision": SHA, "visibility": "public",
                           "draft_only": True, "publication_allowed": False,
                           "sources": [source("documented", FILE_URL),
                                       source("repository_directory", DIR_URL)]}]}
        self.quality = {"schema": 1, "visibility": "public",
                        "generated_at": NOW.isoformat(),
                        "source_selection_generated_at": NOW.isoformat(),
                        "records": [{
                            "repo": NAME, "head": SHA, "visibility": "public",
                            "ci": {"status": "success_at_head",
                                   "run_url": f"https://github.com/{NAME}/actions/runs/1234"}}]}
        self.client = FakeClient(FakeRepo({"tests": []}))

    def report(self):
        return build(self.drafts, self.quality, self.client, now=NOW)

    def test_both_sources_at_exact_sha_with_real_ci_link(self):
        row = self.report()["probes"][0]
        self.assertTrue(row["all_sources_exist_at_pinned_revision"])
        self.assertEqual(self.client.repo.calls, [("README.md", SHA), ("tests", SHA)])
        self.assertTrue(row["ci_run_url_at_head"].endswith("/1234"))
        self.assertTrue(all(not x["statement_semantically_verified"] and
                            not x["proves_runtime_functionality"] for x in row["sources"]))

    def test_missing_document_is_not_success(self):
        self.client.repo.answers["README.md"] = GithubException(404, {"message": "not found"})
        item = self.report()["probes"][0]
        self.assertFalse(item["all_sources_exist_at_pinned_revision"])
        self.assertEqual(item["sources"][0]["status"], "missing")

    def test_wrong_type_is_not_success(self):
        self.client.repo.answers["tests"] = FakeContent()
        item = self.report()["probes"][0]
        self.assertEqual(item["sources"][1]["status"], "type_mismatch")
        self.assertFalse(item["all_sources_exist_at_pinned_revision"])

    def test_rate_limit_is_not_coerced_to_missing_or_success(self):
        self.client.repo.answers["README.md"] = GithubException(403, {"message": "rate limit"})
        item = self.report()["probes"][0]
        self.assertEqual(item["sources"][0]["status"], "unavailable")
        self.assertFalse(item["all_sources_exist_at_pinned_revision"])

    def test_private_repo_fails_before_reading_files(self):
        self.client.repo.private = True
        with self.assertRaisesRegex(ValueError, "Private repository"):
            self.report()
        self.assertEqual(self.client.repo.calls, [])

    def test_stale_revision_makes_zero_remote_calls(self):
        self.quality["records"][0]["head"] = "b" * 40
        item = self.report()["probes"][0]
        self.assertEqual(item["sources"][0]["status"], "revision_outdated")
        self.assertFalse(item["all_sources_exist_at_pinned_revision"])
        self.assertIsNone(item["ci_run_url_at_head"])
        self.assertEqual(self.client.calls, [])

    def test_invalid_url_or_traversal_is_rejected(self):
        self.drafts["drafts"][0]["sources"][0]["url"] = "https://evil.test/a"
        with self.assertRaisesRegex(ValueError, "Foreign"):
            self.report()
        self.drafts["drafts"][0]["sources"][0]["url"] = FILE_URL.replace(
            "/README.md", "/../README.md")
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.report()

    def test_wrong_link_type_rejected(self):
        self.drafts["drafts"][0]["sources"][1]["url"] = DIR_URL.replace("/tree/", "/blob/")
        with self.assertRaisesRegex(ValueError, "unpinned"):
            self.report()

    def test_private_input_or_autopublish_fails_closed(self):
        self.drafts["drafts"][0]["visibility"] = "private"
        with self.assertRaisesRegex(ValueError, "Private"):
            self.report()
        self.drafts["drafts"][0]["visibility"] = "public"
        self.drafts["automatic_publication"] = True
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            self.report()

    def test_fake_ci_link_rejected_without_discarding_file_evidence(self):
        self.quality["records"][0]["ci"]["run_url"] = "https://attacker.test/123"
        item = self.report()["probes"][0]
        self.assertIsNone(item["ci_run_url_at_head"])
        self.assertTrue(item["all_sources_exist_at_pinned_revision"])

    def test_multiple_claims_can_share_a_verified_source_without_extra_api_calls(self):
        self.drafts["drafts"][0]["sources"].append(
            deepcopy(self.drafts["drafts"][0]["sources"][0]))
        row = self.report()["probes"][0]
        self.assertTrue(row["all_sources_exist_at_pinned_revision"])
        self.assertEqual(len(row["sources"]), 3)
        self.assertEqual(self.client.repo.calls, [("README.md", SHA), ("tests", SHA)])


if __name__ == "__main__":
    unittest.main()
