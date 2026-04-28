"""
ScamGuardian v2 FastAPI server.

기존 파이프라인을 웹에서 호출할 수 있도록 HTTP API로 노출한다.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from platform_layer import api_keys as api_key_module
from platform_layer.middleware import PlatformMiddleware
from pydantic import BaseModel, Field

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)

import threading

from db import repository
from pipeline import context_chat, eval as pipeline_eval
from pipeline import kakao_formatter, rag, stt as stt_module
from pipeline.config import DEFAULT_SCAM_TYPES, SCORING_RULES, get_runtime_scam_taxonomy
from pipeline.runner import ScamGuardianPipeline


class AnalyzeRequest(BaseModel):
    source: str | None = None
    text: str | None = None
    whisper_model: str = Field(
        default="medium",
        pattern="^(tiny|base|small|medium|large)$",
    )
    skip_verification: bool = True
    use_llm: bool = True
    use_rag: bool = False


class HumanAnnotationRequest(BaseModel):
    labeler: str | None = None
    scam_type_gt: str
    entities_gt: list[dict[str, Any]] = Field(default_factory=list)
    triggered_flags_gt: list[dict[str, Any]] = Field(default_factory=list)
    transcript_corrected_text: str | None = None
    stt_quality: int | None = Field(default=None, ge=1, le=5)
    notes: str = ""


class ScamTypeCatalogRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=200)
    labels: list[str] = Field(default_factory=list)


def _resolve_source(payload: AnalyzeRequest) -> str:
    return (payload.text or payload.source or "").strip()


def _options_payload() -> dict[str, Any]:
    taxonomy = get_runtime_scam_taxonomy()
    return {
        "scam_types": taxonomy["scam_types"],
        "label_sets": taxonomy["label_sets"],
        "flags": list(SCORING_RULES.keys()),
    }


def _normalize_catalog_payload(payload: ScamTypeCatalogRequest) -> dict[str, Any]:
    normalized_labels: list[str] = []
    seen: set[str] = set()
    for raw_label in payload.labels:
        label = raw_label.strip()
        if not label or label in seen:
            continue
        seen.add(label)
        normalized_labels.append(label)

    return {
        "name": payload.name.strip(),
        "description": (payload.description or "").strip(),
        "labels": normalized_labels,
    }


def _require_db() -> None:
    if not repository.database_configured():
        raise EnvironmentError(
            "DB 기능을 사용하려면 SCAMGUARDIAN_DATABASE_URL(Postgres) 또는 "
            "SCAMGUARDIAN_SQLITE_PATH(SQLite)가 설정되어야 합니다."
        )


def _persist_run(
    pipeline: ScamGuardianPipeline,
    payload: AnalyzeRequest,
    source: str,
    report_dict: dict[str, Any],
    *,
    user_context: dict[str, Any] | None = None,
) -> str | None:
    if not repository.persistence_enabled():
        return None

    transcript_text = (
        pipeline.last_transcript_result.text if pipeline.last_transcript_result is not None else source
    )
    metadata = {
        "source_type": (
            pipeline.last_transcript_result.source_type
            if pipeline.last_transcript_result is not None
            else "text"
        ),
        "steps": [
            {
                "name": step.name,
                "duration_ms": step.duration_ms,
                "detail": step.detail,
            }
            for step in pipeline.steps
        ],
        "rag_context": report_dict.get("rag_context"),
    }
    if user_context:
        metadata["user_context"] = user_context

    run_id = repository.save_analysis_run(
        input_source=source,
        whisper_model=payload.whisper_model,
        skip_verification=payload.skip_verification,
        use_llm=payload.use_llm,
        use_rag=payload.use_rag,
        transcript_text=transcript_text,
        classification_scanner={
            "scam_type": report_dict.get("scam_type", ""),
            "confidence": report_dict.get("classification_confidence", 0.0),
            "is_uncertain": report_dict.get("is_uncertain", False),
        },
        entities_predicted=report_dict.get("entities", []),
        verification_results=pipeline.last_report.all_verifications if pipeline.last_report else [],
        triggered_flags_predicted=report_dict.get("triggered_flags", []),
        total_score_predicted=report_dict.get("total_score", 0),
        risk_level_predicted=report_dict.get("risk_level", ""),
        llm_assessment=report_dict.get("llm_assessment"),
        metadata=metadata,
    )

    try:
        embedding = rag.compute_transcript_embedding(transcript_text)
        repository.save_transcript_embedding(run_id, embedding, rag.embedding_model_name())
    except Exception:
        # 분석 결과 저장은 유지하고, 임베딩 저장 실패만 조용히 건너뛴다.
        pass

    return run_id


def _run_pipeline(payload: AnalyzeRequest) -> dict:
    normalized_payload = AnalyzeRequest(
        source=payload.source,
        text=payload.text,
        whisper_model=payload.whisper_model,
        skip_verification=payload.skip_verification,
        use_llm=True,
        use_rag=payload.use_rag,
    )
    source = _resolve_source(normalized_payload)
    if not source:
        raise ValueError("분석할 텍스트 또는 URL을 입력해주세요.")

    pipeline = ScamGuardianPipeline(whisper_model=normalized_payload.whisper_model)
    report = pipeline.analyze(
        source,
        skip_verification=normalized_payload.skip_verification,
        use_llm=True,
        use_rag=normalized_payload.use_rag,
    )
    # 어뷰즈 가드 (사후): STT/Vision 결과가 너무 길면 LLM 비용 폭주 방지
    transcript_text = pipeline.last_transcript_result.text if pipeline.last_transcript_result else ""
    from platform_layer.abuse_guard import MAX_CHARS as _MAX_CHARS
    if transcript_text and len(transcript_text) > _MAX_CHARS:
        # transcript 절단 — Phase 3 LLM·Phase 4 verifier 가 이미 돌았지만 다음 호출 부담은 줄임
        # 진짜 운영 시 STT/Vision 후 즉시 cap → 분석 자체 거부 정책으로 강화 가능
        import logging as _logging
        _logging.getLogger("abuse_guard").warning(
            "transcript %d자 cap 초과(>%d)", len(transcript_text), _MAX_CHARS,
        )
    report_dict = report.to_dict()
    # 프론트에서 "전체 전사"를 화면에 그대로 보여줄 수 있게 원문 텍스트도 함께 내려준다.
    report_dict["transcript_text"] = (
        pipeline.last_transcript_result.text if pipeline.last_transcript_result is not None else ""
    )
    run_id = _persist_run(pipeline, normalized_payload, source, report_dict)
    if run_id:
        report_dict["analysis_run_id"] = run_id
    return report_dict


app = FastAPI(
    title="ScamGuardian API",
    version="0.1.0",
    description="ScamGuardian v2 파이프라인을 웹에서 호출하기 위한 API",
)

allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "SCAMGUARDIAN_CORS_ORIGINS",
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# v3 platform — API key + rate limit + request log + cost context
app.add_middleware(PlatformMiddleware)


@app.on_event("startup")
def startup() -> None:
    import logging
    log = logging.getLogger("startup")

    if repository.database_configured():
        repository.init_db()

    log.info("모델 워밍업 시작 (콜드스타트 방지)...")
    try:
        pipeline = ScamGuardianPipeline()
        pipeline.analyze("워밍업 테스트", skip_verification=True, use_llm=True, use_rag=False)
        log.info("모델 워밍업 완료")
    except Exception as exc:
        log.warning("모델 워밍업 실패 (무시): %s", exc)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/methodology")
def get_methodology() -> dict[str, Any]:
    """위험도 점수 산정 방식 메타 정보. /methodology 페이지가 호출."""
    from pipeline import config as pcfg

    flags: list[dict[str, Any]] = []
    for key, score_delta in pcfg.SCORING_RULES.items():
        info = pcfg.FLAG_RATIONALE.get(key, {})
        flags.append({
            "flag": key,
            "label_ko": pcfg.FLAG_LABELS_KO.get(key, key),
            "score_delta": score_delta,
            "rationale": info.get("rationale", ""),
            "source": info.get("source", ""),
        })
    flags.sort(key=lambda x: (-x["score_delta"], x["flag"]))

    risk_bands: list[dict[str, Any]] = []
    prev_threshold = -1
    for threshold, level, description in pcfg.RISK_LEVELS:
        risk_bands.append({
            "min": prev_threshold + 1,
            "max": threshold if threshold < 999 else 100,
            "level": level,
            "description": description,
        })
        prev_threshold = threshold

    return {
        "flags": flags,
        "risk_bands": risk_bands,
        "weights": {
            "llm_flag_score_ratio": pcfg.LLM_FLAG_SCORE_RATIO,
            "llm_entity_merge_threshold": pcfg.LLM_ENTITY_MERGE_THRESHOLD,
            "llm_flag_score_threshold": pcfg.LLM_FLAG_SCORE_THRESHOLD,
            "llm_scam_type_override_threshold": pcfg.LLM_SCAM_TYPE_OVERRIDE_THRESHOLD,
            "classification_threshold": pcfg.CLASSIFICATION_THRESHOLD,
            "gliner_threshold": pcfg.GLINER_THRESHOLD,
            "keyword_boost_weight": pcfg.KEYWORD_BOOST_WEIGHT,
        },
        "models": pcfg.MODELS,
    }


@app.get("/api/result/{token}")
async def get_result_by_token(token: str) -> dict[str, Any]:
    """카카오 카드의 '자세히 보기' 링크 백엔드 — 토큰으로 분석 결과 반환.

    1시간 TTL. 토큰 없거나 만료 시 404/410.
    """
    import time as _time
    _cleanup_expired_result_tokens()
    entry = _result_tokens.get(token)
    if entry is None:
        raise HTTPException(status_code=404, detail="결과를 찾을 수 없습니다.")
    if entry.get("expires_at", 0) < _time.time():
        _result_tokens.pop(token, None)
        raise HTTPException(status_code=410, detail="결과 링크가 만료됐어요 (1시간 후 만료).")
    # 플래그별 정당성·출처 — 결과 페이지에서 "왜 이 점수인가요?" 표시
    from pipeline.config import flag_rationale
    flag_info: dict[str, dict[str, str]] = {}
    for f in (entry["result"].get("triggered_flags") or []):
        key = (f.get("flag") or "").strip()
        if key and key not in flag_info:
            info = flag_rationale(key)
            if info:
                flag_info[key] = info
    return {
        "result": entry["result"],
        "user_context": entry.get("user_context"),
        "input_type": entry.get("input_type"),
        "chat_history": entry.get("chat_history") or [],
        "flag_rationale": flag_info,
        "expires_at": entry["expires_at"],
    }


_URL_RE = re.compile(r"https?://\S+")
_YOUTUBE_RE = re.compile(r"https?://(www\.)?(youtube\.com|youtu\.be)/")


_IMAGE_URL_RE = re.compile(r"\.(jpg|jpeg|png|webp|gif|bmp)(\?|$)", re.IGNORECASE)
_PDF_URL_RE = re.compile(r"\.pdf(\?|$)", re.IGNORECASE)


def _wrap_with_soft_warning(response: dict, info: dict | None) -> dict:
    """짧은 메시지 누적 위반 시 응답 최상단에 경고 simpleText 부착.

    첫 번째(count=1) 는 무시 — 정상 인사로 통과시킴.
    두 번째(count>=2) 부터 경고 prepend.
    """
    if not info or info.get("count", 0) < 2 or info.get("blocked"):
        return response
    from platform_layer import abuse_guard as _ag
    count = info["count"]
    limit = _ag.VIOLATION_WARN_LIMIT
    warn = {
        "simpleText": {
            "text": (
                f"⚠️ 짧은 메시지가 반복되고 있어요 ({count}/{limit}).\n"
                "분석할 의심 메시지·URL·문서를 보내주세요. 누적 시 일시 차단됩니다."
            )
        }
    }
    response.setdefault("template", {}).setdefault("outputs", []).insert(0, warn)
    return response


def _classify_url_input(url: str) -> kakao_formatter.InputType:
    """URL 확장자 보고 IMAGE/PDF/URL 구분."""
    InputType = kakao_formatter.InputType
    if _IMAGE_URL_RE.search(url):
        return InputType.IMAGE
    if _PDF_URL_RE.search(url):
        return InputType.PDF
    return InputType.URL


def _kakao_detect_input(
    utterance: str, action_params: dict
) -> tuple[str, kakao_formatter.InputType]:
    """
    카카오 페이로드에서 분석 대상 소스와 입력 유형을 감지한다.
    Returns: (source, InputType)
    """
    InputType = kakao_formatter.InputType

    # 1) action.params 의 파일/영상/이미지/PDF URL (카카오 파일 전송)
    #    카카오 오픈빌더 블록의 파라미터 이름 — 모두 동등하게 처리하되 키워드로 우선 분류.
    for key in (
        "image", "picture", "photo",  # 이미지
        "pdf", "document",            # PDF/문서
        "video", "video_url",         # 영상
        "file", "attachment",         # 일반 파일 (확장자 보고 재분류)
    ):
        val = action_params.get(key)
        url = ""
        if isinstance(val, str) and val.startswith("http"):
            url = val
        elif isinstance(val, dict):
            v = val.get("url", "")
            if isinstance(v, str) and v.startswith("http"):
                url = v
        if not url:
            continue
        if key in ("image", "picture", "photo"):
            return url, InputType.IMAGE
        if key in ("pdf", "document"):
            return url, InputType.PDF
        if key in ("video", "video_url"):
            return url, InputType.VIDEO
        # file/attachment — URL 확장자 보고 분기
        kind = _classify_url_input(url)
        if kind in (InputType.IMAGE, InputType.PDF):
            return url, kind
        return url, InputType.FILE

    # 2) utterance 전체 또는 일부가 URL — 둘 다 첫 매칭 URL 만 사용
    url_match = _URL_RE.search(utterance)
    if url_match:
        url = url_match.group(0)
        return url, _classify_url_input(url)

    # 4) 순수 텍스트
    return utterance, InputType.TEXT


def _kakao_materialize_url(url: str, suffix_hint: str = "") -> str:
    """카카오 CDN 등의 HTTP URL 을 로컬 파일로 다운로드하고 경로 반환.

    이미지/PDF 처럼 우리 vision 파이프라인이 로컬 파일 경로를 기대하는 경우 사용.
    저장 위치: .scamguardian/uploads/kakao/{uuid}{suffix}
    """
    import uuid as _uuid
    log = logging.getLogger("kakao_dl")

    suffix = suffix_hint
    if not suffix:
        # URL 끝에서 확장자 추출 시도
        path = url.split("?", 1)[0]
        idx = path.rfind(".")
        if idx > 0 and len(path) - idx <= 6:
            suffix = path[idx:]
    if not suffix:
        suffix = ".bin"

    target_dir = Path(".scamguardian") / "uploads" / "kakao"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / f"{_uuid.uuid4().hex}{suffix}"

    resp = requests.get(url, stream=True, timeout=30)
    resp.raise_for_status()
    with target.open("wb") as fp:
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            if chunk:
                fp.write(chunk)
    log.info("카카오 미디어 다운로드 완료: %s → %s (%d bytes)",
             url[:80], target.name, target.stat().st_size)
    return str(target)


def _kakao_run_pipeline(source: str, use_llm: bool = False) -> dict:
    """파이프라인을 실행하고 report_dict를 반환한다."""
    use_llm = True
    pipeline = ScamGuardianPipeline()
    report = pipeline.analyze(
        source,
        skip_verification=False,
        use_llm=use_llm,
        use_rag=False,
    )
    report_dict = report.to_dict()
    report_dict["transcript_text"] = (
        pipeline.last_transcript_result.text
        if pipeline.last_transcript_result is not None
        else source
    )
    _persist_run(
        pipeline,
        AnalyzeRequest(
            source=source,
            skip_verification=False,
            use_llm=True,
            use_rag=False,
        ),
        source,
        report_dict,
    )
    return report_dict


def _classify_error(exc: Exception) -> kakao_formatter.ErrorCode:
    """예외 종류에 따라 적절한 ErrorCode를 반환한다."""
    EC = kakao_formatter.ErrorCode
    msg = str(exc).lower()
    if "api" in msg and ("credit" in msg or "quota" in msg or "limit" in msg):
        return EC.API_CREDIT
    if "connection" in msg or "connect" in msg or "unreachable" in msg:
        return EC.SERVER_DOWN
    if "stt" in msg or "whisper" in msg or "audio" in msg or "transcri" in msg:
        return EC.STT_FAIL
    if "timeout" in msg or "timed out" in msg:
        return EC.TIMEOUT
    if "memory" in msg or "ollama" in msg:
        return EC.LLM_UNAVAILABLE
    if "empty" in msg or "비어" in msg:
        return EC.EMPTY_INPUT
    return EC.UNKNOWN


_KAKAO_CALLBACK_TIMEOUT = 55  # 카카오 콜백 제한 60초, 여유 5초
_KAKAO_POLL_TIMEOUT = 600  # 폴링 모드 최대 대기 10분
_KAKAO_JOB_TTL = 600  # 완료된 결과 보관 10분 (초)

# 결과 상세 페이지 공개 토큰 — 카카오 카드의 "자세히 보기" 링크에 박힌 키
_RESULT_TOKEN_TTL = 3600  # 1시간
# token → {result, user_context, input_type, expires_at, user_id, chat_history}
_result_tokens: dict[str, dict[str, Any]] = {}
# 공개 URL — 1) env, 2) ngrok local API, 3) Tailscale Funnel 환경 추정 순서로 탐색
_public_url_cache: dict[str, Any] = {"url": "", "expires": 0.0}


def _get_public_base_url() -> str:
    """결과 링크 베이스 URL 을 동적으로 조회. env 우선, 없으면 ngrok API 자동 탐색.

    60초 캐시. ngrok 재시작 시에도 환경변수 따로 안 바꿔도 됨.
    """
    import time as _time
    now = _time.time()
    if now < _public_url_cache.get("expires", 0):
        return _public_url_cache.get("url", "")

    env = os.getenv("SCAMGUARDIAN_PUBLIC_URL", "").strip().rstrip("/")
    url = env
    if not url:
        try:
            import json as _json
            import urllib.request as _ureq
            with _ureq.urlopen("http://127.0.0.1:4040/api/tunnels", timeout=1) as resp:
                data = _json.loads(resp.read().decode())
                for t in data.get("tunnels", []):
                    pu = (t.get("public_url") or "").strip()
                    if pu.startswith("https"):
                        url = pu.rstrip("/")
                        break
        except Exception:
            pass

    _public_url_cache["url"] = url
    _public_url_cache["expires"] = now + 60
    return url

# 사용자 발화 중 "그냥 분석 결과만 보내줘" 류로 컨텍스트 수집을 강제 종료할 신호
_KAKAO_SKIP_PHRASES = {
    "그냥 분석결과 보내줘",
    "그냥 분석",
    "그만 묻고 분석",
    "건너뛰기",
    "스킵",
    "skip",
}

# 결과확인 동의어 — 정확 매칭 + 부분 매칭으로 폭넓게 인식
_RESULT_REQUEST_EXACT = {
    "결과확인", "결과 확인", "결과", "확인",
}
_RESULT_REQUEST_SUBSTRINGS = (
    "결과확인", "결과 확인",
    "결과 알려", "결과알려", "결과 좀", "결과좀",
    "결과 보여", "결과보여", "결과 받", "결과받",
    "결과 봐", "결과봐", "결과 줘", "결과줘",
    "분석 다됐", "분석다됐", "분석 됐어", "분석됐어",
    "분석 끝", "분석끝", "분석 결과", "분석결과",
    "다 됐어", "다됐어", "다 끝났",
)


def _is_result_request(text: str) -> bool:
    """사용자 발화가 결과 요청인지 판별. '결과확인' 외에 자연 표현도 폭넓게 인식."""
    s = (text or "").strip()
    if not s:
        return False
    if s in _RESULT_REQUEST_EXACT:
        return True
    return any(p in s for p in _RESULT_REQUEST_SUBSTRINGS)

# user_id → 상태 dict (구조는 _new_job_state 참조)
_pending_jobs: dict[str, dict] = {}
# 멀티 스레드/태스크에서 _pending_jobs 동시 수정 방지
_jobs_lock = threading.Lock()
# asyncio bg task 가 GC 되지 않도록 보관
_BG_TASKS: set[asyncio.Task] = set()


def _spawn_bg(coro) -> asyncio.Task:
    """asyncio bg task 를 등록하고 GC 방지를 위해 참조를 보관한다."""
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return task


def _new_job_state(
    *,
    source: str,
    input_type: kakao_formatter.InputType,
) -> dict[str, Any]:
    import time as _time
    return {
        "status": "running",          # 결과확인 polling 호환: running/done/error
        "phase": "collecting_context", # collecting_context/analyzing/done/error
        "result": None,
        "input_type": input_type,
        "source": source,
        "chat_history": [],            # list[ContextTurn]
        "stt_done": False,
        "stt_result": None,
        "context_done": False,
        "user_context": None,
        "analyzing_started": False,
        # 병렬 1차 분석 + 최종 합본 (refine) 관련
        "result_ready_announced": False,  # 1차 결과 도착을 사용자에게 알렸는지
        "done_notice_sent": False,         # 채팅 중 "분석 끝났어요" 안내를 한 번 띄웠는지
        "refine_started": False,           # 최종 합본 분석 시작했는지
        "refined": False,                  # 최종 합본 완료
        "started_at": _time.time(),
        "finished_at": None,
        "error": None,
    }


def _cleanup_expired_result_tokens() -> None:
    import time
    now = time.time()
    expired = [t for t, e in _result_tokens.items() if e.get("expires_at", 0) < now]
    for t in expired:
        del _result_tokens[t]


def _issue_result_token(
    *,
    result: dict[str, Any],
    user_context: dict[str, Any] | None,
    input_type: kakao_formatter.InputType,
    user_id: str | None,
    chat_history: list[Any] | None = None,
) -> tuple[str, str | None]:
    """결과 상세 토큰 발급 + 공개 URL 반환. URL 은 SCAMGUARDIAN_PUBLIC_URL 미설정 시 None."""
    import secrets
    import time
    _cleanup_expired_result_tokens()
    token = secrets.token_urlsafe(16)
    _result_tokens[token] = {
        "result": result,
        "user_context": user_context,
        "input_type": input_type.value if hasattr(input_type, "value") else str(input_type),
        "expires_at": time.time() + _RESULT_TOKEN_TTL,
        "user_id": user_id,
        "chat_history": [
            {"role": getattr(t, "role", ""), "message": getattr(t, "message", "")}
            for t in (chat_history or [])
        ],
    }
    base = _get_public_base_url()
    url = f"{base}/result/{token}" if base else None

    # 어드민 라벨링 세션이 풀 컨텍스트(대화/사용자정보)를 보도록 DB 에 머지
    run_id = (result or {}).get("analysis_run_id")
    if run_id and repository.persistence_enabled():
        try:
            chat_dump = [
                {"role": getattr(t, "role", ""), "message": getattr(t, "message", "")}
                for t in (chat_history or [])
            ]
            partial = {}
            if user_context:
                partial["user_context"] = user_context
            if chat_dump:
                partial["chat_history"] = chat_dump
            if partial:
                repository.merge_run_metadata(run_id, partial)
        except Exception as exc:
            logging.getLogger("token").warning(
                "metadata merge 실패 (run_id=%s): %s", run_id, exc,
            )

    return token, url


def _cleanup_expired_jobs() -> None:
    import time
    now = time.time()
    with _jobs_lock:
        expired = [
            uid for uid, job in _pending_jobs.items()
            if job["status"] != "running" and (now - (job.get("finished_at") or now)) > _KAKAO_JOB_TTL
        ]
        for uid in expired:
            del _pending_jobs[uid]


async def _kakao_callback_task(
    source: str,
    callback_url: str,
    input_type: kakao_formatter.InputType,
    use_llm: bool = True,
) -> None:
    """분석을 백그라운드로 수행한 뒤 카카오 callbackUrl로 결과를 POST한다."""
    import logging
    import requests as _requests

    log = logging.getLogger("kakao_callback")

    try:
        log.info(
            "callback 분석 시작 (제한 %ds):\n"
            "  type: %s\n"
            "  source: %s\n"
            "  use_llm: %s",
            _KAKAO_CALLBACK_TIMEOUT, input_type.value, source[:100], use_llm,
        )
        report_dict = await asyncio.wait_for(
            asyncio.to_thread(_kakao_run_pipeline, source, use_llm),
            timeout=_KAKAO_CALLBACK_TIMEOUT,
        )
        # callback 모드도 자세히 보기 토큰 발급
        _, _result_url = _issue_result_token(
            result=report_dict,
            user_context=None,
            input_type=input_type,
            user_id=None,
        )
        result = kakao_formatter.format_result(report_dict, input_type, result_url=_result_url)
        log.info(
            "callback 분석 완료:\n"
            "  scam_type: %s\n"
            "  risk: %s/100 (%s)\n"
            "  transcript_len: %s자",
            report_dict.get("scam_type", "?"),
            report_dict.get("total_score", "?"),
            report_dict.get("risk_level", "?"),
            len(report_dict.get("transcript_text", "")),
        )
    except asyncio.TimeoutError:
        log.warning("callback 분석 타임아웃 (%ds 초과)", _KAKAO_CALLBACK_TIMEOUT)
        result = kakao_formatter.format_error(
            kakao_formatter.ErrorCode.TIMEOUT,
            detail=f"분석이 {_KAKAO_CALLBACK_TIMEOUT}초를 초과했습니다. 더 짧은 영상이나 텍스트로 시도해주세요.",
        )
    except Exception as exc:
        log.error("callback 분석 실패: %s", exc, exc_info=True)
        error_code = _classify_error(exc)
        result = kakao_formatter.format_error(error_code, detail=str(exc))

    import json as _json

    def _post():
        try:
            log.info(
                "callback POST 전송:\n"
                "  url: %s\n"
                "  body: %s",
                callback_url[:80],
                _json.dumps(result, ensure_ascii=False)[:500],
            )
            resp = _requests.post(callback_url, json=result, timeout=10)
            log.info("callback POST 완료: status=%s body=%s", resp.status_code, resp.text[:200])
        except Exception as e:
            log.error("callback POST 실패: %s", e)

    await asyncio.to_thread(_post)


# ──────────────────────────────────
# 컨텍스트 대화 + 병렬 STT 흐름 (폴링 모드 + 멀티턴)
# ──────────────────────────────────


def _kakao_transcribe_only(source: str) -> stt_module.TranscriptResult:
    """STT 만 단독 수행. 별도 스레드에서 실행."""
    return stt_module.transcribe(source)


def _kakao_analyze_with_context(
    source: str,
    transcript_result: stt_module.TranscriptResult,
    user_context: dict[str, Any] | None,
    input_type: kakao_formatter.InputType,
) -> dict[str, Any]:
    """precomputed_transcript + user_context 로 Phase 2-5 분석 수행."""
    pipeline = ScamGuardianPipeline()
    report = pipeline.analyze(
        source,
        skip_verification=False,
        use_llm=True,
        use_rag=False,
        precomputed_transcript=transcript_result,
        user_context=user_context,
    )
    report_dict = report.to_dict()
    report_dict["transcript_text"] = (
        pipeline.last_transcript_result.text
        if pipeline.last_transcript_result is not None
        else source
    )
    if user_context:
        report_dict["user_context"] = user_context
    _persist_run(
        pipeline,
        AnalyzeRequest(
            source=source,
            skip_verification=False,
            use_llm=True,
            use_rag=False,
        ),
        source,
        report_dict,
        user_context=user_context,
    )
    return report_dict


async def _async_maybe_trigger_analyze(user_id: str) -> None:
    """STT 가 끝났으면 1차 분석을 곧바로 백그라운드에서 시작한다.

    채팅(컨텍스트 수집)은 병렬로 계속 진행되고,
    사용자 답변은 분석 완료 후 refine 단계에서 LLM 에 prior 로 합쳐진다.
    """
    with _jobs_lock:
        job = _pending_jobs.get(user_id)
        if job is None:
            return
        if job.get("status") == "error":
            return
        if not job.get("stt_done"):
            return
        if job.get("analyzing_started"):
            return
        job["analyzing_started"] = True
        # phase 는 collecting_context 로 유지 — 채팅은 계속됨
        source = job["source"]
        input_type = job["input_type"]
        transcript = job["stt_result"]

    # 1차 분석은 user_context 없이 수행
    await _kakao_analyze_only_task(user_id, source, input_type, transcript, None)


async def _kakao_refine_text_task(
    user_id: str,
    transcript_text: str,
    scam_type: str,
    user_context: dict[str, Any],
) -> None:
    """최종 합본 분석: 1차 분석 결과 + 사용자 채팅 답변을 LLM 에 prior 로 주입해 reasoning 보강.

    Serper 검증 / 분류 / 엔티티 추출은 본문만 보니 결과 동일 → 재호출하지 않는다.
    Claude API 1회 추가 비용 (~5–10s) 으로 사용자 답변을 분석에 반영.
    """
    from pipeline import llm_assessor

    log = logging.getLogger("kakao_refine")
    log.info("최종 합본 분석 시작: user=%s scam_type=%s", user_id[:12], scam_type)
    try:
        new_unified = await asyncio.to_thread(
            llm_assessor.analyze_unified,
            transcript_text, scam_type, user_context,
        )
        with _jobs_lock:
            job = _pending_jobs.get(user_id)
            if job is None:
                return
            if job.get("result"):
                # 보강된 LLM assessment 로 교체 (summary/reasoning 갱신)
                job["result"]["llm_assessment"] = new_unified.assessment.to_dict()
                # LLM 이 다른 스캠 유형 제안하면 적용
                if new_unified.scam_type_suggestion is not None:
                    new_type = new_unified.scam_type_suggestion.scam_type
                    if new_type and new_type != job["result"].get("scam_type"):
                        job["result"]["scam_type"] = new_type
                        job["result"]["scam_type_reason"] = new_unified.scam_type_suggestion.reason
            job["refined"] = True
            # DB 에 refine 후 LLM assessment 도 메타데이터로 같이 보존
            run_id_for_db = (job.get("result") or {}).get("analysis_run_id")
        log.info("최종 합본 분석 완료: user=%s", user_id[:12])
        if run_id_for_db and repository.persistence_enabled():
            try:
                repository.merge_run_metadata(run_id_for_db, {
                    "refined_llm_assessment": new_unified.assessment.to_dict(),
                })
            except Exception as exc:
                log.warning("refine metadata merge 실패: %s", exc)
    except Exception as exc:
        import traceback
        log.error(
            "최종 합본 실패: user=%s err=%s\n%s",
            user_id[:12], exc, traceback.format_exc(),
        )
        with _jobs_lock:
            job = _pending_jobs.get(user_id)
            if job is not None:
                job["refined"] = True  # 실패해도 무한 재시도 방지


async def _kakao_stt_only_task(user_id: str, source: str) -> None:
    """STT 만 백그라운드에서 수행. 끝나면 trigger 체크."""
    import time

    log = logging.getLogger("kakao_stt")
    log.info("STT 시작: user=%s source=%s", user_id[:12], source[:80])
    try:
        transcript = await asyncio.wait_for(
            asyncio.to_thread(_kakao_transcribe_only, source),
            timeout=_KAKAO_POLL_TIMEOUT,
        )
        with _jobs_lock:
            job = _pending_jobs.get(user_id)
            if job is None:
                return
            job["stt_done"] = True
            job["stt_result"] = transcript
        log.info("STT 완료: user=%s len=%s", user_id[:12], len(transcript.text))
    except Exception as exc:
        import traceback
        log.error(
            "STT 실패: user=%s err=%s\n%s",
            user_id[:12], exc, traceback.format_exc(),
        )
        with _jobs_lock:
            job = _pending_jobs.get(user_id)
            if job is None:
                return
            job["status"] = "error"
            job["phase"] = "error"
            job["error"] = exc
            job["finished_at"] = time.time()
        return

    await _async_maybe_trigger_analyze(user_id)


async def _kakao_analyze_only_task(
    user_id: str,
    source: str,
    input_type: kakao_formatter.InputType,
    transcript: stt_module.TranscriptResult,
    user_context: dict[str, Any] | None,
) -> None:
    """Phase 2-5 만 백그라운드에서 수행. STT 결과 / user_context 사용."""
    import time

    log = logging.getLogger("kakao_analyze")
    log.info(
        "분석 시작: user=%s type=%s ctx_turns=%s",
        user_id[:12], input_type.value,
        (user_context or {}).get("turn_count", 0),
    )
    try:
        report_dict = await asyncio.wait_for(
            asyncio.to_thread(
                _kakao_analyze_with_context,
                source, transcript, user_context, input_type,
            ),
            timeout=_KAKAO_POLL_TIMEOUT,
        )
        with _jobs_lock:
            job = _pending_jobs.get(user_id)
            if job is None:
                return
            job["status"] = "done"
            # phase 는 collecting_context 유지 — 사용자 채팅을 끊지 않음.
            # phase 를 done 으로 바꾸지 않으면 사용자가 '결과확인' 누를 때까지
            # _kakao_handle_context_answer 가 계속 다음 질문을 생성한다.
            job["result"] = report_dict
            job["finished_at"] = time.time()
        log.info(
            "분석 완료(채팅 계속): user=%s risk=%s/100 (%s)",
            user_id[:12],
            report_dict.get("total_score", "?"),
            report_dict.get("risk_level", "?"),
        )
    except Exception as exc:
        import traceback
        log.error(
            "분석 실패: user=%s err=%s\n%s",
            user_id[:12], exc, traceback.format_exc(),
        )
        with _jobs_lock:
            job = _pending_jobs.get(user_id)
            if job is None:
                return
            job["status"] = "error"
            job["phase"] = "error"
            job["error"] = exc
            job["finished_at"] = time.time()


async def _kakao_start_context_collection(
    user_id: str,
    source: str,
    input_type: kakao_formatter.InputType,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    """첫 입력 (TEXT/URL/VIDEO/FILE) 수신 → STT 시작 + 컨텍스트 첫 질문 응답.

    TEXT 는 STT 가 패스스루이므로 즉시 stt_done 처리.
    URL/VIDEO/FILE 은 STT 를 백그라운드로 돌린다.
    """
    log = logging.getLogger("kakao_ctx")

    with _jobs_lock:
        _pending_jobs[user_id] = _new_job_state(source=source, input_type=input_type)

    if input_type == kakao_formatter.InputType.TEXT:
        # TEXT 는 STT 가 패스스루 — 즉시 처리하고 1차 분석 백그라운드 시작.
        # 사용자 답변은 채팅 누적 → 1차 완료 후 사용자 다음 메시지에 announce + refine.
        try:
            transcript = stt_module.transcribe(source)
            with _jobs_lock:
                job = _pending_jobs.get(user_id)
                if job is not None:
                    job["stt_done"] = True
                    job["stt_result"] = transcript
            # stt_done 세팅됐으니 trigger 가 1차 분석을 백그라운드로 시작
            _spawn_bg(_async_maybe_trigger_analyze(user_id))
        except Exception as exc:
            log.error("TEXT passthrough 실패: %s", exc)
            with _jobs_lock:
                job = _pending_jobs.get(user_id)
                if job is not None:
                    job["status"] = "error"
                    job["phase"] = "error"
                    job["error"] = exc
    else:
        # URL/VIDEO/FILE — STT 백그라운드 시작. STT 완료 후 자동으로 1차 분석 트리거.
        background_tasks.add_task(_kakao_stt_only_task, user_id, source)

    # 첫 질문은 webhook 응답 전에 동기적으로 받아야 함.
    # TEXT 의 경우 본문이 즉시 사용 가능 → Claude 가 본문 단서를 짚어가며 첫 질문
    with _jobs_lock:
        job = _pending_jobs.get(user_id)
        first_transcript_text: str | None = None
        if job is not None and job.get("stt_result") is not None:
            first_transcript_text = job["stt_result"].text
    try:
        first_turn = await asyncio.to_thread(
            context_chat.next_turn, input_type.value, [], first_transcript_text,
        )
    except Exception as exc:
        log.error("첫 질문 생성 실패: %s", exc, exc_info=True)
        # 폴백: 컨텍스트 즉시 종료, STT 결과 기다림
        with _jobs_lock:
            job = _pending_jobs.get(user_id)
            if job is not None:
                job["context_done"] = True
                job["user_context"] = None
        _spawn_bg(_async_maybe_trigger_analyze(user_id))
        return kakao_formatter.format_context_done_waiting(stt_done=False)

    with _jobs_lock:
        job = _pending_jobs.get(user_id)
        if job is None:
            return kakao_formatter.format_error(
                kakao_formatter.ErrorCode.UNKNOWN, "세션이 사라졌습니다.",
            )
        job["chat_history"].append(
            context_chat.ContextTurn(role="bot", message=first_turn.message)
        )
        if first_turn.is_done:
            # 첫 턴부터 DONE 은 드물지만 — 컨텍스트 종료 처리
            job["context_done"] = True
            job["user_context"] = context_chat.summarize_for_pipeline(job["chat_history"])
            stt_done = job["stt_done"]
        else:
            stt_done = None  # 아직 ASK 상태

    if first_turn.is_done:
        _spawn_bg(_async_maybe_trigger_analyze(user_id))
        return kakao_formatter.format_context_done_waiting(stt_done=bool(stt_done))

    return kakao_formatter.format_question(
        first_turn.message, is_first_turn=True, input_type=input_type,
    )


async def _kakao_handle_context_answer(
    user_id: str,
    utterance: str,
) -> dict[str, Any]:
    """수집 중 사용자 답변 도착 → Claude 다음 액션 결정 → 응답."""
    log = logging.getLogger("kakao_ctx")

    with _jobs_lock:
        job = _pending_jobs.get(user_id)
        if job is None:
            return kakao_formatter.format_no_job()
        input_type = job["input_type"]
        # 사용자 답변 추가 (저장 시점에 길이 제한)
        user_turn = context_chat.ContextTurn(
            role="user",
            message=utterance[: context_chat.USER_ANSWER_MAX_CHARS],
        )
        job["chat_history"].append(user_turn)
        history = list(job["chat_history"])
        # STT 가 끝났으면 본문 텍스트도 함께 넘겨 Claude 가 본문 단서로 다음 질문 생성
        transcript_text = (
            job["stt_result"].text if job.get("stt_result") is not None else None
        )

    try:
        next_action = await asyncio.to_thread(
            context_chat.next_turn, input_type.value, history, transcript_text,
        )
    except Exception as exc:
        log.error("Claude next_turn 실패 → DONE 폴백: %s", exc, exc_info=True)
        next_action = context_chat.NextAction(
            action="DONE",
            message="알려주신 내용 잘 받았어요. 분석 결과 곧 알려드릴게요.",
            reasoning=f"claude_error: {exc}",
        )

    # 1차 분석이 채팅 도중에 끝났으면 사용자에게 한 번 알려줌 (1회만)
    notify_done = False
    with _jobs_lock:
        job = _pending_jobs.get(user_id)
        if job is None:
            return kakao_formatter.format_no_job()
        if (
            job.get("status") == "done"
            and not job.get("done_notice_sent")
            and not next_action.is_done
        ):
            notify_done = True
            job["done_notice_sent"] = True
            next_action = context_chat.NextAction(
                action="ASK",
                message=(
                    next_action.message
                    + "\n\n💡 참고로 분석은 끝났어요. "
                    + "더 알려주실 게 있으면 답해주시고, "
                    + "결과를 보시려면 '결과확인'을 누르거나 '결과 알려줘'라고 해주세요."
                ),
                reasoning=next_action.reasoning,
            )
        job["chat_history"].append(
            context_chat.ContextTurn(role="bot", message=next_action.message)
        )
        if next_action.is_done:
            job["context_done"] = True
            job["user_context"] = context_chat.summarize_for_pipeline(job["chat_history"])
            stt_done = job["stt_done"]
        else:
            stt_done = None

    if next_action.is_done:
        _spawn_bg(_async_maybe_trigger_analyze(user_id))
        return kakao_formatter.format_context_done_waiting(stt_done=bool(stt_done))

    if notify_done:
        log.info("→ 분석 완료 안내 동봉: user=%s", user_id[:12])

    return kakao_formatter.format_question(
        next_action.message, is_first_turn=False, input_type=input_type,
    )


def _user_ctx_for_display(job: dict[str, Any]) -> dict[str, Any] | None:
    """결과 카드에 보여줄 user_context — 우선 저장된 값, 없으면 chat_history 에서 즉석 요약."""
    ctx = job.get("user_context")
    if ctx is not None:
        return ctx
    history = job.get("chat_history") or []
    if not history:
        return None
    return context_chat.summarize_for_pipeline(history)


async def _handle_done_state(
    user_id: str,
    background_tasks: BackgroundTasks,
    utterance: str | None = None,
) -> dict[str, Any]:
    """status=done 상태에서 사용자 메시지/결과확인 도착 시 처리.

    - 첫 알림: announce + 답변 있으면 refine 트리거
    - 이미 알림: refine 진행 중이면 still_running, refined 면 결과 반환

    utterance 가 주어지면 알림 직전 chat_history 에 캡처해 refine 에 반영.
    """
    log = logging.getLogger("kakao_done")

    with _jobs_lock:
        job = _pending_jobs.get(user_id)
        if job is None:
            return kakao_formatter.format_no_job()

        # 첫 알림 직전이라면 사용자의 마지막 발화도 chat_history 에 담아 refine 에 반영
        if (
            utterance
            and not job.get("result_ready_announced", False)
        ):
            job["chat_history"].append(
                context_chat.ContextTurn(
                    role="user",
                    message=utterance[: context_chat.USER_ANSWER_MAX_CHARS],
                )
            )

        announced = job.get("result_ready_announced", False)
        refine_started = job.get("refine_started", False)
        refined = job.get("refined", False)
        has_answers = any(
            getattr(t, "role", None) == "user"
            for t in job.get("chat_history", [])
        )

        if not announced:
            # 첫 알림 — 이 순간부터 채팅 중단, refine/결과 폴링 모드로 전환
            job["result_ready_announced"] = True
            job["phase"] = "result_requested"
            if has_answers and not refine_started:
                # refine 트리거
                job["refine_started"] = True
                transcript_text = (
                    job["stt_result"].text
                    if job.get("stt_result") is not None
                    else job.get("source", "")
                )
                user_ctx = _user_ctx_for_display(job) or {}
                scam_type = job["result"].get("scam_type", "")
                trigger_refine = True
            else:
                # 답변 없음 → 1차 결과 그대로 반환 + 잡 정리 + 토큰 발급
                _, url = _issue_result_token(
                    result=job["result"],
                    user_context=_user_ctx_for_display(job),
                    input_type=job["input_type"],
                    user_id=user_id,
                    chat_history=job.get("chat_history") or [],
                )
                result = kakao_formatter.format_result(
                    job["result"], job["input_type"],
                    user_context=_user_ctx_for_display(job),
                    result_url=url,
                )
                _pending_jobs.pop(user_id, None)
                return result

            # announce 응답 (lock 밖에서 schedule)
        elif refine_started and not refined:
            return kakao_formatter.format_refining_in_progress()
        elif refined:
            _, url = _issue_result_token(
                result=job["result"],
                user_context=_user_ctx_for_display(job),
                input_type=job["input_type"],
                user_id=user_id,
                chat_history=job.get("chat_history") or [],
            )
            result = kakao_formatter.format_result(
                job["result"], job["input_type"],
                user_context=_user_ctx_for_display(job),
                result_url=url,
            )
            _pending_jobs.pop(user_id, None)
            return result
        else:
            # 폴백: announced 인데 refine 없음 (대부분 이미 위에서 처리)
            _, url = _issue_result_token(
                result=job["result"],
                user_context=_user_ctx_for_display(job),
                input_type=job["input_type"],
                user_id=user_id,
                chat_history=job.get("chat_history") or [],
            )
            result = kakao_formatter.format_result(
                job["result"], job["input_type"],
                user_context=_user_ctx_for_display(job),
                result_url=url,
            )
            _pending_jobs.pop(user_id, None)
            return result

    # 첫 알림 + refine 트리거 case
    log.info("→ 결과 준비 완료 → announce + refine 트리거: user=%s", user_id[:12])
    background_tasks.add_task(
        _kakao_refine_text_task,
        user_id, transcript_text, scam_type, user_ctx,
    )
    return kakao_formatter.format_result_ready_announce(has_refine=True)


async def _kakao_force_skip_context(user_id: str) -> dict[str, Any]:
    """사용자가 '그냥 분석결과 보내줘' 같은 신호 → 컨텍스트 강제 종료."""
    with _jobs_lock:
        job = _pending_jobs.get(user_id)
        if job is None:
            return kakao_formatter.format_no_job()
        if job.get("status") == "error":
            del _pending_jobs[user_id]
            error_code = _classify_error(job.get("error") or Exception())
            return kakao_formatter.format_error(error_code)
        if job.get("status") == "done":
            _, url = _issue_result_token(
                result=job["result"],
                user_context=_user_ctx_for_display(job),
                input_type=job["input_type"],
                user_id=user_id,
                chat_history=job.get("chat_history") or [],
            )
            result = kakao_formatter.format_result(
                job["result"], job["input_type"],
                user_context=_user_ctx_for_display(job),
                result_url=url,
            )
            del _pending_jobs[user_id]
            return result
        # collecting_context 또는 analyzing 중
        already_analyzing = job.get("analyzing_started", False)
        if job.get("phase") == "collecting_context":
            job["context_done"] = True
            if job.get("user_context") is None:
                job["user_context"] = context_chat.summarize_for_pipeline(
                    job["chat_history"]
                )
            stt_done = job["stt_done"]
        else:
            stt_done = job["stt_done"]

    if already_analyzing:
        # TEXT 즉시 병렬 모드 — 분석이 이미 돌고 있음. 결과 기다리기만 하면 됨
        return kakao_formatter.format_still_running()

    _spawn_bg(_async_maybe_trigger_analyze(user_id))
    return kakao_formatter.format_context_done_waiting(stt_done=stt_done)


@app.post("/webhook/kakao")
async def kakao_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    """
    카카오 오픈빌더 Skill Webhook 엔드포인트.

    분기 흐름:
    - 도움말 / 결과확인 / 스킵 같은 특수 명령 우선 처리
    - 진행 중 job 이 있으면 답변 또는 busy 처리 (멀티턴 컨텍스트 수집)
    - 신규 입력:
      - callbackUrl 있음 → 단발 callback 모드 (컨텍스트 수집 없음)
      - URL/영상 + callback 없음 → 컨텍스트 수집 + 병렬 STT 시작
      - 텍스트 → 즉시 동기 분석
    """
    log = logging.getLogger("kakao_webhook")
    EC = kakao_formatter.ErrorCode
    InputType = kakao_formatter.InputType

    try:
        body = await request.json()
    except Exception:
        return kakao_formatter.format_error(EC.PARSE_ERROR)

    log.info(
        "kakao webhook 수신:\n"
        "  utterance: %s\n"
        "  callbackUrl: %s\n"
        "  action.params: %s",
        (body.get("userRequest", {}).get("utterance") or "")[:100],
        (body.get("userRequest", {}).get("callbackUrl") or "")[:80],
        str(body.get("action", {}).get("params", {}))[:200],
    )

    user_request = body.get("userRequest", {})
    utterance: str = (user_request.get("utterance") or "").strip()
    callback_url: str = (user_request.get("callbackUrl") or "").strip()
    action_params: dict = body.get("action", {}).get("params", {})
    user_id: str = (user_request.get("user", {}).get("id") or "").strip()

    # ── 어뷰즈 누적 차단 우선 검사 (블록 상태면 다른 처리 모두 skip) ──
    soft_warn_info: dict | None = None
    if user_id:
        from platform_layer import abuse_guard as _ag
        blocked, remaining = _ag.block_status(user_id)
        if blocked:
            log.warning("→ blocked user %s (남은 %ds)", user_id[:12], remaining)
            with _jobs_lock:
                _pending_jobs.pop(user_id, None)   # 채팅 강제 종료
            return kakao_formatter.format_abuse_blocked(remaining)
        # 짧은 메시지 누적 트래커 — 통과시키되 반복되면 카운트
        # action_params 에 파일/이미지 있으면 skip (분석 의도 있는 입력)
        has_attachment = any(
            action_params.get(k)
            for k in ("image", "picture", "photo", "pdf", "document", "video", "video_url", "file", "attachment")
        )
        if utterance and not has_attachment:
            soft_warn_info = _ag.track_short_message(user_id, utterance)
            if soft_warn_info and soft_warn_info.get("blocked"):
                log.warning("→ soft block triggered user %s", user_id[:12])
                with _jobs_lock:
                    _pending_jobs.pop(user_id, None)
                return kakao_formatter.format_abuse_blocked(
                    soft_warn_info.get("block_remaining_sec") or _ag.BLOCK_DURATION_SEC
                )

    # ── 특수 명령: 빈 메시지 = welcome (즉답) ──
    if not utterance:
        log.info("→ welcome 응답 반환 (빈 메시지)")
        return kakao_formatter.format_welcome()
    # ── 특수 명령: 사용법 (대화 중에도 escape 가능, 즉답) ──
    if utterance in ("사용법", "도움말", "help", "?"):
        log.info("→ 사용법 응답 반환 (특수 명령)")
        return kakao_formatter.format_help()

    # ── 특수 명령: 분석 초기화 — 진행 중 잡 정리하고 새로 시작 ──
    if utterance in ("분석 초기화", "초기화", "리셋", "reset"):
        had_job = False
        if user_id:
            with _jobs_lock:
                had_job = user_id in _pending_jobs
                _pending_jobs.pop(user_id, None)
        log.info(
            "→ 분석 초기화: user=%s had_job=%s",
            user_id[:12] if user_id else "?", had_job,
        )
        return kakao_formatter.format_reset(had_active_job=had_job)

    # ── 특수 명령: 결과확인 (자연 표현 동의어 포함) ──
    # - collecting_context: 사용자가 종료 의사 표명 → 컨텍스트 강제 종료 + 분석 트리거
    # - analyzing: 폴링
    # - done/error: 결과/에러 반환
    if _is_result_request(utterance):
        _cleanup_expired_jobs()
        with _jobs_lock:
            job = _pending_jobs.get(user_id)
        log.info(
            "→ 결과확인 요청: user=%s status=%s phase=%s",
            user_id[:12] if user_id else "?",
            job and job.get("status"),
            job and job.get("phase"),
        )
        if job is None:
            return kakao_formatter.format_no_job()
        if job.get("status") == "error":
            with _jobs_lock:
                _pending_jobs.pop(user_id, None)
            error_code = _classify_error(job.get("error") or Exception())
            return kakao_formatter.format_error(error_code)
        if job.get("status") == "done":
            return await _handle_done_state(user_id, background_tasks)
        # running 상태에서 collecting_context 면 강제 종료 신호로 해석
        if job.get("phase") == "collecting_context":
            log.info("→ 결과확인 = 컨텍스트 강제 종료 신호로 해석")
            return await _kakao_force_skip_context(user_id)
        # analyzing 중이면 일반 폴링
        return kakao_formatter.format_still_running()

    # ── 특수 명령: 컨텍스트 수집 강제 종료 ──
    if utterance in _KAKAO_SKIP_PHRASES and user_id:
        log.info("→ 스킵 신호 수신: user=%s", user_id[:12])
        with _jobs_lock:
            has_job = user_id in _pending_jobs
        if has_job:
            return await _kakao_force_skip_context(user_id)
        return kakao_formatter.format_no_job()

    # ── 입력 감지 ──
    source, input_type = _kakao_detect_input(utterance, action_params)
    is_heavy = input_type in (
        InputType.URL, InputType.VIDEO, InputType.FILE, InputType.IMAGE, InputType.PDF,
    )
    log.info(
        "입력 감지: type=%s, heavy=%s, source=%s",
        input_type.value, is_heavy, source[:80],
    )

    # ── v3 Phase 1: 이미지/PDF 는 카카오 CDN URL → 로컬 파일 다운로드 후 vision 라우팅 ──
    if input_type in (InputType.IMAGE, InputType.PDF) and source.startswith("http"):
        try:
            suffix_hint = ".pdf" if input_type == InputType.PDF else ""
            local_path = await asyncio.to_thread(
                _kakao_materialize_url, source, suffix_hint,
            )
            log.info(
                "→ 카카오 미디어 로컬 저장: %s → %s",
                input_type.value, Path(local_path).name,
            )
            source = local_path
        except Exception as exc:
            log.error("카카오 미디어 다운로드 실패: %s", exc, exc_info=True)
            return kakao_formatter.format_error(
                kakao_formatter.ErrorCode.UNKNOWN,
                f"파일 다운로드 실패: {exc}",
            )

    # ── 진행 중 job 처리 (callbackUrl 없는 폴링/멀티턴 모드 한정) ──
    if user_id and not callback_url:
        with _jobs_lock:
            job = _pending_jobs.get(user_id)
        if job is not None:
            phase = job.get("phase")
            status = job.get("status")
            if status == "error":
                with _jobs_lock:
                    _pending_jobs.pop(user_id, None)
                error_code = _classify_error(job.get("error") or Exception())
                return kakao_formatter.format_error(error_code)
            if status == "done":
                # 1차 분석은 끝났지만 phase 가 collecting_context 면 사용자가 아직 채팅 중 →
                # 결과 발표하지 말고 다음 질문 계속. 사용자가 명시적으로 '결과확인' 누를 때 announce.
                if phase == "collecting_context":
                    log.info(
                        "→ 분석 완료 후에도 채팅 계속: user=%s (사용자가 결과확인 안 함)",
                        user_id[:12],
                    )
                    return await _kakao_handle_context_answer(user_id, utterance)
                # 그 외(예: refining 중에 사용자가 텍스트 입력) → 안내
                return await _handle_done_state(user_id, background_tasks, utterance=utterance)
            # running
            if is_heavy:
                # 진행 중인데 새 영상/URL → 거절
                log.info("→ busy: 진행 중 job 있음, 새 영상 거절")
                return kakao_formatter.format_busy()
            if phase == "collecting_context":
                # 답변으로 처리
                log.info("→ 컨텍스트 답변 처리: user=%s", user_id[:12])
                return await _kakao_handle_context_answer(user_id, utterance)
            # analyzing 중에 텍스트 입력 → 진행 중 안내
            return kakao_formatter.format_still_running()

    # ── callbackUrl 있으면: 단발 callback 모드 (컨텍스트 수집 없음) ──
    if callback_url:
        log.info(
            "→ callback 모드: 백그라운드 분석 시작, callbackUrl=%s",
            callback_url[:80],
        )
        msg = kakao_formatter.format_analyzing(input_type)
        background_tasks.add_task(
            _kakao_callback_task, source, callback_url, input_type, True,
        )
        resp = {
            "version": "2.0",
            "useCallback": True,
            "data": {"text": msg},
        }
        log.info("→ 즉시 응답: %s", str(resp)[:200])
        return resp

    # ── callbackUrl 없음, 무거운 입력 → 컨텍스트 수집 시작 ──
    if is_heavy:
        if not user_id:
            log.warning("→ user_id 없음, 컨텍스트 수집 불가 → CALLBACK_REQUIRED")
            return kakao_formatter.format_error(EC.CALLBACK_REQUIRED)
        log.info(
            "→ 컨텍스트 수집 모드 시작: user=%s type=%s",
            user_id[:12], input_type.value,
        )
        return await _kakao_start_context_collection(
            user_id, source, input_type, background_tasks,
        )

    # ── 어뷰즈 가드 (TEXT) — 길이/반복/gibberish/도배 ──
    # user_id 가 있으면 위반 누적 → 자동 블록 (3회 경고 후 1시간 차단)
    if user_id:
        from platform_layer import abuse_guard as _ag
        rej = _ag.guard(source, user_id=user_id)
        if rej is not None:
            log.warning(
                "→ abuse guard reject user=%s code=%s (%s)",
                user_id[:12], rej.code, rej.detail,
            )
            if rej.code == "BLOCKED":
                with _jobs_lock:
                    _pending_jobs.pop(user_id, None)
                # remaining_sec=detail 에서 추출
                remaining = 3600
                try:
                    remaining = int(rej.detail.split("=")[-1].split("s")[0])
                except Exception:
                    pass
                return kakao_formatter.format_abuse_blocked(remaining)
            warns_left = _ag.VIOLATION_WARN_LIMIT - _ag.violation_count(user_id)
            return kakao_formatter.format_abuse_warning(rej.message, max(0, warns_left))

    # ── 텍스트: 의도 분류 → 분기 ──
    # Claude Haiku 가 메시지를 보고 GREETING/HELP/CONTENT/ANALYZE_NO_CONTENT/CHAT 분류
    # (짧고 명확한 인사·사용법은 keyword fast-path 로 즉답)
    # [어뷰즈 가드] 짧은 메시지 누적 2회 이상이면 Haiku 호출 skip — 어뷰저 무료 LLM 통로 차단
    if soft_warn_info and soft_warn_info.get("count", 0) >= 2:
        log.info(
            "→ Haiku skip (soft warn count=%d) → welcome 직접 반환",
            soft_warn_info["count"],
        )
        return _wrap_with_soft_warning(kakao_formatter.format_welcome(), soft_warn_info)

    intent = await asyncio.to_thread(context_chat.classify_intent, source)
    log.info("→ TEXT intent: %s", intent)

    if intent == context_chat.INTENT_GREETING:
        return _wrap_with_soft_warning(kakao_formatter.format_welcome(), soft_warn_info)
    if intent == context_chat.INTENT_HELP:
        return _wrap_with_soft_warning(kakao_formatter.format_help(), soft_warn_info)
    if intent == context_chat.INTENT_ANALYZE_NO_CONTENT:
        return _wrap_with_soft_warning(
            kakao_formatter.format_ask_for_content(reason="analyze"), soft_warn_info,
        )
    if intent == context_chat.INTENT_CHAT:
        return _wrap_with_soft_warning(
            kakao_formatter.format_ask_for_content(reason="chat"), soft_warn_info,
        )

    # CONTENT (default) — 본문이 들어왔다고 판단 → 컨텍스트 수집 모드 시작
    if not user_id:
        log.warning("→ TEXT user_id 없음, 컨텍스트 수집 불가 → CALLBACK_REQUIRED")
        return kakao_formatter.format_error(EC.CALLBACK_REQUIRED)
    log.info(
        "→ TEXT 컨텍스트 수집 모드 시작: user=%s len=%s",
        user_id[:12], len(source),
    )
    return await _kakao_start_context_collection(
        user_id, source, input_type, background_tasks,
    )


@app.post("/api/analyze")
async def analyze(payload: AnalyzeRequest, request: Request) -> dict:
    import logging
    log = logging.getLogger("api_analyze")
    source = _resolve_source(payload)
    log.info(
        "/api/analyze 요청:\n"
        "  source: %s\n"
        "  whisper_model: %s, skip_verification: %s, use_llm: true(강제), use_rag: %s",
        source[:100], payload.whisper_model, payload.skip_verification,
        payload.use_rag,
    )
    # 어뷰즈 가드 — 텍스트 입력에 한해 외부 API 호출 전 차단
    # user_id 헤더 (X-User-Id) 가 있으면 위반 누적·자동 블록 적용
    if payload.text and not payload.source:
        from platform_layer import abuse_guard as _ag
        key_id = getattr(request.state, "api_key_id", None)
        user_id = request.headers.get("x-user-id", "").strip() or None
        rej = _ag.guard(payload.text, key_id=key_id, user_id=user_id)
        if rej is not None:
            status = 423 if rej.code == "BLOCKED" else 400
            raise HTTPException(
                status_code=status,
                detail={"code": rej.code, "message": rej.message, "detail": rej.detail},
            )
    try:
        result = await asyncio.to_thread(_run_pipeline, payload)
        log.info(
            "/api/analyze 완료: scam_type=%s, risk=%s/100 (%s)",
            result.get("scam_type", "?"),
            result.get("total_score", "?"),
            result.get("risk_level", "?"),
        )
        return result
    except ValueError as exc:
        log.warning("/api/analyze 입력 오류: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except EnvironmentError as exc:
        log.warning("/api/analyze 환경 오류: %s", exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        log.error("/api/analyze 서버 오류: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/analyze-upload")
async def analyze_upload(
    file: UploadFile = File(...),
    whisper_model: str = Form("medium"),
    skip_verification: bool = Form(True),
    use_llm: bool = Form(True),
    use_rag: bool = Form(False),
) -> dict:
    """
    영상/음성 파일을 업로드 받아 로컬 파일로 저장한 뒤 파이프라인을 수행한다.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="업로드된 파일 이름이 비어 있습니다.")

    suffix = Path(file.filename).suffix
    upload_dir = Path(".scamguardian") / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    tmp_handle = tempfile.NamedTemporaryFile(
        mode="wb",
        delete=False,
        dir=str(upload_dir),
        prefix="upload_",
        suffix=suffix,
    )
    tmp_path = Path(tmp_handle.name)
    wav_path = tmp_path.with_suffix(".wav")
    media_persisted = False
    try:
        with tmp_handle:
            if file.file is None:
                raise HTTPException(status_code=400, detail="업로드된 파일 본문을 읽을 수 없습니다.")
            shutil.copyfileobj(file.file, tmp_handle)

        if tmp_path.stat().st_size == 0:
            raise HTTPException(status_code=400, detail="업로드된 파일이 비어 있습니다(0 bytes).")

        # v3 Phase 1: 이미지·PDF 는 vision OCR 라우팅 — ffmpeg 단계 skip
        from pipeline import vision as _vision_mod
        is_visual = _vision_mod.supported(tmp_path)
        if is_visual:
            payload = AnalyzeRequest(
                source=str(tmp_path),
                whisper_model=whisper_model,
                skip_verification=skip_verification,
                use_llm=True,
                use_rag=use_rag,
            )
        else:
            # Whisper 디코딩 호환성을 위해 먼저 wav(16k mono)로 추출한다.
            # 영상 컨테이너/코덱에 따라 whisper.load_audio가 0-length로 읽히는 케이스를 방지한다.
            extract = subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(tmp_path),
                    "-vn",
                    "-ac",
                    "1",
                    "-ar",
                    "16000",
                    "-f",
                    "wav",
                    str(wav_path),
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if extract.returncode != 0 or not wav_path.exists() or wav_path.stat().st_size == 0:
                raise HTTPException(
                    status_code=400,
                    detail="업로드된 파일에서 오디오를 추출하지 못했습니다. 다른 파일(코덱)로 시도해주세요.",
                )

            payload = AnalyzeRequest(
                source=str(wav_path),
                whisper_model=whisper_model,
                skip_verification=skip_verification,
                use_llm=True,
                use_rag=use_rag,
            )
        result = await asyncio.to_thread(_run_pipeline, payload)

        # 라벨링 검증을 위해 원본 업로드 파일을 run_id 기반 영구 경로에 보존한다.
        run_id = result.get("analysis_run_id") if isinstance(result, dict) else None
        media_persisted = False
        if run_id:
            try:
                target_dir = Path(".scamguardian") / "uploads" / str(run_id)
                target_dir.mkdir(parents=True, exist_ok=True)
                target_path = target_dir / f"source{suffix or ''}"
                shutil.move(str(tmp_path), str(target_path))
                media_persisted = True
                try:
                    repository.merge_run_metadata(run_id, {
                        "media": {
                            "kind": "uploaded_file",
                            "original_filename": file.filename,
                            "stored_path": str(target_path),
                            "size_bytes": target_path.stat().st_size,
                            "suffix": suffix or "",
                        }
                    })
                except Exception as exc:
                    logging.getLogger("upload").warning(
                        "media metadata merge 실패 (run_id=%s): %s", run_id, exc,
                    )
            except Exception as exc:
                logging.getLogger("upload").warning(
                    "원본 업로드 파일 보존 실패 (run_id=%s): %s", run_id, exc,
                )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    finally:
        if not media_persisted:
            try:
                tmp_path.unlink(missing_ok=True)
            except Exception:
                pass
        try:
            wav_path.unlink(missing_ok=True)
        except Exception:
            pass


@app.get("/api/admin/runs")
async def admin_list_runs(
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    try:
        _require_db()
        runs = await asyncio.to_thread(
            repository.list_runs_for_labeling,
            limit=limit,
            offset=offset,
            status_filter=status,
        )
        return {"runs": runs, "limit": limit, "offset": offset}
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


class ClaimRunRequest(BaseModel):
    labeler: str


@app.post("/api/admin/runs/{run_id}/claim")
async def admin_claim_run(run_id: str, payload: ClaimRunRequest) -> dict[str, Any]:
    try:
        _require_db()
        labeler = payload.labeler.strip() or "Admin"
        ok = await asyncio.to_thread(repository.claim_run, run_id, labeler)
        if not ok:
            raise HTTPException(status_code=409, detail="다른 검수자가 이미 작업 중입니다.")
        return {"ok": True}
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/runs/search")
async def admin_search_runs(
    q: str | None = None,
    scam_type: str | None = None,
    risk_level: str | None = None,
    labeled: str | None = None,
    limit: int = 30,
    offset: int = 0,
) -> dict[str, Any]:
    try:
        _require_db()
        labeled_bool: bool | None = None
        if labeled == "true":
            labeled_bool = True
        elif labeled == "false":
            labeled_bool = False
        result = await asyncio.to_thread(
            repository.search_runs,
            query=q,
            scam_type=scam_type,
            risk_level=risk_level,
            labeled=labeled_bool,
            limit=limit,
            offset=offset,
        )
        return result
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/runs/next")
async def admin_next_run() -> dict[str, Any]:
    try:
        _require_db()
        run = await asyncio.to_thread(repository.get_next_unannotated_run)
        return {"run": run, "options": _options_payload()}
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/runs/{run_id}")
async def admin_run_detail(run_id: str) -> dict[str, Any]:
    try:
        _require_db()
        detail = await asyncio.to_thread(repository.get_run_detail, run_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="해당 run을 찾을 수 없습니다.")
        detail["options"] = _options_payload()
        return detail
    except HTTPException:
        raise
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/runs/{run_id}/annotations")
async def admin_save_annotation(run_id: str, payload: HumanAnnotationRequest) -> dict[str, Any]:
    try:
        _require_db()
        run = await asyncio.to_thread(repository.get_run_detail, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="해당 run을 찾을 수 없습니다.")

        # 검수자 이름 미입력 시 기본 'Admin'
        labeler = (payload.labeler or "").strip() or "Admin"
        annotation = await asyncio.to_thread(
            repository.upsert_human_annotation,
            run_id=run_id,
            scam_type_gt=payload.scam_type_gt,
            entities_gt=payload.entities_gt,
            triggered_flags_gt=payload.triggered_flags_gt,
            labeler=labeler,
            transcript_corrected_text=payload.transcript_corrected_text,
            stt_quality=payload.stt_quality,
            notes=payload.notes,
        )
        return {"ok": True, "annotation": annotation}
    except HTTPException:
        raise
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


_MEDIA_MIME_BY_SUFFIX = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".webm": "video/webm",
    ".mkv": "video/x-matroska",
    ".m4a": "audio/mp4",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".aac": "audio/aac",
}


_UPLOADS_ROOT = (Path(".scamguardian") / "uploads").resolve()


def _resolve_admin_media_path(stored_path_str: str) -> Path:
    """저장된 미디어 경로가 uploads 디렉토리 안인지 검증 후 반환 (path traversal 방지)."""
    candidate = Path(stored_path_str).resolve()
    try:
        candidate.relative_to(_UPLOADS_ROOT)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="허용되지 않은 경로입니다.") from exc
    if not candidate.exists() or not candidate.is_file():
        raise HTTPException(status_code=404, detail="미디어 파일을 찾을 수 없습니다.")
    return candidate


@app.get("/api/admin/runs/{run_id}/media")
async def admin_get_media(run_id: str) -> FileResponse:
    """라벨링용으로 보존된 원본 업로드 파일을 스트리밍한다."""
    try:
        _require_db()
        detail = await asyncio.to_thread(repository.get_run_detail, run_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="해당 run을 찾을 수 없습니다.")
        media = (detail["run"].get("metadata") or {}).get("media") or {}
        stored = media.get("stored_path")
        if not stored:
            raise HTTPException(status_code=404, detail="저장된 미디어가 없습니다.")
        path = _resolve_admin_media_path(stored)
        suffix = path.suffix.lower()
        media_type = _MEDIA_MIME_BY_SUFFIX.get(suffix, "application/octet-stream")
        filename = media.get("original_filename") or path.name
        return FileResponse(path, media_type=media_type, filename=filename)
    except HTTPException:
        raise
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/metrics")
async def admin_metrics(scam_type: str | None = None) -> dict[str, Any]:
    try:
        _require_db()
        records = await asyncio.to_thread(repository.fetch_annotated_pairs, scam_type)
        metrics = pipeline_eval.evaluate_annotated_runs(records)
        metrics["filters"] = {"scam_type": scam_type}
        return metrics
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/runs/{run_id}/ai-draft")
async def admin_ai_draft(run_id: str) -> dict[str, Any]:
    """
    Claude API로 라벨링 초안을 자동 생성한다.
    검수자는 초안을 확인 후 수정/승인만 하면 된다.
    """
    try:
        _require_db()
        detail = await asyncio.to_thread(repository.get_run_detail, run_id)
        if detail is None:
            raise HTTPException(status_code=404, detail="해당 run을 찾을 수 없습니다.")

        from pipeline import claude_labeler

        run = detail["run"]
        transcript = run.get("transcript_text", "")
        predicted_scam_type = (run.get("classification_scanner") or {}).get("scam_type", "")
        predicted_entities = run.get("entities_predicted") or []
        predicted_flags = run.get("triggered_flags_predicted") or []

        draft = await asyncio.to_thread(
            claude_labeler.generate_draft,
            transcript,
            predicted_scam_type,
            predicted_entities,
            predicted_flags,
        )
        return {"ok": True, "draft": draft}
    except HTTPException:
        raise
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/stats")
async def admin_stats() -> dict[str, Any]:
    try:
        _require_db()
        stats = await asyncio.to_thread(repository.get_dashboard_stats)
        return stats
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ──────────────────────────────────
# v3 platform — API key 관리 / observability / cost
# ──────────────────────────────────
class CreateApiKeyRequest(BaseModel):
    label: str
    monthly_quota: int = 1000
    rpm_limit: int = 30
    monthly_usd_quota: float = 5.0


@app.post("/api/admin/api-keys")
async def admin_create_api_key(payload: CreateApiKeyRequest) -> dict[str, Any]:
    try:
        _require_db()
        record = await asyncio.to_thread(
            api_key_module.issue,
            label=payload.label,
            monthly_quota=payload.monthly_quota,
            rpm_limit=payload.rpm_limit,
            monthly_usd_quota=payload.monthly_usd_quota,
        )
        return record
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/api-keys")
async def admin_list_api_keys() -> dict[str, Any]:
    try:
        _require_db()
        keys = await asyncio.to_thread(api_key_module.list_keys)
        return {"keys": keys}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/api-keys/{key_id}/revoke")
async def admin_revoke_api_key(key_id: str) -> dict[str, Any]:
    try:
        _require_db()
        ok = await asyncio.to_thread(api_key_module.revoke, key_id)
        if not ok:
            raise HTTPException(status_code=404, detail="키를 찾을 수 없습니다.")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/observability")
async def admin_observability(hours: int = 24, recent_limit: int = 100) -> dict[str, Any]:
    try:
        _require_db()
        summary = await asyncio.to_thread(repository.request_log_summary, hours=hours)
        recent = await asyncio.to_thread(repository.request_log_recent, recent_limit)
        return {"summary": summary, "recent": recent}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/cost")
async def admin_cost(days: int = 30) -> dict[str, Any]:
    try:
        _require_db()
        return await asyncio.to_thread(repository.aggregate_costs, days=days)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/abuse-blocks")
async def admin_abuse_blocks() -> dict[str, Any]:
    """현재 일시 차단된 user_id 목록."""
    from platform_layer import abuse_guard as _ag
    return {"blocks": _ag.list_blocks()}


@app.post("/api/admin/abuse-blocks/{user_id}/unblock")
async def admin_abuse_unblock(user_id: str) -> dict[str, Any]:
    from platform_layer import abuse_guard as _ag
    ok = _ag.unblock(user_id)
    return {"ok": ok}


# ──────────────────────────────────
# v3 학습 세션 관리 endpoints
# ──────────────────────────────────
class StartTrainingRequest(BaseModel):
    model: str                        # "classifier" | "gliner"
    epochs: int = 3
    batch_size: int = 8
    lora: bool = False
    extra_jsonl: str | None = None
    val_ratio: float = 0.1
    seed: int = 17
    base_model: str | None = None


@app.get("/api/admin/training/data-stats")
async def admin_training_data_stats() -> dict[str, Any]:
    """현재 라벨링 데이터 통계 — 라벨 분포, 학습 가능 여부."""
    try:
        from training import data as tdata
        cls = await asyncio.to_thread(tdata.load_classifier_dataset)
        gli = await asyncio.to_thread(tdata.load_gliner_dataset)
        return {
            "classifier": {
                "total": len(cls),
                "labels": tdata.label_distribution(cls),
            },
            "gliner": {
                "total": len(gli),
                "total_entities": sum(len(e.ner) for e in gli),
            },
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/training/sessions")
async def admin_training_start(payload: StartTrainingRequest) -> dict[str, Any]:
    try:
        from training import sessions as tsess
        params = tsess.SessionParams(
            model=payload.model,
            epochs=payload.epochs,
            batch_size=payload.batch_size,
            lora=payload.lora,
            extra_jsonl=payload.extra_jsonl,
            val_ratio=payload.val_ratio,
            seed=payload.seed,
            base_model=payload.base_model,
        )
        info = await asyncio.to_thread(tsess.start_session, params)
        return info
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/training/sessions")
async def admin_training_list(limit: int = 50) -> dict[str, Any]:
    try:
        from training import sessions as tsess
        items = await asyncio.to_thread(tsess.list_sessions, limit)
        return {"sessions": items, "active_models": tsess.get_active_models()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/training/sessions/{session_id}")
async def admin_training_detail(session_id: str) -> dict[str, Any]:
    try:
        from training import sessions as tsess
        info = await asyncio.to_thread(tsess.get_session, session_id)
        if info is None:
            raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다.")
        metrics = await asyncio.to_thread(tsess.read_metrics, session_id, 500)
        log_tail = await asyncio.to_thread(tsess.read_log_tail, session_id, 8000)
        return {"session": info, "metrics": metrics, "log_tail": log_tail}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/training/sessions/{session_id}/cancel")
async def admin_training_cancel(session_id: str) -> dict[str, Any]:
    try:
        from training import sessions as tsess
        ok = await asyncio.to_thread(tsess.cancel_session, session_id)
        if not ok:
            raise HTTPException(status_code=409, detail="취소할 수 없는 상태입니다.")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/training/sessions/{session_id}/activate")
async def admin_training_activate(session_id: str) -> dict[str, Any]:
    try:
        from training import sessions as tsess
        result = await asyncio.to_thread(tsess.activate_session, session_id)
        return {"ok": True, **result}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/admin/scam-types")
async def admin_scam_types() -> dict[str, Any]:
    try:
        _require_db()
        items = await asyncio.to_thread(repository.list_custom_scam_types)
        return {"items": items, "options": _options_payload()}
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/admin/scam-types")
async def admin_add_scam_type(payload: ScamTypeCatalogRequest) -> dict[str, Any]:
    try:
        _require_db()
        normalized = _normalize_catalog_payload(payload)
        if not normalized["name"]:
            raise HTTPException(status_code=400, detail="스캠 유형 이름을 입력해주세요.")
        if normalized["name"] in DEFAULT_SCAM_TYPES:
            raise HTTPException(status_code=400, detail="기본 스캠 유형과 같은 이름은 추가할 수 없습니다.")

        item = await asyncio.to_thread(
            repository.upsert_custom_scam_type,
            name=normalized["name"],
            description=normalized["description"],
            labels=normalized["labels"],
        )
        return {"ok": True, "item": item, "options": _options_payload()}
    except HTTPException:
        raise
    except EnvironmentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
