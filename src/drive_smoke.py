"""Drive read/write check using a small synthetic valid PDF and a unique remote path.

No GitHub collection, NVIDIA requests, portfolio rendering or state mutations.
The remote object is intentionally retained for audit in Portfolio/verificaciones.
"""
from __future__ import annotations

import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile

try:
    from src.drive_readiness import check_drive_config
    from src.publish import upload
except ModuleNotFoundError:
    from drive_readiness import check_drive_config
    from publish import upload


def synthetic_pdf() -> bytes:
    """Generate a minimal one-page PDF without network, browser or personal data."""
    stream = b"BT /F1 16 Tf 40 150 Td (Devlog Weekly - Drive smoke test) Tj ET\n"
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 220] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode("ascii") +
        b" >>\nstream\n" + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    )
    document = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, payload in enumerate(objects, start=1):
        offsets.append(len(document))
        document.extend(f"{index} 0 obj\n".encode() + payload + b"\nendobj\n")
    xref_offset = len(document)
    document.extend(f"xref\n0 {len(offsets)}\n".encode())
    document.extend(b"0000000000 65535 f \n")
    for value in offsets[1:]:
        document.extend(f"{value:010d} 00000 n \n".encode())
    document.extend(
        f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )
    return bytes(document)


def run_smoke(*, config: str, remote: str, run_id: str, attempt: str,
              client_id: str = "", client_secret: str = "") -> dict[str, str]:
    check_drive_config(config, remote, client_id, client_secret)
    if not re.fullmatch(r"[0-9]{5,20}", run_id):
        raise ValueError("GITHUB_RUN_ID no canónico")
    if not re.fullmatch(r"[0-9]{1,6}", attempt):
        raise ValueError("GITHUB_RUN_ATTEMPT no canónico")
    dest = f"{remote}:Portfolio/verificaciones/{run_id}-{attempt}/devlog.pdf"
    payload = synthetic_pdf()
    digest = hashlib.sha256(payload).hexdigest()
    with tempfile.TemporaryDirectory(prefix="devlog-drive-smoke-") as root:
        source = Path(root) / "synthetic.pdf"
        restored = Path(root) / "readback.pdf"
        source.write_bytes(payload)
        upload(source, dest, config, remote, immutable=True)
        upload(Path(dest), str(restored), config, remote)
        if (hashlib.sha256(restored.read_bytes()).hexdigest() != digest
                or source.read_bytes() != payload):
            raise ValueError("Drive devolvió bytes distintos del PDF sintético")
    return {"result": "verified", "remote_path": dest, "sha256": digest}


def main() -> None:
    conf = os.environ.get("RCLONE_CONF", "")
    remote = os.environ.get("RCLONE_REMOTE", "gdrive")
    result = run_smoke(
        config=conf,
        remote=remote,
        run_id=os.environ.get("GITHUB_RUN_ID", ""),
        attempt=os.environ.get("GITHUB_RUN_ATTEMPT", "1"),
        client_id=os.environ.get("RCLONE_DRIVE_CLIENT_ID", ""),
        client_secret=os.environ.get("RCLONE_DRIVE_CLIENT_SECRET", ""),
    )
    print("DRIVE SMOKE: subida y descarga SHA-256 verificadas")
    print("Ruta aislada:", result["remote_path"])
    print("SHA-256:", result["sha256"])


if __name__ == "__main__":
    main()
