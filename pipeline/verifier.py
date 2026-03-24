"""
ScamGuardian v2 — 교차 검증 모듈
추출된 엔티티를 Serper API로 검색하여 신뢰성을 검증한다.
LLM 없이 검색 결과 유무(hit/miss)만으로 판단한다.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass, field
from typing import Any

import requests
from dotenv import load_dotenv

from pipeline.config import SERPER_API_URL, SERPER_DELAY
from pipeline.extractor import Entity

load_dotenv()


@dataclass
class VerificationResult:
    entity: Entity
    query: str
    flag: str                           # SCORING_RULES의 키
    flag_description: str               # 사람이 읽을 수 있는 설명
    triggered: bool                     # 해당 플래그 발동 여부
    search_hits: int = 0                # 검색 결과 수
    evidence_snippets: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entity_text": self.entity.text,
            "entity_label": self.entity.label,
            "query": self.query,
            "flag": self.flag,
            "flag_description": self.flag_description,
            "triggered": self.triggered,
            "search_hits": self.search_hits,
            "evidence_snippets": self.evidence_snippets,
        }


def _serper_search(query: str, num_results: int = 5) -> dict:
    """Serper API를 호출하여 검색 결과를 반환한다."""
    api_key = os.getenv("SERPER_API_KEY", "")
    if not api_key:
        raise EnvironmentError("SERPER_API_KEY가 .env에 설정되지 않았습니다.")

    resp = requests.post(
        SERPER_API_URL,
        headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
        json={"q": query, "num": num_results, "gl": "kr", "hl": "ko"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def _count_hits(result: dict) -> int:
    return len(result.get("organic", []))


def _extract_snippets(result: dict, max_snippets: int = 3) -> list[str]:
    snippets: list[str] = []
    for item in result.get("organic", [])[:max_snippets]:
        snippet = item.get("snippet", "")
        if snippet:
            snippets.append(snippet)
    return snippets


def _has_scam_keywords(snippets: list[str]) -> bool:
    """스니펫에 스캠/사기 관련 키워드가 포함되어 있는지 확인한다."""
    keywords = ["사기", "스캠", "피싱", "신고", "피해", "주의보", "경고", "불법", "미등록", "무허가"]
    text = " ".join(snippets).lower()
    return any(kw in text for kw in keywords)


def _parse_return_rate(text: str) -> float | None:
    """'연 30%', '월 10%' 등에서 퍼센트 수치를 추출한다."""
    match = re.search(r"(\d+(?:\.\d+)?)\s*%", text)
    if match:
        return float(match.group(1))
    return None


# ──────────────────────────────────────────────
# 엔티티 유형별 검증 전략
# ──────────────────────────────────────────────

def _verify_company(entity: Entity, all_entities: list[Entity]) -> list[VerificationResult]:
    """회사명 검증: 사업자등록 + 금감원 등록 + 스캠 신고"""
    results: list[VerificationResult] = []
    name = entity.text

    # 1) 사업자등록 확인
    q1 = f'"{name}" 사업자등록 site:bizno.net'
    sr1 = _serper_search(q1)
    results.append(VerificationResult(
        entity=entity,
        query=q1,
        flag="business_not_registered",
        flag_description=f"'{name}' 사업자등록 정보 미확인",
        triggered=_count_hits(sr1) == 0,
        search_hits=_count_hits(sr1),
        evidence_snippets=_extract_snippets(sr1),
    ))
    time.sleep(SERPER_DELAY)

    # 2) 금감원 등록 확인
    q2 = f'"{name}" site:fss.or.kr'
    sr2 = _serper_search(q2)
    results.append(VerificationResult(
        entity=entity,
        query=q2,
        flag="fss_not_registered",
        flag_description=f"'{name}' 금융감독원 등록 미확인",
        triggered=_count_hits(sr2) == 0,
        search_hits=_count_hits(sr2),
        evidence_snippets=_extract_snippets(sr2),
    ))
    time.sleep(SERPER_DELAY)

    # 3) 대표명 교차 확인
    person_entities = [e for e in all_entities if e.label == "사람 이름"]
    if person_entities:
        person_name = person_entities[0].text
        q3 = f'"{person_name}" "{name}" 대표이사'
        sr3 = _serper_search(q3)
        results.append(VerificationResult(
            entity=entity,
            query=q3,
            flag="ceo_name_mismatch",
            flag_description=f"'{person_name}'이(가) '{name}'의 대표인지 확인 불가",
            triggered=_count_hits(sr3) == 0,
            search_hits=_count_hits(sr3),
            evidence_snippets=_extract_snippets(sr3),
        ))
        time.sleep(SERPER_DELAY)

    return results


def _verify_phone(entity: Entity) -> list[VerificationResult]:
    """전화번호 검증: 스캠 신고 이력"""
    q = f'"{entity.text}" 사기 OR 스캠 OR 피싱 OR 신고'
    sr = _serper_search(q)
    snippets = _extract_snippets(sr)
    return [VerificationResult(
        entity=entity,
        query=q,
        flag="phone_scam_reported",
        flag_description=f"'{entity.text}' 스캠/사기 신고 이력 발견",
        triggered=_has_scam_keywords(snippets),
        search_hits=_count_hits(sr),
        evidence_snippets=snippets,
    )]


def _verify_website(entity: Entity) -> list[VerificationResult]:
    """웹사이트 검증: 피싱 신고"""
    domain = entity.text.replace("http://", "").replace("https://", "").split("/")[0]
    q = f'site:{domain} 사기 OR 피싱 OR 스캠'
    sr = _serper_search(q)
    snippets = _extract_snippets(sr)
    return [VerificationResult(
        entity=entity,
        query=q,
        flag="website_scam_reported",
        flag_description=f"'{domain}' 관련 피싱/사기 신고 발견",
        triggered=_has_scam_keywords(snippets),
        search_hits=_count_hits(sr),
        evidence_snippets=snippets,
    )]


def _verify_account(entity: Entity) -> list[VerificationResult]:
    """계좌번호 검증: 스캠 신고 이력"""
    q = f'"{entity.text}" 사기 OR 보이스피싱 OR 신고'
    sr = _serper_search(q)
    snippets = _extract_snippets(sr)
    return [VerificationResult(
        entity=entity,
        query=q,
        flag="account_scam_reported",
        flag_description=f"계좌 '{entity.text}' 스캠 신고 이력 발견",
        triggered=_has_scam_keywords(snippets),
        search_hits=_count_hits(sr),
        evidence_snippets=snippets,
    )]


def _verify_certification(entity: Entity) -> list[VerificationResult]:
    """인증/보증 기관 검증: 실제 존재 여부"""
    q = f'"{entity.text}" 공식 사이트'
    sr = _serper_search(q)
    return [VerificationResult(
        entity=entity,
        query=q,
        flag="fake_certification",
        flag_description=f"'{entity.text}' 공식 기관 확인 불가",
        triggered=_count_hits(sr) == 0,
        search_hits=_count_hits(sr),
        evidence_snippets=_extract_snippets(sr),
    )]


def _verify_impersonated_agency(entity: Entity) -> list[VerificationResult]:
    """사칭 기관 검증: 공식 전화번호 대조"""
    q = f'"{entity.text}" 공식 대표번호'
    sr = _serper_search(q)
    return [VerificationResult(
        entity=entity,
        query=q,
        flag="fake_government_agency",
        flag_description=f"'{entity.text}' 사칭 의심 — 공식 연락처 불일치",
        triggered=_count_hits(sr) == 0,
        search_hits=_count_hits(sr),
        evidence_snippets=_extract_snippets(sr),
    )]


def _verify_return_rate(entity: Entity) -> list[VerificationResult]:
    """수익률 검증: 비정상 고수익 여부"""
    rate = _parse_return_rate(entity.text)
    triggered = rate is not None and rate > 20.0
    return [VerificationResult(
        entity=entity,
        query="(규칙 기반 판단: 수익률 > 20%)",
        flag="abnormal_return_rate",
        flag_description=f"'{entity.text}' — 비정상적 고수익 주장",
        triggered=triggered,
        search_hits=0,
    )]


def _verify_personal_info(entity: Entity) -> list[VerificationResult]:
    """개인정보 요구 검증: 즉시 플래그"""
    return [VerificationResult(
        entity=entity,
        query="(규칙 기반 판단: 개인정보 요구)",
        flag="personal_info_request",
        flag_description=f"'{entity.text}' — 개인정보 요구 감지",
        triggered=True,
        search_hits=0,
    )]


def _verify_medical_claim(entity: Entity) -> list[VerificationResult]:
    """의료 효능 주장 검증: 식약처 인증 여부"""
    q = f'"{entity.text}" site:mfds.go.kr'
    sr = _serper_search(q)
    return [VerificationResult(
        entity=entity,
        query=q,
        flag="medical_claim_unverified",
        flag_description=f"'{entity.text}' — 식약처 인증 미확인",
        triggered=_count_hits(sr) == 0,
        search_hits=_count_hits(sr),
        evidence_snippets=_extract_snippets(sr),
    )]


def _verify_exchange(entity: Entity) -> list[VerificationResult]:
    """거래소 검증: 실제 등록 거래소인지 확인"""
    q = f'"{entity.text}" 가상자산 거래소 등록'
    sr = _serper_search(q)
    return [VerificationResult(
        entity=entity,
        query=q,
        flag="fake_exchange",
        flag_description=f"'{entity.text}' — 미등록 거래소 의심",
        triggered=_count_hits(sr) == 0,
        search_hits=_count_hits(sr),
        evidence_snippets=_extract_snippets(sr),
    )]


# ──────────────────────────────────────────────
# 레이블 → 검증 함수 매핑
# ──────────────────────────────────────────────

_VERIFY_DISPATCH: dict[str, Any] = {
    "전화번호": _verify_phone,
    "웹사이트 주소": _verify_website,
    "계좌번호": _verify_account,
    "보증 기관명": _verify_certification,
    "인증 기관명": _verify_certification,
    "인허가 기관명": _verify_certification,
    "사칭 기관명": _verify_impersonated_agency,
    "수익 퍼센트": _verify_return_rate,
    "개인정보 항목": _verify_personal_info,
    "치료 효능 주장": _verify_medical_claim,
    "거래소명": _verify_exchange,
}

# 회사명은 다른 엔티티 참조가 필요하므로 별도 처리
_COMPANY_LABELS = {"회사명 또는 기관명"}


def verify(entities: list[Entity], scam_type: str) -> list[VerificationResult]:
    """
    추출된 엔티티 리스트를 교차 검증한다.

    Args:
        entities: GLiNER가 추출한 엔티티 리스트
        scam_type: 분류된 스캠 유형

    Returns:
        검증 결과 리스트 (트리거된 것과 미트리거된 것 모두 포함)
    """
    results: list[VerificationResult] = []

    for entity in entities:
        label = entity.label

        # 회사명: 다른 엔티티(사람 이름)도 참조해야 하므로 별도 호출
        if label in _COMPANY_LABELS:
            results.extend(_verify_company(entity, entities))
            time.sleep(SERPER_DELAY)
            continue

        # 매핑된 검증 함수가 있으면 실행
        verify_fn = _VERIFY_DISPATCH.get(label)
        if verify_fn is not None:
            results.extend(verify_fn(entity))
            time.sleep(SERPER_DELAY)

    return results
