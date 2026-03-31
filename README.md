# ScamGuardian v2

텍스트나 유튜브 URL을 받아 스캠 유형 분류, 엔티티 추출, 검색 기반 검증, 위험도 점수화를 수행하는 파이프라인입니다.

## 구성

- `pipeline/`: 기존 분석 파이프라인
- `api_server.py`: FastAPI 기반 백엔드
- `apps/web/`: Next.js 기반 웹 대시보드
- `db/`: Postgres/pgvector + 로컬 SQLite 저장소 계층

## 빠른 실행

### 1. Python API 실행

```bash
pip install -r requirements.txt
uvicorn api_server:app --reload
```

옵션:

- 검색 검증을 쓰려면 루트 `.env`에 `SERPER_API_KEY`를 넣어야 합니다.
- CORS 허용 도메인을 바꾸려면 `SCAMGUARDIAN_CORS_ORIGINS`를 설정하세요.
- 분석 결과를 DB에 저장하려면 `SCAMGUARDIAN_DATABASE_URL` 또는 `SCAMGUARDIAN_SQLITE_PATH`와 `SCAMGUARDIAN_PERSIST_RUNS=true`를 설정하세요.
- 로컬에서 빠르게 돌릴 때는 `SCAMGUARDIAN_SQLITE_PATH=.scamguardian/scamguardian.sqlite3`만으로도 `/admin`과 라벨 저장이 동작합니다.
- RAG를 쓰려면 pgvector가 켜진 Postgres가 가장 좋지만, 로컬 SQLite 모드에서도 기본 유사도 검색 fallback으로 동작합니다.
- 한국어 GLiNER가 `python-mecab-ko` 없이 로드되지 않으면, 파이프라인은 자동으로 규칙/키워드 기반 엔티티 추출로 계속 진행합니다.

예시:

```bash
SCAMGUARDIAN_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5432/scamguardian
SCAMGUARDIAN_PERSIST_RUNS=true
SCAMGUARDIAN_RAG_TOP_K=3
```

로컬 SQLite 예시:

```bash
SCAMGUARDIAN_SQLITE_PATH=.scamguardian/scamguardian.sqlite3
SCAMGUARDIAN_PERSIST_RUNS=true
SCAMGUARDIAN_RAG_TOP_K=3
```

### 2. 웹 실행

```bash
cd apps/web
npm install
cp .env.example .env.local
npm run dev
```

기본 프록시 대상:

```bash
SCAMGUARDIAN_API_URL=http://127.0.0.1:8000
```

## 라벨링/평가

- 웹 어드민: `http://127.0.0.1:3000/admin` 또는 `3100/admin`
- 어드민에서는 저장된 분석 run을 불러와 사람이 `scam_type`, 엔티티, 플래그, STT 교정본을 수정할 수 있습니다.
- 어드민 대시보드에서 새 스캠 유형을 추가할 수 있고, 저장 즉시 분류 후보/라벨링 옵션에 반영됩니다.
- 저장된 정답 데이터는 `/api/admin/metrics`에서 분류 정확도, 엔티티 F1, 플래그 F1으로 집계됩니다.
- 분석 요청 시 `use_llm=true`와 `use_rag=true`를 함께 보내면, 사람 라벨이 붙은 과거 사례를 찾아 LLM 보조 판정 프롬프트에 참고 사례로 넣습니다.

## 배포 방향

- 프론트엔드: Vercel
- Python API: Railway / Render / Fly.io 중 하나
- 프론트에서는 `/api/analyze`만 호출하고, 실제 Python 서버 주소는 `SCAMGUARDIAN_API_URL`로 연결합니다.