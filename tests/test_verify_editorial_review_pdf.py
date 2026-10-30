import hashlib
import unittest
from src.verify_editorial_review_pdf import validate_source, verified_link

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
            "ci_evidence_synced": True,
            "evidence_report_sha256": "a"*64,
            "observed_ci_by_repo": {r: "unknown" for r in NAMES[:5]},
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

    def test_pdf_source_refuses_old_nonreconciled_ci_manifest(self):
        m=manifest();m["ci_evidence_synced"]=False
        with self.assertRaisesRegex(ValueError,"sin CI reconciliada"):
            validate_source(MD,m)

    def test_pdf_source_refuses_missing_ci_case_and_forged_hash(self):
        m=manifest();m["observed_ci_by_repo"].pop(NAMES[2])
        with self.assertRaisesRegex(ValueError,"sin CI reconciliada"):
            validate_source(MD,m)
        m=manifest();m["evidence_report_sha256"]="invalid"
        with self.assertRaisesRegex(ValueError,"sin CI reconciliada"):
            validate_source(MD,m)

    def test_ci_action_link_must_be_canonical(self):
        from src.verify_editorial_review_pdf import CI_RUN
        self.assertIsNotNone(CI_RUN.fullmatch(
            "/iagorobo24-hub/GuiaIA/actions/runs/40821224773"))
        self.assertIsNone(CI_RUN.fullmatch(
            "/other-user/GuiaIA/actions/runs/40821224773"))
        self.assertIsNone(CI_RUN.fullmatch(
            "/iagorobo24-hub/GuiaIA/actions/runs/not-a-number"))

    def test_only_evidence_from_the_slide_owner_is_accepted(self):
        repo=NAMES[0]
        good="https://github.com/"+repo+"/blob/"+"a"*40+"/README.md"
        self.assertTrue(verified_link(good,repo))
        self.assertFalse(verified_link(good,NAMES[2]))
        self.assertFalse(verified_link(good+"?download=1",repo))
        self.assertFalse(verified_link(good+"#fragment",repo))
        self.assertFalse(verified_link(good.replace("/README.md","/../README.md"),repo))
        self.assertFalse(verified_link("https://github.com.evil.com/"+repo+"/blob/"+"a"*40+"/README.md",repo))

    def test_source_links_are_pinned_to_correct_page(self):
        good="https://github.com/"+NAMES[0]+"/blob/"+"a"*40+"/README.md"
        changed=MD.replace("TIA Portal RocaRoibas 44 scripts",
                           'TIA Portal RocaRoibas 44 scripts <a href="'+good+'">evidence</a>')
        m=manifest();m["markdown_sha256"]=hashlib.sha256(changed.encode()).hexdigest()
        out=validate_source(changed,m)
        self.assertEqual(out["expected_page_links"][2],[good])
        self.assertTrue(all(not links for i,links in enumerate(out["expected_page_links"]) if i!=2))

    def test_source_rejects_foreign_link_on_a_case_page(self):
        foreign="https://github.com/"+NAMES[2]+"/blob/"+"a"*40+"/README.md"
        changed=MD.replace("TIA Portal RocaRoibas 44 scripts",
                           'TIA Portal RocaRoibas 44 scripts <a href="'+foreign+'">wrong</a>')
        m=manifest();m["markdown_sha256"]=hashlib.sha256(changed.encode()).hexdigest()
        with self.assertRaisesRegex(ValueError,"enlace ajeno"):
            validate_source(changed,m)

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
