#!/usr/bin/env python3
"""
ScamGuardian v2 — 공공기관 공개 사례 수집 스크립트

목표:
- 공공기관(경찰청/통합대응단, KISA, 금융위 등) 공개 페이지에서
  보이스피싱/스미싱/피싱 관련 사례성 문구를 수집
- 안내문/문의처/보도자료 헤더/푸터/예방수칙 제목 등은 최대한 제거
- batch_ingest.py 에 바로 넣을 수 있는 JSONL 생성

출력:
- data/processed/public_cases.jsonl               : 적재 추천 샘플
- data/processed/public_cases.rejected.jsonl      : 필터에서 탈락한 샘플
- data/raw/public_cases_fetch_log.json            : 수집 로그

사용 예:
    python scripts/collect_public_cases.py
    python scripts/collect_public_cases.py --org all
    python scripts/collect_public_cases.py --org kisa
    python scripts/collect_public_cases.py --max-items-per-source 50
"""

from __future__ import annotations

import argparse
import io
import json
import re
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"

RAW_DIR.mkdir(parents=True, exist_ok=True)
PROCESSED_DIR.mkdir(parents=True, exist_ok=True)

OUTPUT_JSONL = PROCESSED_DIR / "public_cases.jsonl"
REJECTED_JSONL = PROCESSED_DIR / "public_cases.rejected.jsonl"
FETCH_LOG_JSON = RAW_DIR / "public_cases_fetch_log.json"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7",
}

SOURCE_CONFIGS: dict[str, list[str]] = {
    "kisa": [
        "https://www.boho.or.kr/kr/bbs/list.do?bbsId=B0000030&menuNo=205027",  # 스미싱 주의보 계열
        "https://www.boho.or.kr/kr/bbs/list.do?bbsId=B0000133&menuNo=205020",  # 보안공지 계열
    ],
    "police": [
        "https://www.counterscam112.go.kr/",
        "https://www.counterscam112.go.kr/phishing/prevent.do",
        "https://www.counterscam112.go.kr/board/notice/list.do",
    ],
    "fsc": [
        "https://www.fsc.go.kr/no010101/86250",
        "https://www.fsc.go.kr/no040101?cnId=2426&curPage=&pastPage=&srchKey=sj&srchText=%EB%B3%B4%EC%9D%B4%EC%8A%A4%ED%94%BC%EC%8B%B1",
    ],
}

ORG_LABELS = {
    "kisa": "KISA",
    "police": "경찰청",
    "fsc": "금융위",
}

SCAM_HINTS = [
    "링크",
    "클릭",
    "주소를 재입력",
    "인증",
    "본인 확인",
    "비밀번호",
    "인증번호",
    "계좌",
    "입금",
    "송금",
    "이체",
    "원금 보장",
    "수익 보장",
    "대출",
    "수사",
    "검찰",
    "경찰",
    "금감원",
    "금융감독원",
    "국세청",
    "택배",
    "반송",
    "청첩장",
    "부고",
    "범칙금",
    "과태료",
    "앱 설치",
    "악성앱",
    "보안카드",
    "공인인증서",
    "OTP",
    "카카오톡",
    "엄마 나",
    "아들",
    "딸",
    "안전 계좌",
    "보호 계좌",
    "저금리",
    "사전 물량",
    "투자 리딩방",
]

DROP_KEYWORDS = [
    "예방 방법",
    "예방수칙",
    "행동수칙",
    "대응 방법",
    "유의사항",
    "주의사항",
    "유의하세요",
    "피해예방",
    "보도자료",
    "보도 참고자료",
    "참고자료",
    "참고 ",
    "붙임",
    "문의",
    "대표전화",
    "작성 :",
    "작성:",
    "배포일",
    "담당부서",
    "담당자",
    "국민피해대응단",
    "전기통신금융사기 통합대응단",
    "금융위 문의",
    "홈페이지",
    "저작권",
    "무단전재",
    "재배포",
    "바로가기",
    "다운로드",
    "첨부파일",
    "목차",
    "요약",
]

SECTION_DROP_PATTERNS = [
    r"^o\s",
    r"^□\s",
    r"^■\s",
    r"^※",
    r"^\[붙임",
    r"^\[참고",
    r"^문의\s*:",
    r"^담당부서",
    r"^금융위 문의",
]

URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
PHONE_RE = re.compile(r"\b\d{2,4}-\d{3,4}-\d{4}\b")
DATE_RE = re.compile(r"(20\d{2}[.\-/년]\s*\d{1,2}[.\-/월]\s*\d{1,2}일?)")
MULTISPACE_RE = re.compile(r"\s+")
SENTENCE_SPLIT_RE = re.compile(r"(?:(?<=[.!?])|(?<=다\.))\s+")
KOREAN_CHAR_RE = re.compile(r"[가-힣]")


@dataclass
class FetchLogItem:
    org: str
    url: str
    ok: bool
    status_code: int | None = None
    content_type: str | None = None
    error: str | None = None
    discovered_links: int = 0
    extracted_segments: int = 0
    accepted_segments: int = 0
    rejected_segments: int = 0


def get_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    return session


def fetch_url(session: requests.Session, url: str, timeout: int = 20) -> requests.Response:
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True)
            resp.raise_for_status()
            return resp
        except Exception as exc:
            last_error = exc
            if attempt < 2:
                time.sleep(1.0 * (attempt + 1))
    assert last_error is not None
    raise last_error


def normalize_text(text: str) -> str:
    text = text.replace("\u00a0", " ")
    text = text.replace("\t", " ")
    text = text.replace("\r", "\n")
    text = MULTISPACE_RE.sub(" ", text)
    return text.strip()


def split_text_to_segments(text: str) -> list[str]:
    text = normalize_text(text)
    if not text:
        return []

    # 줄기반 분리
    raw_parts: list[str] = []
    for line in text.split("\n"):
        line = normalize_text(line)
        if not line:
            continue
        raw_parts.append(line)

    # 문장 길이가 길면 문장 분할
    parts: list[str] = []
    for part in raw_parts:
        if len(part) > 180:
            chunks = [normalize_text(s) for s in SENTENCE_SPLIT_RE.split(part) if normalize_text(s)]
            parts.extend(chunks if chunks else [part])
        else:
            parts.append(part)

    # 최종 정리
    cleaned: list[str] = []
    for part in parts:
        part = normalize_text(part)
        if not part:
            continue
        cleaned.append(part)

    return cleaned


def extract_text_from_html(html: str) -> tuple[str, list[str]]:
    soup = BeautifulSoup(html, "html.parser")

    for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
        tag.decompose()

    text = soup.get_text("\n", strip=True)

    links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href:
            links.append(href)

    return text, links


def extract_text_from_pdf_bytes(data: bytes) -> str:
    reader = PdfReader(io.BytesIO(data))
    texts: list[str] = []
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        page_text = normalize_text(page_text)
        if page_text:
            texts.append(page_text)
    return "\n".join(texts)


def is_probably_korean_text(text: str) -> bool:
    return bool(KOREAN_CHAR_RE.search(text))


def score_segment(text: str) -> int:
    score = 0
    t = text

    if len(t) >= 45:
        score += 1
    if len(t) >= 70:
        score += 1

    if URL_RE.search(t):
        score += 3
    if PHONE_RE.search(t):
        score += 1

    hint_hits = sum(1 for hint in SCAM_HINTS if hint in t)
    score += min(hint_hits, 5)

    if "http" in t or "www." in t:
        score += 2
    if "클릭" in t:
        score += 2
    if "입금" in t or "송금" in t or "이체" in t:
        score += 2
    if "앱 설치" in t or "악성앱" in t:
        score += 2
    if "비밀번호" in t or "인증번호" in t or "보안카드" in t:
        score += 2
    if "검찰" in t or "경찰" in t or "금감원" in t or "금융감독원" in t:
        score += 1

    drop_hits = sum(1 for kw in DROP_KEYWORDS if kw in t)
    score -= min(drop_hits * 2, 8)

    for pattern in SECTION_DROP_PATTERNS:
        if re.search(pattern, t):
            score -= 2

    if len(t) < 20:
        score -= 4
    elif len(t) < 35:
        score -= 2

    return score


def reject_reason(text: str) -> str | None:
    t = text.strip()

    if not t:
        return "empty"
    if not is_probably_korean_text(t):
        return "not_korean"
    if len(t) < 18:
        return "too_short"
    if len(t) > 400:
        return "too_long"

    if DATE_RE.fullmatch(t):
        return "date_only"

    for pattern in SECTION_DROP_PATTERNS:
        if re.search(pattern, t):
            return "section_header"

    for kw in DROP_KEYWORDS:
        if kw in t:
            # 단, 스캠 유도 표현이 아주 강한 경우는 살릴 수 있게 아래 score에서 다시 판정
            if score_segment(t) < 5:
                return f"drop_keyword:{kw}"

    # 기관명만 덩그러니 있는 라인
    if len(t) < 40 and any(x in t for x in ["경찰청", "금융위원회", "금융감독원", "KISA", "보호나라"]):
        if score_segment(t) < 4:
            return "org_header"

    return None


def is_good_case_text(text: str) -> bool:
    reason = reject_reason(text)
    if reason is not None:
        return False

    score = score_segment(text)
    if score >= 4:
        return True

    # 점수는 낮아도 URL/입금/클릭/인증번호 등 직접 유도면 살림
    forced_keep = [
        "아래 링크",
        "클릭하여 인증",
        "본인 확인",
        "인증번호를 입력",
        "입금해주시면",
        "송금해주세요",
        "계좌로 보내",
        "앱을 설치",
        "보호 계좌",
        "안전 계좌",
        "급하게 돈",
        "엄마 나",
    ]
    if any(x in text for x in forced_keep):
        return True

    return False


def infer_channel(text: str, url: str) -> str:
    if "보도자료" in text:
        return "press_release"
    if "주의보" in text or "경보" in text:
        return "alert"
    if "FAQ" in text or "faq" in url.lower():
        return "faq"
    if "예방" in text or "수칙" in text:
        return "prevention"
    return "web_page"


def infer_scam_type_hint(text: str) -> str | None:
    if any(x in text for x in ["청첩장", "택배", "반송", "과태료", "범칙금", "악성앱", "앱 설치", "링크"]):
        return "스미싱"
    if any(x in text for x in ["검찰", "경찰", "금감원", "보호 계좌", "안전 계좌"]):
        return "기관사칭"
    if any(x in text for x in ["저금리", "대출", "선납", "보험료"]):
        return "대출 사기"
    if any(x in text for x in ["원금 보장", "수익 보장", "투자 리딩방", "코인"]):
        return "투자 사기"
    if any(x in text for x in ["엄마 나", "카카오톡", "친구 폰"]):
        return "메신저 피싱"
    return None


def build_record(
    *,
    org_key: str,
    url: str,
    doc_title: str,
    published_at: str | None,
    text: str,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "source": "public_agency",
        "source_org": ORG_LABELS.get(org_key, org_key),
        "source_url": url,
        "doc_title": doc_title[:300],
        "published_at": published_at,
        "channel": infer_channel(doc_title + " " + text, url),
        "evidence_level": "official_case",
        "scam_type_hint": infer_scam_type_hint(text),
        "collector": "collect_public_cases.py",
    }
    return {
        "text": text,
        "metadata": metadata,
    }


def parse_links(base_url: str, hrefs: list[str]) -> list[str]:
    results: list[str] = []
    for href in hrefs:
        if href.startswith("javascript:") or href.startswith("#"):
            continue
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.scheme not in {"http", "https"}:
            continue
        if full not in results:
            results.append(full)
    return results


def extract_doc_title(text: str, url: str) -> str:
    lines = [normalize_text(x) for x in text.split("\n") if normalize_text(x)]
    if lines:
        return lines[0][:300]
    return url


def extract_published_at(text: str) -> str | None:
    match = DATE_RE.search(text)
    if not match:
        return None
    return normalize_text(match.group(1))


def process_page(
    *,
    session: requests.Session,
    org_key: str,
    url: str,
    max_links: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], FetchLogItem]:
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    try:
        resp = fetch_url(session, url)
    except Exception as exc:
        return [], [], FetchLogItem(
            org=org_key,
            url=url,
            ok=False,
            error=str(exc),
        )

    content_type = resp.headers.get("Content-Type", "")
    log = FetchLogItem(
        org=org_key,
        url=url,
        ok=True,
        status_code=resp.status_code,
        content_type=content_type,
    )

    discovered_urls: list[str] = []

    if "pdf" in content_type.lower() or url.lower().endswith(".pdf"):
        text = extract_text_from_pdf_bytes(resp.content)
        doc_title = extract_doc_title(text, url)
        published_at = extract_published_at(text)
        segments = split_text_to_segments(text)
    else:
        html = resp.text
        text, hrefs = extract_text_from_html(html)
        doc_title = extract_doc_title(text, url)
        published_at = extract_published_at(text)
        segments = split_text_to_segments(text)
        discovered_urls = parse_links(url, hrefs)

    log.discovered_links = len(discovered_urls)

    seen_segments: set[str] = set()
    filtered_segments: list[str] = []
    for seg in segments:
        seg = normalize_text(seg)
        if not seg or seg in seen_segments:
            continue
        seen_segments.add(seg)
        filtered_segments.append(seg)

    log.extracted_segments = len(filtered_segments)

    for seg in filtered_segments:
        if is_good_case_text(seg):
            accepted.append(
                build_record(
                    org_key=org_key,
                    url=url,
                    doc_title=doc_title,
                    published_at=published_at,
                    text=seg,
                )
            )
        else:
            rejected.append(
                {
                    "text": seg,
                    "metadata": {
                        "source": "public_agency_rejected",
                        "source_org": ORG_LABELS.get(org_key, org_key),
                        "source_url": url,
                        "doc_title": doc_title[:300],
                        "published_at": published_at,
                        "reject_reason": reject_reason(seg),
                        "score": score_segment(seg),
                        "collector": "collect_public_cases.py",
                    },
                }
            )

    log.accepted_segments = len(accepted)
    log.rejected_segments = len(rejected)

    # 목록 페이지에서 발견한 링크 중 관련성 있는 몇 개 추가 수집
    crawled_subpages = 0
    for sub_url in discovered_urls:
        if crawled_subpages >= max_links:
            break
        lower = sub_url.lower()

        # 파일/페이지 중 관련성 낮은 것 배제
        if any(x in lower for x in [".jpg", ".png", ".gif", ".zip", ".hwp"]):
            continue

        # 피싱/스미싱/보이스피싱/금융사기 관련 링크만 우선 수집
        if not any(
            k in sub_url
            for k in ["피싱", "스미싱", "보이스", "금융사기", "phishing", "smishing", "scam", "fraud"]
        ):
            # 링크 텍스트가 없는 상황이라 URL 기준으로 느슨하게만 필터
            continue

        crawled_subpages += 1
        try:
            sub_accepted, sub_rejected, _ = process_page(
                session=session,
                org_key=org_key,
                url=sub_url,
                max_links=0,
            )
            accepted.extend(sub_accepted)
            rejected.extend(sub_rejected)
        except Exception:
            pass

    return accepted, rejected, log


def dedupe_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    deduped: list[dict[str, Any]] = []

    for item in records:
        text = normalize_text(str(item.get("text", "")))
        md = item.get("metadata", {})
        source_url = str(md.get("source_url", "")) if isinstance(md, dict) else ""
        key = (text, source_url)

        if not text or key in seen:
            continue
        seen.add(key)
        deduped.append(item)

    return deduped


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for item in records:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="공공기관 공개 사례 수집기")
    parser.add_argument(
        "--org",
        choices=["all", "kisa", "police", "fsc"],
        default="all",
        help="수집 기관 선택",
    )
    parser.add_argument(
        "--max-items-per-source",
        type=int,
        default=20,
        help="목록 페이지에서 추가로 따라갈 하위 링크 수 제한",
    )
    args = parser.parse_args()

    target_orgs = list(SOURCE_CONFIGS.keys()) if args.org == "all" else [args.org]

    session = get_session()

    all_accepted: list[dict[str, Any]] = []
    all_rejected: list[dict[str, Any]] = []
    fetch_logs: list[dict[str, Any]] = []

    for org_key in target_orgs:
        start_count = len(all_accepted)
        for url in SOURCE_CONFIGS[org_key]:
            print(f"[INFO] 수집 중: {org_key} | {url}")
            accepted, rejected, log = process_page(
                session=session,
                org_key=org_key,
                url=url,
                max_links=args.max_items_per_source,
            )
            all_accepted.extend(accepted)
            all_rejected.extend(rejected)
            fetch_logs.append(asdict(log))

            if log.ok:
                print(
                    f"  -> accepted={log.accepted_segments}, "
                    f"rejected={log.rejected_segments}, "
                    f"links={log.discovered_links}"
                )
            else:
                print(f"  -> [WARN] 수집 실패: {log.error}")

        delta = len(all_accepted) - start_count
        print(f"[{org_key}] {delta}건 accepted 누적")

    all_accepted = dedupe_records(all_accepted)
    all_rejected = dedupe_records(all_rejected)

    write_jsonl(OUTPUT_JSONL, all_accepted)
    write_jsonl(REJECTED_JSONL, all_rejected)
    FETCH_LOG_JSON.write_text(
        json.dumps(fetch_logs, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"\n총 accepted {len(all_accepted)}건 저장: {OUTPUT_JSONL}")
    print(f"총 rejected {len(all_rejected)}건 저장: {REJECTED_JSONL}")
    print(f"수집 로그 저장: {FETCH_LOG_JSON}")
    print("\n다음 단계:")
    print(f"python scripts/batch_ingest.py --jsonl {OUTPUT_JSONL} --skip-verify --workers 1")


if __name__ == "__main__":
    main()