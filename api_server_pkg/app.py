"""FastAPI 앱 빌더 — 미들웨어 + 라우터 include + startup 이벤트."""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from db import repository
from pipeline.runner import ScamGuardianPipeline
from platform_layer.middleware import PlatformMiddleware

from . import admin_platform, admin_runs, admin_training, analyze, health, kakao, result_token


def create_app() -> FastAPI:
    app = FastAPI(
        title="ScamGuardian API",
        version="0.1.0",
        description="ScamGuardian v2 파이프라인을 웹에서 호출하기 위한 API",
    )

    allowed_origins = [
        origin.strip()
        for origin in os.getenv(
            "SCAMGUARDIAN_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        ).split(",")
        if origin.strip()
    ]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # v3 platform — API key + rate limit + request log + cost context + admin auth gating
    app.add_middleware(PlatformMiddleware)

    app.include_router(health.router)
    app.include_router(result_token.router)
    app.include_router(kakao.router)
    app.include_router(analyze.router)
    app.include_router(admin_runs.router)
    app.include_router(admin_platform.router)
    app.include_router(admin_training.router)

    @app.on_event("startup")
    def _startup() -> None:
        log = logging.getLogger("startup")

        if repository.database_configured():
            repository.init_db()

        # 업로드 retention — 시작 시 1회 sweep + 백그라운드 24h 주기.
        try:
            from platform_layer import retention as _retention
            _retention.sweep()
            _retention.start_background_sweeper()
        except Exception as exc:  # noqa: BLE001
            log.warning("retention sweep init 실패 (무시): %s", exc)

        log.info("모델 워밍업 시작 (콜드스타트 방지)...")
        try:
            pipeline = ScamGuardianPipeline()
            pipeline.analyze("워밍업 테스트", skip_verification=True, use_llm=True, use_rag=False)
            log.info("모델 워밍업 완료")
        except Exception as exc:
            log.warning("모델 워밍업 실패 (무시): %s", exc)

    return app
