"""Read-only, fail-closed preflight for the private Google Drive OAuth config.

This checks static configuration only, never contacts Google and never echoes
secrets, tokens, client identifiers or raw config input.
"""
from __future__ import annotations

import configparser
import json
import os
import re


class DriveReadinessError(ValueError):
    """A non-sensitive deployment readiness problem."""


def check_drive_config(config: str | None, remote: str = "gdrive",
                       client_id: str | None = None,
                       client_secret: str | None = None) -> dict[str, str]:
    if not isinstance(remote, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", remote):
        raise DriveReadinessError("nombre de remote inválido")
    if not isinstance(config, str) or not config.strip():
        raise DriveReadinessError("falta configuración de Drive (RCLONE_CONF)")
    if len(config) > 65536:
        raise DriveReadinessError("configuración de Drive excesiva")

    parser = configparser.ConfigParser(interpolation=None, strict=True)
    try:
        parser.read_string(config)
    except configparser.Error as exc:
        raise DriveReadinessError("RCLONE_CONF no tiene formato INI válido") from None

    if not parser.has_section(remote):
        raise DriveReadinessError("remote de Drive no encontrado en RCLONE_CONF")
    selected = parser[remote]
    if selected.get("type", "").strip().lower() != "drive":
        raise DriveReadinessError("el remote de publicación no es Google Drive")
    if selected.get("service_account_file", "").strip() or selected.get(
            "service_account_credentials", "").strip():
        raise DriveReadinessError("Drive personal requiere OAuth de usuario, no service account")

    external_id = (client_id or "").strip()
    external_secret = (client_secret or "").strip()
    if bool(external_id) != bool(external_secret):
        raise DriveReadinessError("credenciales OAuth externas incompletas")
    embedded_id = selected.get("client_id", "").strip()
    embedded_secret = selected.get("client_secret", "").strip()
    if external_id and external_secret:
        credential_location = "variables"
    elif embedded_id and embedded_secret:
        credential_location = "configuración"
    else:
        raise DriveReadinessError("falta un par de credenciales OAuth propias")

    raw_token = selected.get("token", "").strip()
    if not raw_token:
        raise DriveReadinessError("falta token OAuth de Drive")
    try:
        token = json.loads(raw_token)
    except (ValueError, TypeError):
        raise DriveReadinessError("token OAuth no es JSON válido") from None
    if not isinstance(token, dict) or not isinstance(token.get("refresh_token"), str) or not token["refresh_token"].strip():
        raise DriveReadinessError("falta refresh_token OAuth en RCLONE_CONF")

    return {
        "result": "ready_for_live_auth_test",
        "remote_type": "drive",
        "oauth_credentials": credential_location,
        "oauth_refresh": "configured",
    }


def main() -> None:
    import sys
    try:
        check_drive_config(
            os.environ.get("RCLONE_CONF"),
            os.environ.get("RCLONE_REMOTE", "gdrive"),
            os.environ.get("RCLONE_DRIVE_CLIENT_ID"),
            os.environ.get("RCLONE_DRIVE_CLIENT_SECRET"),
        )
    except DriveReadinessError as exc:
        print(f"DRIVE PREFLIGHT BLOQUEADO: {exc}", file=sys.stderr)
        raise SystemExit(1) from None
    print("DRIVE PREFLIGHT ESTÁTICO: válido; OAuth remoto y permisos aún sin verificar")


if __name__ == "__main__":
    main()
