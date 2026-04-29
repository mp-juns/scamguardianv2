"""
ScamGuardian v3.5 — Phase 0.5 URL 디토네이션 (Playwright 격리 컨테이너)

Phase 0(VT) 가 *알려진* 시그니처 lookup 이라면, 이 모듈은 *직접 열어보는* 단계.
의심 URL 을 격리된 헤드리스 Chromium 으로 navigate 해서:
- 최종 URL / 리디렉션 체인
- 페이지 제목 / 스크린샷
- 로그인폼 / 비밀번호 입력 / 민감 필드 감지
- 자동 다운로드 시도 (drive-by)
- 클로킹 (target ≠ final domain)

운영 모드 두 가지:
- `SANDBOX_USE_DOCKER=1` (권장 운영) — `docker run --rm --network=isolated --read-only ...`
- 그 외(기본) — subprocess 로 같은 detonate 스크립트 직접 실행 (dev 모드)

본 모듈은 외부 API 0회 — 격리 컨테이너 안에서만 네트워크 접근. tear-down 후 디스크 정리.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

log = logging.getLogger("sandbox")

SANDBOX_TIMEOUT = int(os.getenv("SANDBOX_TIMEOUT", "30"))
SANDBOX_USE_DOCKER = os.getenv("SANDBOX_USE_DOCKER", "0") == "1"
SANDBOX_DOCKER_IMAGE = os.getenv("SANDBOX_DOCKER_IMAGE", "scamguardian/sandbox:latest")
SANDBOX_OUTPUT_DIR = Path(os.getenv("SANDBOX_OUTPUT_DIR", ".scamguardian/sandbox"))
SANDBOX_REDIRECT_THRESHOLD = 3   # > 이면 excessive_redirects

# 운영 격리: production 은 별도 VPS 의 sandbox 서버를 HTTPS 로 호출.
# 환경변수 둘 다 세팅돼 있으면 remote 모드로 자동 전환.
SANDBOX_BACKEND = os.getenv("SANDBOX_BACKEND", "auto").lower()  # auto | local | remote
SANDBOX_REMOTE_URL = os.getenv("SANDBOX_REMOTE_URL", "").rstrip("/")
SANDBOX_REMOTE_TOKEN = os.getenv("SANDBOX_REMOTE_TOKEN", "")
SANDBOX_REMOTE_TIMEOUT = int(os.getenv("SANDBOX_REMOTE_TIMEOUT", "60"))


def _resolved_backend() -> str:
    """auto: REMOTE_URL+TOKEN 둘 다 있으면 remote, 아니면 local."""
    if SANDBOX_BACKEND in ("local", "remote"):
        return SANDBOX_BACKEND
    if SANDBOX_REMOTE_URL and SANDBOX_REMOTE_TOKEN:
        return "remote"
    return "local"


class SandboxStatus(str, Enum):
    COMPLETED = "completed"
    TIMEOUT = "timeout"
    ERROR = "error"
    BLOCKED = "blocked"        # 컨테이너/브라우저가 거부 (악성 응답 차단 등)
    DISABLED = "disabled"      # 의도적으로 skip (Phase 0 fast-path 트리거 등)


@dataclass
class SandboxResult:
    target_url: str
    scanner: str = "playwright_sandbox"
    status: SandboxStatus = SandboxStatus.COMPLETED
    final_url: str | None = None
    redirect_chain: list[str] = field(default_factory=list)
    title: str | None = None
    screenshot_path: str | None = None
    has_login_form: bool = False
    has_password_field: bool = False
    sensitive_form_fields: list[str] = field(default_factory=list)
    download_attempts: list[dict[str, Any]] = field(default_factory=list)
    cloaking_detected: bool = False
    excessive_redirects: bool = False
    duration_ms: int = 0
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_url": self.target_url,
            "scanner": self.scanner,
            "status": self.status.value,
            "final_url": self.final_url,
            "redirect_chain": list(self.redirect_chain),
            "title": self.title,
            "screenshot_path": self.screenshot_path,
            "has_login_form": self.has_login_form,
            "has_password_field": self.has_password_field,
            "sensitive_form_fields": list(self.sensitive_form_fields),
            "download_attempts": list(self.download_attempts),
            "cloaking_detected": self.cloaking_detected,
            "excessive_redirects": self.excessive_redirects,
            "duration_ms": self.duration_ms,
            "error": self.error,
        }

    @property
    def is_dangerous(self) -> bool:
        """피싱/악성 신호가 하나라도 있으면 True. scorer 의 fast-eval 용."""
        return (
            self.has_password_field
            or bool(self.download_attempts)
            or self.cloaking_detected
        )


def _domain_of(url: str) -> str:
    """URL → 호스트(소문자). 파싱 실패 시 빈 문자열."""
    try:
        from urllib.parse import urlparse
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def _parse_detonate_output(raw_json: str, target_url: str) -> SandboxResult:
    """detonate 스크립트의 stdout JSON → SandboxResult."""
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return SandboxResult(
            target_url=target_url,
            status=SandboxStatus.ERROR,
            error=f"JSON parse: {exc}",
        )

    redirects = data.get("redirect_chain") or []
    final_url = data.get("final_url") or target_url
    target_domain = _domain_of(target_url)
    final_domain = _domain_of(final_url)
    cloaking = bool(target_domain and final_domain and target_domain != final_domain)
    excessive = len(redirects) > SANDBOX_REDIRECT_THRESHOLD

    # 원격 백엔드는 screenshot 을 base64 로 inline 전송 → 호스트에 저장
    screenshot_path = data.get("screenshot_path")
    screenshot_b64 = data.get("screenshot_base64")
    if screenshot_b64 and not (screenshot_path and Path(screenshot_path).exists()):
        try:
            import base64
            SANDBOX_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
            local_dir = SANDBOX_OUTPUT_DIR / uuid.uuid4().hex[:12]
            local_dir.mkdir(parents=True, exist_ok=True)
            local_path = local_dir / "screenshot.png"
            local_path.write_bytes(base64.b64decode(screenshot_b64))
            screenshot_path = str(local_path)
        except Exception as exc:
            log.warning("screenshot decode failed: %s", exc)

    return SandboxResult(
        target_url=target_url,
        status=SandboxStatus(data.get("status", "completed")),
        final_url=final_url,
        redirect_chain=list(redirects),
        title=data.get("title"),
        screenshot_path=screenshot_path,
        has_login_form=bool(data.get("has_login_form")),
        has_password_field=bool(data.get("has_password_field")),
        sensitive_form_fields=list(data.get("sensitive_form_fields") or []),
        download_attempts=list(data.get("download_attempts") or []),
        cloaking_detected=cloaking,
        excessive_redirects=excessive,
        duration_ms=int(data.get("duration_ms") or 0),
        error=data.get("error"),
    )


def _run_subprocess(url: str, output_dir: Path) -> tuple[str, str, int]:
    """detonate 스크립트를 subprocess 로 실행 (dev 모드)."""
    detonate_script = Path(__file__).parent / "sandbox_detonate.py"
    cmd = [
        sys.executable,
        str(detonate_script),
        "--url", url,
        "--output-dir", str(output_dir),
        "--timeout", str(SANDBOX_TIMEOUT),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True,
        timeout=SANDBOX_TIMEOUT + 10,
    )
    return proc.stdout, proc.stderr, proc.returncode


def _run_docker(url: str, output_dir: Path) -> tuple[str, str, int]:
    """Docker 컨테이너 안에서 detonate 실행 (운영 모드)."""
    output_dir_abs = output_dir.resolve()
    cmd = [
        "docker", "run", "--rm",
        "--network=bridge",
        "--read-only",
        "--tmpfs", "/tmp:rw,exec,size=256m",
        "--memory=512m",
        "--cpus=1",
        "--cap-drop=ALL",
        "-v", f"{output_dir_abs}:/sandbox/out:rw",
        SANDBOX_DOCKER_IMAGE,
        "--url", url,
        "--output-dir", "/sandbox/out",
        "--timeout", str(SANDBOX_TIMEOUT),
    ]
    proc = subprocess.run(
        cmd, capture_output=True, text=True,
        timeout=SANDBOX_TIMEOUT + 30,
    )
    return proc.stdout, proc.stderr, proc.returncode


def _detonate_remote(url: str) -> SandboxResult:
    """별도 VPS 의 sandbox 서버에 HTTPS 호출 — production 권장 모드.

    별도 sandbox 서버 (sandbox_server/app.py) 가 SANDBOX_REMOTE_URL 에서 listen.
    Bearer token 으로 인증, 응답은 SandboxResult.to_dict() 와 동일 스키마.
    """
    import requests as _requests

    t0 = time.time()
    try:
        resp = _requests.post(
            f"{SANDBOX_REMOTE_URL}/detonate",
            json={"url": url, "timeout": SANDBOX_TIMEOUT},
            headers={"Authorization": f"Bearer {SANDBOX_REMOTE_TOKEN}"},
            timeout=SANDBOX_REMOTE_TIMEOUT,
        )
        duration_ms = int((time.time() - t0) * 1000)
        if resp.status_code != 200:
            log.error("sandbox remote returned %d: %s", resp.status_code, resp.text[:200])
            return SandboxResult(
                target_url=url,
                status=SandboxStatus.ERROR,
                duration_ms=duration_ms,
                error=f"remote http {resp.status_code}",
            )
        # 원격 응답 = JSON dict, _parse_detonate_output 와 동일 스키마
        result = _parse_detonate_output(resp.text, url)
        if not result.duration_ms:
            result.duration_ms = duration_ms
        log.info("sandbox detonate (remote): url=%.60s duration=%dms status=%s",
                 url, duration_ms, result.status.value)
        return result
    except _requests.Timeout:
        return SandboxResult(
            target_url=url,
            status=SandboxStatus.TIMEOUT,
            duration_ms=int((time.time() - t0) * 1000),
            error="remote sandbox timeout",
        )
    except Exception as exc:
        log.exception("sandbox remote call failed: %s", exc)
        return SandboxResult(
            target_url=url,
            status=SandboxStatus.ERROR,
            duration_ms=int((time.time() - t0) * 1000),
            error=f"{type(exc).__name__}: {exc}",
        )


def _detonate_local(url: str) -> SandboxResult:
    """동일 호스트 Docker / subprocess 디토네이션 — 개발 전용. 운영에선 _detonate_remote 사용."""
    run_id = uuid.uuid4().hex[:12]
    output_dir = SANDBOX_OUTPUT_DIR / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    try:
        if SANDBOX_USE_DOCKER and shutil.which("docker"):
            stdout, stderr, rc = _run_docker(url, output_dir)
            mode = "docker"
        else:
            stdout, stderr, rc = _run_subprocess(url, output_dir)
            mode = "subprocess"
        duration_ms = int((time.time() - t0) * 1000)
        log.info(
            "sandbox detonate (local/%s): url=%.60s rc=%d duration=%dms",
            mode, url, rc, duration_ms,
        )
        if rc != 0:
            return SandboxResult(
                target_url=url,
                status=SandboxStatus.ERROR,
                duration_ms=duration_ms,
                error=f"detonate exit={rc}: {stderr[:200] if stderr else ''}",
            )
        result = _parse_detonate_output(stdout, url)
        if not result.duration_ms:
            result.duration_ms = duration_ms
        return result

    except subprocess.TimeoutExpired:
        return SandboxResult(
            target_url=url,
            status=SandboxStatus.TIMEOUT,
            duration_ms=int((time.time() - t0) * 1000),
            error="subprocess timeout",
        )
    except Exception as exc:
        log.exception("sandbox local detonate failed: %s", exc)
        return SandboxResult(
            target_url=url,
            status=SandboxStatus.ERROR,
            duration_ms=int((time.time() - t0) * 1000),
            error=f"{type(exc).__name__}: {exc}",
        )


def detonate_url(url: str) -> SandboxResult:
    """의심 URL 디토네이션 — 백엔드(local/remote) 자동 분기.

    환경변수:
      SANDBOX_BACKEND=auto  (default: REMOTE_URL+TOKEN 있으면 remote, 아니면 local)
      SANDBOX_REMOTE_URL=https://sandbox.scamguardian.internal
      SANDBOX_REMOTE_TOKEN=<HMAC token>

    실패해도 RuntimeError 안 던짐 — status=ERROR 로 채워서 반환.
    """
    if not url or not url.startswith(("http://", "https://")):
        return SandboxResult(
            target_url=url,
            status=SandboxStatus.ERROR,
            error="invalid url",
        )

    backend = _resolved_backend()
    if backend == "remote":
        return _detonate_remote(url)
    return _detonate_local(url)
