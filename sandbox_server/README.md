# ScamGuardian Sandbox Server

Production 호스트와 분리된 격리 VM 안에서 도는 sandbox 디토네이션 서버.
Production 의 `pipeline/sandbox.py` 가 HTTPS 로 호출.

## 왜 분리하나

- production 호스트 = DB, API 키, 사용자 데이터 보유
- sandbox = untrusted URL/APK 직접 실행
- 같은 호스트에 있으면 컨테이너 이스케이프 한 번에 모든 데이터 노출
- 분리하면 sandbox 가 완전히 털려도 빈 VM 만 잃음

## 옵션 — Multipass VM (Windows 11 Pro 권장)

### 1. Hyper-V 활성화 (Win11 Pro)

PowerShell 관리자:
```powershell
Enable-WindowsOptionalFeature -Online -FeatureName Microsoft-Hyper-V -All
# 재부팅 필요
```

### 2. Multipass 설치

```powershell
winget install Canonical.Multipass
```

### 3. Sandbox VM 생성

```powershell
multipass launch --name sandbox --memory 2G --disk 10G --cpus 2 24.04
multipass shell sandbox
```

### 4. VM 안에서 sandbox 서버 셋업

```bash
# VM 안에서 (multipass shell sandbox 한 상태)
sudo apt update && sudo apt install -y docker.io python3-pip git
sudo usermod -aG docker $USER && exit  # 그룹 적용 위해 한 번 끊기
multipass shell sandbox  # 다시 들어가기

# 우리 코드 가져오기 (sandbox_server/ + pipeline/sandbox_detonate.py + pipeline/sandbox.Dockerfile 만 필요)
git clone <YOUR_REPO_URL> ~/scamguardian-v2
cd ~/scamguardian-v2

# Playwright 컨테이너 이미지 빌드 (per-detonation 컨테이너용)
docker build -f pipeline/sandbox.Dockerfile -t scamguardian/sandbox:latest .

# Python 의존성 (서버 자체용)
pip install fastapi uvicorn pydantic

# 토큰 생성 (production 호스트와 공유)
export SANDBOX_TOKEN=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
echo "공유 토큰: $SANDBOX_TOKEN"   # production 호스트의 SANDBOX_REMOTE_TOKEN 으로도 같은 값 세팅

# 서버 시작
SANDBOX_USE_DOCKER=1 \
SANDBOX_DOCKER_IMAGE=scamguardian/sandbox:latest \
PORT=8001 \
python sandbox_server/app.py
```

### 5. VM IP 확인 + production 에서 호출 설정

```powershell
# Windows PowerShell (host)
multipass info sandbox    # IPv4: 172.x.x.x 확인
```

WSL production 호스트 의 `.env`:
```bash
SANDBOX_BACKEND=remote
SANDBOX_REMOTE_URL=http://172.x.x.x:8001
SANDBOX_REMOTE_TOKEN=<위에서 생성한 토큰>
SANDBOX_ENABLED=1
```

테스트:
```bash
# WSL production 에서
curl -X POST http://172.x.x.x:8001/health
# → {"status":"ok","mode":"docker","auth":true,"image":"scamguardian/sandbox:latest"}

curl -X POST http://172.x.x.x:8001/detonate \
  -H "Authorization: Bearer <토큰>" \
  -H "Content-Type: application/json" \
  -d '{"url":"https://example.com"}'
```

### 6. 자동 시작 (선택)

VM 안에 systemd 서비스로 등록:
```bash
sudo tee /etc/systemd/system/sandbox.service > /dev/null <<EOF
[Unit]
Description=ScamGuardian Sandbox
After=docker.service
Requires=docker.service

[Service]
Type=simple
User=ubuntu
Environment="SANDBOX_TOKEN=<your-token>"
Environment="SANDBOX_USE_DOCKER=1"
Environment="SANDBOX_DOCKER_IMAGE=scamguardian/sandbox:latest"
Environment="PORT=8001"
WorkingDirectory=/home/ubuntu/scamguardian-v2
ExecStart=/usr/bin/python3 sandbox_server/app.py
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now sandbox
sudo systemctl status sandbox
```

VM 자동 시작 (Windows 부팅 시):
```powershell
multipass set client.gui.autostart=true
multipass start sandbox
```

## 옵션 — 클라우드 VPS ($5/월, production 권장)

위 4~6번 단계와 동일하되 다음 차이:
- Hetzner CPX11 / DigitalOcean Basic Droplet 등 1GB RAM 인스턴스
- Ubuntu 24.04
- firewall: production 서버 IP 에서만 8001 포트 inbound 허용
- HTTPS: Caddy/Traefik 으로 TLS 자동 발급 (Let's Encrypt)
- production 호스트에서 `SANDBOX_REMOTE_URL=https://sandbox.scamguardian.app`

## 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| `docker: command not found` | `sudo apt install docker.io && sudo usermod -aG docker $USER` 후 재로그인 |
| `permission denied on /var/run/docker.sock` | docker 그룹 적용 위해 logout/login |
| production 에서 connection refused | VM 방화벽 (`sudo ufw allow 8001`) 또는 sandbox 서버 미실행 |
| 401 Unauthorized | production 의 `SANDBOX_REMOTE_TOKEN` 과 sandbox 의 `SANDBOX_TOKEN` 불일치 |
| 디토네이션 timeout | 기본 30s. `payload.timeout` 늘리거나 페이지가 진짜 죽었는지 확인 |
