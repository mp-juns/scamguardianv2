## ScamGuardian Web

웹 대시보드는 `Next.js`로 작성되어 있고, Python API 서버에 분석 요청을 프록시합니다.

## Local Development

먼저 루트에서 Python API를 실행합니다.

```bash
uvicorn api_server:app --reload
```

그 다음 웹 앱을 실행합니다.

```bash
cp .env.example .env.local
npm run dev
```

기본 포트가 다른 서비스와 겹치면 다음처럼 포트를 바꿔 실행하세요.

```bash
npm run dev -- --port 3100
```

기본 환경 변수:

```bash
SCAMGUARDIAN_API_URL=http://127.0.0.1:8000
```

## Admin

- 라벨링 화면: `/admin`
- 저장된 분석 run이 있어야 라벨링 대상이 표시됩니다.
- 백엔드에서 `SCAMGUARDIAN_DATABASE_URL`과 `SCAMGUARDIAN_PERSIST_RUNS=true`가 설정되어 있어야 합니다.
- 메인 분석 화면에서는 `사람 라벨 DB를 RAG로 참고` 옵션으로 유사 사례 기반 LLM 보조 판정을 켤 수 있습니다.

## Deploy

- Vercel Root Directory: `apps/web`
- Required env: `SCAMGUARDIAN_API_URL`

자세한 전체 배포 절차는 루트의 `DEPLOY.md`를 참고하세요.

You can check out [the Next.js GitHub repository](https://github.com/vercel/next.js) - your feedback and contributions are welcome!

## Deploy on Vercel

The easiest way to deploy your Next.js app is to use the [Vercel Platform](https://vercel.com/new?utm_medium=default-template&filter=next.js&utm_source=create-next-app&utm_campaign=create-next-app-readme) from the creators of Next.js.

Check out our [Next.js deployment documentation](https://nextjs.org/docs/app/building-your-application/deploying) for more details.
