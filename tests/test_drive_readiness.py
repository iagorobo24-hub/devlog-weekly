"""Readiness gate tests without touching external Drive or showing credentials."""
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import yaml
from src.drive_readiness import DriveReadinessError, check_drive_config, main


ROOT = Path(__file__).resolve().parent.parent
SENSITIVE = {
    "client": "example-client-id-TEST-DO-NOT-USE",
    "secret": "example-client-secret-TEST-DO-NOT-USE",
    "refresh": "example-refresh-token-TEST-DO-NOT-USE",
}


def conf(*, client=True, secret=True, refresh=True, remote="gdrive", kind="drive",
         service=False):
    pairs = [f"[{remote}]", f"type = {kind}"]
    if client:
        pairs.append("client_id = " + SENSITIVE["client"])
    if secret:
        pairs.append("client_secret = " + SENSITIVE["secret"])
    if service:
        pairs.append("service_account_file = dummy-credentials.json")
    token = {"access_token": "dummy-access", "token_type": "Bearer"}
    if refresh:
        token["refresh_token"] = SENSITIVE["refresh"]
    pairs.append("token = " + json.dumps(token))
    return "\n".join(pairs) + "\n"


class DriveReadinessTests(unittest.TestCase):
    def test_embedded_custom_oauth_is_accepted_without_exposing_values(self):
        result = check_drive_config(conf())
        self.assertEqual(result["result"], "ready_for_live_auth_test")
        self.assertEqual(result["oauth_credentials"], "configuración")
        for value in SENSITIVE.values():
            self.assertNotIn(value, repr(result))

    def test_external_custom_pair_overrides_both_embedded_missing(self):
        result = check_drive_config(conf(client=False, secret=False),
                                    client_id=SENSITIVE["client"],
                                    client_secret=SENSITIVE["secret"])
        self.assertEqual(result["oauth_credentials"], "variables")
        self.assertEqual(result["oauth_refresh"], "configured")

    def test_missing_config_remote_wrong_type_and_service_account_fail(self):
        cases = [
            (None, {}, "falta configuración"),
            ("", {}, "falta configuración"),
            (conf(remote="wrong"), {}, "no encontrado"),
            (conf(kind="local"), {}, "no es Google Drive"),
            (conf(service=True), {}, "service account"),
            (conf(), {"remote": "bad:remote"}, "nombre de remote"),
        ]
        for value, kwargs, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(DriveReadinessError, message):
                    check_drive_config(value, **kwargs)

    def test_partial_or_shared_oauth_credentials_fail_closed(self):
        cases = [
            (conf(client=False, secret=False), None, None),
            (conf(client=True, secret=False), None, None),
            (conf(client=False, secret=True), None, None),
            (conf(), SENSITIVE["client"], None),
            (conf(), None, SENSITIVE["secret"]),
        ]
        for ini, client_id, client_secret in cases:
            with self.subTest(idx=cases.index((ini, client_id, client_secret))):
                with self.assertRaises(DriveReadinessError):
                    check_drive_config(ini, client_id=client_id, client_secret=client_secret)

    def test_missing_or_malformed_refresh_token_never_succeeds(self):
        with self.assertRaisesRegex(DriveReadinessError, "refresh_token"):
            check_drive_config(conf(refresh=False))
        without_refresh = conf().replace('"refresh_token"', '"not_refresh_token"')
        with self.assertRaisesRegex(DriveReadinessError, "refresh_token"):
            check_drive_config(without_refresh)
        text = conf()
        with self.assertRaisesRegex(DriveReadinessError, "JSON"):
            check_drive_config(text.replace('"refresh_token":', 'not json:'))

    def test_max_size_and_invalid_ini_do_not_echo_input(self):
        with self.assertRaisesRegex(DriveReadinessError, "excesiva"):
            check_drive_config("x" * 65537)
        secret = SENSITIVE["secret"]
        with self.assertRaises(DriveReadinessError) as caught:
            check_drive_config(f"[gdrive]\ntype = drive\nBAD_{secret}\n")
        self.assertNotIn(secret, str(caught.exception))

    def test_cli_exposes_no_secrets_and_reports_static_scope(self):
        output = io.StringIO()
        environment = {
            "RCLONE_CONF": conf(),
            "RCLONE_REMOTE": "gdrive",
            "RCLONE_DRIVE_CLIENT_ID": "",
            "RCLONE_DRIVE_CLIENT_SECRET": "",
        }
        with patch.dict(os.environ, environment), patch("sys.stdout", output):
            main()
        value = output.getvalue()
        self.assertIn("ESTÁTICO", value)
        self.assertIn("aún sin verificar", value)
        for secret in SENSITIVE.values():
            self.assertNotIn(secret, value)
        with patch.dict(os.environ, {"RCLONE_CONF": ""}), patch("sys.stderr", output):
            with self.assertRaises(SystemExit) as caught:
                main()
        self.assertEqual(caught.exception.code, 1)

    def test_weekly_gate_runs_before_any_collection_or_expensive_work(self):
        workflow = yaml.safe_load((ROOT / ".github/workflows/weekly.yml").read_text())
        steps = workflow["jobs"]["devlog"]["steps"]
        indexes = {
            key: next(i for i, step in enumerate(steps) if key in step.get("run", ""))
            for key in ("src.drive_readiness", "npm ci", "install-rclone-pinned.sh",
                        "src/collect.py", "src/synthesize.py", "src/publish.py")
        }
        first = indexes["src.drive_readiness"]
        self.assertTrue(all(first < value for key, value in indexes.items()
                            if key != "src.drive_readiness"))
        self.assertEqual(steps[first]["env"]["RCLONE_REMOTE"], "gdrive")
        self.assertIn("secrets.RCLONE_CONF", steps[first]["env"]["RCLONE_CONF"])


if __name__ == "__main__":
    unittest.main()
