# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

ScamGuardian v2는 한국어 음성/텍스트에서 전화사기를 탐지하는 AI 파이프라인 시스템입니다.

- **Frontend**: Next.js 16 App Router (`apps/web/`) — Next 16은 기존 버전과 API·컨벤션이 다릅니다. `node_modules/next/dist/docs/`를 먼저 확인하세요.
- **Backend**: FastAPI (`api_server.py`) — Next.js Route Handler가 모든 API 요청을 이 서버로 프록시
- **Pipeline**: `pipeline/` — STT → 분류 → 추출 → 검증 → (RAG) → (LLM) → 스코어링 순서로 실행
- **DB**: Postgres(+pgvector) 또는 SQLite, `db/repository.py`가 Facade 역할

## 개발 실행 명령

### Python 백엔드

```bash
pip install -r requirements.txt
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
| `ANTHROPIC_API_KEY` | LLM 보조 판정 + AI 초안 라벨링에 사용 | **필수** (`use_llm=True` 시) |
| `ANTHROPIC_MODEL` | Claude 모델 | `claude-sonnet-4-6` |
| `OPENAI_API_KEY` | OpenAI Whisper API 키 | 없으면 로컬 Whisper 사용 |
| `SCAMGUARDIAN_CORS_ORIGINS` | 허용 CORS 오리진 (콤마 구분) | `http://localhost:3000,...` |

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
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
       STT              분류기           (결과)
    (stt.py)       (classifier.py)         │
          │                │               │
          └────────────────┘               │
                  텍스트                   │
                    │                      │
          ┌─────────▼──────────┐           │
          │  엔티티 추출        │           │
          │  (extractor.py)    │           │
          └─────────┬──────────┘           │
                    │                      │
          ┌─────────▼──────────┐           │
          │  교차 검증          │           │
          │  (verifier.py)     │           │
          │  Serper API 사용   │           │
          └─────────┬──────────┘           │
                    │                      │
          ┌─────────▼──────────┐           │
          │  RAG (선택)         │           │
          │  (rag.py)          │           │
          │  유사 사례 검색     │           │
          └─────────┬──────────┘           │
                    │                      │
          ┌─────────▼──────────┐           │
          │  LLM 보조 판정(선택) │          │
          │  (llm_assessor.py) │           │
          │  Claude API 사용   │           │
          └─────────┬──────────┘           │
                    │                      │
          ┌─────────▼──────────┐           │
          │  스코어링           │           │
          │  (scorer.py)       │           │
          │  → ScamReport      │           │
          └─────────┬──────────┘           │
                    └──────────────────────┘
                           │
                    ScamReport.to_dict()
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
    db/repository      카카오 포맷팅      JSON 응답
    (run 저장)     (kakao_formatter.py)  (웹/CLI)
```

### 파이프라인 단계 (`pipeline/runner.py`)

`ScamGuardianPipeline.analyze(source, skip_verification, use_llm, use_rag)`가 순서대로 실행:

1. **STT** (`stt.py`): YouTube URL / 파일 / 텍스트 → 텍스트. `OPENAI_API_KEY` 있으면 OpenAI Whisper API(빠름), 없으면 로컬 Whisper medium 사용. YouTube는 앞 5분만 mp3로 추출 (카카오 콜백 1분 제한 + OpenAI 25MB 제한 대응)
2. **분류** (`classifier.py`): mDeBERTa NLI + 키워드 부스팅으로 스캠 유형 판별
3. **추출** (`extractor.py`): GLiNER(`taeminlee/gliner_ko`)로 스캠 유형별 엔티티 추출
4. **검증** (`verifier.py`): Serper API로 엔티티 교차검증 (skip_verification=True로 생략 가능)
5. **RAG** (`rag.py`): SBERT 임베딩으로 과거 사람 라벨 사례 검색 (use_llm && use_rag일 때만)
6. **LLM** (`llm_assessor.py`): Claude API로 추가 엔티티/플래그 제안 (use_llm일 때만)
7. **스코어링** (`scorer.py`): 플래그 합산 → 위험 점수 / 레벨 산출

### pipeline/ 파일별 역할

| 파일 | 역할 | 핵심 함수/클래스 |
|------|------|----------------|
| `runner.py` | 전체 파이프라인 오케스트레이터 | `ScamGuardianPipeline.analyze()` |
| `stt.py` | 음성→텍스트 변환 | `transcribe(source)` → `TranscriptResult` |
| `classifier.py` | 스캠 유형 분류 | `classify(text)` → `ClassificationResult` |
| `extractor.py` | 엔티티 추출 | `extract(text, scam_type)` → `list[Entity]` |
| `verifier.py` | Serper API 교차검증 | `verify(entities, scam_type)` → `list[VerificationResult]` |
| `rag.py` | 유사 사례 벡터 검색 | `retrieve_similar_runs(embedding, k)` |
| `llm_assessor.py` | Claude API 보조 판정 | `assess(text, ...)` → `LLMAssessment` |
| `scorer.py` | 플래그 합산 → 점수/레벨 | `score(verification_results, ...)` → `ScamReport` |
| `config.py` | 스캠 유형·플래그·점수 규칙 정의 | `SCORING_RULES`, `RISK_LEVELS`, `get_runtime_scam_taxonomy()` |
| `kakao_formatter.py` | ScamReport → 카카오 챗봇 응답 JSON | `format_result(report, input_type)`, `format_error(code, detail)` |
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

카카오 오픈빌더 Skill 엔드포인트. 입력 유형을 자동 감지(`_kakao_detect_input()`)하여 분기 처리:

#### 입력 감지 로직

`_kakao_detect_input(utterance, action_params)` → `(source, InputType)`:

1. `action.params`에서 `video`/`file`/`video_url`/`attachment` 키 확인 → `VIDEO` 또는 `FILE`
2. utterance 전체가 URL → `URL`
3. utterance 안에 URL 포함 → `URL` (URL 부분 추출)
4. 그 외 → `TEXT`

#### 입력 유형별 처리

| 입력 유형 | callbackUrl 있음 | callbackUrl 없음 |
|-----------|------------------|-------------------|
| `TEXT` | 비동기 callback 분석 | 동기 분석 (4.5초 타임아웃) |
| `URL` | 비동기 callback (STT+분석) | 폴링 모드: 즉시 "분석 시작" 응답 후 백그라운드 실행 |
| `VIDEO`/`FILE` | 비동기 callback (STT+분석) | 폴링 모드: 즉시 "분석 시작" 응답 후 백그라운드 실행 |

#### 폴링 모드 흐름 (callbackUrl 없을 때)

1. 사용자가 URL/영상 전송 → 즉시 "분석 시작됨, '결과확인' 입력하세요" 응답
2. 서버에서 `_pending_jobs[user_id]`에 상태 저장하며 백그라운드 파이프라인 실행
3. 사용자가 `결과확인` 입력:
   - `running` → "아직 분석 중입니다" 응답 (quick reply로 재확인 유도)
   - `done` → 결과 카드 반환 후 job 삭제
   - `error` → 에러 메시지 반환 후 job 삭제
   - 없음 → "진행 중인 분석 없음" 안내
- `user_id`: `userRequest.user.id`로 사용자 식별 (없으면 CALLBACK_REQUIRED 에러 폴백)
- job TTL: 완료 후 10분(`_KAKAO_JOB_TTL`), 최대 대기 5분(`_KAKAO_POLL_TIMEOUT`)

#### 유형별 응답 포맷

`kakao_formatter.py`가 `InputType`에 따라 다른 카드를 생성:

- **TEXT**: `💬 텍스트 분석` — 스캠 유형, 플래그, 엔티티
- **URL**: `🔗 URL/영상 분석` — 위 항목 + 음성 전사(STT) 미리보기 (150자)
- **VIDEO**: `🎬 업로드 영상 분석` — 위 항목 + STT 미리보기
- **FILE**: `📎 파일 분석` — 위 항목 + STT 미리보기

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
- 스킬 서버 주소: `https://scamguardian.tail7e5dfc.ts.net/webhook/kakao`

### 어드민 라벨링 흐름

```
/admin (큐 리스트)
  ├─ GET /api/admin/runs/list      미완료·진행중·완료 필터링, claimed_by 표시
  ├─ POST /api/admin/runs/{id}/claim  검수자 이름으로 claim (30분 TTL, 충돌 시 409)
  └─ GET /api/admin/metrics        per_labeler 통계 + needs_review 목록

/admin/[runId] (에디터)
  ├─ GET /api/admin/runs/{id}      run 상세 + 기존 annotation
  ├─ POST /api/admin/runs/{id}/ai-draft   Claude API로 라벨링 초안 생성 (claude_labeler.py)
  └─ POST /api/admin/runs/{id}/annotations  정답 upsert
```

- `AdminRunEditor.tsx`: 예측값을 초기값으로 표시, 정답이 있으면 덮어쓰기
- AI 초안은 별도 fuchsia 섹션에 표시 → "초안 전체 적용" 버튼으로 폼에 덮어쓰기
- 저장된 엔티티/플래그에 `source: "ai-draft"` 태깅

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
