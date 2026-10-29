import hashlib
import unittest
from src.verify_editorial_review_pdf import validate_source

NAMES = ["iagorobo24-hub/"+n for n in (
    "T-IA-Portal-RocaRoibas", "proyecto-pfc-iago-duran", "GuiaIA",
    "awesome-tia-portal", "atm10sky-es-es-localization", "AUTOMATON")]
KEYWORDS = (
    "SELECCIÓN EDITORIAL", "TIA Portal RocaRoibas PFC Tools GuiaIA",
    "TIA Portal RocaRoibas 44 scripts", "PFC Tools siete",
    "GuiaIA Cuatro herramientas", "Awesome TIA Portal",
    "ATM10 6.462", "AUTOMATON", "PUBLICACIÓN")
MD = "---\nmarp: true\ntheme: portfolio-v2\n---\n" + "\n---\n".join(
    "<!-- _class: pf-closure-test --> BORRADOR INTERNO · NO PUBLICAR " + x for x in KEYWORDS)


def manifest():
    return {"schema": 1, "visibility": "public",
            "selection_status": "frozen_editorial_scope_not_release_approval",
            "curated_portfolio_unchanged": True, "publication_approved": False,
            "automatic_publication": False,
            "main_cases": NAMES[:3], "supporting_cases": NAMES[3:5],
            "excluded_cases": NAMES[5:], "slide_count": 9,
            "markdown_sha256": hashlib.sha256(MD.encode()).hexdigest()}


class PdfSourceTests(unittest.TestCase):
    def test_accepts_guarded_nine_pages(self):
        self.assertEqual(validate_source(MD, manifest())["pages"], 9)

    def test_tampered_markdown_blocked(self):
        with self.assertRaisesRegex(ValueError, "SHA256"):
            validate_source(MD+"!", manifest())

    def test_publication_not_authorized(self):
        m=manifest();m["publication_approved"]=True
        with self.assertRaisesRegex(ValueError, "no autorizado"):
            validate_source(MD,m)

    def test_private_repo_blocked(self):
        m=manifest();m["main_cases"][0]="private/example"
        with self.assertRaisesRegex(ValueError, "privado"):
            validate_source(MD,m)

    def test_missing_slide_blocked(self):
        changed=MD.replace("<!-- _class:", "<!-- broken:",1)
        m=manifest();m["markdown_sha256"]=hashlib.sha256(changed.encode()).hexdigest()
        with self.assertRaisesRegex(ValueError, "incompleto"):
            validate_source(changed,m)

    def test_missing_key_text_blocked(self):
        changed=MD.replace("44 scripts","40 scripts")
        m=manifest();m["markdown_sha256"]=hashlib.sha256(changed.encode()).hexdigest()
        with self.assertRaisesRegex(ValueError,"editorial esperado"):
            validate_source(changed,m)


if __name__ == "__main__":
    unittest.main()
