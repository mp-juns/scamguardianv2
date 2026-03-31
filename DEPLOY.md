# Deployment Guide

## Architecture

- Frontend: `apps/web` on Vercel
- Backend API: `api_server.py` on Render

## 1. Deploy API to Render

Render can use the included `render.yaml`, or you can create the service manually.

### Required environment variables

- `SERPER_API_KEY`
- `SCAMGUARDIAN_CORS_ORIGINS`

Example:

```bash
SCAMGUARDIAN_CORS_ORIGINS=https://your-vercel-app.vercel.app
```

### Service settings

- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn api_server:app --host 0.0.0.0 --port $PORT`
- Health check path: `/health`

## 2. Deploy Web to Vercel

Create a Vercel project from this repository and set:

- Root Directory: `apps/web`
- Framework Preset: `Next.js`

### Required environment variable

- `SCAMGUARDIAN_API_URL`

Example:

```bash
SCAMGUARDIAN_API_URL=https://your-render-service.onrender.com
```

The frontend route handler proxies browser requests through `apps/web/src/app/api/analyze/route.ts`, so the browser never needs the Python API URL directly.

## 3. Post-deploy checklist

1. Open the Render URL and confirm `/health` returns `{"status":"ok"}`.
2. Open the Vercel site and submit a sample text with search verification disabled.
3. Enable search verification and confirm `SERPER_API_KEY` is working.
4. Update `SCAMGUARDIAN_CORS_ORIGINS` if the frontend domain changes.
