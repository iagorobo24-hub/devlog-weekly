import unittest
from datetime import datetime, timezone
from src.portfolio_functional_readiness import validate, extract, build

NOW = datetime(2026,10,29,21,tzinfo=timezone.utc)

def source():
    names=["T-IA-Portal-RocaRoibas","proyecto-pfc-iago-duran","GuiaIA",
           "awesome-tia-portal","atm10sky-es-es-localization"]
    cases=[]
    for i,name in enumerate(names):
        repo="iagorobo24-hub/"+name
        cases.append({"repo":repo,"revision":"a"*40,"visibility":"public",
            "head_matches_revision":True,"ready_for_publication":False,
            "independent_runtime_validated":False,"owner_permission_confirmed":False,
            "ci":{"status":"failure_or_cancelled" if i==1 else
                   "success_at_head" if i in (0,2) else "unknown",
                  "run_url":f"https://github.com/{repo}/actions/runs/9" if i<3 else None}})
    return {"schema":1,"visibility":"public","private_sources_inspected":False,
            "automatic_publication":False,"safe_to_replace_public_portfolio":False,
            "ci_reports_consistent":True,"ci_report_disagreements":[],
            "source_selection_generated_at":NOW.isoformat(),"cases":cases}

def jobs(repo,rid):
    if "pfc" in repo:
        states=[("Lint","success"),("Production dependency audit","failure"),
                ("Unit tests","skipped"),("Production build","skipped"),
                ("End-to-end tests","skipped")]
        status="failure"
    elif "GuiaIA" in repo:
        states=[("Run unittest suite","success")];status="success"
    else:
        states=[("Run Run-WorkspaceChecks.ps1","success")];status="success"
    return {"total_count":1,"jobs":[{"conclusion":status,
        "steps":[{"name":name,"conclusion":state} for name,state in states]}]}

class ReadinessTests(unittest.TestCase):
    def test_exact_job_steps_report_skipped_pfc(self):
        report=build(source(),jobs,NOW)
        pfc=report["cases"][1]
        self.assertEqual(len(pfc["security_failures"]),1)
        self.assertEqual(len(pfc["checks_skipped"]),3)
        self.assertTrue(pfc["ci_jobs_consistent"])
        self.assertFalse(pfc["publication_approved"])

    def test_unit_and_workspace_not_runtime(self):
        report=build(source(),jobs,NOW)
        self.assertEqual(len(report["cases"][0]["checks_passed"]),1)
        self.assertEqual(len(report["cases"][2]["checks_passed"]),1)
        self.assertFalse(report["runtime_certification"])

    def test_empty_ci_not_synthetic_success(self):
        report=build(source(),jobs,NOW)
        self.assertEqual(report["cases"][4]["inspection"],"no_push_run")
        self.assertEqual(report["cases"][4]["checks_passed"],[])

    def test_bogus_run_or_private_report_rejected(self):
        x=source();x["cases"][0]["ci"]["run_url"]="https://evil.com"
        with self.assertRaisesRegex(ValueError,"URL de run"):
            validate(x)
        x=source();x["cases"][0]["head_matches_revision"]=False
        with self.assertRaisesRegex(ValueError,"desfasado"):
            validate(x)

    def test_incomplete_jobs_blocked(self):
        with self.assertRaisesRegex(ValueError,"incompletos"):
            extract({"total_count":2,"jobs":[{"conclusion":"success","steps":[]}]})
        output=build(source(),lambda repo,rid:{"total_count":1,
                     "jobs":[{"conclusion":"success","steps":[]}]},NOW)
        self.assertFalse(output["cases"][1]["ci_jobs_consistent"])
        self.assertFalse(output["safe_to_publish"])

if __name__=="__main__":
    unittest.main()
