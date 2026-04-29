# ScamGuardian v3

한국어 음성·텍스트·이미지·PDF 에서 전화·메신저·문서 사기를 탐지하는 AI 파이프라인.
카카오톡 챗봇·웹 어드민·CLI 어떤 채널로 들어와도 같은 코어 분석 + 결과 응답.

관리 주소: <https://scamguardian.tail7e5dfc.ts.net/admin>

## v3 신규 (2026-04)

- **Phase 0 안전성 필터**: VirusTotal 으로 URL·파일을 분석 전에 자동 검사. 악성 파일이면 STT/분류 skip + `🚨 매우 위험` 즉시 보고.
- **Phase 1 멀티모달 입력**: 이미지(PNG/JPG/WEBP) 와 PDF 도 받음. Claude vision 한 번 호출로 OCR + 시각 단서(가짜 인증마크·과장 폰트·QR) 같이 추출 → 기존 파이프라인 그대로.
- **카카오 webhook image/PDF 라우팅**: 사진·캡쳐·문서 보내면 CDN 다운로드 → vision → 분석 → 결과 카드.
- **Fine-tuning 웹 UI**: `/admin/training` — 분류기·GLiNER 학습 세션을 백그라운드 subprocess 로 시작, recharts 로 loss/F1 실시간 그래프, 완료 후 한 클릭으로 파이프라인 swap.
- **모델 활성화 자동 swap**: 학습 끝나면 `.scamguardian/active_models.json` 갱신 → 다음 분석부터 fine-tuned 모델 사용. 경로 무효 시 base 모델로 자동 fallback.
- **점수 산정 방식 페이지** (`/methodology`): 합산식·등급·플래그별 정당성·인용 학술 출처(Cialdini, Whitty, Stajano & Wilson 등) 모두 공개.
- **Platform 레이어** (`/admin/platform`): API key 발급·revoke, RPM/월별 호출/월별 USD 3중 cap, 외부 API 비용(claude·openai·serper·vt) 실시간 ledger, request_log 기반 observability(p50/p95).
- **어뷰즈 가드**: 길이 cap·반복·gibberish 차단 + 짧은 메시지 누적 트래커. 카카오 user_id 별 3회 경고 후 1시간 자동 블록 + 채팅 강제 종료.
- **테스트** (pytest): 격리된 SQLite + 외부 API mock 0회로 46 passed (`pytest`).

## v3.5 신규 (2026-04-30)

- **Phase 0.5 URL 디토네이션** (`pipeline/sandbox.py`): VT 시그니처가 못 잡는 *zero-day 피싱*을 격리 Chromium 으로 직접 navigate 해서 잡음. 비밀번호 입력폼·민감 입력·자동 다운로드·도메인 클로킹·과도한 리디렉션 5종 자동 플래그 (+15 ~ +60).
- **Sandbox 서버 분리** (`sandbox_server/`): production 호스트와 *별도 VM/VPS* 에서 도는 FastAPI 디토네이션 서버. Bearer 토큰 인증, screenshot base64 inline 반환, stateless. 같은 호스트 격리(컨테이너 이스케이프 위험)에서 물리 분리(잃을 게 없는 VM)로 격상.
- **백엔드 자동 분기**: `SANDBOX_BACKEND=auto` — `SANDBOX_REMOTE_URL`+`SANDBOX_REMOTE_TOKEN` 둘 다 있으면 remote, 아니면 local Docker. dev/staging/prod 무코드 변경.
- **카카오 webhook 멀티모달 실전 검증**: 이미지가 utterance 필드에 CDN URL 박혀서 도착하는 것 확인 (action.params 비어있음). detector fallback (모든 키 훑어 URL 분류) 추가. APK/EXE/DMG 등 실행파일 URL 도 자동 분류해 VT 파일 스캔 강제.
- **PDF 한계 명시**: 카카오 챗봇 채널은 PDF 첨부를 클라이언트 단에서 차단 — 사용자 안내문 ("캡쳐 이미지 또는 클라우드 링크로 보내주세요") 으로 우회.
- **Whisper 비용 추적 버그 수정**: `record_openai_whisper()` 함수 정의만 있고 호출되지 않던 버그. 이제 어드민 비용 차트에 OpenAI provider 정상 노출.
- **어드민 비용 시각화**: `/admin/platform` 에 일별 USD 추이(area chart) + 프로바이더 비중(horizontal bar) 추가.
- **어드민 어뷰즈 차단 관리 UI**: `/admin/platform` 🛑 섹션 — 차단된 user_id 목록·남은 시간·"차단 해제" 버튼.
- **결과확인 명령어 어뷰즈 우회 버그 수정**: "결과확인"(4자) 같은 시스템 명령어가 짧은 메시지 트래커에 위반으로 잘못 카운트되던 문제 수정. `_is_system_command` 화이트리스트 도입.
- **테스트**: 93 passed.

## API 우선 설계

비즈니스 로직은 모두 FastAPI(`api_server.py`) 엔드포인트에 노출돼 있고, 다른 채널은 그 위 얇은 레이어:

```
모바일 앱 (가상)  ─┐
카카오 webhook   ─┤
Next.js 웹 (admin) ─┼─ FastAPI ─ pipeline/ (STT, 분류, 추출, 검증, RAG, LLM, 스코어링)
CLI 스크립트     ─┤              │
배치 스크립트    ─┘              └─ DB (SQLite / Postgres+pgvector)
```

Next.js 의 `apps/web/src/app/api/*/route.ts` 들은 모두 `proxyJsonRequest` / `proxyGet` 만 사용하는 thin proxy. 같은 REST 엔드포인트를 모바일·외부 SDK 가 그대로 호출 가능합니다.

## 구성

| 경로 | 설명 |
|------|------|
| `pipeline/` | STT/Vision → 분류 → 추출 → 검증 → RAG → LLM → 스코어링 (5+1 phase) |
| `pipeline/safety.py` | v3 — VirusTotal 클라이언트 (URL/파일) |
| `pipeline/vision.py` | v3 — Claude vision OCR (이미지/PDF) |
| `pipeline/active_models.py` | v3 — 학습된 체크포인트 swap reader |
| `api_server.py` | FastAPI 엔드포인트 + 카카오 webhook + 결과 토큰 페이지 |
| `platform_layer/` | v3.x — API key·rate limit·cost ledger·observability·abuse_guard middleware |
| `apps/web/` | Next.js 16 App Router 어드민·결과·methodology·training·platform UI |
| `db/` | SQLite / Postgres(pgvector) 저장소 |
| `training/` | v3 — 분류기·GLiNER fine-tune 스크립트 + 세션 관리자 |
| `tests/` | v3.x — pytest 단위·통합 테스트 (46 passed) |
| `scripts/` | 스택 실행, 배치 인제스트, AI Hub CLI 래퍼 |

## 빠른 실행

### 전체 스택

```bash
./scripts/start_stack.sh    # uvicorn(8000) + next dev(3100) + Tailscale Funnel
./scripts/watch_logs.sh     # 로그 실시간 확인
```

### 개별 실행

```bash
# Python 백엔드
pip install -r requirements.txt
pip install pypdfium2                          # v3 — PDF 렌더 (필수)
uvicorn api_server:app --reload

# Next.js 프론트엔드
cd apps/web && npm install
cp .env.example .env.local && npm run dev -- --port 3100
```

### 학습 (선택)

```bash
pip install -r training/requirements-train.txt
# 또는 /admin/training 에서 UI 로 시작
```

### CLI 분석

```bash
python run_analysis.py "https://youtube.com/watch?v=..."
python run_analysis.py --text "투자 설명 텍스트"
python run_analysis.py --file ./scam_poster.png   # v3 — 이미지/PDF 도 가능
```

## 환경 변수 (`.env`)

| 변수 | 설명 | 기본값 |
|------|------|--------|
| `SCAMGUARDIAN_API_URL` | Next.js → FastAPI 프록시 대상 | `http://127.0.0.1:8000` |
| `SCAMGUARDIAN_SQLITE_PATH` | SQLite DB 경로 | `.scamguardian/scamguardian.sqlite3` |
| `SCAMGUARDIAN_PERSIST_RUNS` | 분석 결과 DB 저장 여부 | `false` |
| `SCAMGUARDIAN_DATABASE_URL` | Postgres 연결 문자열 | (없으면 SQLite) |
| `ANTHROPIC_API_KEY` | LLM 보조 + 라벨링 초안 + vision OCR + 컨텍스트 챗봇 | **필수** |
| `ANTHROPIC_MODEL` | Claude 메인 분석 모델 | `claude-sonnet-4-6` |
| `ANTHROPIC_HAIKU_MODEL` | 컨텍스트 챗봇 + 의도 분류 | `claude-haiku-4-5-20251001` |
| `ANTHROPIC_VISION_MODEL` | v3 — vision OCR 모델 | `claude-sonnet-4-6` |
| `VIRUSTOTAL_API_KEY` | v3 — URL·파일 안전성 검사 | 없으면 Phase 0 skip |
| `VIRUSTOTAL_RPM` | VT 분당 호출 한도 | `4` (free tier) |
| `ABUSE_SOFT_THRESHOLD` | 어뷰즈 가드 — "짧은 메시지" 임계 (자수) | `10` |
| `ABUSE_WARN_LIMIT` | 짧은 메시지 누적 경고 횟수 | `3` |
| `ABUSE_BLOCK_DURATION` | 자동 블록 지속 시간(초) | `3600` |
| `ABUSE_VIOLATION_WINDOW` | 위반 누적 윈도우(초) | `3600` |
| `ANALYZE_MAX_TEXT_LENGTH` | `/api/analyze` 텍스트 입력 최대 글자 | `5000` |
| `SERPER_API_KEY` | 교차 검증용 검색 API | 필수 (검증 활성 시) |
| `OPENAI_API_KEY` | OpenAI Whisper API | 없으면 로컬 Whisper |
| `SCAMGUARDIAN_CORS_ORIGINS` | 허용 CORS 오리진 (콤마 구분) | `http://localhost:3000,...` |
| `SCAMGUARDIAN_PUBLIC_URL` | 결과 상세 페이지 베이스 URL | (없으면 ngrok 자동 발견) |
| `VISION_PDF_MAX_PAGES` | v3 — PDF 처리 시 최대 페이지 | `5` |
| `VIRUSTOTAL_RPM` | v3 — VT 분당 호출 한도 | `4` (free tier) |

## 파이프라인 (v3)

```
입력 (텍스트 / URL / 음성 / 영상 / 이미지 / PDF)
  │
  ▼
Phase 0  Safety Filter      VirusTotal — URL·파일 악성 검사 (v3 신규)
  │                         악성 확정 시 fast-path → 매우 위험 보고
  ▼
Phase 1  STT / OCR          Whisper (음성·영상) | Claude vision (이미지·PDF, v3)
  │
  ▼
Phase 2  분류                mDeBERTa NLI + 키워드 부스팅 (또는 fine-tuned task-specific)
  │
  ▼
Phase 3  병렬 실행           ┌ LLM 통합 (analyze_unified)
  │                         ├ GLiNER 엔티티 추출
  │                         └ RAG 유사 사례 검색
  ▼
Phase 4  교차 검증           Serper API (병렬 + 세마포어 레이트 리미팅)
  │
  ▼
Phase 5  스코어링            플래그 합산 → 위험 점수 / 레벨
  │
  ▼
ScamReport (JSON, safety_check 포함)
```

## 사기 유형 (12종)

투자 사기 / 건강식품 사기 / 부동산 사기 / 코인 사기 / 기관 사칭 / 대출 사기 /
메신저 피싱 / 로맨스 스캠 / 취업·알바 사기 / 납치·협박형 / 스미싱 / 중고거래 사기

어드민에서 커스텀 유형 추가 가능 → 즉시 파이프라인에 반영.

## 어드민 기능

| 경로 | 기능 |
|------|------|
| `/admin` | 라벨링 큐 — 검수자 claim, 상태 필터 |
| `/admin/[runId]` | 라벨 편집 — AI 초안, 엔티티/플래그/유형, **원본 미디어**(영상·오디오·이미지·PDF) 뷰어 |
| `/admin/stats` | DB 대시보드 — 분포·추이 |
| `/admin/browse` | DB 브라우저 — 검색·필터 |
| `/admin/training` | **v3** — Fine-tuning 세션 (시작·진행률 그래프·활성화) |
| `/admin/training/about` | **v3** — 모델 역할·파이프라인 위치·학습 효과 설명 |
| `/admin/platform` | **v3.x** — API key 발급·revoke + observability(p50/p95) + 비용 대시보드 |
| `/methodology` | 점수 산정 방식 — 합산식·등급·플래그별 정당성·학술 출처 |
| `/result/[token]` | 카카오 카드의 "자세한 결과 보기" — 1시간 토큰 |

## 카카오톡 챗봇 연동

### v3 입력 분기 (자동)

| 입력 | InputType | 처리 흐름 |
|------|-----------|----------|
| 텍스트 | TEXT | 의도 분류 (인사·사용법·내용·잡담) → 컨텍스트 수집 + 백그라운드 분석 |
| URL | URL | Phase 0 안전성 검사 → STT(YouTube) + 컨텍스트 수집 |
| 영상 파일 | VIDEO | Phase 0 → STT + 컨텍스트 수집 |
| **이미지** | **IMAGE** | **CDN 다운로드 → Phase 0 → vision OCR → 컨텍스트 수집** |
| **PDF** | **PDF** | **CDN 다운로드 → Phase 0 → vision OCR (페이지별) → 컨텍스트 수집** |

### 결과 카드 (v3)

악성 탐지 시 `🚨 위험! 이 파일은 악성으로 확인됐어요. VirusTotal X/Y 엔진 탐지` 경고가 결과 카드 **최상단** 에 prominent.

## 학습 데이터 배치 생성

```bash
# 내장 시드 샘플
python scripts/batch_ingest.py --skip-verify

# 외부 텍스트
python scripts/batch_ingest.py --file samples.txt --skip-verify

# JSONL
python scripts/batch_ingest.py --jsonl data/processed/cases.jsonl --skip-verify

# 공공기관 공개 자료 → JSONL
python scripts/collect_public_cases.py --org all
```

## AI Hub 데이터 자동화 (v3)

```bash
export AIHUB_API_KEY=...

# 1. 키워드 검색
python scripts/aihub.py list-datasets --grep 콜센터,상담,민원

# 2. 데이터셋 파일 트리
python scripts/aihub.py list-files 98

# 3. 라벨링 zip 만 골라 다운로드 (원천 음성 skip)
python scripts/aihub.py download-labels 98 --domain 금융 --dry-run
python scripts/aihub.py download-labels 98 --domain 금융
```

## Fine-tuning

`/admin/training` 에서 시작 → 백그라운드 subprocess → recharts 그래프 → 완료 후 활성화 한 클릭.

```bash
# CLI 로 직접 (선택)
python -m training.train_classifier --output-dir checkpoints/cls-v1 --epochs 3 --lora
python -m training.train_gliner    --output-dir checkpoints/gli-v1 --epochs 5
```

설명 페이지: <http://localhost:3100/admin/training/about>

## 외부 API 호출 보안 — API key + rate limit + abuse guard

`/api/analyze` 와 `/api/analyze-upload` 는 API key 필수:

```bash
curl -X POST https://your-host/api/analyze \
  -H "Authorization: Bearer sg_..." \
  -H "X-User-Id: client-user-123"   # 옵션: per-user 어뷰즈 누적
  -H "Content-Type: application/json" \
  -d '{"text": "분석할 텍스트"}'
```

3중 cap (모두 키별 독립):
- **RPM** (slid window, in-memory)
- **월별 호출 수**
- **월별 USD 비용** (claude+openai+serper+vt 합산)

초과 시 `429` + `Retry-After`. 발급/관리는 `/admin/platform`.

어뷰즈 가드 (`platform_layer/abuse_guard.py`):
- 길이 cap (`ANALYZE_MAX_TEXT_LENGTH=5000`), 반복/도배/gibberish 차단
- 짧은 메시지 누적 트래커 — 카카오 user_id 별 3회 경고 후 1시간 자동 블록 + 채팅 종료
- 첫 메시지는 free pass, 누적 시 Claude Haiku 호출도 skip → 어뷰즈 비용 통로 차단

## 테스트

```bash
pip install pytest
pytest                          # 46 passed (5초)
pytest tests/test_abuse_guard.py  # 모듈 단위
```

격리된 SQLite + 외부 API 환경변수 자동 mock 처리 (`tests/conftest.py`).

## 품질 관리

`GET /api/admin/metrics`:
- `classification_accuracy` / `entity_micro` / `flag_micro`
- `per_labeler` 통계, `needs_review` 목록

## 배포

| 구성요소 | 플랫폼 |
|----------|--------|
| 프론트엔드 | Vercel (Root Directory: `apps/web`) |
| Python API | Render (`uvicorn api_server:app --host 0.0.0.0 --port $PORT`) |

세부 설정: `DEPLOY.md`, `render.yaml`
