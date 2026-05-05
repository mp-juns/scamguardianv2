"""v4 Live Call Guard — 실시간 통화 중 사기 탐지 endpoint **draft**.

⚠️ DESIGN PREVIEW ONLY — NOT YET IMPLEMENTED
─────────────────────────────────────────────
이 모듈의 모든 endpoint 는 schema 검토 + 외부 통합 설계용 stub 이다.
모든 실제 호출은 HTTP 501 Not Implemented 를 반환한다.

설계 배경 (CLAUDE.md `v4 계획` 섹션):
- 사기 *후* 가 아닌 사기 *중* 차단 — 보이스피싱 통화 도중 위험 신호 감지 시 즉시 경보
- **사용자 본인 발화만 분석** — 통신비밀보호법 + iOS 마이크 권한 + STT 잡음 한 번에 해결
- 5초 chunk Whisper API + Haiku 한 줄 의도 분류 (`experiments/v4_intent/classify_haiku.py`)
- 임계 초과 시 WebSocket push (alarm + visual + 진동)

Schema 출처:
- `experiments/v4_intent.classify_haiku.Label` — META_AWARE/SENSITIVE_INFO/TRANSFER_AGREE/NORMAL
- `experiments/v4_whisper.chunker.ChunkResult` — index/start_sec/end_sec/text/latency_ms

이 reference implementation 은 endpoint 설계만 보여주며, 실제 구현 (WebSocket / 누적
슬라이딩 윈도우 / Cialdini 신호 카탈로그 / 경보 push) 은 별도 이터레이션에서 진행한다.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter()

_DRAFT_NOTE = (
    "\n\n⚠️ **v4 draft — design preview only, not yet implemented.** "
    "호출 시 `501 Not Implemented` 반환. schema 검토 + 외부 클라이언트 통합 설계용."
)


# ──────────────────────────────────
# Schema (draft)
# ──────────────────────────────────


class StreamStartRequest(BaseModel):
    """v4.0 — 통화 세션 생성 요청 (draft)."""
    user_id: str = Field(description="카카오 user.id 또는 외부 식별자")
    locale: str = Field(default="ko", description="STT 언어 코드 (기본 ko)")
    chunk_sec: int = Field(default=5, ge=1, le=30,
                           description="Whisper chunk 길이. v4.0 권장 5s")


class StreamStartResponse(BaseModel):
    session_id: str
    issued_at: float = Field(description="epoch sec")
    expires_at: float = Field(description="epoch sec — 세션 자동 종료 시각")
    upload_url: str = Field(description="chunk POST 대상 (보통 같은 호스트)")


class StreamChunkRequest(BaseModel):
    """v4.0 — 5초 PCM chunk 업로드 (draft).

    실제 구현은 multipart/form-data 또는 WebSocket binary frame 로 전환 가능.
    """
    session_id: str
    chunk_index: int = Field(ge=0)
    audio_base64: str = Field(description="16kHz mono PCM 또는 wav, base64")


SignalLabel = Literal["META_AWARE", "SENSITIVE_INFO", "TRANSFER_AGREE", "NORMAL"]


class StreamChunkResponse(BaseModel):
    """chunk 검출 즉답 — 의도 분류 + 누적 신호 개수 (draft).

    Identity: 점수·등급 X. 검출된 메타인식·민감정보·송금동의 신호 누적 개수만.
    """
    chunk_index: int
    transcript: str = Field(description="5초 chunk Whisper 결과")
    label: SignalLabel = Field(description="experiments/v4_intent Haiku 분류기")
    cumulative_signal_count: int = Field(
        ge=0,
        description="현재까지 누적된 위험 신호 총 개수 (v4.1 슬라이딩 윈도우)",
    )
    alert: bool = Field(description="임계 초과 여부 — true 면 클라이언트가 경보 트리거")
    alert_reason: str | None = Field(default=None,
                                     description="경보 사유 (alert=true 일 때만)")


class StreamEndResponse(BaseModel):
    """통화 종료 후 사후 검출 결과 (draft).

    Phase 4 (Serper 검증) 까지 수행한 DetectionReport 와 동등.
    Identity: 점수·등급 X — detected_signals[] 만 보고. 통합 기업이 자체 판정.
    """
    session_id: str
    full_transcript: str
    detected_signals: list[dict[str, Any]] = Field(
        description="시간순 검출 신호 list (각 신호의 학술/법적 근거 포함)"
    )
    alert_count: int = Field(description="통화 도중 발동된 경보 횟수")
    summary: str = Field(description="'위험 신호 N개 검출되었습니다.' 류 요약")
    disclaimer: str = Field(
        description="ScamGuardian 은 사기 판정을 내리지 않습니다 안내",
    )
    analysis_run_id: str | None = Field(
        default=None,
        description="DB 저장된 경우 — `/api/result/{token}` 으로 카드 조회 가능",
    )


class StreamSessionDetail(BaseModel):
    """세션 상태 조회 응답 (draft). 점수·등급 표면 X."""
    session_id: str
    status: Literal["active", "ended", "expired"]
    chunks_received: int
    cumulative_signal_count: int = Field(
        ge=0,
        description="현재까지 누적된 위험 신호 총 개수",
    )
    started_at: float
    last_chunk_at: float | None
    transcript_so_far: str


# ──────────────────────────────────
# Endpoints (stub — 모두 501)
# ──────────────────────────────────


@router.post(
    "/api/v4/stream/start",
    tags=["v4 (draft)"],
    summary="[draft] Live Call 세션 시작",
    description=(
        "통화 시작 시점에 호출 — session_id 발급 + chunk 업로드 endpoint 안내.\n\n"
        "구현 시 웹앱이 `getUserMedia` → AudioWorklet 으로 16kHz mono PCM 5초 buffer 생성 후 "
        "`/api/v4/stream/chunk` 로 순차 전송."
        + _DRAFT_NOTE
    ),
    response_model=StreamStartResponse,
    responses={501: {"description": "v4 미구현 — design preview"}},
)
async def stream_start(payload: StreamStartRequest) -> StreamStartResponse:
    raise HTTPException(
        status_code=501,
        detail="v4 Live Call Guard is design preview only — see CLAUDE.md `v4 계획`",
    )


@router.post(
    "/api/v4/stream/chunk",
    tags=["v4 (draft)"],
    summary="[draft] 5초 chunk 업로드 + 즉시 의도 분류",
    description=(
        "한 chunk 단위로 STT (`whisper-1` 또는 로컬) + Haiku 의도 분류 (`META_AWARE | "
        "SENSITIVE_INFO | TRANSFER_AGREE | NORMAL`) 수행.\n\n"
        "임계 초과 시 응답에 `alert=true` + `alert_reason` 포함 → 클라이언트가 경보음·진동 트리거. "
        "구현 시 WebSocket push 로 양방향 채널 권장."
        + _DRAFT_NOTE
    ),
    response_model=StreamChunkResponse,
    responses={501: {"description": "v4 미구현 — design preview"}},
)
async def stream_chunk(payload: StreamChunkRequest) -> StreamChunkResponse:
    raise HTTPException(
        status_code=501,
        detail="v4 Live Call Guard is design preview only — see CLAUDE.md `v4 계획`",
    )


@router.post(
    "/api/v4/stream/end",
    tags=["v4 (draft)"],
    summary="[draft] 통화 종료 + 사후 분석",
    description=(
        "사용자가 통화 종료 → 누적 transcript 로 Phase 4 (Serper 교차 검증) + Phase 5 "
        "(스코어링) 수행. 결과는 `analysis_run_id` 로 DB 저장되어 `/api/result/{token}` 카드 "
        "발급 가능."
        + _DRAFT_NOTE
    ),
    response_model=StreamEndResponse,
    responses={501: {"description": "v4 미구현 — design preview"}},
)
async def stream_end(session_id: str) -> StreamEndResponse:
    raise HTTPException(
        status_code=501,
        detail="v4 Live Call Guard is design preview only — see CLAUDE.md `v4 계획`",
    )


@router.get(
    "/api/v4/stream/{session_id}",
    tags=["v4 (draft)"],
    summary="[draft] 세션 상태 조회",
    description=(
        "현재 누적 transcript / 누적 위험도 / chunk 개수. 폴링 또는 모니터링 UI 용."
        + _DRAFT_NOTE
    ),
    response_model=StreamSessionDetail,
    responses={501: {"description": "v4 미구현 — design preview"}},
)
async def stream_get(session_id: str) -> StreamSessionDetail:
    raise HTTPException(
        status_code=501,
        detail="v4 Live Call Guard is design preview only — see CLAUDE.md `v4 계획`",
    )
