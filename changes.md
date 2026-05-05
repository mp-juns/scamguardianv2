# changes.md

milestone 단위 변경 로그. 누적 append, 최신이 위.

---

## 2026-05-04 — v4 Whisper 5초 chunk 한국어 정확도 측정 ⚠️ FAIL (그러나 valuable)

**무엇**: 5개 한국어 시나리오 (검찰사칭/금융사칭/메타인식/송금동의/대조군) 를 edge-tts 합성, OpenAI Whisper API 5초 chunk 로 transcribe, WER 측정.

**결과**: 평균 WER **0.307** (임계 0.20 → FAIL). 5/2 PASS. chunk 평균 latency 1985ms.

**왜 valuable**:
- v4 직진 못 한다는 명확한 시그널 — 30분 검증의 본 목적이 "들어가기 전 break point 찾기"
- 실패 원인 3가지가 모두 알려진 패턴 → 처방 가능

**핵심 발견 (3종 실패 패턴)**:
1. **침묵 chunk 환각** (s1_prosecutor) — 발화 종료 후 침묵 5초 chunk 에 Whisper 가 "MBC 뉴스 이덕영입니다" 환각. Whisper 학습 데이터의 뉴스 종영 멘트 bias. → **VAD pre-filter** 필요.
2. **Chunk 경계 단어 절단** (s3, s4, s5) — 5초 경계가 단어 중간에 떨어져서 양쪽 chunk 모두 부정확. 예: "되는 건가요" → "되는 겁니까? | 건가요?". → **overlapping window (2초 hop) + dedupe** 필요.
3. **한국어 숫자/신조어 표기** (s5) — "두 시쯤" → "2시쯤" 의미 동일하지만 token WER 잡힘. → **CER 또는 의미 기반 metric** 검토.

**산출물**:
- `experiments/v4_whisper/synthetic_samples.jsonl` (5개 발화 정의)
- `experiments/v4_whisper/audio/*.mp3 + *.txt` (TTS + reference)
- `experiments/v4_whisper/generate_synthetic.py` (edge-tts 합성, --speakerphone 옵션)
- `experiments/v4_whisper/batch_eval.py` (5샘플 batch + WER aggregation)
- `experiments/v4_whisper/results.md` (per-sample 결과 + 핵심 발견 + 처방)

**의존성 추가**: `edge-tts` (개발 전용, requirements.txt 미포함).

**v4 설계 결정**:
- 5초 고정 chunk 단순 chunker 는 production 부적합
- chunker v2 = VAD pre-filter + overlapping window + dedupe → 재측정 후 평균 WER < 0.15 또는 CER < 0.10 통과해야 v4.0 진입
- 또는 Deepgram 한국어 (정확도 ↑, 비용 5×) 비교 검증 후 결정

다음: api_server.py 분리 + v4 검증 종합 커밋 → 사용자 확인 후 chunker v2 또는 다른 방향 선택.

---

## 2026-05-04 — api_server.py 라우터 분리 완료 ✅

**무엇**: `api_server.py` (2368 LOC 모놀리스) → `api_server.py` (41 LOC entry) + `api_server_pkg/` (10개 모듈, 2437 LOC).

분리 단위:
| 모듈 | LOC | 역할 |
|---|---|---|
| `state.py` | 42 | 모듈 전역 상태 (`pending_jobs`, `result_tokens`, `jobs_lock`, `bg_tasks`, `public_url_cache`) + 타임아웃 상수 + `spawn_bg` |
| `models.py` | 61 | Pydantic 요청 모델 7종 (AnalyzeRequest 등) |
| `common.py` | 155 | `persist_run`, `run_pipeline`, `resolve_source`, `options_payload`, `require_db` |
| `health.py` | 58 | `/health`, `/api/methodology` |
| `result_token.py` | 145 | `/api/result/{token}` + `issue_result_token` + `get_public_base_url` (60s 캐시) |
| `kakao.py` | 1187 | `/webhook/kakao` + 모든 `_kakao_*` + 멀티턴 컨텍스트 흐름 |
| `analyze.py` | 187 | `/api/analyze`, `/api/analyze-upload` |
| `admin_runs.py` | 301 | runs/metrics/stats/ai-draft/media/scam-types |
| `admin_platform.py` | 108 | login/api-keys/observability/cost/abuse-blocks |
| `admin_training.py` | 109 | training/* 세션 관리 |
| `app.py` | 76 | FastAPI 인스턴스 + middleware + include_router + startup |

**왜**: 단일 파일 2368 LOC 가 (1) 한 파일 안에 컨텍스트 수집·웹훅·라벨링·플랫폼이 다 섞여 한 화면에 안 잡힘 (2) git blame/diff 노이즈 (3) 새 기능 (v4 Live Call Guard) 도 같은 파일에 들어가면 더 비대해질 예정. 라우터 단위 분리로 모듈 응집도 ↑.

**구현 노트**:
- 외부 import 호환성 100% — 테스트가 `from api_server import _kakao_detect_input` / `_resolve_admin_media_path` / `_is_system_command` / `_wrap_with_soft_warning` / `app` 직접 가져옴 → 모두 re-export
- 모듈 전역 상태는 `api_server_pkg.state` 한 곳에 모음 (`_pending_jobs` → `state.pending_jobs` 등). 여러 모듈이 같은 dict 인스턴스 공유.
- 라우터 패턴: 각 모듈에 `router = APIRouter()`, `app.py` 에서 `include_router(...)` 일괄 등록.
- `importlib.reload(api_server)` 호환 — `api_server.py` 가 thin entry 라 reload 시 `create_app()` 재실행됨.

**결과**: ✅ pytest 93/93 통과 (6.51s, baseline 6.95s 보다 살짝 빠름). TestClient 로 `/health`, `/api/methodology` 검증 — 36 routes (admin 26개) 정상.

다음: v4 Whisper 5초 chunk 한국어 정확도 측정 (TTS 합성 음성 5~6개).

---

## 2026-05-04 — pytest baseline 확인 (refactor 시작 전)

**무엇**: `pytest -q` 실행, 13개 파일 / 93 테스트 통과 (6.95s).

**왜**: api_server.py (2368 LOC) 라우터별 분리 리팩토링 들어가기 전, baseline 확인. 분리 후 동일하게 93/93 통과해야 통과 판정.

**결과**: ✅ 93 passed. 분리 작업 시작 가능.

다음: api_server/ 패키지 골격 + helpers + health 분리.
