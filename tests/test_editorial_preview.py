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

    def test_rejects_private_injections(self):
        self.s["proposed_slate"][0]["visibility"]="private"
        with self.assertRaisesRegex(ValueError,"privado"):
            render(self.s,self.d)

    def test_rejects_any_autopublish(self):
        self.s["proposed_slate"][0]["publishable"]=True
        with self.assertRaisesRegex(ValueError,"indebidamente"):
            render(self.s,self.d)


if __name__ == "__main__":
    unittest.main()
