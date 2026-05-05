# Stage 2 — APK 정적 분석 Lv 1 진짜 구현 (2026-05-05)

목적: Stage 1 narrative 의 Tier 2 (정적 Lv1) 를 실제 코드로. androguard 기반 manifest·
권한·서명 분석 → 3 종 검출 신호 (`apk_dangerous_permissions_combo`, `apk_self_signed`,
`apk_suspicious_package_name`) 추가. Stage 3 (Tier 3 bytecode) 는 다음.

## 작업 범위

### 건드릴 곳
- `requirements.txt` — `androguard` 추가
- `pipeline/apk_analyzer.py` — 신설, Lv 1 분석 함수
- `pipeline/config.py` — DETECTED_FLAGS / FLAG_LABELS_KO / FLAG_RATIONALE 에 3 종 신호 추가
- `pipeline/runner.py` — Phase 0.6 (APK 정적 분석) 통합
- `pipeline/signal_detector.py` — `apk_static_result` 인자 + 검출 로직
- `tests/test_apk_analyzer.py` — 신설, helper 함수 + 통합 contract
- `docs/openapi.json` — scripts/dump_openapi.py 재생성

### 안 건드릴 곳
- `pipeline/dex_pattern_analyzer.py` — Stage 3 (Lv 2)
- 동적 분석 — 결정대로 Lv 2 까지만
- `pipeline/kakao_formatter.py` — 검출 reframe 에서 이미 detected_signals 기반

## Step 1: 의존성
- [x] `requirements.txt` 에 androguard>=4.1.0 추가
- [x] `pip install androguard` (4.1.3 설치 확인)
- [x] import path 검증 — `androguard.core.apk.APK` + `androguard.misc.AnalyzeAPK`

## Step 2: pipeline/apk_analyzer.py (Lv 1 + Lv 2 통합)
- [x] `APKStaticReport` + `APKBytecodeReport` dataclass
- [x] **Lv 1**: `analyze_apk_static(apk_path)` — 위험 권한 4종 임계 / `_check_self_signed` (asn1crypto subject==issuer) / `_is_suspicious_impersonation` (정상 한국 앱 typo-squatting)
- [x] **Lv 2**: `analyze_apk_bytecode(apk_path)` — `AnalyzeAPK` 결과로 7 종 패턴 검출
  - `_has_method_xref` — SmsManager.sendTextMessage / TelephonyManager.listen / DevicePolicyManager.lockNow xref
  - `_references_accessibility_service` — AccessibilityService 상속
  - `_contains_string_keywords` — 사칭 키워드 (검찰·금감원·은행·안전계좌)
  - `_has_suspicious_url_constants` — IP 직접·무료 도메인·비표준 포트 regex
  - `_looks_obfuscated` — 1-2글자 클래스명 비율 + 클래스 50개 이상 임계
- [x] `is_apk_file(path)` — `.apk` 확장자 또는 `PK\x03\x04` ZIP magic
- [x] 정상 한국 앱 list 16 개 + 의심 suffix list 7 개 — 모두 명시적 list (magic number X)
- [x] 모든 분석 함수 try/except graceful — 실패 시 빈 detected_flags + error 필드

## Step 3: pipeline/config.py
- [x] `DETECTED_FLAGS` 에 10 종 추가 (Lv 1 × 3 + Lv 2 × 7)
- [x] `FLAG_LABELS_KO` 한국어 매핑 10 종
- [x] `FLAG_RATIONALE` 학술/법적 근거 10 종:
  - S2W TALON (SecretCalls·KrBanker·SecretCrow·MoqHao 보고서)
  - KISA (사이버 위협 인텔리전스 / 모바일 보안)
  - 안랩 보이스피싱 분석 리포트
  - 정보통신망법 제48조, 통신사기피해환급법 제2조 제2호, 형법 제283조
  - Cialdini (2021), Stajano & Wilson (2011)
  - Allix et al. (2016) AndroZoo, Wei et al. (2018), Mavroeidis & Bromander (2017)
  - OWASP Mobile Top 10, Android API Documentation

## Step 4: pipeline/signal_detector.py
- [x] `detect()` 시그니처에 `apk_static_result` + `apk_bytecode_result` 추가
- [x] Lv 1 → DetectedSignal (detection_source="static_lv1")
- [x] Lv 2 → DetectedSignal (detection_source="static_lv2")
- [x] `DETECTED_FLAGS` 외 flag 무시 (환각 차단)
- [x] dedupe (같은 flag 가 양쪽에서 들어와도 1번만)
- [x] `DetectionReport` 에 `apk_static_check` + `apk_bytecode_check` 필드 추가

## Step 5: pipeline/runner.py
- [x] `apk_analyzer` import
- [x] Phase 0.6 (Phase 0.5 sandbox 직후 / Phase 1 STT 직전)
  - `is_apk_file(source)` 감지
  - Lv 1 + Lv 2 순차 호출, 각각 try/except graceful
  - StepLog "APK" 로 lv1_flags + lv2_flags 카운트 기록
- [x] signal_detector.detect() 호출 시 두 result 전달

## Step 6: 테스트
- [x] tests/test_apk_analyzer.py 신설 — 55 테스트:
  - `is_apk_file` (5): 확장자·magic bytes·missing·directory·text 거부
  - `_is_suspicious_impersonation` (12 parametrize): 정상 일치 vs typo-squatting vs suffix
  - 합성 minimal APK fixture (2): parse 실패에도 graceful return contract
  - schema 키 검증 (2): `total_score`/`risk_level` 절대 없음
  - signal_detector 통합 (4): static/bytecode → DetectedSignal, dedupe, 환각 차단
  - 매핑 검증 (30 parametrize): 10 flag × (DETECTED_FLAGS 멤버 + FLAG_LABELS_KO + FLAG_RATIONALE rationale·source)
- [x] **pytest -q → 169 passed** (직전 114 + 신규 55)

## Step 7: docs
- [x] `scripts/dump_openapi.py` 재실행 → 33 endpoint, 75,938 bytes
- [x] `CLAUDE.md` Tier 2/3 — *미구현* 표시 → 실제 동작 (function 명·flag 명 명시) 으로 갱신
- [x] `README.md` 동일 — *(Stage 2 — 미구현)* / *(Stage 3 — 미구현)* 표시 제거
- [x] `INTEGRATION_GUIDE.md` 의 7 신호 예시 헤더 — "Stage 2·3 미구현" → "Stage 2·3 구현 완료" + 동작 메커니즘 명시

## Step 8: lessons.md (4 신규 패턴)
- [x] **패턴 5**: 한국 보이스피싱 APK 검출은 시그니처+정적+심화정적 3-tier 가 학술 표준
- [x] **패턴 6**: bytecode 패턴은 단독 신호로 약함, 누적+조합으로만 강함 — 5 종 false positive 시나리오 명시
- [x] **패턴 7**: "동적 분석" vs "심화 정적 분석" 학술 용어 정확히 구분
- [x] **패턴 8**: androguard LGPL — 동적 링크 OK, fork/embed 는 라이선스 의무

## 검증
- [x] `pytest -q` → **169 passed, 0 failed**
- [x] `python -c "from api_server import app"` → boot OK, 39 routes
- [x] `from pipeline.apk_analyzer import ...` 모든 심볼 import OK
- [x] 합성 minimal APK fixture (parse 불가능한 invalid manifest) 던져서 graceful (error 필드만 채워짐) 확인
- [x] 10 APK flag × 3 (DETECTED_FLAGS + FLAG_LABELS_KO + FLAG_RATIONALE) = 30 매칭 확인
- [x] Forbidden Actions 위반 0: "차단합니다" / "production-grade" / "위험 점수" 신규 추가 0건

## 주의 (CLAUDE.md Forbidden Actions)
- ❌ 점수·등급 신규 추가 X — Stage 2 reframe 이후 절대 X
- ❌ "production" / "차단합니다" / "100% 잡는다" X
- ❌ magic number X — 모든 임계는 명시적 list
- ✅ FLAG_RATIONALE 신규 3 종은 학술/법적 근거 (S2W TALON / KISA / 정보통신망법 / Cialdini) 동반 필수

## Review (2026-05-05) — Stage 2/3 통합 (APK 정적 분석 Lv 1 + Lv 2)

### 산출물

**신설 (3 파일)**:
- `pipeline/apk_analyzer.py` (~340 줄) — `APKStaticReport` + `APKBytecodeReport` + `analyze_apk_static()` + `analyze_apk_bytecode()` + `is_apk_file()` + helper 7 종
- `tests/test_apk_analyzer.py` (~270 줄, 55 테스트) — unit + integration + schema contract + 매핑 검증

**수정 (5 파일)**:
- `requirements.txt` — `androguard>=4.1.0`
- `pipeline/config.py` — `DETECTED_FLAGS` × 10 / `FLAG_LABELS_KO` × 10 / `FLAG_RATIONALE` × 10 추가
- `pipeline/signal_detector.py` — `detect()` 시그니처 확장 + DetectionReport 에 `apk_static_check`/`apk_bytecode_check` 필드
- `pipeline/runner.py` — Phase 0.6 (Lv 1 + Lv 2) 통합
- `CLAUDE.md` + `README.md` + `docs/INTEGRATION_GUIDE.md` + `tasks/lessons.md` — 미구현 표시 → 실제 동작 + 4 신규 패턴

### 핵심 metric

| 항목 | 결과 |
|------|------|
| pytest | **169 passed, 0 failed** (114 → +55) |
| 새 검출 신호 | 10 종 (Lv 1 × 3 + Lv 2 × 7) |
| 학술 출처 동반 | 10/10 — 모든 신호에 `rationale` + `source` (S2W TALON / KISA / 정보통신망법 / Cialdini / Stajano-Wilson / OWASP / Allix·Wei 학술 논문) |
| 서버 부팅 | OK, 39 routes |
| openapi.json | 33 endpoint, 75,938 bytes |
| Forbidden Actions 위반 | 0 — "차단합니다" / "production-grade" / "위험 점수" 신규 추가 0건 |

### 학술 정직성 (핵심 boundary)

- **"심화 정적 분석" 용어 일관 사용** — "동적 분석" 단어 신규 사용 0건. CLAUDE.md / README / INTEGRATION_GUIDE / apk_analyzer.py 모두 "정적 분석 / bytecode pattern matching" 으로 정확히 표기
- **false positive 한계 명시** — apk_analyzer.py 모듈 docstring + FLAG_RATIONALE 본문 + lessons.md 패턴 6 에 "정상 메신저 앱도 SmsManager 사용 / 정상 앱도 Accessibility 사용 / 단독 신호로는 약함" 명시
- **"단일 신호로 사기 판정 X"** — signal_detector / kakao_formatter 가 누적 신호만 보고, 판정은 통합 기업 (Identity Boundary 일관)
- **검출률 60-80% 정직 표현** — README + CLAUDE.md 학술 인용 (Allix et al. 2016 / Wei et al. 2018) 동반

### Identity Boundary 준수

- ❌ 점수·등급 응답에 노출 0 — 10 신호 모두 검출 사실 + rationale + source 만
- ❌ "위험 점수 X점" / "안전·의심·위험 등급" 신규 추가 0
- ❌ "100% 잡는다" / "production-grade" / "차단합니다" 0
- ❌ magic number 신규 0 — 모든 임계 (`_DANGEROUS_PERMISSION_THRESHOLD = 4`, `_OBFUSCATION_RATIO_THRESHOLD = 0.30` 등) 명시적 named constant
- ✅ FLAG_RATIONALE 신규 10 종은 모두 학술/법적 근거 (Cialdini 2021 / Stajano-Wilson 2011 / Allix 2016 / Wei 2018 / S2W TALON / KISA / 정보통신망법 / 통신사기피해환급법 / 형법 / Android API Doc / OWASP) 동반

### 의도적으로 *안* 한 것

- **진짜 동적 분석 stub 0** — 사용자 명시 결정 (Lv 2 까지만)
- **에뮬레이터 통합 0** — future work 영역, 호스트 위험 + 5-7주 작업
- **악성 APK 샘플 commit 0** — 합성 minimal APK fixture 만, 진짜 샘플은 KISA 수동 fetch (gitignore)
- **카카오 카드 포맷 변경 0** — 직전 detection reframe 에서 이미 detected_signals 기반

### 미해결 (다음 stage 후보)

- 실제 악성 APK 샘플 (KISA 공개 분석 자료) 으로 검출 정확도 측정 — 별도 fixture 디렉토리 + gitignore 정책 필요
- false positive 측정 — Play Store 정상 앱 (카카오톡 / 네이버 / 은행 앱) 던져서 어떤 신호가 잘못 검출되는지 통계
- Phase 0.6 의 timeout 정책 — 매우 큰 APK (>100MB) 에서 AnalyzeAPK 가 분 단위 걸릴 수 있음, signal 처리로 cap 필요
- `runner.py` 의 source detection — 현재 `is_apk_file()` 만, MIME type / 다운로드 후 검사 등 더 견고한 routing
