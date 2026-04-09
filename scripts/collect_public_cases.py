#!/usr/bin/env python3
"""
공공기관 공개 자료에서 사기/스미싱 사례 텍스트를 수집해 JSONL로 저장한다.

기본 대상:
- KISA 보호나라(boho.or.kr)
- 경찰청 전기통신금융사기 통합대응단(counterscam112.go.kr)
- 금융위원회/금감원(fsc.go.kr)

출력 형식(JSONL 각 줄):
{"text": "...", "metadata": {...}}

예시:
    python scripts/collect_public_cases.py --org all
    python scripts/collect_public_cases.py --org kisa --max-items-per-source 20
    python scripts/collect_public_cases.py --output data/processed/public_cases.jsonl
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from html import unescape
from pathlib import Path
from typing import Iterable
from urllib.parse import urljoin, urlparse

import requests

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw" / "public_cases"
PROCESSED_DIR = ROOT / "data" / "processed"
USER_AGENT = "ScamGuardianPublicCollector/1.0 (+official-public-data-only)"
TIMEOUT = 20


@dataclass(frozen=True)
class SourceSpec:
    org: str
    title: str
    channel: str
    listing_urls: list[str]
    allowed_domains: tuple[str, ...]
    detail_url_patterns: tuple[str, ...] = ()
    direct_urls: tuple[str, ...] = ()


SOURCE_SPECS: list[SourceSpec] = [
    SourceSpec(
        org="kisa",
        title="KISA 보호나라 스미싱 주의보/보안공지",
        channel="security_notice",
        listing_urls=[
            "https://www.boho.or.kr/kr/bbs/view.do?bbsId=B0000030&menuNo=205027&nttId=71280",
            "https://www.boho.or.kr/kr/bbs/view.do?bbsId=B0000133&menuNo=205020&nttId=71675",
        ],
        allowed_domains=("boho.or.kr",),
        detail_url_patterns=("/kr/bbs/view.do",),
    ),
    SourceSpec(
        org="police",
        title="경찰청 전기통신금융사기 통합대응단",
        channel="advisory",
        listing_urls=[
            "https://www.counterscam112.go.kr/bbs003/board/boardList.do",
            "https://www.counterscam112.go.kr/bbs006/board/boardList.do",
        ],
        allowed_domains=("counterscam112.go.kr",),
        detail_url_patterns=("/bbs003/board/boardDetail.do", "/bbs006/board/boardDetail.do"),
        direct_urls=(
            "https://www.counterscam112.go.kr/",
        ),
    ),
    SourceSpec(
        org="fsc",
        title="금융위원회 보이스피싱 예방 자료",
        channel="prevention_guide",
        listing_urls=[
            "https://www.fsc.go.kr/no010101/86250",
            "https://www.fsc.go.kr/no040101?cnId=2426&curPage=&pastPage=&srchKey=sj&srchText=%EB%B3%B4%EC%9D%B4%EC%8A%A4%ED%94%BC%EC%8B%B1",
        ],
        allowed_domains=("fsc.go.kr",),
        detail_url_patterns=("/no010101/", "/edu/cardnews", "/comm/getFile"),
        direct_urls=(
            "https://www.fsc.go.kr/no010101/86250",
            "https://www.fsc.go.kr/comm/getFile?fileNo=2&fileTy=ATTACH&srvcId=BBSTY1&upperNo=86250",
        ),
    ),
]

SCAM_HINTS = [
    "링크", "url", "클릭", "설치", "앱", "원격", "송금", "이체", "입금", "계좌", "현금",
    "검찰", "경찰", "금감원", "택배", "등기", "부고", "청첩장", "과태료", "범칙금", "대출",
    "보증금", "공탁금", "카드", "명의도용", "본인확인", "악성", "apk", "사칭", "피싱", "스미싱",
]
URL_RE = re.compile(r"https?://\S+", re.I)
TAG_RE = re.compile(r"<[^>]+>")
MULTISPACE_RE = re.compile(r"[ \t]+")
MULTINEW_RE = re.compile(r"\n{3,}")
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.I)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
DATE_RE = re.compile(r"(20\d{2}[.-]\d{1,2}[.-]\d{1,2})")


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": USER_AGENT})
    return s


def _slugify(value: str) -> str:
    value = re.sub(r"[^0-9A-Za-z가-힣._-]+", "-", value.strip())
    return value.strip("-")[:80] or "document"


def _is_allowed(url: str, allowed_domains: tuple[str, ...]) -> bool:
    host = urlparse(url).netloc.lower()
    return any(host.endswith(domain) for domain in allowed_domains)


def _clean_html_text(html: str) -> str:
    html = re.sub(r"<script[\s\S]*?</script>", " ", html, flags=re.I)
    html = re.sub(r"<style[\s\S]*?</style>", " ", html, flags=re.I)
    html = re.sub(r"</(p|div|li|tr|br|h1|h2|h3|h4|h5|h6)>", "\n", html, flags=re.I)
    text = TAG_RE.sub(" ", html)
    text = unescape(text)
    text = MULTISPACE_RE.sub(" ", text)
    text = MULTINEW_RE.sub("\n\n", text)
    return text.strip()


def _extract_title(html: str, fallback: str) -> str:
    m = TITLE_RE.search(html)
    if not m:
        return fallback
    title = _clean_html_text(m.group(1))
    return title or fallback


def _extract_dates(text: str) -> str | None:
    m = DATE_RE.search(text)
    if not m:
        return None
    return m.group(1).replace(".", "-")


def _extract_links(base_url: str, html: str, spec: SourceSpec) -> list[str]:
    urls: list[str] = []
    for href in HREF_RE.findall(html):
        abs_url = urljoin(base_url, href)
        if not _is_allowed(abs_url, spec.allowed_domains):
            continue
        if spec.detail_url_patterns and not any(pattern in abs_url for pattern in spec.detail_url_patterns):
            continue
        urls.append(abs_url)
    deduped: list[str] = []
    seen: set[str] = set()
    for url in [*spec.direct_urls, *urls]:
        if url not in seen:
            seen.add(url)
            deduped.append(url)
    return deduped


def _extract_pdf_text(content: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
    except Exception as exc:  # pragma: no cover
        raise RuntimeError("PDF 추출을 위해 pypdf가 필요합니다. requirements.txt 설치 후 다시 시도하세요.") from exc

    import io
    reader = PdfReader(io.BytesIO(content))
    parts: list[str] = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        if page_text.strip():
            parts.append(page_text)
    return "\n\n".join(parts).strip()


def _looks_like_case(line: str) -> bool:
    compact = line.strip()
    if len(compact) < 18:
        return False
    lowered = compact.lower()
    if URL_RE.search(compact):
        return True
    return any(hint in lowered for hint in SCAM_HINTS)


def _split_candidate_blocks(text: str) -> list[str]:
    text = text.replace("\r\n", "\n")
    blocks = re.split(r"\n\s*\n", text)
    candidates: list[str] = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue
        lines = [MULTISPACE_RE.sub(" ", line).strip(" -•·\t") for line in block.splitlines()]
        lines = [line for line in lines if line]
        if not lines:
            continue
        joined = " ".join(lines)
        if _looks_like_case(joined):
            candidates.append(joined)
            continue
        for line in lines:
            if _looks_like_case(line):
                candidates.append(line)
    return candidates


def _normalize_case_text(text: str) -> str:
    text = MULTISPACE_RE.sub(" ", text)
    return text.strip()


def _infer_type(text: str) -> str | None:
    mapping = {
        "기관사칭": ["검찰", "경찰", "금감원", "명의도용"],
        "대출빙자": ["대출", "보증금", "공탁금"],
        "스미싱": ["택배", "링크", "url", "클릭", "앱", "부고", "청첩장", "과태료", "범칙금"],
        "카드배송사칭": ["카드", "배송", "등기"],
    }
    lowered = text.lower()
    for label, hints in mapping.items():
        if any(h.lower() in lowered for h in hints):
            return label
    return None


def _build_record(*, text: str, spec: SourceSpec, source_url: str, doc_title: str, published_at: str | None) -> dict[str, object]:
    normalized = _normalize_case_text(text)
    return {
        "text": normalized,
        "metadata": {
            "source": "public_agency",
            "source_org": spec.org,
            "source_title": spec.title,
            "source_url": source_url,
            "doc_title": doc_title,
            "published_at": published_at,
            "channel": spec.channel,
            "evidence_level": "official_public_case",
            "scam_type_hint": _infer_type(normalized),
            "has_url": bool(URL_RE.search(normalized)),
        },
    }


def collect_from_spec(spec: SourceSpec, *, max_items_per_source: int, save_raw: bool, session: requests.Session) -> list[dict[str, object]]:
    collected: list[dict[str, object]] = []
    seen_texts: set[str] = set()
    raw_dir = RAW_DIR / spec.org
    raw_dir.mkdir(parents=True, exist_ok=True)

    candidate_urls: list[str] = []
    for listing_url in spec.listing_urls:
        try:
            response = session.get(listing_url, timeout=TIMEOUT)
            response.raise_for_status()
        except Exception as exc:
            print(f"[WARN] 목록 페이지 수집 실패: {listing_url} ({exc})", file=sys.stderr)
            continue

        html = response.text
        if save_raw:
            (raw_dir / f"listing-{_slugify(listing_url)}.html").write_text(html, encoding="utf-8")
        candidate_urls.extend(_extract_links(listing_url, html, spec))

    # direct URLs only source도 허용
    for url in spec.direct_urls:
        if url not in candidate_urls:
            candidate_urls.append(url)

    for source_url in candidate_urls:
        if len(collected) >= max_items_per_source:
            break
        try:
            response = session.get(source_url, timeout=TIMEOUT)
            response.raise_for_status()
        except Exception as exc:
            print(f"[WARN] 상세 페이지 수집 실패: {source_url} ({exc})", file=sys.stderr)
            continue

        content_type = (response.headers.get("content-type") or "").lower()
        if "pdf" in content_type or source_url.lower().endswith(".pdf"):
            try:
                text = _extract_pdf_text(response.content)
            except Exception as exc:
                print(f"[WARN] PDF 추출 실패: {source_url} ({exc})", file=sys.stderr)
                continue
            doc_title = source_url.rsplit("/", 1)[-1]
        else:
            html = response.text
            if save_raw:
                (raw_dir / f"detail-{_slugify(source_url)}.html").write_text(html, encoding="utf-8")
            text = _clean_html_text(html)
            doc_title = _extract_title(html, source_url)

        published_at = _extract_dates(text)
        cases = _split_candidate_blocks(text)
        for case_text in cases:
            normalized = _normalize_case_text(case_text)
            if normalized in seen_texts:
                continue
            seen_texts.add(normalized)
            collected.append(
                _build_record(
                    text=normalized,
                    spec=spec,
                    source_url=source_url,
                    doc_title=doc_title,
                    published_at=published_at,
                )
            )
            if len(collected) >= max_items_per_source:
                break

    return collected


def _iter_specs(org: str) -> Iterable[SourceSpec]:
    org = org.lower().strip()
    if org == "all":
        return SOURCE_SPECS
    return [spec for spec in SOURCE_SPECS if spec.org == org]


def main() -> None:
    parser = argparse.ArgumentParser(description="공공기관 공개 사기 사례 수집기")
    parser.add_argument("--org", choices=["all", "kisa", "police", "fsc"], default="all")
    parser.add_argument("--output", default=str(PROCESSED_DIR / "public_cases.jsonl"))
    parser.add_argument("--max-items-per-source", type=int, default=50)
    parser.add_argument("--no-raw", action="store_true", help="raw HTML/PDF 저장 생략")
    args = parser.parse_args()

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = ROOT / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    session = _session()
    all_records: list[dict[str, object]] = []
    for spec in _iter_specs(args.org):
        records = collect_from_spec(
            spec,
            max_items_per_source=max(1, args.max_items_per_source),
            save_raw=not args.no_raw,
            session=session,
        )
        print(f"[{spec.org}] {len(records)}건 수집")
        all_records.extend(records)

    deduped: list[dict[str, object]] = []
    seen: set[str] = set()
    for record in all_records:
        text = str(record.get("text", "")).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        deduped.append(record)

    with output_path.open("w", encoding="utf-8") as fh:
        for record in deduped:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"총 {len(deduped)}건 저장: {output_path}")


if __name__ == "__main__":
    main()
