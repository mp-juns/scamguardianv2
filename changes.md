# changes.md

milestone 단위 변경 로그. 누적 append, 최신이 위.

---

## 2026-05-05 — APK 검출 4-tier 구현 (정적 Lv1 + Lv2 + 동적 Lv3 인터페이스)

**무엇**: VirusTotal (Tier 1) 단독 → 4-tier APK 검출 architecture. zero-day 보이스피싱 APK 대응.

**Tier 1 (이미 있음)**: VirusTotal 70+ 백신 시그니처 매칭

**Tier 2 — 정적 분석 Lv 1** (`pipeline/apk_analyzer.analyze_apk_static`):
- `androguard.core.apk.APK` 기반 manifest 분석
- 위험 권한 4종 이상 동시 → `apk_dangerous_permissions_combo`
- subject == issuer 휴리스틱 → `apk_self_signed`
- 정상 한국 앱 (kakao/naver/은행 등) typo-squatting → `apk_suspicious_package_name`

**Tier 3 — 심화 정적 분석 Lv 2** (`pipeline/apk_analyzer.analyze_apk_bytecode`):
- `androguard.misc.AnalyzeAPK` — dex disassemble + xref (코드 *읽기만*, 실행 X)
- 7 종 신호: `apk_sms_auto_send_code`, `apk_call_state_listener`, `apk_accessibility_abuse`,
  `apk_impersonation_keywords`, `apk_hardcoded_c2_url`, `apk_string_obfuscation`,
  `apk_device_admin_lock`

**Tier 4 — 동적 분석 Lv 3 인터페이스만** (`pipeline/apk_analyzer.analyze_apk_dynamic`):
- ⚠️ 로컬 실행 절대 금지 (HARD BLOCK 정책) — 호스트 멀웨어 감염 위험
- `APK_DYNAMIC_ENABLED=0` 기본 비활성, `backend=local` 어떤 env 조합으로도 풀리지 않음
- `backend=remote` + REMOTE_URL+TOKEN 둘 다 있을 때만 별도 VM 호출
- 5 종 candidate flag: `apk_runtime_c2_network_call`, `apk_runtime_sms_intercepted`,
  `apk_runtime_overlay_attack`, `apk_runtime_credential_exfiltration`,
  `apk_runtime_persistence_install`
- 실제 remote VM (Android 에뮬레이터 + Frida + MobSF stack) 구축은 future work
  — 5-7주 작업 + 별도 인프라 + 격리 정책 검증

**Phase 0.6 통합** (`pipeline/runner.py`):
- 입력이 APK 파일 (`.apk` 확장자 또는 ZIP magic) 일 때만 호출
- Lv 1 → Lv 2 → Lv 3 순차 실행, 각각 try/except graceful (실패 시 무시)
- StepLog 에 lv1/lv2/lv3 신호 개수 기록

**검출 신호 카탈로그 (총 15 종, 모두 학술/법적 근거 동반)**:
- 출처: S2W TALON 보고서 (SecretCalls·SecretCrow·KrBanker·MoqHao) / KISA / 안랩
- 학술: Cialdini (2021), Stajano & Wilson (2011), Allix et al. (2016) AndroZoo,
  Wei et al. (2018), Mavroeidis & Bromander (2017)
- 법령: 정보통신망법 제48조, 통신사기피해환급법 제2조 제2호, 형법 제283조
- API/표준: Android Documentation, OWASP Mobile Top 10, Frida

**산출물**:
- `pipeline/apk_analyzer.py` (~500 줄, Lv1 + Lv2 + Lv3)
- `pipeline/config.py` — DETECTED_FLAGS / FLAG_LABELS_KO / FLAG_RATIONALE 에 15 종 추가
- `pipeline/signal_detector.py` — `apk_static_result` / `apk_bytecode_result` /
  `apk_dynamic_result` 인자 + DetectionReport 의 3 종 check 필드
- `pipeline/runner.py` — Phase 0.6 통합 (APK 파일 자동 감지)
- `tests/test_apk_analyzer.py` (~470 줄, 70 테스트):
  - Lv 1: helper 단위 + 매핑 검증
  - Lv 2: signal_detector 통합 + 환각 차단
  - Lv 3: 안전 정책 회귀 가드 (기본 비활성 / local HARD BLOCK / auto 결정 / remote 환각 차단)
- `requirements.txt` — `androguard>=4.1.0`

**검증**:
- `pytest -q` → 184 passed (직전 114 → +70)
- 184 = baseline 85 (점수 reframe 전) + signal_detection 8 + detection_report_schema 13
  + APK Lv1 (12) + APK Lv2 (8) + Lv3 (15) + LV3 매핑 (5) + 기타
- `from api_server import app` boot OK
- Forbidden Actions: 0 위반 (점수·등급·"100% 차단"·"production-grade" 신규 0건)
- "동적 분석" vs "심화 정적 분석" 학술 용어 정확히 구분 (CLAUDE.md / README / lessons.md)

**Identity Boundary 일관**:
- ❌ 단일 신호로 "사기다" 단정 X — 누적 + 조합 시점에서만 강함 명시 (apk_analyzer.py docstring + FLAG_RATIONALE 본문 + lessons.md 패턴 6)
- ❌ 진짜 동적 분석 (에뮬레이터 실행) 하지 않음 — Lv 3 는 인터페이스 + 카탈로그만
- ❌ 로컬 실행 절대 금지 (3중 안전망: ENABLED=0 / local HARD BLOCK / remote URL+TOKEN 강제)
- ✅ 모든 신호에 학술/법적 근거 + 출처 동반 (false positive 한계도 함께 명시)

---

## 2026-05-05 — Identity reframe: 점수·등급 시스템 → 신호 검출 시스템 (Stage 1·2·3)

**무엇**: ScamGuardian 의 정체성을 "사기 판정 시스템" 에서 "사기 신호 검출 reference
implementation" 으로 reframe. VirusTotal 모델 채택 — 검출 보고만, 판정은 통합 기업이.

**왜**:
- 학부 reference 단계에서 점수의 정확한 숫자 (왜 25 점? 24 점 아니고?) 를 정당화 불가
- 등급 결정 (안전/주의/위험/매우 위험) 도 자체 RCT 없이 임계 정당화 불가
- 판정 책임을 통합 기업으로 명시적 위임 → 보안 도구의 표준 분리 모델 (VT, OWASP ZAP)
- FLAG_RATIONALE 의 학술/법적 근거가 점수 숫자보다 *훨씬* 더 무거운 자산임을 인정

**Stage 1 (narrative reframe — docs only)**:
- `CLAUDE.md` — Identity / What ScamGuardian Does NOT Do / Forbidden Actions 섹션 신설
- `README.md` — 첫 단락 교체 (사기 탐지 AI → 신호 검출 reference implementation)

**Stage 2 (코어 코드 reframe)**:
- `pipeline/signal_detector.py` 신설 — `DetectedSignal` + `DetectionReport` + `detect()`
- `pipeline/scorer.py` 삭제 (Option A 채택)
- `pipeline/config.py` — `SCORING_RULES`(dict) → `DETECTED_FLAGS`(list), `RISK_LEVELS`·
  `get_risk_level`·`LLM_FLAG_SCORE_RATIO` 폐기, `LLM_FLAG_SCORE_THRESHOLD` →
  `LLM_FLAG_DETECTION_CONFIDENCE_THRESHOLD` (env 호환 유지)
- `pipeline/runner.py` — `analyze()` 가 `DetectionReport` 반환
- `api_server_pkg/analyze.py` — description 전체 재작성 + Identity Boundary 명시
- 부수 1줄 rename: `common.py`, `health.py`, `llm_assessor.py`, `claude_labeler.py`
- **FLAG_RATIONALE 0 줄 변경** — 학술/법적 근거 그대로 보존

**Stage 3 (마무리)**:
- `pipeline/kakao_formatter.py` — 점수·등급 출력 → detected_signals 카드 + disclaimer
- `api_server_pkg/kakao/tasks.py`, `result_token.py` — log 필드 신호 개수로
- `api_server_pkg/v4_stream.py` — draft schema 도 `cumulative_signal_count` 로
- `api_server_pkg/app.py` — FastAPI title "ScamGuardian Signal Detection API"
- `tests/test_safety_scoring.py` (4) + `tests/test_sandbox_parser.py` (4) — signal_detector 로 reframe
- `tests/test_signal_detection.py` 신설 (8 테스트) — flag 검출 정확성 + LLM 환각 차단
- `tests/test_detection_report_schema.py` 신설 (13 테스트) — schema contract + 회귀 가드 (`total_score`/`risk_level` 등 폐기 필드 재도입 즉시 실패)
- `apps/web/src/app/result/[token]/page.tsx` — 점수 산정 + 위험 등급 테이블 제거 → detected_signals 카드 + 학술 근거 + disclaimer
- `apps/web/src/app/admin/{page,[runId]/AdminRunEditor,stats/page}.tsx` — 점수 표시 → 검출 신호 개수, 위험 등급 chart 제거
- `docs/INTEGRATION_GUIDE.md` — Public API 응답 schema 갱신, "Signal Detection API" rebrand
- `db/repository.py` 컬럼명은 호환 유지 (`total_score_predicted` → 신호 개수, `risk_level_predicted` → "")

**검증**:
- `pytest -q` → **114 passed, 0 failed** (회귀 0)
- `python -c "from api_server import app"` → boot OK
- `grep -rn "total_score\|risk_level" --include="*.py"` 사용처: 모두 *호환 컬럼명* 또는 *test 의 회귀 가드 (응답에 *없어야* 한다고 명시)*
- `/api/methodology` 응답: `flags[]` 의 각 항목에 `score_delta` 없음, `risk_bands` 사라짐
- `/api/analyze` description: "DetectionReport / detected_signals / Identity Boundary" 포함, "total_score / risk_level" 없음
- 카카오 카드: "🚨 위험 신호 N개 검출" + 신호별 학술 근거 + disclaimer

**Identity Boundary (CLAUDE.md Forbidden Actions 준수)**:
- ❌ 응답·UI·docstring 어디서도 "위험 점수 X점" 신규 추가 0
- ❌ "안전/의심/위험" 등급 매기기 신규 추가 0
- ❌ "이 콘텐츠는 사기입니다" 단정 신규 추가 0
- ✅ "위험 신호 N개 검출되었습니다, 자세한 근거는 detected_signals 참고" 형식만 사용
- ✅ FLAG_RATIONALE 0 줄 변경 — 학술/법적 근거 (Cialdini, Whitty, Stajano & Wilson, FBI IC3, KISA 등) 그대로

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
