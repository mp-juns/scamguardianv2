"""
ScamGuardian v2 — 중앙 설정 모듈
레이블 세트, SLIMER D&G 정의, 스코어링 가중치를 관리한다.
"""

from __future__ import annotations

import os
from typing import Any

# ──────────────────────────────────────────────
# 스캠 유형 후보 (zero-shot 분류용)
# ──────────────────────────────────────────────
DEFAULT_SCAM_TYPES: list[str] = [
    "투자 사기",
    "건강식품 사기",
    "부동산 사기",
    "코인 사기",
    "기관 사칭",
    "대출 사기",
    "메신저 피싱",
    "로맨스 스캠",
    "취업·알바 사기",
    "납치·협박형",
    "스미싱",
    "중고거래 사기",
]

# NLI 모델용 설명적 레이블 → 짧은 레이블 매핑
# mDeBERTa가 의미를 더 잘 구분하도록 구체적 설명 사용
DEFAULT_SCAM_TYPE_DESCRIPTIONS: dict[str, str] = {
    "높은 수익률을 보장하며 투자금을 요구": "투자 사기",
    "건강식품이나 약으로 질병 치료를 주장하며 판매": "건강식품 사기",
    "부동산 개발 투자 수익을 약속하며 돈을 요구": "부동산 사기",
    "암호화폐 코인 투자로 큰 수익을 약속": "코인 사기",
    "경찰 검찰 금융감독원 등 정부기관을 사칭하여 개인정보나 송금을 요구": "기관 사칭",
    "저금리 대출을 빙자하여 선납금이나 보증금을 요구": "대출 사기",
    "카카오톡이나 SNS에서 지인이나 가족을 사칭하여 급전을 요청": "메신저 피싱",
    "온라인에서 연애 감정을 이용하여 해외 송금이나 투자금을 요구": "로맨스 스캠",
    "재택알바나 채용을 빙자하여 교육비나 선입금을 요구": "취업·알바 사기",
    "가족을 납치했다고 협박하며 즉각적인 송금을 요구": "납치·협박형",
    "문자 링크를 통해 악성앱 설치를 유도하거나 개인정보를 탈취": "스미싱",
    "중고 물품 거래를 빙자하여 물건을 보내지 않거나 가짜 송금 확인증을 사용": "중고거래 사기",
}

# ──────────────────────────────────────────────
# 공통 베이스 레이블 (모든 스캠 유형에 적용)
# ──────────────────────────────────────────────
BASE_LABELS: list[str] = [
    "사람 이름",
    "회사명 또는 기관명",
    "전화번호",
    "이메일 주소",
    "웹사이트 주소",
    "금액",
    "날짜 또는 기간",
]

# ──────────────────────────────────────────────
# 스캠 유형별 특화 레이블 세트 (베이스 + 특화)
# ──────────────────────────────────────────────
DEFAULT_LABEL_SETS: dict[str, list[str]] = {
    "투자 사기": [
        *BASE_LABELS,
        "수익 퍼센트",
        "투자 상품명",
        "보증 기관명",
        "사업자 등록번호",
        "계좌번호",
    ],
    "건강식품 사기": [
        *BASE_LABELS,
        "제품명",
        "치료 효능 주장",
        "대상 질환명",
        "인증 기관명",
        "전문가 직함",
    ],
    "부동산 사기": [
        *BASE_LABELS,
        "지역명 또는 주소",
        "수익 퍼센트",
        "개발 사업명",
        "인허가 기관명",
        "공인중개사 번호",
    ],
    "코인 사기": [
        *BASE_LABELS,
        "코인 또는 토큰명",
        "거래소명",
        "수익 퍼센트",
        "지갑 주소",
        "백서 또는 프로젝트명",
    ],
    "기관 사칭": [
        *BASE_LABELS,
        "사칭 기관명",
        "직함 또는 직책",
        "사건번호 또는 공문번호",
        "계좌번호",
        "개인정보 항목",
    ],
    "대출 사기": [
        *BASE_LABELS,
        "대출 한도",
        "대출 금리",
        "선납금 또는 수수료",
        "선납금 명목",
        "사칭 금융기관명",
        "계좌번호",
    ],
    "메신저 피싱": [
        *BASE_LABELS,
        "사칭 지인 이름",
        "송금 목적",
        "SNS 또는 메신저 플랫폼",
        "계좌번호",
        "카카오톡 ID",
    ],
    "로맨스 스캠": [
        *BASE_LABELS,
        "사칭 신분 또는 직업",
        "사칭 국적",
        "연락 플랫폼",
        "송금 목적",
        "계좌번호",
    ],
    "취업·알바 사기": [
        *BASE_LABELS,
        "일당 또는 급여",
        "직종명",
        "선납금 명목",
        "선납금 또는 수수료",
        "사칭 회사명",
        "계좌번호",
    ],
    "납치·협박형": [
        *BASE_LABELS,
        "협박 대상 관계",
        "요구 금액",
        "송금 기한",
        "계좌번호",
        "협박 수단",
    ],
    "스미싱": [
        *BASE_LABELS,
        "악성 URL",
        "사칭 기관명",
        "발신 번호",
        "개인정보 항목",
        "사칭 서비스명",
    ],
    "중고거래 사기": [
        *BASE_LABELS,
        "거래 플랫폼명",
        "거래 상품명",
        "허위 운송장 번호",
        "계좌번호",
        "에스크로 회피 수단",
    ],
}


def _normalize_custom_labels(labels: list[str] | None) -> list[str]:
    seen: set[str] = set()
    normalized: list[str] = []
    for label in labels or []:
        text = str(label).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _custom_description_for_type(scam_type: str) -> str:
    return f"{scam_type}와 관련된 기만, 사칭, 금전 요구를 포함한 사기 수법"


def build_scam_taxonomy(
    custom_types: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    scam_types = list(DEFAULT_SCAM_TYPES)
    descriptions = dict(DEFAULT_SCAM_TYPE_DESCRIPTIONS)
    label_sets = {name: list(labels) for name, labels in DEFAULT_LABEL_SETS.items()}

    for item in custom_types or []:
        scam_type = str(item.get("name", "")).strip()
        if not scam_type or scam_type in scam_types:
            continue

        description = str(item.get("description", "")).strip() or _custom_description_for_type(
            scam_type
        )
        labels = _normalize_custom_labels(item.get("labels"))

        scam_types.append(scam_type)
        descriptions[description] = scam_type
        label_sets[scam_type] = labels or list(BASE_LABELS)

    return {
        "scam_types": scam_types,
        "descriptions": descriptions,
        "label_sets": label_sets,
    }


def get_runtime_scam_taxonomy() -> dict[str, Any]:
    custom_types: list[dict[str, Any]] = []
    try:
        from db import repository

        if repository.database_configured():
            custom_types = repository.list_custom_scam_types()
    except Exception:
        custom_types = []

    return build_scam_taxonomy(custom_types)


SCAM_TYPES: list[str] = list(DEFAULT_SCAM_TYPES)
SCAM_TYPE_DESCRIPTIONS: dict[str, str] = dict(DEFAULT_SCAM_TYPE_DESCRIPTIONS)
LABEL_SETS: dict[str, list[str]] = {
    name: list(labels) for name, labels in DEFAULT_LABEL_SETS.items()
}

# ──────────────────────────────────────────────
# SLIMER D&G: 레이블별 정의(Definition) + 가이드라인(Guideline)
# GLiNER 레이블 자체에는 넣지 않고, 검증·스코어링에서 판단 기준으로 활용
# ──────────────────────────────────────────────
LABEL_DEFINITIONS: dict[str, dict[str, str]] = {
    # --- 공통 베이스 ---
    "사람 이름": {
        "definition": "실명으로 언급된 특정 개인",
        "guideline": "화자 본인, 대표자, 보증인 포함. 직함만 있고 이름 없으면 제외",
    },
    "회사명 또는 기관명": {
        "definition": "영상에서 언급된 회사, 단체, 기관 이름",
        "guideline": "실제 존재 여부와 무관하게 추출. 'OO그룹', 'OO투자' 등 포함",
    },
    "전화번호": {
        "definition": "연락처로 제시된 전화번호",
        "guideline": "국제번호 포함. 수신거부나 신고 여부 검색에 활용",
    },
    "이메일 주소": {
        "definition": "연락처로 제시된 이메일",
        "guideline": "도메인 포함 추출",
    },
    "웹사이트 주소": {
        "definition": "언급된 URL 또는 도메인",
        "guideline": "http 없이 도메인만 언급해도 추출",
    },
    "금액": {
        "definition": "투자금, 가격, 수수료 등 화폐 단위 금액",
        "guideline": "숫자+단위 함께 추출. '소액', '저렴' 등 모호한 표현 제외",
    },
    "날짜 또는 기간": {
        "definition": "언급된 날짜, 마감일, 기간",
        "guideline": "긴박감 조성용 기한 포함",
    },
    # --- 투자 사기 특화 ---
    "수익 퍼센트": {
        "definition": "수익률로 표현된 퍼센트 수치",
        "guideline": "'연 30%', '월 10%' 등. 단위 포함 추출",
    },
    "투자 상품명": {
        "definition": "펀드, 주식, 채권 등 투자 상품 이름",
        "guideline": "정식 상품명이 아닌 자칭 상품명도 포함",
    },
    "보증 기관명": {
        "definition": "수익이나 원금을 보증한다고 주장하는 기관",
        "guideline": "가짜 규제기관 사칭 여부 검증 대상",
    },
    "사업자 등록번호": {
        "definition": "사업자등록번호 또는 법인등록번호",
        "guideline": "숫자 패턴(XXX-XX-XXXXX) 추출",
    },
    "계좌번호": {
        "definition": "송금 대상 은행 계좌번호",
        "guideline": "은행명 포함 시 함께 추출",
    },
    # --- 건강식품 사기 특화 ---
    "제품명": {
        "definition": "건강식품, 의약품, 보조제 이름",
        "guideline": "브랜드명, 성분명 모두 포함",
    },
    "치료 효능 주장": {
        "definition": "특정 질병의 치료·완치를 주장하는 표현",
        "guideline": "'암 완치', '당뇨 치료' 등 의학적 효능 주장",
    },
    "대상 질환명": {
        "definition": "치료 대상으로 언급된 질병명",
        "guideline": "정식 질병명 및 구어체 표현 모두 추출",
    },
    "인증 기관명": {
        "definition": "제품 인증·승인을 받았다고 주장하는 기관",
        "guideline": "식약처, FDA 등 가짜 인증 사칭 포함",
    },
    "전문가 직함": {
        "definition": "권위를 부여하기 위해 사용된 직함",
        "guideline": "'박사', '교수', '한의사' 등. 이름과 함께 추출",
    },
    # --- 부동산 사기 특화 ---
    "지역명 또는 주소": {
        "definition": "투자 대상 부동산의 위치",
        "guideline": "시/군/구, 도로명, 단지명 등",
    },
    "개발 사업명": {
        "definition": "재개발, 신도시, 택지개발 등 사업 이름",
        "guideline": "정부 사업 사칭 여부 검증 대상",
    },
    "인허가 기관명": {
        "definition": "건축·개발 인허가를 내줬다고 주장하는 기관",
        "guideline": "국토부, 시청, 구청 등",
    },
    "공인중개사 번호": {
        "definition": "공인중개사 등록번호",
        "guideline": "자격 확인용",
    },
    # --- 코인 사기 특화 ---
    "코인 또는 토큰명": {
        "definition": "가상자산(암호화폐) 이름",
        "guideline": "비트코인 등 기존 코인 및 신규 토큰 모두 포함",
    },
    "거래소명": {
        "definition": "가상자산 거래소 이름",
        "guideline": "업비트, 바이낸스 등 사칭 여부 확인",
    },
    "지갑 주소": {
        "definition": "암호화폐 지갑 주소",
        "guideline": "긴 영숫자 문자열 패턴",
    },
    "백서 또는 프로젝트명": {
        "definition": "가상자산 프로젝트 또는 백서 이름",
        "guideline": "가짜 프로젝트 여부 확인 대상",
    },
    # --- 기관 사칭 특화 ---
    "사칭 기관명": {
        "definition": "사칭되고 있는 정부 기관·금융 기관 이름",
        "guideline": "금감원, 검찰, 경찰, 은행 등",
    },
    "직함 또는 직책": {
        "definition": "권위를 사칭하기 위한 직함",
        "guideline": "'수사관', '팀장', '검사' 등",
    },
    "사건번호 또는 공문번호": {
        "definition": "가짜 공식 문서의 번호",
        "guideline": "사건번호, 공문번호, 접수번호 등",
    },
    "개인정보 항목": {
        "definition": "요구하는 개인정보의 종류",
        "guideline": "주민번호, 비밀번호, OTP 등",
    },
    # --- 대출 사기 특화 ---
    "대출 한도": {
        "definition": "제시된 대출 가능 금액",
        "guideline": "'최대 1억', '5천만 원' 등 구체적 금액",
    },
    "대출 금리": {
        "definition": "제시된 대출 금리",
        "guideline": "'연 2.9%', '저금리' 등",
    },
    "선납금 또는 수수료": {
        "definition": "대출·취업·거래 전 먼저 요구하는 금액",
        "guideline": "보증금, 수수료, 공증비, 교육비, 등록금 등 명목 불문",
    },
    "선납금 명목": {
        "definition": "선납금을 요구하는 이유나 명목",
        "guideline": "'보험료', '공증비', '교육비', '기자재비' 등",
    },
    "사칭 금융기관명": {
        "definition": "대출 권유 시 사칭하는 금융기관 이름",
        "guideline": "서민금융진흥원, 국민은행 등 실존 기관 사칭",
    },
    # --- 메신저 피싱 특화 ---
    "사칭 지인 이름": {
        "definition": "사칭하는 지인·가족의 이름 또는 관계",
        "guideline": "'엄마', '친구 민수' 등",
    },
    "송금 목적": {
        "definition": "돈을 요청하는 이유",
        "guideline": "'핸드폰 고장', '급하게 필요', '잠깐 빌려줘' 등",
    },
    "SNS 또는 메신저 플랫폼": {
        "definition": "사기에 사용된 메신저/SNS 플랫폼",
        "guideline": "카카오톡, 인스타그램, 페이스북, 라인 등",
    },
    "카카오톡 ID": {
        "definition": "사기에 사용된 카카오톡 또는 SNS 계정 ID",
        "guideline": "아이디 문자열 그대로 추출",
    },
    # --- 로맨스 스캠 특화 ---
    "사칭 신분 또는 직업": {
        "definition": "신뢰를 얻기 위해 사칭하는 신분·직업",
        "guideline": "'UN 소속 의사', '미군 장교', '해외 파견 엔지니어' 등",
    },
    "사칭 국적": {
        "definition": "사칭하는 국적 또는 출신지",
        "guideline": "'미국', '캐나다', '독일' 등",
    },
    "연락 플랫폼": {
        "definition": "로맨스 스캠이 시작된 플랫폼",
        "guideline": "틱톡, 인스타그램, 데이팅앱 등",
    },
    # --- 취업·알바 사기 특화 ---
    "일당 또는 급여": {
        "definition": "제시된 일당, 시급, 월급",
        "guideline": "'일당 15만 원', '시급 5만 원' 등",
    },
    "직종명": {
        "definition": "제시된 업무 종류",
        "guideline": "'재택 데이터 입력', '스마트폰 리뷰' 등",
    },
    "사칭 회사명": {
        "definition": "채용 광고에서 사칭하는 회사 이름",
        "guideline": "대기업·유명 기업 사칭 포함",
    },
    # --- 납치·협박형 특화 ---
    "협박 대상 관계": {
        "definition": "납치·협박 대상으로 언급된 가족 관계",
        "guideline": "'자녀', '배우자', '부모' 등",
    },
    "송금 기한": {
        "definition": "협박에서 요구하는 송금 마감 시간",
        "guideline": "'30분 안에', '지금 당장' 등",
    },
    "협박 수단": {
        "definition": "협박에 사용되는 위협 내용",
        "guideline": "'경찰 부르면 죽인다', '신체 해를 가한다' 등",
    },
    # --- 스미싱 특화 ---
    "악성 URL": {
        "definition": "문자에 포함된 의심 링크",
        "guideline": "단축 URL, 이상한 도메인 등",
    },
    "발신 번호": {
        "definition": "스미싱 문자 발신 번호",
        "guideline": "070, 국제번호, 변작된 번호 포함",
    },
    "사칭 서비스명": {
        "definition": "스미싱에서 사칭하는 서비스·기업명",
        "guideline": "'CJ대한통운', '쿠팡', '국민은행' 등",
    },
    # --- 중고거래 사기 특화 ---
    "거래 플랫폼명": {
        "definition": "사기가 발생한 중고거래 플랫폼",
        "guideline": "중고나라, 당근마켓, 번개장터 등",
    },
    "거래 상품명": {
        "definition": "사기 거래 대상 물품",
        "guideline": "아이폰, 게임기, 티켓 등",
    },
    "허위 운송장 번호": {
        "definition": "발송했다고 속이는 가짜 운송장 번호",
        "guideline": "CJ대한통운, 한진 등 운송사 추적번호 형식",
    },
    "에스크로 회피 수단": {
        "definition": "안전결제를 우회하도록 유도하는 방법",
        "guideline": "'직거래로 해요', '수수료 아끼려고' 등",
    },
}

# ──────────────────────────────────────────────
# 스코어링 규칙: 검증 플래그 → 가산점
# ──────────────────────────────────────────────
SCORING_RULES: dict[str, int] = {
    "business_not_registered": 20,      # 사업자 미등록
    "phone_scam_reported": 25,          # 전화번호 스캠 신고 이력
    "ceo_name_mismatch": 15,            # 대표명 불일치
    "fss_not_registered": 15,           # 금감원 미등록
    "fake_certification": 20,           # 가짜 인증기관
    "website_scam_reported": 20,        # 웹사이트 피싱 신고
    "abnormal_return_rate": 15,         # 비정상 고수익 주장 (>20%)
    "fake_government_agency": 25,       # 정부기관 사칭
    "personal_info_request": 20,        # 개인정보 요구
    "medical_claim_unverified": 20,     # 미인증 의료 효능 주장
    "fake_exchange": 20,                # 가짜 거래소
    "account_scam_reported": 25,        # 계좌 스캠 신고 이력
    "prepayment_requested": 20,         # 선납금/수수료 먼저 요구 (대출·취업 사기)
    "urgent_transfer_demand": 20,       # 즉각 송금·이체 요구
    "threat_or_coercion": 25,           # 협박·강요 발화 감지
    "impersonation_family": 20,         # 가족·지인 사칭
    "romance_foreign_identity": 15,     # 해외 신분(군인·의사·외교관) 사칭
    "job_deposit_requested": 20,        # 취업·알바 선입금 요구
    "smishing_link_detected": 20,       # 스미싱 링크 포함
    "fake_escrow_bypass": 15,           # 직거래·가짜 에스크로 유도

    # ──────────────────────────────────────────────
    # v3 Phase 0: 안전성 필터 (VirusTotal 자동 트리거)
    # 악성 단독으로도 '매우 위험(71+)' 등급 직행 — 다중 안티바이러스 합의 신호는
    # 다른 어떤 휴리스틱보다 강하므로 점수도 가장 높게 책정.
    # ──────────────────────────────────────────────
    "malware_detected": 80,             # 파일이 VT 에서 악성으로 다중 탐지
    "phishing_url_confirmed": 75,       # URL 이 VT 에서 피싱/악성으로 다중 탐지
    "suspicious_file_signal": 25,       # 파일이 VT 에서 일부 엔진만 의심 (low confidence)
    "suspicious_url_signal": 25,        # URL 이 VT 에서 일부 엔진만 의심

    # ──────────────────────────────────────────────
    # 노션 다음 단계: BERT 유사도/쿼리 A-B-C 플래그
    # ──────────────────────────────────────────────
    "authority_context_mismatch": 15,   # 화자 프로파일 vs 발화 맥락 의미 불일치
    "authority_context_uncertain": 5,   # 의미가 애매(주의)
    "query_a_confirmed": -20,           # 신뢰 언론에서 화자+발언 동시 히트
    "query_a_unconfirmed": 20,          # 신뢰 언론 동시 히트 부재
    "query_b_factcheck_found": 25,      # 팩트체크/검증 결과에 스캠 단서 포함
    "query_b_confirmed": -15,           # 팩트체크에서 확인/부인(denied) 단서 발견
    "query_c_scam_pattern_found": 15,   # 스캠 패턴 관련 단서 확인
}


# 사용자 노출용 한국어 플래그 라벨 — 위 SCORING_RULES 키와 1:1 매핑
FLAG_LABELS_KO: dict[str, str] = {
    "business_not_registered": "사업자 미등록",
    "phone_scam_reported": "전화번호 스캠 신고 이력",
    "ceo_name_mismatch": "대표자명 불일치",
    "fss_not_registered": "금감원 미등록 업체",
    "fake_certification": "가짜 인증기관",
    "website_scam_reported": "웹사이트 피싱·사기 신고",
    "abnormal_return_rate": "비정상적 고수익 주장",
    "fake_government_agency": "정부기관 사칭",
    "personal_info_request": "개인정보 요구",
    "medical_claim_unverified": "미인증 의료 효능 주장",
    "fake_exchange": "가짜 거래소",
    "account_scam_reported": "계좌 스캠 신고 이력",
    "prepayment_requested": "선납금·수수료 요구",
    "urgent_transfer_demand": "즉각 송금·이체 요구",
    "threat_or_coercion": "협박·강요 발화",
    "impersonation_family": "가족·지인 사칭",
    "romance_foreign_identity": "해외 신분 사칭",
    "job_deposit_requested": "취업·알바 선입금 요구",
    "smishing_link_detected": "스미싱 의심 링크",
    "fake_escrow_bypass": "에스크로 회피 유도",
    "malware_detected": "악성코드 탐지",
    "phishing_url_confirmed": "피싱 URL 확인",
    "suspicious_file_signal": "의심 파일 신호",
    "suspicious_url_signal": "의심 URL 신호",
    "authority_context_mismatch": "발화 맥락 불일치",
    "authority_context_uncertain": "발화 맥락 애매",
    "query_a_confirmed": "신뢰 언론에서 확인됨",
    "query_a_unconfirmed": "신뢰 언론 확인 불가",
    "query_b_factcheck_found": "팩트체크 결과 의심",
    "query_b_confirmed": "팩트체크에서 사실 확인",
    "query_c_scam_pattern_found": "스캠 패턴 단서",
}


def flag_label_ko(flag: str) -> str:
    """플래그 영문 키를 한국어 라벨로. 매핑 없으면 원본 반환."""
    return FLAG_LABELS_KO.get(flag, flag)


# 플래그 점수의 정당성·근거 — 사용자/라벨러에게 "왜 이 점수인가요?" 답변용.
# 공식 출처(KISA, 금감원, 경찰청)와 학술 자료(Cialdini 영향력 원리, Whitty 스캠
# 설득 모델, FBI IC3 등) 를 함께 인용해 점수의 정당성을 강화한다.
#
# 공통 학술 프레임워크:
# - Cialdini, R. B. (2021). Influence, New and Expanded: The Psychology of
#   Persuasion. Harper Business. — 권위(authority)·희소성(scarcity)·
#   사회적 증거(social proof) 6대 영향력 원리
# - Whitty, M. T. (2013). The Scammers Persuasive Techniques Model.
#   British Journal of Criminology, 53(4), 665–684. — 사기범 설득 단계 모델
# - Stajano, F., & Wilson, P. (2011). Understanding scam victims: Seven
#   principles for systems security. CACM, 54(3), 70–75. — 사회공학 7원칙
# - FBI IC3 Annual Internet Crime Report — 글로벌 사기 통계
# - 금융감독원 보이스피싱·유사수신 감독사례집 (연간) — 국내 통계
FLAG_RATIONALE: dict[str, dict[str, str]] = {
    "business_not_registered": {
        "rationale": "정상 사업자라면 국세청 사업자등록 조회에 노출됨. 미등록 = 비공식 거래 → 사기 위험 높음. 점수 20점은 단독으로는 위험 등급(41~70)에 못 미치지만 추가 신호와 결합 시 결정적 가산점.",
        "source": "국세청 사업자등록상태조회 / 전자상거래법 제12조 / Stajano & Wilson (2011) Principle 1: Distraction (위장된 정상성)",
    },
    "phone_scam_reported": {
        "rationale": "신고 이력 있는 번호는 재범 확률 매우 높음. KISA 통계 기준 신고 번호의 70%+ 가 추가 신고 발생. 25점은 단일 플래그 최고 등급으로, 신고 DB 매칭만으로도 '주의→위험' 격상이 가능함.",
        "source": "KISA 보이스피싱 동향 보고서 / Anderson, R. (2008) Security Engineering Ch.2 — 재범자 베이지안 사전확률",
    },
    "ceo_name_mismatch": {
        "rationale": "법인 대표자명이 공식 등록 정보와 다르면 사칭 가능성. 단독 신호로는 애매할 수 있어 15점 (보조 신호급).",
        "source": "금융감독원 유사수신 감독사례집 / Cialdini (2021) — 권위(Authority) 원리 악용 패턴",
    },
    "fss_not_registered": {
        "rationale": "투자권유는 금감원 등록 업체만 합법. 미등록 업체 권유는 자본시장법 위반. 법적 위반이지만 합법 자문업자 가장 사례도 있어 15점 보수적 책정.",
        "source": "자본시장과 금융투자업에 관한 법률 제11조 / 금융감독원 불법금융 동향 보고서",
    },
    "fake_certification": {
        "rationale": "존재하지 않거나 위조된 인증기관 명칭 사용은 표시·광고 공정화법 위반 + 사기 표지. Cialdini 의 권위 원리 악용 — '인증' 단어만으로 신뢰 형성.",
        "source": "표시·광고의 공정화에 관한 법률 제3조 / Cialdini (2021) — Authority Heuristic / Whitty (2013) — Authority cue 단계",
    },
    "website_scam_reported": {
        "rationale": "도메인이 피싱·사기 신고 DB에 등록된 경우. 동일 도메인 재범률 80%+. APWG 글로벌 통계도 동일 추세.",
        "source": "KISA 피싱사이트 신고센터 / phishtank / APWG Phishing Activity Trends Report (분기 발행)",
    },
    "abnormal_return_rate": {
        "rationale": "연 20% 이상 수익 보장은 자본시장법상 불법 권유 신호. 정상 주식·채권 펀드의 장기 평균 수익률은 연 5~10% (S&P 500 historical 약 10% 명목). 보장형 + 고수익은 Ponzi 사기 핵심 패턴.",
        "source": "금융감독원 보이스수신 감독사례집 / SEC Investor Bulletin: Affinity Fraud / Frankel, T. (2012) The Ponzi Scheme Puzzle, Oxford UP",
    },
    "fake_government_agency": {
        "rationale": "검찰·경찰·금감원 등 공공기관은 전화·문자로 자금 이체 요구 절대 안 함. Cialdini 의 권위 원리를 가장 강하게 악용. 25점은 단독 만으로 '주의→위험' 격상 가능한 최고 등급.",
        "source": "검찰청·경찰청·금감원 합동 보이스피싱 예방 가이드 / Cialdini (2021) — Authority / Modic & Lea (2013) Scam compliance and the psychology of persuasion, SSRN",
    },
    "personal_info_request": {
        "rationale": "주민번호·계좌번호·OTP 등 민감정보를 요구하는 패턴은 보이스피싱 핵심 지표. 정상 금융기관은 비밀번호·OTP 를 절대 묻지 않음.",
        "source": "KISA 보이스피싱 행위 분석 / 개인정보보호법 제15조 / Hadnagy, C. (2018) Social Engineering: The Science of Human Hacking, Wiley",
    },
    "medical_claim_unverified": {
        "rationale": "식약처 미인증 효능 주장은 약사법 위반. 건강식품 사기는 노년층 표적이며 Cialdini 의 사회적 증거(가짜 후기) + 권위(가짜 박사) 결합 패턴.",
        "source": "약사법 제68조 / 식품의약품안전처 부당 광고 단속 / FTC Health Fraud Reports / Cialdini (2021) — Social Proof",
    },
    "fake_exchange": {
        "rationale": "금감원·금융위 등록되지 않은 거래소는 자금 출금 불가 사례 다수. 코인 사기 핵심. Pig butchering(殺豬盤) 사기의 표준 단계.",
        "source": "특정금융거래정보법 제7조 / FBI IC3 Cryptocurrency Fraud Report / Cross, C. (2023) Romance fraud and pig butchering, Trends & Issues in Crime, AIC",
    },
    "account_scam_reported": {
        "rationale": "계좌가 사기 이용 신고 이력 있음. 즉각 송금 차단 권고. 통신사기피해환급법상 의심 계좌는 지급정지 대상. 25점 최고 등급.",
        "source": "전기통신금융사기 피해 방지 및 환급에 관한 특별법 / 금융감독원 사기 이용계좌 통계",
    },
    "prepayment_requested": {
        "rationale": "취업·대출 명목 선납금 요구는 사기죄 + 대부업법 위반. 실제 합법 업체는 선납 없음. Stajano & Wilson 의 'Need and Greed' 원칙(절박한 상황 표적) 악용.",
        "source": "대부업 등의 등록 및 금융이용자 보호에 관한 법률 / 직업안정법 / Stajano & Wilson (2011) Principle 4: Need and Greed",
    },
    "urgent_transfer_demand": {
        "rationale": "즉각 송금 요구는 보이스피싱 1순위 패턴. 사고력 마비 유도(visceral influence). Loewenstein (1996) 의 hot-cold empathy gap 이론으로 설명되는 의사결정 왜곡.",
        "source": "경찰청 사이버수사국 보이스피싱 통계 / Cialdini (2021) — Scarcity / Loewenstein, G. (1996) Out of control: Visceral influences on behavior, OBHDP, 65(3) / Whitty (2013) — Urgency 단계",
    },
    "threat_or_coercion": {
        "rationale": "협박·강요 발화는 형법 제283조 협박죄. 정상 거래에는 절대 등장 안 함. 공포(fear appeal) 활용 사회공학 — Witte (1992) Extended Parallel Process Model 로 설명.",
        "source": "형법 제283조 / KISA 통계 / Witte, K. (1992) Putting the fear back into fear appeals, Communication Monographs, 59(4)",
    },
    "impersonation_family": {
        "rationale": "가족 사칭은 메신저피싱 표준 패턴. 영상통화 거부 시 100% 사기. Cialdini 의 호감(Liking) 원리 + 절박감 결합. 노년층·부모층 피해 집중.",
        "source": "경찰청 메신저피싱 예방 가이드 / 금융감독원 메신저피싱 통계 / Cialdini (2021) — Liking / Whitty (2013) — emotional manipulation",
    },
    "romance_foreign_identity": {
        "rationale": "해외 군인·의사·외교관 사칭은 로맨스 스캠 표준. FBI IC3 2023 보고서 기준 로맨스 스캠 피해액 6.5억 달러. Whitty 의 스캠 설득 모델 4단계(grooming) 핵심.",
        "source": "FBI IC3 2023 Internet Crime Report / Whitty, M. T. (2013) The Scammers Persuasive Techniques Model, Br J Criminology, 53(4) / Whitty & Buchanan (2012) The online romance scam, Cyberpsychology, 15(3)",
    },
    "job_deposit_requested": {
        "rationale": "정상 채용은 입사 전 금전 요구 없음. 직업안정법 위반. 청년·구직자 표적의 절박감 악용.",
        "source": "직업안정법 제32조 / 고용노동부 채용 사기 단속 / Stajano & Wilson (2011) — Need and Greed",
    },
    "smishing_link_detected": {
        "rationale": "단축 URL 또는 비정상 도메인 포함 SMS 는 스미싱 의심. KISA 차단 통계 다수. APWG 보고서상 SMS phishing(smishing)은 2022 이후 이메일 피싱 능가하는 주요 채널.",
        "source": "KISA 스미싱 차단 시스템 / 방송통신위원회 스미싱 통계 / APWG Phishing Activity Trends Report",
    },
    "fake_escrow_bypass": {
        "rationale": "공식 에스크로 회피 유도는 중고거래 사기 표준. 안전결제 우회 = 위험 신호. 가격 할인 명분으로 정상 절차 무력화 — Stajano & Wilson 의 'Distraction' 원칙.",
        "source": "경찰청 사이버범죄 통계 / 한국인터넷진흥원 중고거래 사기 동향 / Stajano & Wilson (2011) Principle 1: Distraction",
    },
    "malware_detected": {
        "rationale": "VirusTotal 다중 안티바이러스 엔진(보통 70+개)이 첨부 파일을 악성코드로 탐지. 30점은 단독으로 '매우 위험' 등급 직행 — 메신저 피싱의 결정적 증거.",
        "source": "VirusTotal Public API v3 / NIST SP 800-83 Guide to Malware Incident Prevention",
    },
    "phishing_url_confirmed": {
        "rationale": "VirusTotal 의 URL 분석에서 다중 엔진이 피싱·악성으로 분류. APWG·Google Safe Browsing·PhishTank 등 다중 출처 합의 신호.",
        "source": "VirusTotal URL Scan / APWG Phishing Activity Trends Report / Google Safe Browsing Transparency Report",
    },
    "suspicious_file_signal": {
        "rationale": "일부 엔진만 의심으로 판정 (false positive 가능성 잔존). 확정적 차단보단 사용자에게 주의 환기 목적의 보조 가산점.",
        "source": "VirusTotal API / 자체 임계값 설계",
    },
    "suspicious_url_signal": {
        "rationale": "URL 이 일부 엔진에서만 의심 — 신생 도메인이거나 평판 낮은 호스팅. 다른 신호와 결합 시 결정적 단서.",
        "source": "VirusTotal URL Scan / APWG 신생 피싱 도메인 통계",
    },
    "authority_context_mismatch": {
        "rationale": "발화자 직업·신원 vs 발화 내용의 SBERT 임베딩 코사인 유사도가 임계 미만 → 사칭 의심. 의미적 일관성 분석 기법.",
        "source": "Reimers & Gurevych (2019) Sentence-BERT, EMNLP / Cer et al. (2017) STS Benchmark",
    },
    "authority_context_uncertain": {
        "rationale": "유사도 경계선상 — 명확하지 않지만 낮은 가산 점수로 보수적 반영. 5점은 단독으론 등급 변화 없으며 다른 신호의 보조 가중치 역할.",
        "source": "자체 임계값 튜닝 / Reimers & Gurevych (2019) SBERT",
    },
    "query_a_confirmed": {
        "rationale": "신뢰 언론(Reuters/Bloomberg/연합 등)에서 화자+발언 동시 확인 → 신뢰도 ↑, 차감. 출처 다중 검증 원칙.",
        "source": "Domain Trust Score (자체 스펙) / Graves, L. (2016) Deciding What's True: The Rise of Political Fact-Checking, Columbia UP",
    },
    "query_a_unconfirmed": {
        "rationale": "신뢰 언론에서 확인 불가 = 출처 검증 실패. 권위 인용의 진위 불명 시 회의 원칙.",
        "source": "Domain Trust Score (자체 스펙) / SIFT 미디어 리터러시 모델 (Caulfield, 2017)",
    },
    "query_b_factcheck_found": {
        "rationale": "팩트체크 결과에서 사기 단서가 발견됨. 독립 검증 기관의 사후 판정 활용.",
        "source": "SNU FactCheck / Snopes / IFCN (International Fact-Checking Network) Code of Principles",
    },
    "query_b_confirmed": {
        "rationale": "팩트체크에서 사실 확인됨 → 신뢰도 보정. 가짜 양성(false positive) 완화 장치.",
        "source": "SNU FactCheck / IFCN",
    },
    "query_c_scam_pattern_found": {
        "rationale": "검색 결과에서 동일/유사 사기 패턴 단서 발견. 사회적 증거(피해자 후기·뉴스)로 추가 가중.",
        "source": "Serper API 검색 휴리스틱 / Cialdini (2021) — Social Proof",
    },
}


def flag_rationale(flag: str) -> dict[str, str]:
    """플래그 점수의 정당성·출처 반환. 매핑 없으면 빈 dict."""
    return FLAG_RATIONALE.get(flag, {})

# ──────────────────────────────────────────────
# 도메인 신뢰도 등급 (노션 스펙 반영)
# ──────────────────────────────────────────────
DOMAIN_TRUST_SCORES: dict[str, int] = {
    # S
    "reuters.com": 3,
    "bloomberg.com": 3,
    "bbc.com": 3,
    "ap.org": 3,
    # A
    "yonhap.co.kr": 2,
    "chosun.com": 2,
    "joongang.co.kr": 2,
}

TRUSTED_QUERY_A_DOMAINS: list[str] = list(DOMAIN_TRUST_SCORES.keys())

# ──────────────────────────────────────────────
# 위험도 레벨 (총점 구간 → 레벨)
# ──────────────────────────────────────────────
RISK_LEVELS: list[tuple[int, str, str]] = [
    (20, "안전", "특이사항 없음"),
    (40, "주의", "일부 의심 요소가 발견됨"),
    (70, "위험", "다수의 스캠 징후가 확인됨"),
    (999, "매우 위험", "높은 확률의 스캠"),
]


def get_risk_level(score: int) -> tuple[str, str]:
    """총점으로부터 위험도 레벨과 설명을 반환한다."""
    for threshold, level, description in RISK_LEVELS:
        if score <= threshold:
            return level, description
    return "매우 위험", "높은 확률의 스캠"


# ──────────────────────────────────────────────
# 모델 식별자
# ──────────────────────────────────────────────
MODELS = {
    "classifier": "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli",
    "gliner": "taeminlee/gliner_ko",
    "sbert_similarity": "paraphrase-multilingual-MiniLM-L12-v2",
    "whisper": "medium",
}

# ──────────────────────────────────────────────
# GLiNER 추출 설정
# ──────────────────────────────────────────────
GLINER_THRESHOLD: float = 0.4          # 재현율 우선 (미탐 방지)
GLINER_CHUNK_SIZE: int = 300           # 문자 기준 청크 크기
GLINER_CHUNK_OVERLAP: int = 50         # 청크 간 겹침 문자 수

# ──────────────────────────────────────────────
# 분류 설정
# ──────────────────────────────────────────────
CLASSIFICATION_THRESHOLD: float = 0.3  # 이 이하면 "판별 불가"

# 키워드 부스팅: NLI 스코어가 애매할 때 키워드 존재로 보정
KEYWORD_BOOST: dict[str, list[str]] = {
    "투자 사기": ["투자", "수익", "수익률", "보장", "펀드", "주식", "원금", "배당"],
    "건강식품 사기": ["건강식품", "치료", "효능", "완치", "약", "질병", "암", "당뇨", "식품", "보조제", "의사", "박사"],
    "부동산 사기": ["부동산", "아파트", "토지", "분양", "재개발", "임대", "평당", "전세", "월세"],
    "코인 사기": ["코인", "비트코인", "토큰", "거래소", "가상자산", "암호화폐", "이더리움", "채굴"],
    "기관 사칭": ["검찰", "경찰", "금감원", "금융감독원", "수사", "사건번호", "안전계좌", "주민번호", "영장", "압수수색"],
    "대출 사기": ["대출", "저금리", "신용등급", "무담보", "무보증", "당일 입금", "선납", "보증금", "수수료", "서민금융"],
    "메신저 피싱": ["카카오톡", "SNS", "지인", "엄마", "아빠", "급해", "잠깐", "계좌", "보내줘", "빌려줘", "사칭"],
    "로맨스 스캠": ["사랑", "좋아해", "만나고 싶어", "군인", "의사", "해외", "달러", "송금", "선물", "비자", "외교관"],
    "취업·알바 사기": ["재택", "알바", "채용", "일당", "시급", "교육비", "등록금", "선입금", "합격", "취업", "스마트폰"],
    "납치·협박형": ["납치", "잡혀있어", "다쳐", "죽여", "협박", "빨리", "경찰 부르면", "가족", "자녀", "보내지 않으면"],
    "스미싱": ["택배", "결제", "링크", "클릭", "확인하세요", "앱 설치", "본인인증", "보안", "업데이트", "URL"],
    "중고거래 사기": ["중고나라", "당근마켓", "번개장터", "직거래", "운송장", "택배", "에스크로", "안전결제", "선입금"],
}
KEYWORD_BOOST_WEIGHT: float = 0.25  # 키워드 매칭 시 가산할 최대 스코어
KEYWORD_NO_MATCH_PENALTY: float = 0.05  # 키워드가 하나도 없을 때 감점

# ──────────────────────────────────────────────
# Serper API 설정
# ──────────────────────────────────────────────
SERPER_API_URL: str = "https://google.serper.dev/search"
SERPER_DELAY: float = 0.5              # 쿼리 간 딜레이 (초)
SERPER_MAX_CONCURRENT: int = int(os.getenv("SERPER_MAX_CONCURRENT", "3"))
SERPER_BATCH_DELAY: float = float(os.getenv("SERPER_BATCH_DELAY", "0.2"))

# ──────────────────────────────────────────────
# STT 설정
# ──────────────────────────────────────────────
STT_BACKEND: str = os.getenv("STT_BACKEND", "whisper")  # "whisper" | "claude"

# ──────────────────────────────────────────────
# Ollama / LLM 보조 판정 설정
# ──────────────────────────────────────────────
OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3.5:9b")
OLLAMA_TIMEOUT_SECONDS: int = int(os.getenv("OLLAMA_TIMEOUT_SECONDS", "120"))
OLLAMA_KEEP_ALIVE: str = os.getenv("OLLAMA_KEEP_ALIVE", "15m")
OLLAMA_MAX_TRANSCRIPT_CHARS: int = int(os.getenv("OLLAMA_MAX_TRANSCRIPT_CHARS", "1200"))
OLLAMA_MAX_ENTITY_COUNT: int = int(os.getenv("OLLAMA_MAX_ENTITY_COUNT", "12"))
OLLAMA_MAX_TRIGGERED_FLAG_COUNT: int = int(os.getenv("OLLAMA_MAX_TRIGGERED_FLAG_COUNT", "6"))
OLLAMA_NUM_PREDICT: int = int(os.getenv("OLLAMA_NUM_PREDICT", "384"))
RAG_TOP_K: int = int(os.getenv("SCAMGUARDIAN_RAG_TOP_K", "3"))
RAG_MAX_CASES_IN_PROMPT: int = int(os.getenv("SCAMGUARDIAN_RAG_MAX_CASES_IN_PROMPT", "3"))

LLM_ENTITY_MERGE_THRESHOLD: float = float(os.getenv("LLM_ENTITY_MERGE_THRESHOLD", "0.7"))
LLM_FLAG_SCORE_THRESHOLD: float = float(os.getenv("LLM_FLAG_SCORE_THRESHOLD", "0.75"))
LLM_FLAG_SCORE_RATIO: float = float(os.getenv("LLM_FLAG_SCORE_RATIO", "0.5"))
LLM_SCAM_TYPE_OVERRIDE_THRESHOLD: float = float(
    os.getenv("LLM_SCAM_TYPE_OVERRIDE_THRESHOLD", "0.7")
)
