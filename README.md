# ScamGuardian v2

한국어 음성·텍스트에서 전화사기를 탐지하는 AI 파이프라인 시스템.  
카카오톡 챗봇, 웹 어드민, CLI를 통해 사용 가능.

관리 주소 : https://scamguardian.tail7e5dfc.ts.net/admin
## 구성

| 경로 | 설명 |
|------|------|
| `pipeline/` | STT → 분류 → 추출 → 검증 → RAG → LLM → 스코어링 |
| `api_server.py` | FastAPI 백엔드 (카카오 웹훅 + REST API) |
| `apps/web/` | Next.js 16 웹 프론트엔드 (어드민 포함) |
| `db/` | SQLite / Postgres(pgvector) 저장소 계층 |
| `scripts/` | 스택 실행·배치 인제스트 스크립트 |

## 빠른 실행

### 전체 스택 (권장)

```bash
./scripts/restart_stack.sh   # uvicorn(8000) + next dev(3100) 동시 실행
./scripts/watch_logs.sh      # 로그 실시간 확인
```

### 개별 실행

```bash
# Python 백엔드
pip install -r requirements.txt
uvicorn api_server:app --reload

# Next.js 프론트엔드
cd apps/web
npm install
cp .env.example .env.local
npm run dev -- --port 3100
```

### CLI 분석

```bash
python run_analysis.py "https://youtube.com/watch?v=..."
python run_analysis.py --text "투자 설명 텍스트"
```

## 환경 변수 (`.env`)

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `SCAMGUARDIAN_API_URL` | Next.js → FastAPI 프록시 대상 | `http://127.0.0.1:8000` |
| `SCAMGUARDIAN_SQLITE_PATH` | SQLite DB 경로 | `.scamguardian/scamguardian.sqlite3` |
| `SCAMGUARDIAN_PERSIST_RUNS` | 분석 결과 DB 저장 여부 | `false` |
| `SCAMGUARDIAN_DATABASE_URL` | Postgres 연결 문자열 | (없으면 SQLite) |
| `ANTHROPIC_API_KEY` | LLM 보조 판정 + AI 라벨링 초안 | 필수 (`use_llm=true` 시) |
| `ANTHROPIC_MODEL` | Claude 모델 | `claude-sonnet-4-6` |
| `SERPER_API_KEY` | 교차 검증용 Google 검색 API | 필수 (검증 활성 시) |
| `OPENAI_API_KEY` | OpenAI Whisper API | 없으면 로컬 Whisper 사용 |
| `SCAMGUARDIAN_CORS_ORIGINS` | 허용 CORS 오리진 (콤마 구분) | `http://localhost:3000,...` |

## 파이프라인 단계

```
입력 (텍스트 / YouTube URL / 음성 파일)
  │
  ▼
STT (stt.py)               OpenAI Whisper API 또는 로컬 Whisper medium
  │
  ▼
분류 (classifier.py)        mDeBERTa NLI + 키워드 부스팅 → 사기 유형 판별
  │
  ▼
엔티티 추출 (extractor.py)   GLiNER(taeminlee/gliner_ko) → 유형별 엔티티
  │
  ▼
교차 검증 (verifier.py)     Serper API로 엔티티 진위 확인 (생략 가능)
  │
  ▼
RAG (rag.py)               SBERT 임베딩 → 과거 사람 라벨 사례 검색 (선택)
  │
  ▼
LLM 판정 (llm_assessor.py)  Claude API 보조 판정 (선택)
  │
  ▼
스코어링 (scorer.py)        플래그 합산 → 위험 점수 / 레벨
  │
  ▼
ScamReport (JSON)
```

## 사기 유형 (12종)

투자 사기 / 보이스피싱 / 대출 사기 / 메신저 피싱 / 로맨스 스캠 /  
취업·알바 사기 / 납치·협박형 / 스미싱 / 중고거래 사기 / 정상 외

어드민에서 커스텀 유형 추가 가능 → 즉시 파이프라인에 반영.

## 어드민 기능

| 경로 | 기능 |
|------|------|
| `/admin` | 라벨링 큐 — 검수자 claim, 상태 필터 (미완료/진행중/완료) |
| `/admin/[runId]` | 라벨 편집 — AI 초안 생성, 엔티티/플래그/사기유형 수정 |
| `/admin/stats` | DB 대시보드 — 사기 유형 분포, 위험도 분포, 일별 추이 |
| `/admin/browse` | DB 브라우저 — 텍스트 검색, 필터, 페이지네이션 |

### 라벨링 데이터 배치 생성

```bash
# 내장 시드 샘플(23개) DB 저장
python scripts/batch_ingest.py --skip-verify

# 외부 텍스트 파일 (줄마다 1개, # 주석 지원)
python scripts/batch_ingest.py --file samples.txt --skip-verify

# JSONL 파일 (text + metadata 포함)
python scripts/batch_ingest.py --jsonl data/processed/public_cases.jsonl --skip-verify

# 공공기관 공개 자료 수집 → JSONL 생성
python scripts/collect_public_cases.py --org all

# DB 저장 없이 결과만 확인
python scripts/batch_ingest.py --dry-run
```

## 카카오톡 챗봇 연동

카카오 오픈빌더 스킬 서버 URL: `https://scamguardian.tail7e5dfc.ts.net/webhook/kakao`

| 입력 | 처리 방식 |
|------|-----------|
| 텍스트 발화 | 즉시 동기 분석 |
| YouTube URL | 콜백으로 백그라운드 처리 (60초 내 결과) |
| 카카오 파일/영상 업로드 | URL 추출 후 콜백 처리 |

**오픈빌더 설정 필요사항**
- 스킬 블록에서 **콜백 사용** 체크
- 파일 업로드는 블록에 파일 타입 파라미터 추가

**로컬 외부 노출 (Tailscale Funnel)**

```bash
tailscale set --hostname scamguardian   # 호스트명 설정 (최초 1회)
tailscale funnel --bg 3100              # Next.js 포트 노출
```

웹 어드민도 같은 주소 `/admin` 경로로 외부 접근 가능.

## 품질 관리

`GET /api/admin/metrics` 반환값:

- `classification_accuracy`: 전체 분류 정확도
- `entity_micro` / `flag_micro`: precision / recall / F1
- `per_labeler`: 검수자별 완료 수, 분류 정확도, 엔티티 F1
- `needs_review`: 분류 불일치 또는 recall 낮은 run 목록

## 배포

| 구성요소 | 플랫폼 |
|----------|--------|
| 프론트엔드 | Vercel (Root Directory: `apps/web`) |
| Python API | Render (`uvicorn api_server:app --host 0.0.0.0 --port $PORT`) |

세부 설정: `DEPLOY.md`, `render.yaml`


## 공공기관 공개 사례 수집

공식 공개 페이지와 첨부 PDF에서 사례성 문구를 수집해 JSONL로 저장한 뒤, 기존 배치 인제스트로 DB에 적재할 수 있다.

지원 출처:
- `kisa`: 보호나라 스미싱 주의보/보안공지
- `police`: 전기통신금융사기 통합대응단 예보·경보/FAQ
- `fsc`: 금융위원회 보이스피싱 예방 자료/카드뉴스

```bash
# 1) 공식 공개 자료를 JSONL로 수집
python scripts/collect_public_cases.py --org all --max-items-per-source 50

# 2) 수집 결과를 기존 파이프라인으로 적재
python scripts/batch_ingest.py --jsonl data/processed/public_cases.jsonl --skip-verify
```

JSONL 각 줄 예시:

```json
{"text":"[CJ대한통운] 고객님 택배가 주소 불명...","metadata":{"source":"public_agency","source_org":"kisa","source_url":"https://...","doc_title":"...","published_at":"2026-02-10","channel":"security_notice","evidence_level":"official_public_case"}}
```

DB 브라우저 검색 API는 `source`, `source_org`, `channel` 필터를 지원한다.
