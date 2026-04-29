"""
v4 실험 1 — Haiku 한 줄 의도 분류기.

목적: 사용자(피해자) 발화에서 즉시 경보 신호 3가지(메타인식·민감정보 누설·송금동의)
를 NORMAL 과 분리할 수 있는지 빠르게 검증.

설계 원칙:
- 단발 호출 (chunk 마다 1 회). 누적 슬라이딩 윈도우는 v4.1 에서.
- 짧은 응답 (max_tokens 16). 비용·지연 모두 최소화.
- 시스템 프롬프트가 라벨 4종으로 강제 분류.
- 라벨 외 응답이 와도 정상 처리 (정규식으로 첫 토큰 추출).
"""

from __future__ import annotations

import os
import re
from typing import Literal

Label = Literal["META_AWARE", "SENSITIVE_INFO", "TRANSFER_AGREE", "NORMAL"]
LABELS: tuple[Label, ...] = ("META_AWARE", "SENSITIVE_INFO", "TRANSFER_AGREE", "NORMAL")

SYSTEM_PROMPT = """당신은 보이스피싱 통화 중인 피해자의 발화를 실시간으로 분류하는 모듈입니다.
사용자(피해자)의 *한 마디 발화* 만 보고 다음 4가지 중 하나로 분류하세요:

- META_AWARE: 사기·피싱·이상함을 의심하거나 진위 확인을 요청. 예: "이거 사기 아니에요?", "좀 이상한데", "진짜 검찰청 맞아요?"
- SENSITIVE_INFO: 주민번호·OTP·비밀번호·CVC·보안카드·통장비번 등 민감정보를 *말하고 있음*. 예: "주민번호는...", "OTP 825612"
- TRANSFER_AGREE: 송금·이체·입금에 동의하거나 이미 보냄. 예: "지금 이체할게요", "300만원 보냈습니다"
- NORMAL: 위 셋 중 어느 것도 아님. 일반 대화·맞장구·질문.

**반드시 4개 라벨 중 하나만**, 다른 단어 없이 출력하세요. 예: META_AWARE
"""


def _get_client():
    import anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY 가 설정되지 않았습니다.")
    return anthropic.Anthropic(api_key=api_key)


def _normalize(raw: str) -> Label:
    raw_upper = (raw or "").strip().upper()
    for label in LABELS:
        if label in raw_upper:
            return label
    # fallback — 첫 단어만 비교
    first = re.split(r"\s+", raw_upper, maxsplit=1)[0] if raw_upper else ""
    if first in LABELS:
        return first  # type: ignore[return-value]
    return "NORMAL"


def classify(utterance: str, model: str | None = None) -> tuple[Label, str]:
    """발화 → (정규화된 라벨, 원본 응답)."""
    client = _get_client()
    target_model = model or os.getenv("ANTHROPIC_HAIKU_MODEL", "claude-haiku-4-5-20251001")
    msg = client.messages.create(
        model=target_model,
        max_tokens=16,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": utterance}],
    )
    raw = msg.content[0].text if msg.content else ""
    return _normalize(raw), raw
