"""
ScamGuardian sandbox 서버 — production 호스트와 분리된 격리 VPS/VM 안에서 동작.

이 서버:
- POST /detonate { url } 만 받음 (production 의 pipeline.sandbox._detonate_remote 가 호출)
- 받은 URL 을 Docker 컨테이너 안 Playwright 로 디토네이션
- JSON 결과 + (선택) screenshot base64 반환
- DB 없음, API 키 없음, 사용자 데이터 없음 — 털려도 잃을 게 없는 ephemeral 노드

배포:
  - 별도 Multipass VM, Hyper-V VM, 또는 클라우드 VPS
  - production 호스트와 *다른 머신* 이어야 의미 있음 (같은 호스트면 격리 0)

인증:
  - Bearer token (HMAC) — production 호스트와 sandbox 서버가 사전 공유한 비밀
  - 환경변수 SANDBOX_TOKEN 으로 주입

네트워크 정책 (배포 시):
  - inbound: production 서버 IP 에서만 허용 (firewall / security group)
  - outbound: 인터넷 자유 (디토네이션 대상이 외부 사이트라서)
  - production 내부 IP 로의 outbound 차단 (잠재 공격자 우회 방지)
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
import shutil
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel, Field

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s")
log = logging.getLogger("sandbox_server")

SANDBOX_TOKEN = os.getenv("SANDBOX_TOKEN")
SANDBOX_TIMEOUT_DEFAULT = int(os.getenv("SANDBOX_TIMEOUT", "30"))
SANDBOX_OUTPUT_DIR = Path(os.getenv("SANDBOX_OUTPUT_DIR", "/var/lib/scamguardian-sandbox"))
SANDBOX_USE_DOCKER = os.getenv("SANDBOX_USE_DOCKER", "1") == "1"
SANDBOX_DOCKER_IMAGE = os.getenv("SANDBOX_DOCKER_IMAGE", "scamguardian/sandbox:latest")
INCLUDE_SCREENSHOT_BASE64 = os.getenv("SANDBOX_INCLUDE_SCREENSHOT", "1") == "1"

if not SANDBOX_TOKEN:
    log.warning(
        "SANDBOX_TOKEN 미설정 — 인증 비활성화. 운영 환경에선 반드시 설정하세요."
    )

app = FastAPI(title="ScamGuardian Sandbox", version="0.1")


class DetonateRequest(BaseModel):
    url: str
    timeout: int = Field(default=SANDBOX_TIMEOUT_DEFAULT, ge=5, le=120)


def _check_auth(authorization: str | None) -> None:
    if not SANDBOX_TOKEN:
        return  # dev 모드 — 인증 skip
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    presented = authorization.removeprefix("Bearer ").strip()
    if not secrets.compare_digest(SANDBOX_TOKEN, presented):
        raise HTTPException(status_code=401, detail="invalid token")


def _run_subprocess(url: str, output_dir: Path, timeout: int) -> tuple[str, str, int]:
    """동일 머신 subprocess (dev 모드)."""
    detonate_script = Path(__file__).parent.parent / "pipeline" / "sandbox_detonate.py"
    cmd = [
        sys.executable, str(detonate_script),
        "--url", url, "--output-dir", str(output_dir),
        "--timeout", str(timeout),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 10)
    return proc.stdout, proc.stderr, proc.returncode


def _run_docker(url: str, output_dir: Path, timeout: int) -> tuple[str, str, int]:
    """Docker 컨테이너 격리 (운영 권장)."""
    cmd = [
        "docker", "run", "--rm",
        "--network=bridge",
        "--read-only",
        "--tmpfs", "/tmp:rw,exec,size=256m",
        "--memory=512m",
        "--cpus=1",
        "--cap-drop=ALL",
        "-v", f"{output_dir.resolve()}:/sandbox/out:rw",
        SANDBOX_DOCKER_IMAGE,
        "--url", url,
        "--output-dir", "/sandbox/out",
        "--timeout", str(timeout),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 30)
    return proc.stdout, proc.stderr, proc.returncode


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "mode": "docker" if (SANDBOX_USE_DOCKER and shutil.which("docker")) else "subprocess",
        "auth": bool(SANDBOX_TOKEN),
        "image": SANDBOX_DOCKER_IMAGE if SANDBOX_USE_DOCKER else None,
    }


@app.post("/detonate")
def detonate(payload: DetonateRequest, authorization: str | None = Header(default=None)) -> dict[str, Any]:
    _check_auth(authorization)

    url = (payload.url or "").strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="invalid url")

    run_id = uuid.uuid4().hex[:12]
    output_dir = SANDBOX_OUTPUT_DIR / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info("detonate start: run_id=%s url=%.80s timeout=%ds", run_id, url, payload.timeout)
    t0 = time.time()
    try:
        if SANDBOX_USE_DOCKER and shutil.which("docker"):
            stdout, stderr, rc = _run_docker(url, output_dir, payload.timeout)
            mode = "docker"
        else:
            stdout, stderr, rc = _run_subprocess(url, output_dir, payload.timeout)
            mode = "subprocess"
    except subprocess.TimeoutExpired:
        log.warning("detonate timeout: run_id=%s", run_id)
        _cleanup(output_dir)
        return {
            "status": "timeout",
            "target_url": url,
            "redirect_chain": [],
            "duration_ms": int((time.time() - t0) * 1000),
            "error": "subprocess timeout",
        }
    except Exception as exc:
        log.exception("detonate error: %s", exc)
        _cleanup(output_dir)
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")

    duration_ms = int((time.time() - t0) * 1000)
    log.info("detonate done: run_id=%s mode=%s rc=%d duration=%dms", run_id, mode, rc, duration_ms)

    if rc != 0:
        _cleanup(output_dir)
        return {
            "status": "error",
            "target_url": url,
            "redirect_chain": [],
            "duration_ms": duration_ms,
            "error": f"detonate exit={rc}: {stderr[:200]}",
        }

    try:
        result = json.loads(stdout)
    except json.JSONDecodeError as exc:
        _cleanup(output_dir)
        return {
            "status": "error",
            "target_url": url,
            "redirect_chain": [],
            "duration_ms": duration_ms,
            "error": f"json parse: {exc}",
        }

    # screenshot 을 host(production) 로 전달 — base64 인코딩
    if INCLUDE_SCREENSHOT_BASE64 and result.get("screenshot_path"):
        try:
            shot_path = Path(result["screenshot_path"])
            if shot_path.exists():
                result["screenshot_base64"] = base64.b64encode(shot_path.read_bytes()).decode()
        except Exception as exc:
            log.warning("screenshot read failed: %s", exc)

    _cleanup(output_dir)
    return result


def _cleanup(output_dir: Path) -> None:
    """디토네이션 결과물 즉시 삭제 — sandbox 서버는 stateless."""
    try:
        shutil.rmtree(output_dir, ignore_errors=True)
    except Exception:
        pass


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8001"))
    uvicorn.run(app, host="0.0.0.0", port=port)
