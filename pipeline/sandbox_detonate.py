"""
ScamGuardian sandbox detonator — Playwright 헤드리스 Chromium 으로 의심 URL 열어보기.

이 스크립트는:
1. Docker 컨테이너 안에서 (운영) 또는
2. subprocess 로 (개발)

격리된 환경에서 실행돼야 한다. stdout 에 JSON 한 줄 출력 → `pipeline/sandbox.py` 가 파싱.

탐지 항목:
- 최종 URL / 리디렉션 체인
- 페이지 제목
- 스크린샷 (PNG)
- 로그인폼 / 비밀번호 입력 / 민감 필드
- 자동 다운로드 시도 (drive-by)

의도적으로 *최소* 의존성 — playwright 만 있으면 동작.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any


def _detect_sensitive_fields(field_attrs: list[dict[str, Any]]) -> list[str]:
    """input 필드 속성 리스트 → 민감 필드 라벨 추출."""
    sensitive: list[str] = []
    keywords = {
        "password": "password",
        "pwd": "password",
        "passwd": "password",
        "ssn": "주민번호",
        "주민": "주민번호",
        "rrn": "주민번호",
        "credit": "카드번호",
        "card": "카드번호",
        "cvc": "카드번호",
        "cvv": "카드번호",
        "otp": "OTP",
        "pin": "PIN",
        "account": "계좌번호",
        "계좌": "계좌번호",
    }
    for attrs in field_attrs:
        # type=password 는 항상 민감
        if (attrs.get("type") or "").lower() == "password":
            if "password" not in sensitive:
                sensitive.append("password")
            continue
        # name/id/placeholder 에서 키워드 검출
        haystack = " ".join([
            (attrs.get("name") or ""),
            (attrs.get("id") or ""),
            (attrs.get("placeholder") or ""),
            (attrs.get("autocomplete") or ""),
        ]).lower()
        for kw, label in keywords.items():
            if kw in haystack and label not in sensitive:
                sensitive.append(label)
    return sensitive


def detonate(url: str, output_dir: Path, timeout_sec: int) -> dict[str, Any]:
    """URL 을 navigate 하고 분석 결과 dict 반환."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return {
            "status": "error",
            "error": "playwright not installed (pip install playwright && playwright install chromium)",
            "redirect_chain": [],
        }

    redirect_chain: list[str] = []
    download_attempts: list[dict[str, Any]] = []
    final_url: str | None = None
    title: str | None = None
    field_attrs: list[dict[str, Any]] = []
    error: str | None = None
    status = "completed"

    output_dir.mkdir(parents=True, exist_ok=True)
    screenshot_file = output_dir / "screenshot.png"

    t0 = time.time()
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                ],
            )
            context = browser.new_context(
                viewport={"width": 1280, "height": 800},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                ),
                accept_downloads=True,
                ignore_https_errors=True,
            )

            # 리디렉션 추적: response 이벤트로 실제 redirect 체인 수집
            def on_response(resp):
                # 30x 응답이면 redirect 시작 URL 기록
                try:
                    if 300 <= resp.status < 400:
                        redirect_chain.append(resp.url)
                except Exception:
                    pass

            page = context.new_page()
            page.on("response", on_response)
            page.on("download", lambda d: download_attempts.append({
                "suggested_filename": d.suggested_filename,
                "url": d.url,
            }))

            try:
                resp = page.goto(url, timeout=timeout_sec * 1000, wait_until="domcontentloaded")
                final_url = page.url
                if resp is None:
                    error = "no response"
                else:
                    title = page.title() or None

                # 입력 필드 속성 수집
                try:
                    field_attrs = page.evaluate(
                        """() => {
                            const out = [];
                            for (const el of document.querySelectorAll('input')) {
                                out.push({
                                    type: el.type,
                                    name: el.name,
                                    id: el.id,
                                    placeholder: el.placeholder,
                                    autocomplete: el.autocomplete,
                                });
                            }
                            return out;
                        }"""
                    ) or []
                except Exception:
                    field_attrs = []

                # 스크린샷 best-effort
                try:
                    page.screenshot(path=str(screenshot_file), full_page=False, timeout=5000)
                except Exception as exc:
                    error = f"screenshot: {exc}"

            except Exception as exc:
                # navigate 자체가 죽어도 부분 결과 살림
                msg = str(exc)
                if "timeout" in msg.lower() or "Timeout" in msg:
                    status = "timeout"
                else:
                    status = "blocked"
                error = msg[:200]
                final_url = page.url if page.url else None

            context.close()
            browser.close()

    except Exception as exc:
        status = "error"
        error = f"{type(exc).__name__}: {exc}"

    sensitive = _detect_sensitive_fields(field_attrs)
    has_password = any(
        (f.get("type") or "").lower() == "password" for f in field_attrs
    )
    has_login_form = has_password or bool({"이메일", "email"} & set(
        (f.get("name") or "").lower() for f in field_attrs
    ))

    return {
        "status": status,
        "final_url": final_url,
        "redirect_chain": redirect_chain,
        "title": title,
        "screenshot_path": str(screenshot_file) if screenshot_file.exists() else None,
        "has_login_form": has_login_form,
        "has_password_field": has_password,
        "sensitive_form_fields": sensitive,
        "download_attempts": download_attempts,
        "duration_ms": int((time.time() - t0) * 1000),
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="ScamGuardian sandbox URL detonator")
    parser.add_argument("--url", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--timeout", type=int, default=30)
    args = parser.parse_args()

    result = detonate(args.url, Path(args.output_dir), args.timeout)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
