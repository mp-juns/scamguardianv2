# ScamGuardian v2 — AI Agent 인수인계 (Handoff)

이 문서는 **다음 AI/개발자가 “토큰 아끼고” 바로 이어서 작업**할 수 있도록, 프로젝트의 **파일별 역할**, **스크립트/모듈 연결 구조**, **데이터 모델**, **실행/배포 흐름**, **최근 변경 타임라인(커밋 기반)**을 한 파일에 압축 정리한 인수인계 문서입니다.

---

## TL;DR (30초 온보딩)

- **프론트**: Next.js App Router (`apps/web`)  
  - 브라우저는 **항상** `apps/web/src/app/api/*`(Route Handler)를 호출
  - Route Handler가 `SCAMGUARDIAN_API_URL`로 **Python FastAPI**에 프록시
- **백엔드**: FastAPI (`api_server.py`)  
  - `/api/analyze`, `/api/analyze-upload`로 파이프라인 실행
  - `/api/admin/*`로 라벨링/메트릭/스캠유형(커스텀) 관리
- **파이프라인**: `pipeline/runner.py`(오케스트레이터) → `stt/classifier/extractor/verifier/(rag)/(llm_assessor)/scorer`
- **DB**: `db/`에서 **Postgres(+pgvector)** 또는 **SQLite** 선택  
  - 로컬 빠른 라벨링은 SQLite 권장: `SCAMGUARDIAN_SQLITE_PATH=.scamguardian/scamguardian.sqlite3`
  - 저장 활성화는 `SCAMGUARDIAN_PERSIST_RUNS=true` 필요

---

## 최근 변경 타임라인 (git log 기반)

> 실제 “언제 뭘 했는지”는 커밋 메시지 기준으로만 요약합니다(세부 diff는 `git show <hash>`로 확인).

- **2026-03-31** `bb41750`: 웹으로 기능 통합 및 서버 라우팅  
  - Next.js 프록시(`/api/*`) + FastAPI API + Admin 라벨링 흐름이 합쳐진 시점
- **2026-03-25** `d43d729`: 테스트 3 수정 사항없음
- **2026-03-24** `c4cb3b7`: debug mode 추가(STT 다운로드/전사/단계 추적)
- **2026-03-24** `43b1ae4`: pipeline 코드 추가(분류/추출/검증/스코어링 등)
- **2026-03-24** `1504d98`: init / `d0f6be8`: Initial commit

---

## 현재 워킹디렉터리 주의사항(중요)

- `.scamguardian/scamguardian.sqlite3`가 **수정됨**(라벨링/분석 run 저장 결과일 가능성이 큼)  
  - 일반적으로 DB 파일은 커밋 대상이 아닙니다(데이터/개인정보 포함 가능)
- `apps/web`가 “modified content, untracked content”로 표시됨  
  - `apps/web` 내부에 아직 커밋되지 않은 파일(예: `.env.local`, 빌드 산출물, 실험 파일 등)이 있을 수 있음

---

## 아키텍처 개요(연결 구조)

### 전체 데이터 흐름

1) **브라우저 UI**(Next.js 페이지)  
2) **Next.js Route Handler**(`/api/*`) → `SCAMGUARDIAN_API_URL`로 프록시  
3) **FastAPI**(`api_server.py`)가 요청을 받아 `ScamGuardianPipeline` 실행  
4) 결과를 JSON으로 반환 + (옵션) DB에 run 저장 + 임베딩 저장  
5) `/admin`에서 저장된 run을 사람이 라벨링하고 `/api/admin/metrics`로 품질 지표를 확인

### 텍스트 다이어그램

```
[Browser]
  ├─ / (apps/web/src/app/page.tsx)
  │    └─ POST /api/analyze or /api/analyze-upload
  │         └─ Next route handler -> proxy -> FastAPI
  └─ /admin (apps/web/src/app/admin/page.tsx)
       ├─ GET /api/admin/runs/next  -> FastAPI -> DB
       ├─ GET /api/admin/metrics   -> FastAPI -> DB -> pipeline/eval.py
       ├─ GET/POST /api/admin/scam-types -> FastAPI -> DB -> pipeline/config.py taxonomy 반영
       └─ /admin/[runId] (AdminRunEditor) -> 라벨 저장 POST

[FastAPI api_server.py]
  /api/analyze, /api/analyze-upload
    └─ pipeline/runner.py ScamGuardianPipeline.analyze()
         STT -> 분류 -> 추출 -> (검증) -> (RAG) -> (LLM) -> 스코어링
    └─ (옵션) db/repository.py 저장 + pipeline/rag.py 임베딩 저장
```

---

## 폴더/파일 역할 (핵심만)

### 루트

- **`api_server.py`**: FastAPI 서버(웹에서 파이프라인 호출 + admin API 제공)
- **`run_analysis.py`**: CLI 분석 진입점(YouTube/파일/텍스트)
- **`README.md`**: 로컬 실행/환경변수/라벨링/배포 방향 요약
- **`DEPLOY.md`**, **`render.yaml`**: Render/Vercel 배포 가이드/설정
- **`test_pipeline.py`**: 파이프라인 통합 테스트(로컬)
- **`.scamguardian/`**: 로컬 실행 산출물(로그/업로드/ollama 모델/SQLite 등) 저장소

### `apps/web` (Next.js)

- **`src/app/page.tsx`**: 메인 분석 UI  
  - 텍스트/URL 분석 + 파일 업로드(STT) 지원  
  - 옵션: `skipVerification`, `useLlm`, `useRag`(RAG는 `useLlm` 켜면 자동 동반)
- **`src/app/admin/page.tsx`**: 어드민 대시보드  
  - 다음 라벨링 대상(`/api/admin/runs/next`)  
  - 메트릭(`/api/admin/metrics`)  
  - 커스텀 스캠 유형 추가(`/api/admin/scam-types`)
- **`src/app/admin/[runId]/AdminRunEditor.tsx`**: 단일 run 라벨 편집 UI  
  - 예측값/원본 transcript 표시 + 사람 정답 라벨 저장
- **`src/app/api/_lib/backend.ts`**: 프록시 공통 로직  
  - `SCAMGUARDIAN_API_URL` 기본값 `http://127.0.0.1:8000`
- **`src/app/api/*/route.ts`**: 각 엔드포인트 프록시(Route Handler)

### `pipeline/` (Python)

- **`runner.py`**: 오케스트레이션(단계 실행, step log, 옵션에 따라 RAG/LLM 포함)
- **`stt.py`**: STT(Whisper). YouTube/파일/텍스트 처리
- **`classifier.py`**: zero-shot 분류(NLI + 키워드 부스팅)
- **`extractor.py`**: 엔티티 추출(GLiNER 우선, 환경에 따라 fallback)
- **`verifier.py`**: Serper API 검색 기반 교차 검증(플래그 발동 근거 생성)
- **`scorer.py`**: 최종 위험 점수/레벨 산출(규칙 기반 + LLM 플래그는 축소 반영)
- **`rag.py`**: SBERT 임베딩 생성 + DB에서 유사(사람 라벨) 사례 검색
- **`llm_assessor.py`**: Ollama LLM 보조 판정(추가 엔티티/플래그 제안)
- **`eval.py`**: 사람이 라벨한 정답과 예측을 비교해 메트릭 산출(`/api/admin/metrics`)
- **`config.py`**: 중앙 설정(스캠 유형/레이블/스코어링 룰/환경변수)

### `db/` (저장소 계층)

- **`repository.py`**: Postgres(+pgvector) 또는 SQLite로 라우팅하는 Facade  
  - 스키마 자동 생성(`CREATE TABLE IF NOT EXISTS`)
- **`sqlite_repository.py`**: SQLite 구현  
  - 임베딩은 JSON 텍스트로 저장하고, 유사도는 L2 거리로 계산(fallback)

---

## API 계약(프론트가 기대하는 형태)

### 분석

- **브라우저 → Next**: `POST /api/analyze`(JSON) 또는 `POST /api/analyze-upload`(multipart)
- **Next → Python**: 동일 path로 프록시

분석 결과(`pipeline/scorer.py`의 `ScamReport.to_dict()` 기반) 핵심 필드:

- `scam_type`, `classification_confidence`, `is_uncertain`
- `entities[]` (label/text/score/start/end/source 등)
- `triggered_flags[]` (flag/description/score_delta/evidence/source)
- `total_score`, `risk_level`, `risk_description`
- `verification_count`
- `llm_assessment`(옵션), `rag_context`(옵션)

추가로 FastAPI는 프론트 표시용으로:
- `transcript_text`(전체 전사)  
- `analysis_run_id`(DB 저장 시 run id)

### 어드민(라벨링)

- `GET /api/admin/runs/next`  
  - 사람이 라벨하지 않은 가장 오래된 run 1개 반환(없으면 null)
- `GET /api/admin/runs/{runId}`  
  - `run`(예측/원본) + `annotation`(정답, 있으면) + `options`(스캠유형/레이블/플래그 목록)
- `POST /api/admin/runs/{runId}/annotations`  
  - 정답 라벨 upsert
- `GET /api/admin/metrics`  
  - 라벨된 샘플 기준 성능 지표
- `GET/POST /api/admin/scam-types`  
  - 커스텀 스캠 유형(이름/설명/레이블) 추가/조회

---

## 라벨링 데이터 모델(프론트/백엔드/DB가 공유하는 의미)

### “예측” vs “정답”

- **예측**은 `analysis_runs`에 저장:
  - `classification_scanner`, `entities_predicted`, `triggered_flags_predicted`, `total_score_predicted`, `risk_level_predicted`
- **정답**은 `human_annotations`에 저장(1:1):
  - `scam_type_gt`, `entities_gt`, `triggered_flags_gt`, `transcript_corrected_text`, `stt_quality`, `notes`

### AdminRunEditor의 핵심 UX/로직

- 초기 로딩 시:
  - 정답(annotation)이 있으면 정답을 먼저 폼에 채움
  - 정답이 없으면 예측(run)을 폼에 채워서 “수정/검수”하게 함
- 엔티티:
  - `enabled` 체크로 포함/제외
  - 레이블 옵션은 `options.label_sets[scamType]` 기반(스캠 유형별 레이블 세트)
- 플래그:
  - `options.flags`(= `SCORING_RULES`의 키 목록) 기반으로 선택
  - `evidence`는 UI에서는 문자열 1개(서버에서는 dict 형태로 저장)

---

## 점수/리스크 산정 규칙(핵심)

### 규칙 기반(기본)

- `pipeline/config.py`의 `SCORING_RULES`: `flag -> 점수 델타`
- `pipeline/scorer.py`는 `verification_results` 중 `triggered=True`인 flag를 중복 없이 합산
- 최종 위험 레벨은 `get_risk_level(total_score)`:
  - 0~20: 안전
  - 21~40: 주의
  - 41~70: 위험
  - 71+: 매우 위험

### LLM 보조 반영(옵션)

- LLM이 제안한 플래그는 **그대로 반영하지 않음**
  - `LLM_FLAG_SCORE_THRESHOLD` 이상일 때만
  - `LLM_FLAG_SCORE_RATIO` 비율로 **축소 반영**(기본 0.5)
- LLM 제안 엔티티는 `LLM_ENTITY_MERGE_THRESHOLD` 이상이면 병합되며 `source="llm"`로 표기

---

## RAG(유사 사례) 구조

- 목적: **“사람이 정답 확정한 과거 사례”**를 찾아 LLM 프롬프트에 참고로 넣기
- 임베딩: `pipeline/rag.py`에서 SentenceTransformer로 384차원 임베딩 생성(정규화)
  - Postgres(+pgvector): vector 컬럼에 저장/검색
  - SQLite: JSON 텍스트 저장 + 전체 스캔 L2 거리로 fallback 검색(느리지만 동작)
- RAG는 `use_llm=true`일 때만 의미가 있으며, 실제 실행도 `use_llm && use_rag`일 때만 켜짐(`runner.py`의 `effective_use_rag`)

---

## 로컬 실행(개발) — 가장 빠른 루트

### A) 최소: 백엔드 + 웹(직접)

1) Python API

```bash
pip install -r requirements.txt
uvicorn api_server:app --reload
```

2) Web

```bash
cd apps/web
npm install
cp .env.example .env.local
npm run dev
```

### B) 라벨링/저장까지: SQLite 모드 권장

```bash
export SCAMGUARDIAN_SQLITE_PATH=.scamguardian/scamguardian.sqlite3
export SCAMGUARDIAN_PERSIST_RUNS=true
```

### C) 스택 한 번에(로그 포함)

- `scripts/start_stack.sh`: Ollama + uvicorn + next dev를 nohup으로 실행하고 `.scamguardian/logs/*`에 기록  
- `scripts/watch_logs.sh`: 3개 로그를 동시에 tail

```bash
./scripts/start_stack.sh
./scripts/watch_logs.sh
```

> `start_stack.sh`는 conda env(`CONDA_ENV`, 기본 `capstone`)에서 백엔드를 띄우는 변형이므로, 로컬 환경에 conda가 없다면 `scripts/restart_stack.sh`(uvicorn 직접) 쪽이 더 맞을 수 있습니다.

---

## 배포

- **Frontend**: Vercel (Root Directory: `apps/web`)
  - env: `SCAMGUARDIAN_API_URL=https://<your-api>`
- **Backend**: Render (Start: `uvicorn api_server:app --host 0.0.0.0 --port $PORT`)
  - env: `SERPER_API_KEY`, `SCAMGUARDIAN_CORS_ORIGINS`, (옵션) DB 관련 환경변수

세부는 `DEPLOY.md`, `render.yaml` 참고.

---

## 환경변수(중요만)

### Backend(FastAPI / pipeline)

- **검색 검증(Serper)**: `SERPER_API_KEY`
- **CORS**: `SCAMGUARDIAN_CORS_ORIGINS` (comma-separated)
- **DB**
  - Postgres: `SCAMGUARDIAN_DATABASE_URL`
  - SQLite: `SCAMGUARDIAN_SQLITE_PATH`
  - 저장 on/off: `SCAMGUARDIAN_PERSIST_RUNS=true|false`
- **RAG**
  - `SCAMGUARDIAN_RAG_TOP_K`
  - `SCAMGUARDIAN_RAG_MAX_CASES_IN_PROMPT`
- **Ollama**
  - `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS` 등(`pipeline/config.py` 참고)

### Frontend(Next.js)

- `SCAMGUARDIAN_API_URL` (프록시 대상 Python API)

---

## “다음 작업자”가 흔히 하는 작업 포인트

- **스캠 유형/레이블 확장**
  - 기본값: `pipeline/config.py`의 `DEFAULT_SCAM_TYPES`, `DEFAULT_LABEL_SETS`
  - 런타임 확장: 어드민에서 커스텀 스캠유형 추가 → DB의 `scam_type_catalog` → `get_runtime_scam_taxonomy()`로 즉시 반영
- **스코어링 튜닝**
  - 플래그 가중치: `SCORING_RULES`
  - 리스크 구간: `RISK_LEVELS`
  - LLM 반영 강도: `LLM_FLAG_SCORE_THRESHOLD`, `LLM_FLAG_SCORE_RATIO`, `LLM_ENTITY_MERGE_THRESHOLD`
- **라벨링 UX 개선**
  - `apps/web/src/app/admin/[runId]/AdminRunEditor.tsx`가 단일 진실 소스
  - “예측값을 초기값으로, 정답이 있으면 덮어쓰기” 구조
- **성능/비용**
  - SQLite RAG fallback은 전체 스캔이라 느려질 수 있음 → pgvector 권장
  - Serper 검증은 네트워크 비용/지연이 큼 → 디폴트 `skip_verification`이 true로 설계됨

---

## 레포 탐색 빠른 링크(파일 경로)

- `api_server.py`
- `run_analysis.py`
- `pipeline/runner.py`
- `pipeline/scorer.py`
- `pipeline/config.py`
- `pipeline/rag.py`
- `pipeline/llm_assessor.py`
- `db/repository.py`
- `db/sqlite_repository.py`
- `apps/web/src/app/page.tsx`
- `apps/web/src/app/api/_lib/backend.ts`
- `apps/web/src/app/admin/page.tsx`
- `apps/web/src/app/admin/[runId]/AdminRunEditor.tsx`
- `DEPLOY.md`

