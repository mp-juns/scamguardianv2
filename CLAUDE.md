# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

ScamGuardian v3 — 한국어 음성·텍스트·이미지·PDF 사기 탐지 AI 파이프라인. 카카오 챗봇·웹·CLI 모두 같은 코어 사용.

- **API 우선 설계**: 모든 비즈니스 로직은 FastAPI (`api_server.py`) 에. Next.js 는 thin proxy(`apps/web/src/app/api/_lib/backend.ts`) + UI. 모바일·외부 SDK 는 같은 REST 엔드포인트 직접 호출 가능.
- **Frontend**: Next.js 16 App Router (`apps/web/`) — Next 16은 기존 버전과 API·컨벤션이 다릅니다. `node_modules/next/dist/docs/`를 먼저 확인하세요.
- **Backend**: FastAPI (`api_server.py`) — 분석·webhook·라벨링·학습 세션·결과 토큰 페이지 모두 한 서버.
- **Pipeline**: `pipeline/` — **6 phase** (Phase 0 Safety + Phase 1 STT/Vision + Phase 2~5)
- **DB**: Postgres(+pgvector) 또는 SQLite, `db/repository.py`가 Facade 역할
- **v3 신규**: Phase 0 안전성 필터 (VirusTotal), Phase 1 멀티모달 입력 (이미지·PDF vision OCR), Fine-tuning 웹 UI + 자동 swap.

## 개발 실행 명령

### Python 백엔드

```bash
pip install -r requirements.txt
pip install pypdfium2                          # v3 — PDF 렌더 (필수)
pip install -r training/requirements-train.txt  # 학습할 때만
uvicorn api_server:app --reload
```

### Next.js 프론트엔드

```bash
cd apps/web
npm install
cp .env.example .env.local   # SCAMGUARDIAN_API_URL 설정
npm run dev
npm run lint
npm run build
```

### 전체 스택 한 번에 (로그 포함)

```bash
./scripts/start_stack.sh    # uvicorn + next dev + Tailscale Funnel을 nohup으로 실행
./scripts/watch_logs.sh     # 3개 로그 동시 tail
```

> `start_stack.sh`는 conda 환경(`CONDA_ENV`, 기본 `capstone`)을 사용합니다. conda가 없으면 `scripts/restart_stack.sh`를 사용하세요.
> Ollama는 더 이상 필수가 아닙니다 (LLM이 Claude API로 교체됨).

### CLI 분석 (파이프라인 직접)

```bash
python run_analysis.py "https://youtube.com/watch?v=..."
python run_analysis.py --text "투자 설명 텍스트"
python test_pipeline.py   # 통합 테스트
```

### 라벨링 데이터 배치 생성

```bash
# 내장 시드 샘플(23개) DB 저장
python scripts/batch_ingest.py --skip-verify

# 외부 텍스트 파일로 배치 실행 (줄마다 1개 샘플, # 주석 지원)
python scripts/batch_ingest.py --file samples.txt --skip-verify

# JSONL 파일 (text + metadata 포함)
python scripts/batch_ingest.py --jsonl data/processed/public_cases.jsonl --skip-verify

# DB 저장 없이 결과만 확인
python scripts/batch_ingest.py --dry-run
```

## 환경 변수 (`.env` 또는 `.env.local`)

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `SCAMGUARDIAN_API_URL` | Next.js → FastAPI 프록시 대상 | `http://127.0.0.1:8000` |
| `SCAMGUARDIAN_SQLITE_PATH` | SQLite DB 경로 | `.scamguardian/scamguardian.sqlite3` |
| `SCAMGUARDIAN_PERSIST_RUNS` | 분석 결과 DB 저장 여부 | `false` |
| `SCAMGUARDIAN_DATABASE_URL` | Postgres 연결 문자열 | (없으면 SQLite 사용) |
| `SERPER_API_KEY` | 교차 검증용 Google 검색 API | 필수 (검증 활성 시) |
| `ANTHROPIC_API_KEY` | LLM 보조 판정 + AI 초안 라벨링 + 컨텍스트 수집 챗봇 + 의도 분류 | **필수** |
| `ANTHROPIC_MODEL` | Claude 메인 분석 모델 | `claude-sonnet-4-6` |
| `ANTHROPIC_HAIKU_MODEL` | 컨텍스트 챗봇 + 의도 분류 모델 | `claude-haiku-4-5-20251001` |
| `SCAMGUARDIAN_PUBLIC_URL` | 결과 상세 페이지 베이스 URL (없으면 ngrok 자동 발견) | (없음) |
| `OPENAI_API_KEY` | OpenAI Whisper API 키 | 없으면 로컬 Whisper 사용 |
| `SCAMGUARDIAN_CORS_ORIGINS` | 허용 CORS 오리진 (콤마 구분) | `http://localhost:3000,...` |
| `SERPER_MAX_CONCURRENT` | Serper API 동시 호출 수 | `3` |
| `SERPER_BATCH_DELAY` | Serper 호출 간 딜레이 (초) | `0.2` |
| `VIRUSTOTAL_API_KEY` | **v3** — Phase 0 URL/파일 안전성 검사 | 없으면 Phase 0 skip |
| `VIRUSTOTAL_RPM` | VT 분당 호출 한도 | `4` (free tier) |
| `ANTHROPIC_VISION_MODEL` | **v3** — vision OCR 모델 (이미지/PDF) | `claude-sonnet-4-6` |
| `VISION_PDF_MAX_PAGES` | PDF 처리 시 최대 페이지 수 | `5` |
| `VISION_PDF_DPI` | PDF 페이지 렌더 DPI | `150` |
| `AIHUB_API_KEY` | AI Hub CLI 자동화 (`scripts/aihub.py`) | 학습 데이터 받을 때만 |

## 아키텍처

### 전체 데이터 흐름

```
┌─────────────────────────────────────────────────────────────────────┐
│  입력 경로                                                           │
│                                                                     │
│  카카오톡 챗봇  ──→  POST /webhook/kakao                            │
│  웹 브라우저   ──→  Next.js (/api/*) ──→  POST /api/analyze        │
│  CLI           ──→  python run_analysis.py                         │
│  배치 인제스트  ──→  python scripts/batch_ingest.py                 │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
                           ▼
              ScamGuardianPipeline.analyze()
              (pipeline/runner.py)
                           │
                  Phase 0: 안전성 (safety.py)  [v3]
                           │  VirusTotal — URL/파일 악성 검사
                           │  악성 확정 시 fast-path → 매우 위험 보고
                           │
                  Phase 1: STT / OCR (stt.py + vision.py)  [v3 vision]
                           │  음성·영상 → Whisper, 이미지·PDF → Claude vision
                           │
                  Phase 2: 분류 (classifier.py)
                           │
                  Phase 3: ─── 병렬 실행 (ThreadPoolExecutor) ───
                           │                │                │
                    LLM 통합 호출     엔티티 추출        RAG 검색
                  (llm_assessor.py)  (extractor.py)    (rag.py)
                    analyze_unified()  GLiNER            SBERT
                           │                │                │
                           └────────────────┴────────────────┘
                                          │
                  Phase 4: 교차 검증 (verifier.py, 내부 병렬)
                           │  Serper API × 상위 15 엔티티
                           │
                  Phase 5: 스코어링 (scorer.py) → ScamReport
                           │
                    ScamReport.to_dict()
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
    db/repository      카카오 포맷팅      JSON 응답
    (run 저장)     (kakao_formatter.py)  (웹/CLI)
```

### 파이프라인 단계 (`pipeline/runner.py`)

`ScamGuardianPipeline.analyze(source, skip_verification, use_llm, use_rag)` — **6 Phase (Phase 0~5)**:

```
Phase 0: VirusTotal 안전성 검사 (URL·파일만, v3)
Phase 1: STT / OCR  — Whisper(음성) | Claude vision(이미지·PDF, v3)
Phase 2: mDeBERTa 분류 (또는 fine-tuned task-specific, v3)
Phase 3: ┌ LLM 통합 호출 (analyze_unified) ┐  ← ThreadPoolExecutor 병렬
         ├ GLiNER 엔티티 추출               │
         └ RAG 유사 사례 검색               ┘
Phase 4: Serper 교차 검증 (내부 병렬, 세마포어 레이트 리미팅)
Phase 5: 스코어링
```

0. **안전성** (`safety.py`, v3): URL → VT URL 스캔, 파일 → SHA256 lookup → 미스 시 업로드. 4 req/min 토큰버킷. 악성 확정 시 fast-path: STT/분류 skip + `malware_detected` (80점) 또는 `phishing_url_confirmed` (75점) 단독 트리거 → "매우 위험" 직행.
1. **STT/OCR** (`stt.py` + `vision.py`): 텍스트 패스스루, YouTube URL → Whisper, 음성 파일 → Whisper, **이미지·PDF → Claude vision OCR + 시각 단서 통합** (v3). `stt.transcribe()` 가 확장자 보고 자동 라우팅.
2. **분류** (`classifier.py`): zero-shot NLI + 키워드 부스팅 또는 **fine-tuned multi-class** (v3 — `active_models.json` 에 활성 체크포인트 있으면 자동 swap).
3. **병렬 실행** (Phase 3): 분류 결과를 기반으로 아래 3개를 `ThreadPoolExecutor`로 동시 실행
   - **추출** (`extractor.py`): GLiNER(`taeminlee/gliner_ko` 또는 fine-tuned, v3)로 스캠 유형별 엔티티 추출
   - **LLM 통합** (`llm_assessor.py`): `analyze_unified()` — 스캠 유형 재판정 + 엔티티/플래그 제안을 **1회 API 호출**로 처리
   - **RAG** (`rag.py`): SBERT 임베딩으로 과거 사람 라벨 사례 검색 (use_rag일 때만)
4. **검증** (`verifier.py`): Serper API로 엔티티 교차검증. **엔티티별 병렬 검증** + 세마포어 레이트 리미팅. 검증 대상 상위 15개 (라벨당 최대 2개).
5. **스코어링** (`scorer.py`): 플래그 합산 → 위험 점수 / 레벨. `safety_result` 받아 자동 플래그 추가.

### pipeline/ 파일별 역할

| 파일 | 역할 | 핵심 함수/클래스 |
|------|------|----------------|
| `runner.py` | 전체 파이프라인 오케스트레이터 | `ScamGuardianPipeline.analyze(source, ..., precomputed_transcript, user_context)` |
| `safety.py` | **v3** Phase 0 — VirusTotal URL/파일 스캔 | `scan_url()`, `scan_file()`, `safety_check()` → `SafetyResult` |
| `vision.py` | **v3** Phase 1 — Claude vision OCR (이미지/PDF) | `transcribe(path)`, `transcribe_image()`, `transcribe_pdf()` → `VisionResult` |
| `stt.py` | 음성→텍스트 + **확장자 자동 라우팅** (v3 — vision 자동 호출) | `transcribe(source)` → `TranscriptResult` |
| `classifier.py` | 스캠 유형 분류 (zero-shot 또는 **fine-tuned**, v3) | `classify(text)` → `ClassificationResult` |
| `extractor.py` | GLiNER 엔티티 추출 (**path swap 자동**, v3) | `extract(text, scam_type)` → `list[Entity]` |
| `verifier.py` | Serper API 교차검증 | `verify(entities, scam_type)` → `list[VerificationResult]` |
| `rag.py` | 유사 사례 벡터 검색 | `retrieve_similar_runs(embedding, k)` |
| `llm_assessor.py` | Claude API 보조 판정 | `analyze_unified(text, scam_type, user_context)` → `UnifiedLLMResult` |
| `scorer.py` | 플래그 합산 + **safety 자동 플래그** (v3) | `score(verification_results, ..., safety_result)` → `ScamReport` |
| `active_models.py` | **v3** — `.scamguardian/active_models.json` reader (60s TTL 캐시) | `get_active_path(role)`, `invalidate()` |
| `config.py` | 스캠 유형·플래그·점수·라벨·근거 정의 | `SCORING_RULES`, `FLAG_LABELS_KO`, `FLAG_RATIONALE`, `RISK_LEVELS` |
| `kakao_formatter.py` | ScamReport → 카카오 응답 JSON (**IMAGE/PDF, safety 카드** v3) | `format_result()`, `format_question()`, `format_welcome()` |
| `context_chat.py` | 카카오 챗봇 컨텍스트 수집 + 의도 분류 | `next_turn()`, `classify_intent()`, `summarize_for_pipeline()` |
| `claude_labeler.py` | 라벨링 초안 자동 생성 | `generate_draft(transcript, ...)` |
| `eval.py` | 예측 vs 정답 라벨 비교 | `evaluate_annotated_runs(records)` |

### 스코어링 핵심 (`pipeline/config.py`)

- `SCORING_RULES`: 플래그 → 점수 델타 매핑
- `RISK_LEVELS`: 0–20 안전 / 21–40 주의 / 41–70 위험 / 71+ 매우 위험
- LLM 제안 플래그는 `LLM_FLAG_SCORE_RATIO`(기본 0.5) 비율로 **축소 반영** (맹신 방지)
- LLM 제안 엔티티는 `LLM_ENTITY_MERGE_THRESHOLD` 이상이면 병합, `source="llm"` 표기

### DB 계층 (`db/`)

- `repository.py`: `SCAMGUARDIAN_DATABASE_URL`이 있으면 Postgres, 없으면 SQLite로 라우팅
- `sqlite_repository.py`: 임베딩을 JSON 텍스트로 저장, 유사도는 L2 거리 전체 스캔 (느림)
- Postgres는 pgvector 벡터 컬럼 사용 (빠름)
- 스키마는 `repository.init_db()`에서 `CREATE TABLE IF NOT EXISTS`로 자동 생성
- `analysis_runs`에 `claimed_by` / `claimed_at` 컬럼 존재 (라벨링 큐 claim 시스템용, TTL 30분)

### Next.js API 프록시 (`apps/web/src/app/api/`)

- `_lib/backend.ts`: `proxyJsonRequest` / `proxyGet`으로 FastAPI에 전달
- 모든 Route Handler는 이 두 함수만 사용, 직접 비즈니스 로직 없음
- `SCAMGUARDIAN_API_URL` 환경변수가 없으면 `http://127.0.0.1:8000` 기본값

### 카카오톡 챗봇 웹훅 (`/webhook/kakao`)

카카오 오픈빌더 Skill 엔드포인트. **컨텍스트 수집 멀티턴 + 병렬 분석 + 1.5-pass refine** 흐름.

#### 입력 감지 + 의도 분류

`_kakao_detect_input()` → `(source, InputType)`: action.params 확인 → utterance URL → TEXT.

**TEXT 입력은 추가로 `context_chat.classify_intent()`로 의도 분류** (Claude Haiku, fast-path 우선):
- `GREETING` → format_welcome
- `HELP` → format_help
- `CONTENT` → 컨텍스트 수집 모드 시작 (긴 텍스트는 fast-path, LLM 호출 X)
- `ANALYZE_NO_CONTENT` → "분석할 내용 보여주세요" 응답
- `CHAT` → "어떤 일이세요? 보내주시면 살펴볼게요" 응답

#### 컨텍스트 수집 + 병렬 분석 (모든 입력 유형 공통)

```
사용자가 콘텐츠 보냄 (TEXT/URL/VIDEO/FILE)
   ├─ 1차 분석 백그라운드 시작 (TEXT 즉시 / URL/영상은 STT 후)
   └─ 첫 질문 즉답 (Claude 호출 없는 static Q1, 응답 ~50ms)
         "📩 받았어요! 🔍 분석 시작했어요. 그 동안 정보 좀 여쭤볼게요"

사용자 답변 ↔ 봇이 본문 단서 짚어가며 능동 질문 (Q2부터 Claude Haiku, 1~3s)
   - context_chat.next_turn(input_type, history, transcript_text) 호출
   - Claude는 본문 + 누적 대화 모두 보고 다음 질문 생성

[1차 분석 백그라운드에서 완료] — phase 는 collecting_context 유지, 사용자에게 알리지 않음
   - 사용자 다음 답변에 "💡 분석은 끝났어요. '결과확인'을 누르거나 '결과 알려줘' 라고 해주세요" 자동 부착 (1회만)

사용자가 결과 요청 (`결과확인` / `결과 알려줘` / `분석 다됐어?` 등 자연 표현 인식)
   → "🎉 분석 완료! 정보 반영해 정리 중" + refine 트리거 (LLM phase만 user_context와 재호출, ~5-10s)
   → phase 를 result_requested 로 잠금, 채팅 종료

[refine 완료]
사용자 결과확인 다시 누르면
   → 결과 카드 + "자세한 결과 보기" webLink 버튼 + 잡 정리
```

#### 잡 상태 (`_pending_jobs[user_id]`)

| 필드 | 의미 |
|------|------|
| `status` | `running` / `done` / `error` |
| `phase` | `collecting_context` (채팅 가능) / `result_requested` (정리 중) / `error` |
| `chat_history` | 봇/사용자 발화 시간순 (refine 의 user_context 소스) |
| `stt_done`, `stt_result` | STT 완료 + TranscriptResult |
| `analyzing_started` | 1차 분석 트리거됐는지 |
| `result_ready_announced` | 첫 알림(🎉 완료) 한 번 됐는지 |
| `done_notice_sent` | 채팅 중 "분석 끝남" 안내 한 번 부착했는지 |
| `refine_started`, `refined` | 최종 합본 단계 |
| `result`, `user_context` | 최종 산출물 |

`_jobs_lock` (threading.Lock) 으로 다중 사용자 동시 접속 race 방지. 사용자별 `userRequest.user.id` 키로 격리.

#### 응답 포맷 (`kakao_formatter.py`)

핵심 포맷터:
- `format_welcome()`: 첫 인사 ("안녕하세요! 어떤 일로 오셨어요?")
- `format_help()`: 사용법 안내
- `format_question(question, is_first_turn, input_type)`: 챗봇 질문 (intro + 본문)
- `format_ask_for_content(reason)`: ANALYZE_NO_CONTENT/CHAT 응답
- `format_result(report, input_type, user_context, result_url)`: 최종 결과 카드 + webLink
- `format_result_ready_announce(has_refine)`: 🎉 완료 알림
- `format_refining_in_progress()`: 정리 중 폴링 응답
- `format_reset(had_active_job)`: 분석 초기화 응답
- `format_busy()`: 진행 중인데 새 영상 보냈을 때 거절

**플래그는 모두 한국어 라벨**로 표시: `flag_label_ko()` (FLAG_LABELS_KO 27종 매핑).

**모든 응답에 동일 퀵 리플라이 두 개**: `사용법` / `분석 초기화`.

#### 에러 처리 시스템

`ErrorCode` enum(11종)으로 구조화된 에러 메시지:

| 코드 | 상황 |
|------|------|
| `API_CREDIT` | API 크레딧/쿼터 소진 |
| `SERVER_DOWN` | 서버 연결 불가 |
| `STT_FAIL` | Whisper/음성 인식 실패 |
| `TIMEOUT` | 처리 시간 초과 |
| `LLM_UNAVAILABLE` | Ollama/LLM 메모리 부족 등 |
| `CALLBACK_REQUIRED` | URL/파일인데 콜백 미설정 |
| `FILE_TOO_LARGE` | 100MB 초과 |
| `EMPTY_INPUT` | 빈 입력 |
| `INVALID_URL` | 유효하지 않은 URL |
| `PARSE_ERROR` | 요청 JSON 파싱 실패 |
| `UNKNOWN` | 기타 |

`_classify_error(exc)` 함수가 예외 메시지를 분석하여 적절한 `ErrorCode`로 자동 매핑.

#### 카카오 오픈빌더 설정 필수사항

- 스킬 블록에서 **"콜백 사용"** 체크 → `callbackUrl`이 페이로드에 포함돼야 영상 분석이 안정적
- 콜백 기능은 **카카오 관리자센터 → 챗봇 > 설정 > AI 챗봇 관리에서 별도 신청 후 승인** 필요
- 파일 업로드를 받으려면 블록에 **파일 타입 파라미터** 추가 (`video`, `file`, `video_url` 등)
- 스킬 서버 주소: Tailscale Funnel (`https://scamguardian.tail7e5dfc.ts.net/webhook/kakao`) 또는 ngrok 터널 사용
- **참고**: 카카오 오픈빌더에서 Tailscale `.ts.net` 도메인 접속이 불안정할 수 있음. ngrok 권장: `~/bin/ngrok http 3100`

### 결과 상세 페이지 (공개) + 토큰 (`/result/[token]`)

카카오 카드의 "자세한 결과 보기" 버튼 → 1시간 유효 토큰 기반 공개 페이지.

- 토큰 발급: `_issue_result_token()` (api_server.py) — `secrets.token_urlsafe(16)`, 메모리 저장 (`_result_tokens`)
- TTL: `_RESULT_TOKEN_TTL = 3600` (1시간)
- 공개 URL 베이스: `_get_public_base_url()` — env(`SCAMGUARDIAN_PUBLIC_URL`) 우선, 없으면 ngrok 로컬 API(`127.0.0.1:4040`) 자동 발견 (60초 캐시)
- 백엔드 엔드포인트: `GET /api/result/{token}` → result + user_context + chat_history + flag_rationale + expires_at
- 프론트: `apps/web/src/app/result/[token]/page.tsx` — Tailwind, 서버 컴포넌트
- 섹션: 위험도 배지 / AI 요약 / 사용자 제공 정보(fuchsia 강조) / 점수 산정 방식(합산식 + 등급 테이블 + 플래그별 근거·출처) / 발동 플래그 상세 / 추출 엔티티 / 입력 본문(접기) / 챗봇 대화 전체(접기) / 만료 안내

### 플래그 점수 정당성 (`pipeline/config.py:FLAG_RATIONALE`)

각 플래그 점수의 근거 + 출처 매핑 (27종). 결과 페이지에서 "왜 이 점수?" 답변용.

예:
- `abnormal_return_rate` → "연 20% 이상 수익 보장은 자본시장법상 불법 권유 신호" / 금융감독원 유사수신 감독사례집
- `urgent_transfer_demand` → "즉각 송금 요구는 보이스피싱 1순위 패턴" / 경찰청 사이버수사국 통계
- `fake_government_agency` → "공공기관은 전화·문자로 자금 이체 요구 절대 안 함. 100% 사기" / 검찰청·경찰청·금감원 합동 가이드

### 어드민 라벨링 흐름

```
/admin (큐 리스트)
  ├─ GET /api/admin/runs/list      미완료·진행중·완료 필터링, claimed_by 표시
  ├─ POST /api/admin/runs/{id}/claim  검수자 이름 (미입력 시 "Admin" 기본)
  └─ GET /api/admin/metrics        per_labeler 통계 + needs_review 목록

/admin/[runId] (에디터)
  ├─ GET /api/admin/runs/{id}      run 상세 + metadata + 기존 annotation
  ├─ POST /api/admin/runs/{id}/ai-draft   Claude API로 라벨링 초안 생성
  └─ POST /api/admin/runs/{id}/annotations  정답 upsert (labeler 미입력 시 "Admin")
```

- `AdminRunEditor.tsx`: 예측값을 초기값으로 표시, 정답이 있으면 덮어쓰기
- AI 초안은 fuchsia 섹션에 표시 → "초안 전체 적용" 버튼으로 폼에 덮어쓰기
- 저장된 엔티티/플래그에 `source: "ai-draft"` 태깅
- **풀 컨텍스트 노출** (라벨링 정확도 ↑):
  - `metadata.user_context.qa_pairs` — 사용자가 챗봇과 나눈 Q&A 페어 (fuchsia 섹션)
  - `metadata.chat_history` — 봇/사용자 발화 시간순 전체 (펼치기/접기)
  - 카카오 결과 토큰 발급/refine 완료 시점에 `repository.merge_run_metadata()` 로 DB 보존

### 라벨링 품질 관리 (`pipeline/eval.py`)

`evaluate_annotated_runs(records)` 반환값:

- `classification_accuracy`: 전체 분류 정확도
- `entity_micro` / `flag_micro`: precision / recall / F1 (micro 평균)
- `per_labeler`: 검수자별 완료 수 / 분류 정확도 / 엔티티 F1
- `needs_review`: 분류 불일치 또는 엔티티·플래그 recall 낮은 run 목록 (재검토 권장)

### 스캠 유형 확장

- 기본값: `pipeline/config.py`의 `DEFAULT_SCAM_TYPES` (12종), `DEFAULT_LABEL_SETS`
- 런타임 확장: 어드민에서 추가 → `scam_type_catalog` 테이블 → `get_runtime_scam_taxonomy()`로 즉시 반영

## 분석 결과 스키마 (프론트-백 계약)

`ScamReport.to_dict()` 핵심 필드:

```json
{
  "scam_type": "투자 사기",
  "classification_confidence": 0.85,
  "is_uncertain": false,
  "entities": [{"label": "수익 퍼센트", "text": "연 30%", "score": 0.9, "source": "gliner"}],
  "triggered_flags": [{"flag": "abnormal_return_rate", "score_delta": 15, "evidence": {}}],
  "total_score": 45,
  "risk_level": "위험",
  "risk_description": "다수의 스캠 징후가 확인됨",
  "transcript_text": "...",
  "analysis_run_id": "uuid (DB 저장 시)"
}
```

## 배포

- **Frontend**: Vercel (Root Directory: `apps/web`)
- **Backend**: Render (`uvicorn api_server:app --host 0.0.0.0 --port $PORT`)
- 세부 설정: `DEPLOY.md`, `render.yaml`

## v3 신규 시스템 (2026-04-29)

### Phase 0 안전성 필터 (`pipeline/safety.py`)

VirusTotal API v3 클라이언트. URL/파일을 분석 전에 자동 검사.

- **SHA256 lookup 우선** — 캐시 히트 시 즉답, 미스면 업로드 + `/analyses/{id}` 폴링(최대 30s)
- **레이트 리미팅** — 단순 토큰 버킷 (분당 4건 free tier 한도)
- **공통 분류**: `ThreatLevel.{SAFE, UNKNOWN, SUSPICIOUS, MALICIOUS}` — malicious >= 3 엔진 / suspicious 2+ / 그 외 safe
- **새 플래그**: `malware_detected`(80), `phishing_url_confirmed`(75), `suspicious_file_signal`(25), `suspicious_url_signal`(25)
- **fast-path** (runner.py): 악성 파일 확정 시 STT/분류 skip + 30점이 아닌 **80점**으로 "매우 위험" 직행

### Phase 1 vision OCR (`pipeline/vision.py`)

이미지·PDF → 한국어 본문(텍스트 + 시각 단서). Claude vision (sonnet-4-6).

- 입력: `.jpg .jpeg .png .webp .gif .bmp .pdf`
- PDF 는 `pypdfium2` 로 페이지별 PNG 렌더 (기본 5페이지, 150 DPI)
- 이미지 다운스케일: long edge 1568px (Anthropic 권장)
- 시스템 프롬프트가 OCR + 시각 단서 통합 본문을 한 번에 출력하도록 강제
- `stt.transcribe()` 가 확장자 보고 vision 자동 라우팅

### Fine-tuning 시스템 (`training/`)

라벨 데이터로 `pipeline/classifier.py` (mDeBERTa) + `pipeline/extractor.py` (GLiNER) 도메인 특화 학습.

| 파일 | 역할 |
|------|------|
| `training/data.py` | DB(human_annotations) + 외부 JSONL → ClassifierExample/GlinerExample. char→token span 자동 변환, stratified split |
| `training/train_classifier.py` | mDeBERTa SFT + LoRA 옵션. HF Trainer + `MetricsEmitCallback` (log/eval/epoch 마다 metrics.jsonl emit) |
| `training/train_gliner.py` | GLiNER fine-tune. fit() 없는 버전은 JSON 만 저장 + 외부 trainer 안내 |
| `training/sessions.py` | subprocess 세션 관리자. `.scamguardian/training_sessions/{id}/{status.json,metrics.jsonl,train.log}` 파일 기반 |
| `training/requirements-train.txt` | peft / datasets / evaluate / accelerate / seqeval / sklearn |

웹 UI: `/admin/training` — 데이터 통계 + 세션 시작 폼 + 진행률 그래프(recharts) + 로그 tail + 활성화 버튼.
설명 페이지: `/admin/training/about` — 모델 역할 + 파이프라인 위치 + before/after 표 + 권장 학습 분량.

### 모델 swap (`pipeline/active_models.py`)

`/admin/training` 의 "파이프라인 적용" 버튼 → `.scamguardian/active_models.json` 갱신.
- 60초 TTL 캐시. 활성화 직후 `invalidate()` 호출되어 즉시 반영.
- `classifier.py` — 활성 경로 있으면 task-specific multi-class pipeline, 없으면 zero-shot fallback.
- `extractor.py` — GLiNER path swap. 활성 경로 변경되면 모델 재로드.
- 경로 무효 시 base 모델로 자동 fallback (안전장치).

### AI Hub CLI 자동화 (`scripts/aihub.py`)

`aihubshell` 래퍼 — 데이터셋 검색·라벨링 zip 만 골라 다운로드.

```bash
export AIHUB_API_KEY=...
python scripts/aihub.py list-datasets --grep 콜센터,상담,민원
python scripts/aihub.py list-files 98
python scripts/aihub.py download-labels 98 --domain 금융 --dry-run
```

신청·승인은 사이트에서만 가능 (CLI 자동화 불가). 승인 후 라벨링 zip 만 골라받아 원천 음성 GB 단위 다운로드 회피.

### 카카오 webhook 멀티모달 (v3)

`_kakao_detect_input` 가 action_params 의 `image / picture / photo / pdf / document / video / file` 키 + URL 확장자 (`.jpg/.png/.pdf` 등) 보고 자동 분류:
- IMAGE / PDF 면 webhook 핸들러가 `_kakao_materialize_url()` 로 카카오 CDN URL → `.scamguardian/uploads/kakao/{uuid}.{ext}` 다운로드 → 로컬 경로로 source 교체
- 그 후 기존 `_kakao_start_context_collection()` 흐름 그대로 — `stt.transcribe()` 가 vision 자동 라우팅
- `format_question` / `format_analyzing` / `format_queued` 모두 IMAGE/PDF 메시지 추가

## 다음 작업 (TODO)

(2026-04-29 정리 — v3 작업 거의 마무리)

### 가능한 후속

1. **AI Hub 데이터 도착 → ingest 스크립트**: `scripts/ingest_aihub.py` — 데이터셋별 라벨 JSON 스키마 보고 우리 JSONL 포맷(text + label/entities) 으로 변환. 실물 데이터 받은 다음에 작성.
2. **카카오 webhook 실제 이미지·PDF 테스트**: 합성 포스터 말고 진짜 사기 광고/캡쳐로 vision OCR 정확도 검증.
3. **active_models 모델 메타 표시**: `/admin/training` 활성 모델 카드에 학습 데이터 양, 마지막 평가 F1 함께 노출.
4. **GLiNER 학습 보강**: 현재 fit() API 없는 버전 fallback 만 동작. 외부 trainer (urchade/GLiNER 공식 가이드) 통합.
