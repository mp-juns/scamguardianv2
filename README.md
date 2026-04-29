# ScamGuardian

한국어 음성·텍스트·이미지·문서·URL 에서 사기를 탐지하는 AI 파이프라인.
카카오톡 챗봇 / 웹 / CLI 어떤 채널이든 같은 코어가 분석.

> 📖 **상세 아키텍처·시나리오·API·플래그 명세**: [`.scamguardian/README.md`](./.scamguardian/README.md)

## 빠른 실행

### 의존성
```bash
pip install -r requirements.txt
pip install pypdfium2                  # PDF 렌더 (필수)
```

### 환경변수 (`.env`)
```bash
# 분석에 필수
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...                  # Whisper API
SERPER_API_KEY=...                     # 교차검증
VIRUSTOTAL_API_KEY=...                 # Phase 0 안전성

# 옵션
SCAMGUARDIAN_DATABASE_URL=postgresql:// # 없으면 SQLite
SCAMGUARDIAN_PERSIST_RUNS=true          # 분석 결과 DB 저장
SCAMGUARDIAN_PUBLIC_URL=https://...     # 결과 페이지 베이스
```

### 실행
```bash
# 백엔드 (FastAPI)
uvicorn api_server:app --reload

# 프론트엔드 (Next.js)
cd apps/web && npm install && npm run dev

# 한 번에 (Tailscale Funnel 포함)
./scripts/start_stack.sh
./scripts/watch_logs.sh
```

### CLI 분석
```bash
python run_analysis.py "https://youtube.com/watch?v=..."
python run_analysis.py --text "투자 설명 텍스트"
```

### 테스트
```bash
pytest    # 93 passed
```

## 디렉터리

```
api_server.py        FastAPI — 모든 비즈니스 로직 (분석·webhook·라벨링·플랫폼 어드민)
pipeline/            7-Phase 분석 파이프라인 (Phase 0~5, 0.5 sandbox 포함)
platform_layer/      API key·rate limit·cost ledger·observability·abuse_guard
db/                  Postgres / SQLite 라우팅 facade
apps/web/            Next.js 16 — 프록시 + 어드민 UI
sandbox_server/      v3.5 — 격리 VM 안에서 도는 sandbox 디토네이션 서버
training/            Fine-tuning 시스템 (분류기·GLiNER)
experiments/         v4 검증 실험 (intent classifier, whisper chunker)
tests/               pytest 스위트
scripts/             배치 인제스트·운영 스크립트
.scamguardian/       런타임 데이터 + **상세 문서** (README.md)
```

## 주요 채널

- **카카오톡 챗봇**: `POST /webhook/kakao` (오픈빌더 연동)
- **웹 분석**: `https://<host>/` (프론트엔드)
- **어드민**: `https://<host>/admin/*` (라벨링 / 플랫폼 / 학습)
- **REST API**: `POST /api/analyze` (외부 클라이언트, API key 필요)
- **결과 공개 페이지**: `/result/[token]` (1시간 TTL)

자세한 내용은 [`.scamguardian/README.md`](./.scamguardian/README.md) 참고.

## 배포

- **Frontend**: Vercel (Root Directory: `apps/web`)
- **Backend**: Render / VPS (`uvicorn api_server:app --host 0.0.0.0 --port $PORT`)
- **Sandbox 서버 (v3.5)**: 별도 VM/VPS — `sandbox_server/README.md`
- 세부 설정: `DEPLOY.md`, `render.yaml`

## 라이선스 / 기여

내부 프로젝트. 외부 기여 시 사전 협의 필요.
