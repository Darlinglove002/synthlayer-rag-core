"""Smoke test for the running stack, going through the web container's /api proxy.

    python scripts/smoke.py [http://localhost:8030]

Uploads one eval PDF, asks two questions, checks the cited page, then cleans up.
Standard library only, so it runs anywhere (CI runner, laptop) without installing anything.
"""

import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8030").rstrip("/")
PDF = Path(__file__).parent.parent / "eval" / "corpus" / "brightbay_admin_guide.pdf"


def call(method: str, path: str, body: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(
        BASE + "/api" + path, data=body, headers=headers or {}, method=method
    )
    try:
        with urllib.request.urlopen(req, timeout=180) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None)
    except urllib.error.HTTPError as e:
        return e.code, None


def upload(name: str, data: bytes):
    boundary = uuid.uuid4().hex
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{name}"\r\n'
            f"Content-Type: application/pdf\r\n\r\n"
        ).encode()
        + data
        + f"\r\n--{boundary}--\r\n".encode()
    )
    return call(
        "POST", "/documents", body, {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    )


def ask(q: str) -> dict:
    status, out = call(
        "POST", "/ask", json.dumps({"query": q}).encode(), {"Content-Type": "application/json"}
    )
    assert status == 200, f"/ask returned {status}"
    return out


def main() -> None:
    assert call("GET", "/health")[0] == 200, "api not healthy through the proxy"
    status, doc = upload(PDF.name, PDF.read_bytes())
    assert status == 201, f"upload failed: {status}"
    try:
        a = ask("How long are old snapshots kept before being deleted?")
        assert a["grounded"] and "14 days" in a["answer"], a["answer"]
        assert a["citations"][0]["page"] == 2, a["citations"]
        print("in-scope  OK :", a["answer"])

        b = ask("What is the capital of France?")
        assert not b["grounded"], b["answer"]
        print("off-topic OK :", b["answer"])
    finally:
        call("DELETE", f"/documents/{doc['document_id']}")
    print("smoke test passed")


if __name__ == "__main__":
    main()
