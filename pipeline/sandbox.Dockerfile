# ScamGuardian sandbox container — Playwright Chromium 격리 디토네이션
#
# 빌드:
#   docker build -f pipeline/sandbox.Dockerfile -t scamguardian/sandbox:latest .
#
# 실행 (sandbox.py 가 자동으로 호출):
#   docker run --rm --network=bridge --read-only \
#     --tmpfs /tmp:rw,exec,size=256m --memory=512m --cpus=1 --cap-drop=ALL \
#     -v /host/output:/sandbox/out:rw \
#     scamguardian/sandbox:latest \
#     --url https://suspicious.example --output-dir /sandbox/out --timeout 30
#
# Playwright 공식 이미지 — chromium + 의존성 사전 설치돼 있어 가장 안정적.
FROM mcr.microsoft.com/playwright/python:v1.47.0-jammy

WORKDIR /sandbox

# detonate 스크립트만 컨테이너로 복사 — 본 모듈은 외부 파이프라인 의존성 없음.
COPY pipeline/sandbox_detonate.py /sandbox/detonate.py

# 비특권 사용자로 실행 — playwright 이미지의 기본 사용자(pwuser) 사용
USER pwuser

ENTRYPOINT ["python", "/sandbox/detonate.py"]
