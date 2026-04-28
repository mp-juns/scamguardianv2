"""
ScamGuardian v3 — Phase 1 확장: 이미지·PDF → 한국어 텍스트(OCR + 시각 단서) 변환.

Claude vision (sonnet-4-6) 한 번 호출로 텍스트 인식과 시각적 사기 단서를 같이
뽑아 자연스러운 한국어 본문으로 합친다. 출력은 기존 파이프라인(분류기·추출기·
스코어러) 가 그대로 사용할 수 있도록 `stt.TranscriptResult` 와 호환되는 형태.

지원 입력:
- 이미지 (.jpg .jpeg .png .webp .gif .bmp)
- PDF (.pdf) — 첫 N페이지(기본 5)를 이미지로 렌더해 단일 멀티이미지 메시지로 전송
"""

from __future__ import annotations

import base64
import io
import logging
import mimetypes
import os
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger("vision")

DEFAULT_MODEL = os.getenv("ANTHROPIC_VISION_MODEL", os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"))
PDF_MAX_PAGES = int(os.getenv("VISION_PDF_MAX_PAGES", "5"))
PDF_RENDER_DPI = int(os.getenv("VISION_PDF_DPI", "150"))
IMAGE_MAX_BYTES = 5 * 1024 * 1024   # Anthropic API 단일 이미지 권장 한도
IMAGE_MAX_LONG_EDGE = 1568           # Anthropic 권장: 짧은 변 ~1568px 권장

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp"}
PDF_SUFFIXES = {".pdf"}


VISION_SYSTEM_PROMPT = (
    "당신은 한국어 보이스피싱·금융사기 분석 전문가의 OCR 어시스턴트입니다. "
    "이미지(또는 PDF 페이지) 를 받아 사기 분석에 필요한 모든 정보를 한국어 본문으로 정리합니다."
)


VISION_USER_PROMPT = """
첨부된 이미지(또는 PDF 페이지)를 분석해서 아래 형식의 **한국어 본문 한 단락**으로 출력해 주세요.
별도 JSON·헤더·번호 없이 사람이 읽는 자연스러운 본문 형태입니다.

본문에 반드시 포함:
1. 이미지에 적힌 모든 텍스트(문구·로고 텍스트·연락처·URL·계좌번호·QR코드 옆 텍스트 등) 를 빠짐없이 그대로 옮김.
2. 시각적 사기 신호 — 위조·과장·모방으로 의심되는 요소를 한국어로 묘사:
   - 가짜 인증 마크 / 위조 로고 (예: '금융감독원' / 'KB국민은행' 등을 사칭한 그래픽)
   - 과장된 폰트·색상 (대형 빨간 글씨로 '확정 수익' 등)
   - 긴급성 강조 표시 (마감시간·한정 인원·24시간 등)
   - 메신저·SNS 캡쳐인 경우 — 발신자 표시명, 프로필 사진의 사칭 단서, 대화 흐름
   - QR 코드·단축 URL 의 존재 여부
3. 페이지가 여러 장이면 각 페이지 내용을 시간 순서대로 통합.
4. 의견·판단(사기다·정상이다)은 추가하지 말고 *관찰*만.

이 본문이 다음 단계 한국어 분류기에 그대로 입력되므로, **자연스러운 한국어 문장**으로 써야 합니다.
""".strip()


@dataclass
class VisionResult:
    text: str
    source_type: str          # "image" | "pdf"
    page_count: int = 1
    model: str = ""


def is_image(path: Path) -> bool:
    return path.suffix.lower() in IMAGE_SUFFIXES


def is_pdf(path: Path) -> bool:
    return path.suffix.lower() in PDF_SUFFIXES


def supported(path: str | Path) -> bool:
    p = Path(path)
    return is_image(p) or is_pdf(p)


# ──────────────────────────────────
# 이미지 전처리 — 너무 크면 다운스케일
# ──────────────────────────────────
def _maybe_downscale(image_bytes: bytes, suffix: str) -> tuple[bytes, str]:
    """Anthropic 권장 크기로 다운스케일. 원본이 충분히 작으면 그대로."""
    if len(image_bytes) <= IMAGE_MAX_BYTES and not _likely_oversized(image_bytes):
        media_type = _media_type_for(suffix)
        return image_bytes, media_type
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        return image_bytes, _media_type_for(suffix)

    with Image.open(io.BytesIO(image_bytes)) as img:
        img = img.convert("RGB")
        w, h = img.size
        long_edge = max(w, h)
        if long_edge > IMAGE_MAX_LONG_EDGE:
            scale = IMAGE_MAX_LONG_EDGE / long_edge
            img = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        return buf.getvalue(), "image/jpeg"


def _likely_oversized(image_bytes: bytes) -> bool:
    return len(image_bytes) > IMAGE_MAX_BYTES // 2


def _media_type_for(suffix: str) -> str:
    suffix = suffix.lower()
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
    }.get(suffix, mimetypes.guess_type(f"x{suffix}")[0] or "image/jpeg")


# ──────────────────────────────────
# PDF → 페이지별 PNG 렌더
# ──────────────────────────────────
def _render_pdf_pages(path: Path, max_pages: int = PDF_MAX_PAGES) -> list[bytes]:
    import pypdfium2 as pdfium  # type: ignore

    pages: list[bytes] = []
    pdf = pdfium.PdfDocument(str(path))
    try:
        n = min(len(pdf), max_pages)
        scale = PDF_RENDER_DPI / 72.0  # PDF default 72 DPI
        for i in range(n):
            page = pdf[i]
            try:
                bitmap = page.render(scale=scale, rotation=0)
                pil_image = bitmap.to_pil()
                buf = io.BytesIO()
                pil_image.save(buf, format="PNG")
                pages.append(buf.getvalue())
            finally:
                page.close()
        return pages
    finally:
        pdf.close()


# ──────────────────────────────────
# Claude vision 호출
# ──────────────────────────────────
def _anthropic_client():
    import anthropic
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise EnvironmentError("ANTHROPIC_API_KEY 가 설정되지 않았습니다.")
    return anthropic.Anthropic(api_key=api_key)


def _call_vision(
    image_chunks: list[tuple[bytes, str]],
    *,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 2048,
) -> str:
    client = _anthropic_client()

    content: list[dict] = []
    for img_bytes, media_type in image_chunks:
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": base64.standard_b64encode(img_bytes).decode("ascii"),
            },
        })
    content.append({"type": "text", "text": VISION_USER_PROMPT})

    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=VISION_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": content}],
    )
    text_parts: list[str] = []
    for block in message.content:
        text = getattr(block, "text", None)
        if text:
            text_parts.append(text)
    return "\n".join(text_parts).strip()


# ──────────────────────────────────
# 공개 API
# ──────────────────────────────────
def transcribe_image(path: str | Path, *, model: str = DEFAULT_MODEL) -> VisionResult:
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"이미지를 찾을 수 없습니다: {p}")
    if not is_image(p):
        raise ValueError(f"이미지 확장자가 아닙니다: {p.suffix}")
    image_bytes = p.read_bytes()
    payload = _maybe_downscale(image_bytes, p.suffix)
    text = _call_vision([payload], model=model)
    return VisionResult(text=text, source_type="image", page_count=1, model=model)


def transcribe_pdf(
    path: str | Path,
    *,
    model: str = DEFAULT_MODEL,
    max_pages: int = PDF_MAX_PAGES,
) -> VisionResult:
    p = Path(path)
    if not p.exists() or not p.is_file():
        raise FileNotFoundError(f"PDF를 찾을 수 없습니다: {p}")
    if not is_pdf(p):
        raise ValueError(f"PDF 확장자가 아닙니다: {p.suffix}")
    pages = _render_pdf_pages(p, max_pages=max_pages)
    if not pages:
        raise ValueError("PDF 페이지를 렌더링하지 못했습니다.")
    chunks = [_maybe_downscale(b, ".png") for b in pages]
    text = _call_vision(chunks, model=model)
    return VisionResult(text=text, source_type="pdf", page_count=len(pages), model=model)


def transcribe(path: str | Path) -> VisionResult:
    """확장자 보고 이미지·PDF 자동 라우팅."""
    p = Path(path)
    if is_image(p):
        return transcribe_image(p)
    if is_pdf(p):
        return transcribe_pdf(p)
    raise ValueError(f"지원하지 않는 파일 형식입니다: {p.suffix}")
