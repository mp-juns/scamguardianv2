# ScamGuardian Integration Guide — Signal Detection API

> **Reference implementation.** 이 문서는 ScamGuardian 검출 코어를 외부 클라이언트
> (카카오 챗봇·디스코드 봇·웹앱·통신사 앱 등) 에 붙이기 위한 통합 가이드다.
> 동작하는 reference 일 뿐 — 운영 시점에 rate limit·cost cap·인증 정책을 본인 환경에
> 맞춰 조정해야 한다.
>
> ⚠️ **Identity Boundary** (CLAUDE.md): **ScamGuardian 은 검출 시스템이지 판정 시스템이
> 아니다.** VirusTotal 이 70개 백신의 검출 결과를 보고만 하는 모델과 동일. 응답에는 검출된
> 위험 신호 list 와 각 신호의 학술/법적 근거만 담긴다 — `total_score`/`risk_level` 같은
> 점수·등급 필드는 **응답 schema 에 없다**. 최종 판정 logic 은 통합한 기업이 자체
> risk tolerance 에 따라 구현한다.

자동 생성된 OpenAPI spec: [`docs/openapi.json`](./openapi.json) — 서버 띄운 뒤
`/docs` (Swagger UI) 또는 `/redoc` 에서도 같은 내용을 볼 수 있다.

---

## 1. 5단계 통합 흐름 — 어떤 클라이언트든 똑같다

ScamGuardian 의 *모든* 통합은 동일한 5 단계를 거친다.

```
┌──────────────────────────────────────────────────────────────────┐
│ ① Auth        → admin 이 API key 발급 (sg_<urlsafe>)            │
│ ② Send input  → POST /api/analyze (text/url) or                  │
│                  POST /api/analyze-upload (file)                 │
│ ③ Wait        → 5–60s (URL/영상이면 STT 시간 추가)              │
│ ④ Receive     → DetectionReport JSON                             │
│                  (detected_signals[] + summary + disclaimer)     │
│ ⑤ Decide      → 통합 기업이 자체 판정 logic 으로 사용자에게 표시 │
└──────────────────────────────────────────────────────────────────┘
```

클라이언트 비교:

| 클라이언트 | 트리거 | 입력 채널 | 응답 채널 | 인증 |
|-----------|--------|----------|-----------|------|
| **카카오 챗봇** | 사용자가 메시지 보냄 | `/webhook/kakao` (멀티턴 컨텍스트 수집) | 카카오 카드 + `자세히 보기` 토큰 | 카카오 자체 (API key skip) |
| **디스코드 봇** | 슬래시 커맨드 `/check` | `POST /api/analyze` | embed | API key Bearer |
| **웹앱** (Next.js) | 폼 제출 | `POST /api/analyze` 또는 `/analyze-upload` | JSON → SSR 결과 페이지 | proxy 가 보유한 키 |
| **통신사 앱** (예: 보이스피싱 차단) | 통화 종료 자동 | `/api/analyze-upload` (녹음 파일) | 푸시 알림 + 결과 카드 | 디바이스별 API key |

> 카카오만 멀티턴 컨텍스트 수집 흐름이 별도다. 다른 클라이언트는 모두 단발 호출.
> 단발 호출 때 사용자 컨텍스트(추가 질문 답변)를 함께 보내고 싶다면 `payload.text`
> 안에 `[원문]\n[Q&A]` 형식으로 합쳐서 한 번에 전달한다.

---

## 2. Public API 4개 endpoint

외부 통합에서 쓰이는 endpoint 는 정확히 4개. 모두 `Public` 태그.

### 2.1 `POST /api/analyze` — 텍스트·URL 분석

```bash
curl -X POST https://api.example.com/api/analyze \
  -H "Authorization: Bearer sg_xxx" \
  -H "Content-Type: application/json" \
  -d '{
    "text": "검찰청 박수사관입니다. 즉시 300만원 안전계좌로 이체하세요.",
    "skip_verification": false,
    "use_rag": false
  }'
```

응답 (`DetectionReport`, 요약):

```json
{
  "scam_type": "수사기관 사칭",
  "classification_confidence": 0.92,
  "is_uncertain": false,
  "detected_signals": [
    {
      "flag": "fake_government_agency",
      "label_ko": "정부기관 사칭",
      "rationale": "검찰·경찰·금감원 등 공공기관은 전화·문자로 자금 이체 요구 절대 안 함. Cialdini 의 권위 원리를 가장 강하게 악용...",
      "source": "검찰청·경찰청·금감원 합동 보이스피싱 예방 가이드 / Cialdini (2021) — Authority",
      "detection_source": "rule",
      "evidence": ["검찰청 박수사관"],
      "description": "기관 사칭 검출"
    },
    {
      "flag": "urgent_transfer_demand",
      "label_ko": "즉각 송금·이체 요구",
      "rationale": "즉각 송금 요구는 보이스피싱 1순위 패턴...",
      "source": "경찰청 사이버수사국 보이스피싱 통계 / Cialdini (2021) — Scarcity",
      "detection_source": "rule",
      "evidence": ["즉시 300만원 이체"],
      "description": "긴급 송금 요구 검출"
    }
  ],
  "summary": "위험 신호 2개 검출되었습니다. 자세한 근거는 detected_signals 참고.",
  "disclaimer": "ScamGuardian 은 사기 판정을 내리지 않습니다. 위 검출 신호의 학술·법적 근거를 참고해 통합 기업의 자체 판정 logic 으로 결정하세요.",
  "entities": [
    {"label": "기관명", "text": "검찰청", "score": 0.95, "source": "gliner"},
    {"label": "금액", "text": "300만원", "score": 0.91, "source": "gliner"}
  ],
  "transcript_text": "검찰청 박수사관입니다. ...",
  "analysis_run_id": "8e7c2b1a-..."
}
```

핵심 응답 필드 의미:

| 필드 | 의미 |
|------|------|
| `detected_signals[]` | 검출된 위험 신호 list. 각 신호마다 `flag` (영문 키) / `label_ko` (한국어) / `rationale` (학술·법적 근거 문장) / `source` (출처 기관·논문) / `detection_source` (rule/llm/safety/sandbox) / `evidence` 포함 |
| `summary` | "위험 신호 N개 검출되었습니다." 형태. UI 헤드라인용 |
| `disclaimer` | "ScamGuardian 은 사기 판정을 내리지 않습니다 ..." 안내. 결과 카드 하단 필수 노출 |
| `scam_type` / `classification_confidence` | 추정 유형 + 분류 신뢰도. **판정이 아니라 검출 컨텍스트** |
| `entities[]` | GLiNER 추출 + LLM 보강. `source: "gliner"|"llm"|"ai-draft"` 출처 |
| `analysis_run_id` | DB 저장됐을 때만. 라벨링 / `/api/result/{token}` 카드 발급에 사용 |

❌ **응답에 없는 필드**: `total_score`, `risk_level`, `risk_description`, `is_scam`, `agent_verdict` 등 점수·등급·"사기다" 단정 필드는 **응답에 노출되지 않는다** (Identity Boundary).

### 2.2 `POST /api/analyze-upload` — 파일 업로드

```bash
curl -X POST https://api.example.com/api/analyze-upload \
  -H "Authorization: Bearer sg_xxx" \
  -F "file=@suspect_call.m4a" \
  -F "whisper_model=medium" \
  -F "skip_verification=true"
```

지원 확장자: `.mp4 .mov .webm .mkv .m4a .mp3 .wav .ogg .aac .jpg .jpeg .png .webp
.gif .bmp .pdf`. 100MB 이하 권장. 업로드 원본은 라벨링용으로
`.scamguardian/uploads/{run_id}/source.{ext}` 에 보존.

#### APK 검출 응답 예시 (Stage 2·3 구현 완료)

악성 APK 파일을 `/api/analyze-upload` 로 보내면, Tier 1 (VirusTotal) 결과 외에
다음 정적 분석 신호들이 `detected_signals[]` 에 추가됩니다. `androguard` 기반
manifest 분석 (Lv 1) + dex bytecode 패턴 매칭 (Lv 2) — 코드 *읽기만*, 실행 X.

```json
{
  "scam_type": "메신저 피싱",
  "detected_signals": [
    {
      "flag": "apk_dangerous_permissions_combo",
      "label_ko": "위험 권한 조합",
      "rationale": "SEND_SMS + READ_SMS + BIND_ACCESSIBILITY_SERVICE 동시 요구는 한국 보이스피싱 APK 의 결정적 권한 패턴 — OTP 가로채기 + 다른 앱 화면 가로채기 동시 가능. 정상 메시저 앱은 ACCESSIBILITY 안 씀.",
      "source": "S2W TALON SecretCalls 분석 / KISA 안드로이드 악성앱 동향 / Android Permissions Best Practices",
      "detection_source": "static_lv1",
      "evidence": ["android.permission.SEND_SMS", "android.permission.READ_SMS", "android.permission.BIND_ACCESSIBILITY_SERVICE"],
      "description": "manifest 권한 분석 — 보이스피싱 패턴 일치"
    },
    {
      "flag": "apk_self_signed",
      "label_ko": "자체 서명 인증서",
      "rationale": "공인 CA 가 아닌 자체 서명 인증서로 서명된 APK. 정상 Play Store 배포 앱은 검증된 서명 사용. 사이드로딩 APK 의 표지.",
      "source": "Android Developer Documentation: Sign your app / KISA 사이드로딩 위험 가이드",
      "detection_source": "static_lv1",
      "evidence": ["issuer: CN=Unknown, OU=Unknown"],
      "description": "APK 서명 검증 실패"
    },
    {
      "flag": "apk_suspicious_package_name",
      "label_ko": "의심스러운 패키지명 위장",
      "rationale": "공식 앱 패키지명 (`com.kakao.talk`, `com.nhn.android.search` 등) 을 흉내낸 typo-squatting 패턴. KrBanker 류 은행 사칭 APK 의 표준 수법.",
      "source": "S2W TALON KrBanker 보고서 / KISA 모바일 사칭 앱 통계",
      "detection_source": "static_lv1",
      "evidence": ["package: com.kakao.taIk (대문자 i 위장)"],
      "description": "패키지명 typo-squatting 검출"
    },
    {
      "flag": "apk_sms_auto_send_code",
      "label_ko": "SMS 자동 발송 코드",
      "rationale": "`SmsManager.sendTextMessage` API 를 호출하면서 사용자 UI 노출 없이 백그라운드에서 SMS 를 보내는 코드. 인증번호·OTP 가로채기 후 사기범 서버로 전송하는 전형 패턴 — MoqHao 와 SecretCalls 모두 사용.",
      "source": "S2W TALON MoqHao 분석 / Android SmsManager API Documentation",
      "detection_source": "static_lv2",
      "evidence": ["dex: invoke-virtual SmsManager.sendTextMessage", "called from background Service"],
      "description": "bytecode 패턴 — 자동 SMS 발송"
    },
    {
      "flag": "apk_call_state_listener",
      "label_ko": "통화 상태 가로채기",
      "rationale": "`TelephonyManager.listen(PhoneStateListener.LISTEN_CALL_STATE)` 등록은 통화 수신·발신을 모두 모니터링한다는 신호. 피해자가 경찰·금감원에 전화 걸 때 가로채는 SecretCalls 의 핵심 메커니즘.",
      "source": "S2W TALON SecretCalls 보고서 / Android TelephonyManager API",
      "detection_source": "static_lv2",
      "evidence": ["dex: TelephonyManager.listen(LISTEN_CALL_STATE)", "PhoneStateListener subclass found"],
      "description": "bytecode 패턴 — 통화 가로채기"
    },
    {
      "flag": "apk_accessibility_abuse",
      "label_ko": "접근성 서비스 악용",
      "rationale": "AccessibilityService 를 상속한 클래스가 `onAccessibilityEvent` 안에서 `performGlobalAction` 또는 `getRootInActiveWindow` 호출. 다른 앱 화면 읽기·자동 클릭·자동 입력에 악용 — KrBanker 의 가짜 은행 UI 오버레이 핵심.",
      "source": "OWASP Mobile Top 10 / Google Play Accessibility Policy / S2W TALON KrBanker",
      "detection_source": "static_lv2",
      "evidence": ["AccessibilityService subclass + performGlobalAction 호출"],
      "description": "bytecode 패턴 — accessibility 악용"
    },
    {
      "flag": "apk_impersonation_keywords",
      "label_ko": "사칭 키워드 string 검출",
      "rationale": "dex 의 string constants 풀에 \"검찰청\", \"금융감독원\", \"보안승급\", \"안전계좌\" 같은 권위 사칭 키워드 다수 등장. UI 텍스트나 푸시 알림에 사용되어 사용자 신뢰 형성. Cialdini 의 권위(Authority) 원리 악용.",
      "source": "S2W TALON 한국 보이스피싱 패밀리 분석 / Cialdini (2021) — Authority / KISA 보이스피싱 키워드 통계",
      "detection_source": "static_lv2",
      "evidence": ["string: \"검찰청 사이버수사대\"", "string: \"안전계좌로 즉시 이체하세요\""],
      "description": "dex string 분석 — 사칭 키워드"
    }
  ],
  "summary": "위험 신호 7개 검출되었습니다. 자세한 근거는 detected_signals 참고.",
  "disclaimer": "ScamGuardian 은 사기 판정을 내리지 않습니다. 위 검출 신호의 학술·법적 근거를 참고해 통합 기업의 자체 판정 logic 으로 결정하세요.",
  "analysis_run_id": "..."
}
```

> ✅ **Stage 2·3 구현 완료** — 위 7 종 신호 모두 `pipeline/apk_analyzer.py` 의 `analyze_apk_static`
> (Lv 1) + `analyze_apk_bytecode` (Lv 2) 로 검출. Tier 1 (VirusTotal) 의 `malware_detected` /
> `phishing_url_confirmed` 와 함께 입력이 APK 면 Phase 0.6 에서 자동 호출.
>
> 한국 보이스피싱 패밀리 매핑:
>
> | 패밀리 | 강하게 매칭되는 신호 |
> |--------|---------------------|
> | **SecretCalls / SecretCrow** | `apk_call_state_listener`, `apk_accessibility_abuse`, `apk_dangerous_permissions_combo` |
> | **KrBanker** | `apk_suspicious_package_name`, `apk_accessibility_abuse`, `apk_impersonation_keywords` |
> | **MoqHao** | `apk_sms_auto_send_code`, `apk_dangerous_permissions_combo`, `apk_self_signed` |
>
> 학술 기준 정적 분석 검출률은 **60-80%**. 정교하게 난독화·packing·reflection 다 쓴
> APK 는 정적 분석 영역 밖이며, 그건 진짜 동적 분석 (future work) 자리.

### 2.3 `GET /api/result/{token}` — 결과 카드 백엔드

분석 결과의 토큰 기반 공개 페이지. 발급 시 1시간 TTL. 카카오 카드의 *자세히 보기*
링크가 호출. 다른 클라이언트도 자체 결과 페이지 만들 때 활용 가능.

```bash
curl https://api.example.com/api/result/abcd1234efgh5678
```

응답: `result` (`DetectionReport` 전체) + `flag_rationale` (검출된 신호별 근거·출처) +
`chat_history` (있으면) + `expires_at`. 만료 시 `410`.

### 2.4 `GET /api/methodology` — 검출 신호 카탈로그 + 학술/법적 근거

검출 가능한 위험 신호 카탈로그와 각 신호의 학술·법적 근거. 통합 기업이 자체 판정
logic 을 설계할 때 참조용. 인증 선택. **점수·등급 정보 없음** — `flags[]` 의 각 항목은
`{flag, label_ko, rationale, source}` 만 노출.

```bash
curl https://api.example.com/api/methodology | jq '.flags[:3]'
```

응답: `flags[]` (27종 플래그 + `rationale` + `source` 기관) + `risk_bands[]` +
`weights` (LLM 반영 비율) + `models` (사용 모델명).

---

## 3. Authentication

### 3.1 API key 발급 절차

1. 운영자가 `SCAMGUARDIAN_ADMIN_TOKEN` 환경변수 설정
2. 어드민 패널 (`/admin`) 또는 직접 호출:

```bash
curl -X POST https://api.example.com/api/admin/api-keys \
  -H "X-Admin-Token: $SCAMGUARDIAN_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "label": "discord-bot",
    "monthly_quota": 1000,
    "rpm_limit": 30,
    "monthly_usd_quota": 5.0
  }'
```

3. 응답의 `plaintext_key` (`sg_<urlsafe>`) 를 *한 번만* 노출 — DB 에는 sha256
   해시만 저장. 분실 시 revoke 후 재발급.

### 3.2 키 사용

두 헤더 중 하나로 전달:

```
Authorization: Bearer sg_xxx
X-API-Key: sg_xxx
```

선택 헤더:

- `X-User-Id` — 외부 클라이언트가 per-user 어뷰즈 누적이 필요할 때 사용 (디스코드
  user_id 등). 카카오 webhook 은 `userRequest.user.id` 가 자동 사용됨.
- `X-Request-Id` — 클라이언트 trace ID. 응답에도 같은 값 echo.

### 3.3 인증 적용 범위

`platform_layer/middleware.py` 가 path 패턴으로 4 카테고리 분류:

| 카테고리 | 패턴 | 인증 |
|---------|------|------|
| `require` | `/api/analyze`, `/api/analyze-upload` | API key 필수 |
| `optional` | `/api/result/`, `/api/methodology` | API key 선택 (있으면 사용량 기록) |
| `admin` | `/api/admin/*` (login 제외) | `SCAMGUARDIAN_ADMIN_TOKEN` 필수 |
| `skip` | `/webhook/`, `/health`, `/docs`, `/openapi`, `/redoc` | 인증 없음 |

---

## 4. Rate limit + cost

### 4.1 다단계 한도

`platform_layer/rate_limit.py` + `platform_layer/middleware.py` 가 키별 3중 cap 적용:

1. **분당 RPM** — 슬라이딩 윈도우 (`_WINDOW_SEC = 60.0`). 키 발급 시 `rpm_limit`
   필드 (기본 `30`).
2. **월별 USD cap** — `monthly_usd_quota` (기본 `5.0`). cost ledger 합산이 한도
   넘으면 차단.
3. **월별 호출 수** — `monthly_quota` (기본 `1000`). atomic 차감.

초과 시 `429 Too Many Requests` + `Retry-After` 헤더 + `code: rate_limit_rpm |
quota_monthly | quota_status:revoked` 등 세부 코드.

### 4.2 비용 단가 (`platform_layer/pricing.py`)

| Provider | 단가 |
|----------|------|
| Claude Sonnet 4.6 | input $3 / 1M tokens, output $15 / 1M tokens |
| Claude Haiku 4.5 | input $0.80 / 1M, output $4 / 1M |
| Claude Opus 4.7 | input $15 / 1M, output $75 / 1M |
| OpenAI Whisper | $0.006 / minute (audio) |
| Serper | ~$0.001 / query (basic plan) |
| VirusTotal Public | 무료 (4 req/min) |

> 가격은 외부 공급사 정책에 따라 변동된다. 운영 시점에 `pricing.py` 와 실제 청구서를
> 정기 비교하라.

### 4.3 어뷰즈 가드 (`platform_layer/abuse_guard.py`)

분석 endpoint 호출 *전* 단계에서 외부 API 비용을 방어:

| 가드 | 임계 |
|------|------|
| 입력 길이 cap | `MAX_CHARS = 5000` (`ANALYZE_MAX_TEXT_LENGTH` env override) |
| 입력 최소 | `MIN_CHARS = 2` |
| 반복 패턴 | 상위 3 글자 비율 > 80% 면 reject (`REPETITIVE`) |
| Gibberish | 한국어/영문/숫자 비율 < 50% 면 reject (`GIBBERISH`) |
| 중복 throttle | 5분 내 같은 입력 5회 (`DUPLICATE`) |
| 위반 누적 차단 | `VIOLATION_WARN_LIMIT = 3` 회 초과 → 1시간 (`BLOCK_DURATION_SEC = 3600`) BLOCK |

차단 상태에서 호출하면 `423 Locked`.

---

## 5. Error handling

### 5.1 HTTP status 매핑

| Status | 의미 | Body 예시 |
|--------|------|----------|
| `400` | 빈 입력 / 어뷰즈 reject (REPETITIVE/GIBBERISH/DUPLICATE) / DB 미설정 | `{"detail": {"code": "REPETITIVE", "message": "...", "detail": "..."}}` |
| `401` | API key 누락 또는 무효 | `{"detail": "API key 가 필요합니다", "code": "missing_or_invalid_api_key"}` |
| `403` | API key revoked | `{"detail": "API key 상태: revoked", "code": "key_revoked"}` |
| `409` | claim 충돌 / 학습 세션 취소 불가 | `{"detail": "다른 검수자가 이미 작업 중입니다."}` |
| `410` | 결과 토큰 만료 | `{"detail": "결과 링크가 만료됐어요"}` |
| `423` | 어뷰즈 누적 차단 — 1시간 후 재시도 | `{"detail": {"code": "BLOCKED", ...}}` |
| `429` | Rate limit / 월 cap 초과 — `Retry-After` 헤더 참조 | `{"detail": "분당 호출 한도를 초과했습니다.", "code": "rate_limit_rpm"}` |
| `501` | v4 draft endpoint — 미구현 | `{"detail": "v4 Live Call Guard is design preview only"}` |
| `503` | `SCAMGUARDIAN_ADMIN_TOKEN` 미설정 — 어드민 비활성 | `{"detail": "...어드민 접근이 비활성화..."}` |
| `500` | 파이프라인 내부 오류 | `{"detail": "..."}` |

### 5.2 카카오 webhook 전용 ErrorCode

`pipeline.kakao_formatter.ErrorCode` enum (11종) — 카카오 응답 본문 안 사용자
친화 메시지로 자동 매핑:

`API_CREDIT / SERVER_DOWN / STT_FAIL / TIMEOUT / LLM_UNAVAILABLE /
CALLBACK_REQUIRED / FILE_TOO_LARGE / EMPTY_INPUT / INVALID_URL /
PARSE_ERROR / UNKNOWN`

`api_server_pkg/kakao/commands.py:_classify_error()` 가 예외 메시지 키워드를
보고 자동 분류한다 — 직접 매핑할 일은 적다.

### 5.3 모든 응답에 trace ID

성공·실패 모두 응답 헤더에 `X-Request-Id` 가 echo 된다. 디버깅 시 클라이언트
로그와 서버 `request_log` 테이블을 같은 id 로 매칭하라.

---

## 6. v4 — Live Call Guard (draft)

> ⚠️ **Design preview only.** 현재 endpoint 는 모두 `501 Not Implemented` 반환.
> Schema 검토 + 외부 클라이언트 통합 설계용.

### 핵심 아이디어

사기 *후* 가 아닌 사기 *중* 차단. 사용자가 보이스피싱 의심 전화를 받는 순간
카톡으로 트리거 → 웹앱이 *사용자 본인 발화* 만 실시간 분석 → 위험 신호 감지 시
즉시 "전화 끊으세요!" 경보.

**왜 사용자 본인만**: 통신비밀보호법 + iOS 마이크 권한 + STT 잡음 문제를 한 번에
해결. 학술적으로도 새 영역 — 기존 연구는 모두 사기범 발화 분석. 이 시스템은
*피해자 측 compliance signal* 을 잡는다 (Cialdini 영향력 원리가 피해자 발화에서
어떻게 드러나는지).

### Endpoint 요약

| Endpoint | 역할 |
|---------|------|
| `POST /api/v4/stream/start` | 통화 세션 생성 (session_id 발급) |
| `POST /api/v4/stream/chunk` | 5초 PCM chunk 업로드 + 즉시 의도 분류 |
| `POST /api/v4/stream/end` | 통화 종료 + 사후 Phase 4–5 분석 |
| `GET  /api/v4/stream/{session_id}` | 세션 상태 조회 (폴링) |

### Schema 출처

- `experiments/v4_intent/classify_haiku.py` — `Label = META_AWARE |
  SENSITIVE_INFO | TRANSFER_AGREE | NORMAL`. Haiku 한 줄 의도 분류 결과 검증
  `experiments/v4_intent/results.md`.
- `experiments/v4_whisper/chunker.py` — `ChunkResult(index, start_sec, end_sec,
  text, latency_ms)`. 5초 chunk Whisper API 결과 검증
  `experiments/v4_whisper/results.md`.

### 구현 로드맵 (CLAUDE.md `v4 계획` 참조)

- **v4.0** — 사용자 발화 메타인식 표현 검출 (정규식 + Haiku). 5초 chunk Whisper
- **v4.1** — 누적 슬라이딩 윈도우 + Cialdini 신호 카탈로그
- **v4.2** — 통화 후 사후 검색 분석 + 카톡 결과 카드
- **v4.3** — iOS 호환성 검증 + 백그라운드 권한 우회 패턴

---

## Appendix: spec 동기화

서버 코드와 `docs/openapi.json` 을 일치시키려면:

```bash
python scripts/dump_openapi.py            # 갱신
python scripts/dump_openapi.py --check    # CI 용 — diff 시 비제로 종료
```
