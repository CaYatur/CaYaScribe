from __future__ import annotations

import hmac
import os

from fastapi import Header, HTTPException


def expected_token() -> str:
    token = os.environ.get("CAYA_TOKEN", "")
    if not token:
        raise RuntimeError("CAYA_TOKEN is not set")
    return token


def require_bearer(authorization: str | None = Header(default=None)) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing_token")
    got = authorization.split(" ", 1)[1].strip()
    if not hmac.compare_digest(got, expected_token()):
        raise HTTPException(status_code=401, detail="bad_token")
