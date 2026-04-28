"""
API key 발급·검증 — 32 byte urlsafe + sha256 해시 저장.

key 형식: `sg_<32-char-base64url>` — 사람이 보기에도 SG 의 키임을 알 수 있게.
DB 에는 sha256 hash 만 저장. 발급 시 plaintext 한 번만 반환.
"""

from __future__ import annotations

import hashlib
import secrets
from typing import Any

from db import repository

KEY_PREFIX = "sg_"
PLAINTEXT_LENGTH = 32  # urlsafe — 실제 길이 ~43


def _hash(plaintext: str) -> str:
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def generate_plaintext() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(PLAINTEXT_LENGTH)


def issue(
    *,
    label: str,
    monthly_quota: int = 1000,
    rpm_limit: int = 30,
    monthly_usd_quota: float = 5.0,
) -> dict[str, Any]:
    """API key 발급. plaintext 는 응답에만 1회 노출, DB 엔 hash 만 저장.

    Returns:
        {"plaintext": "sg_...", "id": ..., "label": ..., ...}
    """
    if not label.strip():
        raise ValueError("label 은 비어있을 수 없습니다.")
    plaintext = generate_plaintext()
    record = repository.create_api_key(
        label=label.strip(),
        key_hash=_hash(plaintext),
        monthly_quota=monthly_quota,
        rpm_limit=rpm_limit,
        monthly_usd_quota=monthly_usd_quota,
    )
    return {**record, "plaintext": plaintext}


def lookup(plaintext: str) -> dict[str, Any] | None:
    if not plaintext or not plaintext.startswith(KEY_PREFIX):
        return None
    return repository.get_api_key_by_hash(_hash(plaintext))


def list_keys() -> list[dict[str, Any]]:
    return repository.list_api_keys(limit=200)


def revoke(key_id: str) -> bool:
    return repository.revoke_api_key(key_id)
