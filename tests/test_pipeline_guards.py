"""Regresiones: nunca publicar datos parciales ni leer repos privados."""
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from github import GithubException
from src import collect, synthesize


class TestCollectorGuards(unittest.TestCase):
    def test_bad_credentials_is_fatal(self):
        gh = Mock()
        gh.get_repo.side_effect = GithubException(401, {"message": "Bad credentials"})
        with self.assertRaisesRegex(RuntimeError, "no se pudo acceder"):
            collect.collect_repo(gh, "example/repo", {}, datetime.now(timezone.utc),
                                 datetime.now(timezone.utc), set())

    def test_private_repo_is_rejected(self):
        gh = Mock()
        gh.get_repo.return_value = SimpleNamespace(private=True)
        with self.assertRaisesRegex(RuntimeError, "privado bloqueado"):
            collect.collect_repo(gh, "example/private", {}, datetime.now(timezone.utc),
                                 datetime.now(timezone.utc), set())


class TestSynthesisGuards(unittest.TestCase):
    def test_missing_summary_is_fatal(self):
        with self.assertRaisesRegex(RuntimeError, "síntesis incompleta"):
            synthesize.ensure_complete_summaries(
                [{"name": "example/repo"}], [])

    def test_complete_summaries_allowed(self):
        synthesize.ensure_complete_summaries(
            [{"name": "example/repo"}], [{"name": "example/repo"}])

    def test_retired_models_are_not_defaults(self):
        self.assertNotIn("nvidia/llama-3.3-nemotron-super-49b-v1", synthesize.FALLBACK_MODELS)
        self.assertTrue(synthesize.FALLBACK_MODELS)


if __name__ == "__main__":
    unittest.main()
