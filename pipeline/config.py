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
]

# NLI 모델용 설명적 레이블 → 짧은 레이블 매핑
# mDeBERTa가 의미를 더 잘 구분하도록 구체적 설명 사용
DEFAULT_SCAM_TYPE_DESCRIPTIONS: dict[str, str] = {
    "높은 수익률을 보장하며 투자금을 요구": "투자 사기",
    "건강식품이나 약으로 질병 치료를 주장하며 판매": "건강식품 사기",
    "부동산 개발 투자 수익을 약속하며 돈을 요구": "부동산 사기",
    "암호화폐 코인 투자로 큰 수익을 약속": "코인 사기",
    "경찰 검찰 금융감독원 등 정부기관을 사칭하여 개인정보나 송금을 요구": "기관 사칭",
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
}
KEYWORD_BOOST_WEIGHT: float = 0.25  # 키워드 매칭 시 가산할 최대 스코어
KEYWORD_NO_MATCH_PENALTY: float = 0.05  # 키워드가 하나도 없을 때 감점

# ──────────────────────────────────────────────
# Serper API 설정
# ──────────────────────────────────────────────
SERPER_API_URL: str = "https://google.serper.dev/search"
SERPER_DELAY: float = 0.5              # 쿼리 간 딜레이 (초)

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
