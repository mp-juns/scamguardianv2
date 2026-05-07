# ScamGuardian — 검출 신호 학술·법적 근거 + 코드 매핑

**문서 버전**: v1.5 (2026-05-06) — 자문·심사용 친절판 (정중체)
**용도**: 자문 미팅 · 학부 졸업 발표 · 졸업 심사용 *단일 참고서*
**작성 원칙**: 영어 줄임말·전문 용어가 처음 등장할 때마다 한국어로 풀어쓰며, 각 학술·법령 인용이 *우리 코드의 어디에 박혀 있는지* 끝에 명시합니다.

**v1.5 변경 사항**:
1. **카테고리 E (한국 표적 신호) 복원** — 카카오톡 위장 / 택배 SMS / 청첩장 / 부고장 / 금융기관 사칭 5개 한국 공격 시나리오를 *개념 인덱스*로 §5 에 복원하고, 각각을 코드의 *기존 실존 flag* (`apk_suspicious_package_name`, `impersonation_family`, `smishing_link_detected`, `prepayment_requested`, `fss_not_registered`, `fake_government_agency`) 에 정확히 매핑.
2. **§10.2 한국 법령 일람 일관성 보완** — 본문 인용 법령 vs 일람 누락 항목 5개 추가 (특정금융정보법, 대부업법, 직업안정법, 약사법, 전기통신사업법).
3. **§8 (Lv 3 동적 분석) narrative 강화** — *interface-first* 설계 의도 명시 (§8.0 신규), §8.1~§8.5 각 신호 헤더에 구현 상태 표기 (🚧 인터페이스 정의 완료 / 외부 격리 VM 통합 시 작동), §0.7 표 last row 갱신.
4. **카테고리 시프트** — v1.4 §5 (APK Lv 1) → v1.5 §6, §6 (Lv 2) → §7, §7 (Lv 3) → §8, §8 (가이드라인) → §9, §9 (Bibliography) → §10, §10 (Caveats) → §11. 본문 cross-reference 도 함께 갱신.

---

## 0. 개요

### 0.1 이 문서의 목적

ScamGuardian 이 검출하는 모든 위험 신호 (`detected_signals` — *"검출된 신호 목록"*) 각각에 대해 다음 네 가지를 한 곳에 정리한 참고서입니다.

1. **학술 근거** — 동료 평가 (peer-review · *전문가 심사를 거친 학술지*) 논문 또는 단행본
2. **한국 법령 근거** — 위반 시 처벌 조항
3. **정부·산업 보고서 근거** — 통계·사례
4. **🔗 코드 매핑** — 이 근거가 *어떤 파일·어떤 검출 신호에 박혀 있는지*

### 0.2 이 시스템의 정체성 (가장 중요합니다)

**ScamGuardian 은 "사기다/아니다" 판정을 내리는 시스템이 아닙니다.**

VirusTotal (*바이러스토탈* — 한 번에 70개 백신 엔진 결과를 모아 보여주는 무료 사이트) 이 *"이 파일은 멀웨어다"* 라고 단정하지 않고 *각 백신의 검출 결과만 모아서 표시* 하는 것과 같은 모델입니다.

```
❌ "이 메시지는 사기다"
✅ "이 메시지에서 다음 N 개의 위험 신호가 검출되었습니다.
    각 신호의 학술·법적 근거는 다음과 같습니다."
```

판정 (verdict — *"이건 사기다" 같은 결론*) 은 우리 시스템을 통합한 기업 (예: 통신사·은행·메신저 앱) 이 자기 서비스 정책에 맞게 내립니다.

### 0.3 본 문서의 인용 표준

- **학술 논문** — 저자(연도). 제목. 학술지명, 권(호), 쪽수. DOI/URL 을 동반합니다.
  - DOI (Digital Object Identifier · *논문 영구 식별자*) 는 [doi.org](https://doi.org/) 를 통해 항상 원문에 접근 가능합니다.
- **단행본** — 저자(연도). 제목 (판). 출판사 — Chapter (장) 단위로 인용합니다.
- **한국 법조항** — 「법명」 제N조 제M항 — [국가법령정보센터(law.go.kr)](https://www.law.go.kr/) 에서 조회 가능합니다.
- **정부·산업 보고서** — 기관 / 보고서명 / 발간연월 — 가능한 한 원문 URL 을 동반합니다.

### 0.4 학회·저널 약어 풀이 (이 문서에서 자주 등장합니다)

| 약어 | 풀이 | 분야 |
|---|---|---|
| **CACM** | Communications of the ACM (美 컴퓨터학회 *월간 회보*) | 컴퓨터과학 종합 |
| **ACM CCS** | Conference on Computer and Communications Security (ACM *컴퓨터·통신 보안 학회*) | 시스템 보안 최상위 |
| **NDSS** | Network and Distributed System Security *Symposium* (네트워크·분산시스템 보안 심포지엄) | 네트워크 보안 최상위 |
| **IEEE S&P** | IEEE Symposium on Security and Privacy (*"오클랜드 학회"* 로도 불립니다) | 보안·프라이버시 최상위 |
| **USENIX Security** | USENIX Security *Symposium* | 시스템 보안 최상위 4대 |
| **WWW** | The Web Conference (*"웹 컨퍼런스"*, 옛 WWW Conference) | 웹 기술 최상위 |
| **ACSAC** | Annual Computer Security Applications Conference (연례 *응용 보안 학회*) | 산업 응용 보안 |
| **MobiSys** | International Conference on Mobile Systems, Applications, and Services (*모바일 시스템 응용 학회*) | 모바일 시스템 최상위 |
| **ICML** | International Conference on Machine Learning (*머신러닝 국제 학회*) | AI/머신러닝 최상위 |
| **RAID** | International Symposium on Research in Attacks, Intrusions, and Defenses (*공격·침입·방어 연구 심포지엄*) | 침입탐지 |
| **BJC** | The British Journal of Criminology (*영국 범죄학 저널*) | 범죄학 최상위 |
| **OBHDP** | Organizational Behavior and Human Decision Processes (*조직 행동과 인간 의사결정 학술지*) | 행동경제학 |
| **SSRN** | Social Science Research Network (*사회과학 연구 네트워크*, 사전논문 저장소) | 학제 간 |

> 위 약어들은 모두 컴퓨터·범죄학·심리학 분야의 *최상위 학회/저널* 입니다. 학술 인용에서 가장 권위 있는 출처입니다.

### 0.5 자주 쓰는 전문 용어 풀이

| 용어 | 풀이 |
|---|---|
| **API** (Application Programming Interface) | *프로그램끼리 통신할 때 사용하는 약속된 인터페이스* |
| **OTP** (One-Time Password) | *일회용 비밀번호* — 은행 인증 시 받는 6자리 숫자 |
| **C&C 서버** (Command-and-Control) | *해커가 멀웨어를 원격 조종하는 명령·제어 서버* |
| **APK** (Android Package) | *안드로이드 앱 설치 파일* (`.apk` 확장자) |
| **dex** (Dalvik Executable) | *안드로이드 앱 안의 실행 코드* — 자바 컴파일 결과 |
| **bytecode** | *기계어 직전의 중간 코드* — 사람도 어느 정도 읽을 수 있습니다 |
| **xref** (Cross-Reference) | *코드 안에서 어떤 함수가 호출되는 지점들* |
| **manifest** (`AndroidManifest.xml`) | *앱이 요구하는 권한·구성 요소를 선언한 파일* |
| **CA** (Certificate Authority) | *공인 인증서를 발급하는 기관* (예: 한국정보인증) |
| **typosquatting** | *오타 유도 위장 도메인* — 예: `kakaotalkk.com` (가짜) vs `kakaotalk.com` (진짜) |
| **smishing** (SMS + phishing) | *문자 메시지 피싱* — 가짜 링크 클릭 유도 |
| **drive-by download** | *클릭 안 해도 페이지 열리자마자 자동 다운로드* — 악성 |
| **cloaking** | *봇과 사람에게 다른 페이지를 보여주는 수법* — 검색엔진을 속입니다 |
| **obfuscation** | *난독화* — 코드를 일부러 읽기 어렵게 변환합니다 |
| **peer-review** | *동료 평가* — 학술 논문의 표준. 같은 분야 전문가 2-3명이 *익명으로* 검증합니다 |
| **defense in depth** | *다층 방어* — 여러 층의 검사가 겹쳐서 한 층이 뚫려도 다음 층이 잡습니다 |

### 0.6 거짓 양성 (false positive) 의 정직한 표시

검출 신호 중 일부는 *정상 콘텐츠에서도 흔히 나타납니다*. 단독 사용 시 **거짓 양성** (false positive — *정상인데 위험으로 잘못 판단*) 위험이 큽니다.

- `apk_self_signed` (자체 서명) — 정상 사이드로딩 앱도 자체 서명을 사용합니다
- `apk_string_obfuscation` (난독화) — 정상 앱도 ProGuard 같은 표준 도구를 사용합니다
- `suspicious_writing_style` (이상한 문체) — 정상 외국인이 쓴 한국어일 수 있습니다
- `ai_generated_content_suspected` (AI 생성 의심) — 정상 AI 활용 콘텐츠가 가능합니다

이런 신호는 **다른 강한 신호와 결합 시점에서만** 의미가 있습니다 — *예: 자체 서명 + 위험 권한 4개 + 사칭 키워드 동시* 면 신뢰도가 매우 높아집니다.

### 0.7 코드에서 학술 근거가 어떻게 흐르는지

```
①  학술 논문·법령 인용
        ↓
②  pipeline/config.py 의 FLAG_RATIONALE 사전(dictionary)에 박힙니다.
    예: FLAG_RATIONALE["urgent_transfer_demand"] = {
            "rationale": "Stajano-Wilson 2011 의 Time Principle ...",
            "source": "CACM 54(3) / 통신사기피해환급법 제2조 제2호"
        }
        ↓
③  pipeline/signal_detector.py 가 검출 결과를
    DetectedSignal(flag, label_ko, rationale, source, ...) 객체로 변환합니다.
        ↓
④  pipeline/runner.py 가 전체 분석을 실행하고
    DetectionReport.detected_signals[] 로 모읍니다.
        ↓
⑤  외부 API 응답:
    POST /api/analyze 의 detected_signals[] 필드
    GET /api/result/{token} 의 flag_rationale 필드
    GET /api/methodology 의 flags[] 카탈로그
        ↓
⑥  사용자 화면:
    apps/web/src/app/result/[token]/page.tsx 의 검출 신호 카드
    카카오 챗봇 응답 카드
```

**검출이 일어나는 단계별 코드 위치**:

| 단계 | 코드 모듈 | 검출하는 신호 |
|---|---|---|
| Phase 0 (안전성) | `pipeline/safety.py` | `malware_detected`, `phishing_url_confirmed`, `suspicious_*_signal` |
| Phase 0.5 (격리 브라우저 분석) | `pipeline/sandbox.py` | `sandbox_password_form_detected`, `sandbox_auto_download_attempt` 외 |
| Phase 0.6 — APK 정적 Lv 1 | `pipeline/apk_analyzer.analyze_apk_static` | `apk_dangerous_permissions_combo`, `apk_self_signed`, `apk_suspicious_package_name` |
| Phase 0.6 — APK 심화 정적 Lv 2 | `pipeline/apk_analyzer.analyze_apk_bytecode` | `apk_sms_auto_send_code`, `apk_call_state_listener`, `apk_accessibility_abuse` 외 |
| Phase 0.6 — APK 동적 Lv 3 *(interface-first)* | `pipeline/apk_analyzer.analyze_apk_dynamic` | `apk_runtime_*` 5종 — interface 만 박혀 있으며, 외부 격리 가상머신 통합은 future work 입니다. 로컬 실행은 5단계 enum (`APKDynamicStatus`) 으로 영구 차단됩니다 |
| Phase 4 (인터넷 교차 검증) | `pipeline/verifier.py` | `urgent_transfer_demand`, `fake_government_agency`, `phone_scam_reported` 외 텍스트 신호 |
| LLM 보조 검출 | `pipeline/llm_assessor.py` | LLM 이 추가 제안하며, 신뢰도 임계값 (0.75) 통과 시 채택됩니다 |

---

## 1. 카테고리 A — 사기범의 행동 패턴 (심리학·범죄학 기반)

### 1.1 `urgent_transfer_demand` — 즉각 송금·이체 요구

**우리가 검출하는 것**: 통화·메시지에서 *"지금 즉시 송금하세요" / "10분 안에 이체"* 같은 패턴입니다.

**왜 위험한가 (학술 근거)**:

📖 **Stajano & Wilson (2011)** — *"Understanding scam victims: seven principles for systems security"* (사기 피해자 이해: 시스템 보안의 7원칙)
- 학술지: **CACM** (美 컴퓨터학회 월간 회보), 54권 3호, 70–75쪽
- DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)
- 핵심 인용 (저자의 §"Time Principle" — 시간 원칙):
  > *"중요한 결정을 시간 압박 아래에서 내릴 때, 사람은 평소와 다른 *덜 합리적인* 의사결정 전략을 쓰게 되며, 사기범은 피해자를 그 방향으로 유도합니다."*
- 풀이: *시간이 없다고 생각하면 머리가 멈춥니다. 사기꾼은 일부러 그 상태로 몰아넣습니다.*

📖 **Cialdini (2021)** — *"Influence: The Psychology of Persuasion"* (영향력: 설득의 심리학, 신판 확장본)
- 단행본, Harper Business 출판
- Chapter 7 "Scarcity" (희소성) — *"한정 시간 압박"* 절
- 풀이: *"오늘만 할인" 같은 한정 시간 표현이 왜 사람을 움직이게 만드는지에 대한 심리학적 메커니즘입니다.*

📖 **Loewenstein (1996)** — *"Out of control: Visceral influences on behavior"* (통제 불능: 의사결정에 미치는 본능적 영향)
- 학술지: **OBHDP** (조직 행동과 인간 의사결정 학술지), 65권 3호
- DOI: [10.1006/obhd.1996.0028](https://doi.org/10.1006/obhd.1996.0028)
- 풀이: *공포·욕망·시간 압박 같은 "본능적 자극(visceral)" 이 합리적 판단을 어떻게 마비시키는지 설명하는 행동경제학 모델입니다.*

**한국 법령**:

⚖️ [통신사기피해환급법 제2조 제2호](https://www.law.go.kr/법령/전기통신금융사기피해방지및피해금환급에관한특별법) — *"전기통신금융사기란 전기통신을 이용해 타인을 기망(속임)·공갈(협박)하여 자금을 송금·이체하도록 하는 행위입니다."*
⚖️ [형법 제347조 제1항(사기)](https://www.law.go.kr/법령/형법) — *"사람을 속여 재물을 받거나 재산상 이익을 취득"* — 10년 이하 징역에 해당합니다.
⚖️ 통신사기피해환급법 제15조의2 제1항 — *전기통신금융사기 가해자는 1년 이상 유기징역에 처해집니다.*

**정부·산업 보고서**:

📊 **금융감독원** [「2023년 보이스피싱 피해현황 분석」](https://www.fss.or.kr/), 2024.03 — 피해액 **1,965억 원** (전년 대비 +35.4%), 1인당 평균 1,700만 원입니다.
📊 **FBI** [*2024 Internet Crime Report*](https://www.ic3.gov/AnnualReport/Reports/2024_IC3Report.pdf) (미국 연방수사국 *인터넷 범죄 신고센터* 연간 보고서), 2025.04 — 피싱·사칭 피해 $16.6B (33% 증가) 규모입니다.

**🔗 우리 코드의 어디**:
- 검출 신호 키: `urgent_transfer_demand` (한국어 라벨: *"즉각 송금·이체 요구"*)
- 학술 근거 박힘: `pipeline/config.py` 의 `FLAG_RATIONALE["urgent_transfer_demand"]` 사전에 들어 있습니다.
- 검출 코드: `pipeline/verifier.py` — Serper 검색으로 키워드·패턴을 매칭합니다.
- 응답 노출: `/api/analyze` 결과의 `detected_signals[]` 항목에 학술 근거(`rationale`) 와 출처(`source`) 가 함께 노출됩니다.

---

### 1.2 `fake_government_agency` — 공권력·금융기관 사칭

**우리가 검출하는 것**: 검찰·경찰·금감원·국세청·은행 등 *공적 권위 기관* 을 사칭하는 패턴입니다.

**왜 위험한가**:

📖 **Cialdini (2021), Chapter 6 "Authority: Directed Deference"** — *"권위: 지시받은 복종"*
- 풀이: *제복·직함·말투만으로 사람들이 의심을 멈추는 심리* (예: 경찰관이라며 신분증을 보여주면 진위 확인을 안 하게 됩니다).

📖 **Stajano & Wilson (2011)** — §"Social Compliance Principle" (사회적 순응 원칙, **CACM 54권 3호** pp.71–72). DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)
- 핵심 인용:
  > *"사회는 사람들에게 권위에 의문을 던지지 않도록 훈련시킵니다. 사기꾼은 이 '의심 정지' 를 악용합니다."*

📖 **Modic & Lea (2013)** — *"Scam compliance and the psychology of persuasion"* (사기 순응과 설득의 심리학)
- **SSRN** (사회과학 연구 네트워크 사전논문 저장소). DOI: [10.2139/ssrn.2364464](https://doi.org/10.2139/ssrn.2364464)

**한국 법령**:

⚖️ [형법 제225조 (공문서 위조)](https://www.law.go.kr/법령/형법), 제227조 (허위공문서작성), 제230조 (공문서 부정행사)
⚖️ 통신사기피해환급법 제2조 제2호 / 제15조의2 제1항
⚖️ 「특정경제범죄 가중처벌 등에 관한 법률」 제3조 — *피해 5억 원 이상이면 가중처벌됩니다.*

**정부·산업 보고서**:

📊 **경찰청 국가수사본부** [「2025년 1분기 보이스피싱 현황」](https://www.police.go.kr/), 2025.04.27 — 기관사칭형 **51%** (2,991건), 50대 이상 피해자 53% 입니다.
📊 **금융감독원** 「2023년 보이스피싱 피해현황 분석」 — 정부기관 사칭형 **31.1%** 입니다.
📊 **S2W TALON** (한국 보안 회사 *위협 인텔리전스* 팀) [*"Detailed Analysis of HeadCalls: Impersonation of Korean Public and Financial Institutions"*](https://medium.com/s2wblog), 2025.08

**🔗 우리 코드의 어디**:
- 신호: `fake_government_agency` (*"정부기관 사칭"*)
- 학술 근거: `pipeline/config.py:FLAG_RATIONALE["fake_government_agency"]` 에 Cialdini Authority + 형법 제225조 인용이 박혀 있습니다.
- 검출: `pipeline/verifier.py` (인터넷 검색 교차 검증) 와 `pipeline/llm_assessor.py` (LLM 의미 분석) 에서 수행됩니다.

---

### 1.3 `threat_or_coercion` — 협박·강요 발화

**우리가 검출하는 것**: *"체포된다 / 계좌 동결된다 / 고발하겠다"* 등 공포 고지로 의사결정을 마비시키는 패턴입니다.

**왜 위험한가**:

📖 **Whitty (2013)** — *"The scammers persuasive techniques model"* (사기꾼의 설득 기법 모델)
- 학술지: **BJC** (영국 범죄학 저널), 53권 4호, 665–684쪽
- DOI: [10.1093/bjc/azt009](https://doi.org/10.1093/bjc/azt009)
- §"Stage 4: The Sting" (4단계: 결정타) — *위기를 만들어 즉시 행동하게 만듭니다.*

📖 **Witte (1992)** — *"Putting the fear back into fear appeals"* (공포 호소에 공포를 다시 넣다)
- *EPPM* (Extended Parallel Process Model — 확장 병렬 처리 모형) 이론
- 학술지: Communication Monographs (커뮤니케이션 학술지), 59권 4호
- DOI: [10.1080/03637759209376276](https://doi.org/10.1080/03637759209376276)
- 풀이: *공포 메시지가 어떤 조건에서 행동을 *강제* 하는지 설명하는 표준 모형입니다.*

📖 **Langenderfer & Shimp (2001)** — *"Consumer vulnerability to scams, swindles, and fraud: A new theory of visceral influences on persuasion"* (소비자의 사기 취약성: 본능적 영향이 설득에 미치는 새 이론)
- 학술지: Psychology & Marketing (심리학과 마케팅), 18권 7호. DOI: [10.1002/mar.1029](https://doi.org/10.1002/mar.1029)

**한국 법령**:

⚖️ [형법 제283조 (협박)](https://www.law.go.kr/법령/형법) — *3년 이하 징역, 500만 원 이하 벌금에 해당합니다.*
⚖️ 형법 제350조 (공갈) — *협박 + 재산상 이익 = 가중처벌됩니다.*
⚖️ 통신사기피해환급법 제2조 제2호 (기망·공갈을 명시적으로 포함합니다)

**🔗 코드 매핑**:
- 신호: `threat_or_coercion`
- `pipeline/config.py:FLAG_RATIONALE["threat_or_coercion"]` 에 *형법 제283조 + Witte EPPM 인용* 이 박혀 있습니다.
- 검출은 `pipeline/verifier.py` 와 LLM 보조에서 수행됩니다.

---

### 1.4 시간 압박 (`urgent_transfer_demand` 와 통합됩니다)

학술 근거는 위 1.1 과 동일합니다 (Stajano-Wilson Time Principle / Cialdini Scarcity / Loewenstein visceral). 별도 flag 없이 LLM 이 컨텍스트로 검출합니다.

---

### 1.5 `medical_claim_unverified` — 미인증 의료 효능 주장 (사회적 증거 조작 포함)

**우리가 검출하는 것**: *"이 약 먹으면 암이 낫는다 / 당뇨가 사라진다"* 같은 식약처 미인증 효능 주장 + *가짜 후기·추천* 결합 패턴입니다.

**왜 위험한가**:

📖 **Cialdini (2021), Chapter 4 "Social Proof: Truths Are Us"** — *사회적 증거: 다른 사람들이 그렇다 하면 우리도 그렇다고 믿는 심리*
📖 **Stajano & Wilson (2011)** §"Herd Principle" (군중 원칙, **CACM 54(3)** p.72) — *짜고 친 가짜 계정* (shills, sock-puppets, astroturfing, Sybil attack 등). DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)

**한국 법령**:

⚖️ 약사법 제68조 — *허위·과대 광고를 금지합니다.*
⚖️ 식품의약품안전처 부당 광고 단속 지침
⚖️ 표시·광고 공정화법 제3조 제1항 제1·2호 / 제17조 제1호 (2년 이하 징역 또는 1억5천만 원 이하 벌금)

**🔗 코드 매핑**: `medical_claim_unverified` — `pipeline/config.py:FLAG_RATIONALE["medical_claim_unverified"]` 에 약사법 + Cialdini Social Proof 인용이 박혀 있습니다.

---

### 1.6 `impersonation_family` / `romance_foreign_identity` — 가족·연인 위장

**우리가 검출하는 것**:
- `impersonation_family`: *"엄마 나야"* 형 메신저피싱입니다.
- `romance_foreign_identity`: 해외 군인·의사·외교관 등 신분 위장 로맨스 스캠입니다.

**왜 위험한가**:

📖 **Whitty (2013)** — *"The Scammers Persuasive Techniques Model"* — *7단계 모델*: 동기부여 → 프로파일링 → 그루밍(친밀감 형성) → 결정타 → 지속 → (성적 학대) → 재피해. **BJC 53(4)**. DOI: [10.1093/bjc/azt009](https://doi.org/10.1093/bjc/azt009)
- 풀이: *로맨스 스캠이 짧은 사기가 아니라 몇 달에 걸친 **단계적 설득** 임을 학술적으로 모델링한 논문입니다.*

📖 **Whitty & Buchanan (2012)** — *"The online romance scam: A serious cybercrime"*. CyberPsych & Behavior, 15(3). DOI: [10.1089/cyber.2011.0352](https://doi.org/10.1089/cyber.2011.0352)
📖 **Whitty & Buchanan (2016)** — *"The online dating romance scam: psychological impact"*. Criminology & Criminal Justice, 16(2). DOI: [10.1177/1748895815603773](https://doi.org/10.1177/1748895815603773)
📖 **Cialdini (2021), Chapter 5 "Liking"** — *"호감 원칙"* — *공통점·칭찬·협력으로 신뢰를 형성합니다.*

**한국 법령**:
⚖️ 통신사기피해환급법 제2조 제2호 (메신저피싱 포섭)
⚖️ 형법 제347조 사기

**정부·산업 보고서**:
📊 금감원 「2023년 보이스피싱 피해현황 분석」 — 가족·지인 사칭 메신저피싱 **33.7%** (2위) 입니다.
📊 FBI [*IC3 2024*](https://www.ic3.gov/AnnualReport/Reports/2024_IC3Report.pdf) — Romance/Confidence 가 별도 카테고리이며, 60대 이상에서 최다 피해가 나옵니다.

**🔗 코드 매핑**:
- `impersonation_family` → `pipeline/config.py:FLAG_RATIONALE["impersonation_family"]` (Cialdini Liking + Whitty 인용)
- `romance_foreign_identity` → `FLAG_RATIONALE["romance_foreign_identity"]` (Whitty 7-stage 모델 + FBI IC3)
- 검출은 `pipeline/verifier.py` 와 `pipeline/llm_assessor.py` 에서 이루어집니다.

---

## 2. 카테고리 B — 거래·상거래 신호

### 2.1 `abnormal_return_rate` — 비정상 수익률 약속

**우리가 검출하는 것**: *"월 10% 수익 / 일 1% 보장"* 등 시장 평균을 크게 초과하는 수익률 약속입니다.

**왜 위험한가**:

📖 **Stajano & Wilson (2011)** §"Need and Greed Principle" (필요와 욕심 원칙, **CACM 54(3)** p.73). DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)
- 핵심 인용: *"너무 좋아 보이면, 사실은 사기일 가능성이 매우 높습니다."* — 사기 인식의 표준 격언

📖 **Lea, Fischer, & Evans (2009)** — [*"The Psychology of Scams: Provoking and Committing Errors of Judgement"*](https://webarchive.nationalarchives.gov.uk/ukgwa/20140402142426/http://www.oft.gov.uk/shared_oft/reports/consumer_protection/oft1070.pdf) (OFT1070)
- **OFT** (Office of Fair Trading — *영국 공정거래청*) 보고서

📖 **Frankel (2012)** — *"The Ponzi Scheme Puzzle"* (폰지 사기의 수수께끼). Oxford University Press 단행본
- 풀이: *원금보장 + 고수익 = 폰지 사기 (Ponzi scheme — 후속 투자금으로 앞 투자자에게 수익을 지급) 의 핵심 패턴입니다.*

**한국 법령**:

⚖️ [유사수신행위의 규제에 관한 법률 제2조 제1·2호](https://www.law.go.kr/법령/유사수신행위의규제에관한법률) — *원금 또는 그 이상 지급 약정을 금지합니다*. 제3조 (금지) / 제6조 제1항 (5년 이하 징역 또는 5천만 원 이하 벌금) — **2024.05.28 시행 개정으로 가상자산이 포함되었습니다.**
⚖️ 자본시장법 제17조 (미등록 투자자문업) / 제445조 (벌칙)
⚖️ 형법 제347조 사기

**정부·산업 보고서**:
📊 금감원·금융위 「유사수신행위 Q&A」
📊 미국 **FTC** (Federal Trade Commission — *연방거래위원회*) [*Consumer Sentinel Data Book 2024*](https://www.ftc.gov/reports/consumer-sentinel-network-data-book-2024) — *"투자 사기 $5.7B 1위 카테고리"*

**🔗 코드 매핑**:
- `abnormal_return_rate`
- `pipeline/config.py:FLAG_RATIONALE["abnormal_return_rate"]` — *"연 20% 이상 수익 보장은 자본시장법상 불법 권유입니다. 정상 주식·채권 펀드 장기 평균은 5~10% 입니다. 보장형 + 고수익은 폰지 사기 핵심 패턴입니다"* — Frankel 2012 / SEC Investor Bulletin / 금감원 인용이 박혀 있습니다.
- 검출: `pipeline/verifier.py` 가 키워드·정규식 매칭을 수행합니다.

---

### 2.2 `business_not_registered` — 사업자 미등록

**한국 법령**:
⚖️ [전자상거래법 제12조 제1항](https://www.law.go.kr/법령/전자상거래등에서의소비자보호에관한법률) — 통신판매업자 신고 의무가 있습니다. 위반 시 제40조 제1항 제4호에 따라 과태료가 부과됩니다.
⚖️ 부가가치세법 제8조 (사업자등록)

**정부 자료**:
📊 [공정거래위원회 통신판매업자 정보공개시스템](https://www.ftc.go.kr/) — 신고번호 조회가 가능합니다.

**🔗 코드 매핑**: `pipeline/config.py:FLAG_RATIONALE["business_not_registered"]` 에 Stajano-Wilson Distraction (위장된 정상성) 인용이 박혀 있고, `pipeline/verifier.py` 가 Serper 검색으로 사업자등록 부재를 검증합니다.

---

### 2.3 `account_scam_reported` — 의심 계좌 (대포통장)

**우리가 검출하는 것**: *짧은 기간 내 다중 입출금, 신생 계좌, 명의자/사용자 불일치* 등 대포통장 의심 패턴입니다.

**학술 근거**:
📖 **Florêncio & Herley (2013)** — *"Where do all the attacks go?"* (공격은 어디로 가는가?). *Economics of Information Security and Privacy III* 단행본 13–33쪽. DOI: [10.1007/978-1-4614-1981-5_2](https://doi.org/10.1007/978-1-4614-1981-5_2)
- 풀이: *돈세탁 통로 (money mule — *돈 운반책*) 의 경제학적 분석입니다.*

**한국 법령**:
⚖️ [전자금융거래법 제6조 제3항](https://www.law.go.kr/법령/전자금융거래법) — *접근매체 (통장·카드) 양도·양수·대여를 금지합니다*. 제49조 제4항 — *5년 이하 징역 또는 3천만 원 이하 벌금에 해당합니다.*
⚖️ 통신사기피해환급법 제2조 제4호 (사기이용계좌 정의), 제4조 (지급정지), 제9조 (채권소멸)
⚖️ **대법원 2012.07.05. 선고 2011도16167** — *'양도'의 의미: 소유권/처분권의 확정적 이전*

**🔗 코드 매핑**: `pipeline/config.py:FLAG_RATIONALE["account_scam_reported"]` 에 통신사기피해환급법 + 금감원 통계 인용이 박혀 있습니다.

---

### 2.4 `fake_exchange` — 가짜 거래소 (암호화폐 결제 요구 포함)

**학술 근거**:
📖 **Xia et al. (2020)** — *"Characterizing cryptocurrency exchange scams"*. Computers & Security, 98. DOI: [10.1016/j.cose.2020.101993](https://doi.org/10.1016/j.cose.2020.101993)

**한국 법령**:
⚖️ 유사수신행위법 제2조 (2024.05.28 — *가상자산 포함*)
⚖️ 「가상자산 이용자 보호 등에 관한 법률」 제2조 제1호
⚖️ 「특정금융거래정보의 보고 및 이용 등에 관한 법률」(특정금융정보법) — *가상자산사업자 신고 의무*

**정부 자료**:
📊 FBI [*IC3 2024*](https://www.ic3.gov/AnnualReport/Reports/2024_IC3Report.pdf) — *암호화폐 손실 $9.3B (+66%)*
📊 FTC [*New crypto payment scam alert*](https://consumer.ftc.gov/) — *"정부·법 집행기관·공공요금 회사는 결코 암호화폐로 결제를 요구하지 않습니다."*

**🔗 코드 매핑**: `pipeline/config.py:FLAG_RATIONALE["fake_exchange"]` 에 FBI IC3 + Cross 2023 인용이 박혀 있습니다.

---

### 2.5 `prepayment_requested` — 선납금·수수료 먼저 요구

**우리가 검출하는 것**: 대출·취업·거래 *전에* 보증금·수수료·교육비 등을 먼저 요구하는 패턴입니다.

**왜 위험한가**:
📖 **Stajano & Wilson (2011)** — Principle 4: *"Need and Greed"* (절박한 상황 표적). DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)

**한국 법령**:
⚖️ 「대부업 등의 등록 및 금융이용자 보호에 관한 법률」 / 「직업안정법」 제32조 — *채용·대출 명목 선납금 요구는 불법입니다.*

**🔗 코드 매핑**: `pipeline/config.py:FLAG_RATIONALE["prepayment_requested"]` 에 Stajano-Wilson + 직업안정법 인용이 박혀 있습니다.

---

## 3. 카테고리 C — 디지털 콘텐츠 신호

### 3.1 `phone_scam_reported` — 전화번호 신고 이력

**학술 근거**:
📖 **Tu et al. (2016)** — *"SoK: Everyone hates robocalls"* (모두가 로보콜을 미워한다 — 시스템적 지식 정리). **IEEE S&P 2016**, 320–338쪽. DOI: [10.1109/SP.2016.27](https://doi.org/10.1109/SP.2016.27)
- *SoK* (Systematization of Knowledge — *지식 체계화*) — 한 분야의 모든 연구를 정리한 종합 논문입니다.

**한국 법령**:
⚖️ 전기통신사업법 제84조의2 — *전화번호 거짓표시를 금지합니다* (발신번호 변작). 1년 이하 징역 또는 1천만 원 이하 벌금에 해당합니다.
⚖️ 정보통신망법 제50조 (영리목적 광고성 정보 전송 제한)

**정부 자료**:
📊 [전기통신금융사기 통합신고대응센터 ☎112 / counterscam112.go.kr](https://counterscam112.go.kr/)
📊 경찰청 — *"강제수신·강제발신 (강수강발) 기능"* 80여 개 기관 번호 매핑 분석 (2025.04.27)

**🔗 코드 매핑**: `pipeline/config.py:FLAG_RATIONALE["phone_scam_reported"]` 에 KISA 통계 + Anderson *Security Engineering* 베이지안 사전확률 인용이 박혀 있습니다. 검출은 `pipeline/verifier.py` Serper API 에서 수행됩니다.

---

### 3.2 `smishing_link_detected` — 스미싱 의심 링크

**학술 근거 (URL 단축 공격)**:
📖 **Maggi et al. (2013)** — *"Two years of short URLs internet measurement"* (2년간 단축 URL 측정). **WWW '13** (웹 컨퍼런스), 861–872쪽. DOI: [10.1145/2488388.2488463](https://doi.org/10.1145/2488388.2488463)
📖 **Klien & Strohmaier (2012)** — *"Short links under attack"* (공격받는 단축 링크). ACM Hypertext '12. DOI: [10.1145/2309996.2310002](https://doi.org/10.1145/2309996.2310002)

**한국 법령**:
⚖️ 정보통신망법 제48조 제2항 (악성프로그램 유포 금지) / 제50조

**정부 자료**:
📊 [KISA 한국인터넷진흥원 — 「택배 등 일상생활 사칭 스미싱 대응」](https://www.kisa.or.kr/1020601)
📊 과기정통부 — *"2024년 부고·청첩장 등 미끼문자 24만 건"*

**🔗 코드 매핑**: `pipeline/config.py:FLAG_RATIONALE["smishing_link_detected"]` 에 박혀 있습니다.

---

### 3.3 도메인 위장 검출 (typosquatting)

**학술 근거**:
📖 **Spaulding, Upadhyaya, & Mohaisen (2016)** — *"The landscape of domain name typosquatting"* (오타 도메인 위장의 현황). arXiv: [1603.02767](https://arxiv.org/abs/1603.02767)
📖 **Nikiforakis et al. (2013)** — *"Bitsquatting: Exploiting bit-flips for fun, or profit?"* (비트 뒤집기 도메인 위장). **WWW '13**. DOI: [10.1145/2488388.2488474](https://doi.org/10.1145/2488388.2488474)
📖 **Kintis et al. (2017)** — *"Hiding in plain sight: A longitudinal study of combosquatting abuse"* (눈에 띄게 숨기: 조합 도메인 위장 종단연구). **ACM CCS 2017**. DOI: [10.1145/3133956.3134002](https://doi.org/10.1145/3133956.3134002)

**한국 법령**:
⚖️ [인터넷주소자원법 제12조](https://www.law.go.kr/법령/인터넷주소자원에관한법률) — 부정한 목적의 도메인 등록을 금지합니다.
⚖️ 「부정경쟁방지 및 영업비밀보호에 관한 법률」 제2조 제1호 아목

**🔗 코드 매핑**: 우리는 *APK 패키지명 위장* 검출 (`apk_suspicious_package_name`) 에 이 학술 근거를 적용합니다 — `pipeline/apk_analyzer._is_suspicious_impersonation()` 에서 정상 한국 앱 list (kakao/naver/은행) 와 명시적으로 비교합니다.

---

### 3.4 `apk_impersonation_keywords` — 사칭 키워드

**학술 근거**:
📖 **Kim et al. (2022) HearMeOut** — *"Detecting voice phishing activities in Android"* (안드로이드의 보이스피싱 활동 검출). **MobiSys '22** (*모바일 시스템 학회*) 422–435쪽 — **한국 1,017개 보이스피싱 앱을 분석한 연구입니다.** DOI: [10.1145/3498361.3538939](https://doi.org/10.1145/3498361.3538939) ⭐ *우리 시스템의 한국 표적 검출의 핵심 학술 근거입니다.*
📖 **Stajano & Wilson (2011)** §"Social Compliance Principle" — *권위 신호* 활용. DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)

**한국 법령**:
⚖️ 형법 제225·227·230조 (공문서 위조·허위·부정행사)
⚖️ 통신사기피해환급법 제2조 제2호

**정부 자료**:
📊 **경찰청 [「2025년 1분기 보이스피싱 현황」](https://www.police.go.kr/), 2025.04.27 — 위험 키워드를 공식 공개했습니다**: 사건조회·특급보안·엠바고·약식조사·자산검수·자산이전·감상문 제출.

**🔗 코드 매핑**:
- 신호: `apk_impersonation_keywords`
- 검출: `pipeline/apk_analyzer._contains_string_keywords()` 가 APK 의 *dex 문자열 풀* (앱 안에 박힌 문자열) 을 검사합니다.
- 키워드 정의: `pipeline/apk_analyzer._IMPERSONATION_KEYWORDS` (frozenset 14종): 검찰·경찰·금감원·금융감독원·수사·구속·체포·고소·안전계좌·보안승급·보안카드·사칭·피해자·압수수색이 들어 있습니다.
- 학술 근거 동반: `pipeline/config.py:FLAG_RATIONALE["apk_impersonation_keywords"]` (Cialdini Authority + Stajano-Wilson + S2W TALON 인용)

---

## 4. 카테고리 D — 격리 브라우저 분석 (Sandbox)

> **Sandbox** (모래상자·격리 환경) — *의심 URL 을 평소 컴퓨터에서 열면 위험하니, 격리된 가상 브라우저에서 열어 행동만 관찰합니다*. v3.5 부터 격리 Chromium 으로 의심 URL 을 직접 navigate 하는 기능이 추가되었습니다.

### 4.1 `sandbox_password_form_detected` — 비밀번호 입력란 발견

**학술 근거**:
📖 [**OWASP** *Web Security Testing Guide v4.2*](https://owasp.org/www-project-web-security-testing-guide/) (Open Web Application Security Project — *오픈 웹앱 보안 프로젝트*, 비영리), §4.4 *Identity Management Testing*
📖 **Marchal et al. (2017)** — *"Off-the-Hook: An efficient and usable client-side phishing prevention application"* (낚시바늘 빼기 — 효율적이고 쓸 만한 클라이언트 측 피싱 방어 앱). IEEE Transactions on Computers 66(10), 1717–1733. DOI: [10.1109/TC.2017.2703808](https://doi.org/10.1109/TC.2017.2703808)

**한국 법령**:
⚖️ 정보통신망법 제49조 (비밀 침해·도용·누설 금지)
⚖️ 개인정보보호법 제15조 제1항·제17조

**🔗 코드 매핑**:
- 신호: `sandbox_password_form_detected`
- 검출: `pipeline/sandbox.py` (Phase 0.5) 가 격리 Chromium 으로 URL 을 열고 `<input type="password">` (비밀번호 필드) 를 검출합니다.
- 학술 근거: `pipeline/config.py:FLAG_RATIONALE["sandbox_password_form_detected"]` 에 *OWASP A07 (Identification & Authentication Failures) + APWG 2024* 인용이 박혀 있습니다.

---

### 4.2 `sandbox_sensitive_form_detected` — 민감 정보 입력란

**학술 근거**:
📖 **Bilge et al. (2009)** — [*"EXPOSURE: Finding malicious domains using passive DNS analysis"*](https://www.ndss-symposium.org/wp-content/uploads/2017/09/14_3.pdf). **NDSS 2009**

**한국 법령**:
⚖️ [개인정보보호법 제24조의2](https://www.law.go.kr/법령/개인정보보호법) — *주민등록번호 처리를 제한합니다 (법령 근거 없는 한 처리 금지)*
⚖️ 개인정보보호법 제23조 (민감정보 처리 제한)
⚖️ 정보통신망법 제23조의2 (주민등록번호 사용 제한)

**🔗 코드 매핑**: 검출은 `pipeline/sandbox_detonate.py:_detect_sensitive_fields()` 가 주민번호·OTP·CVC(카드 보안코드)·계좌·카드번호 필드를 검출합니다. *PCI DSS 4.0 (Payment Card Industry Data Security Standard — 카드결제업계 보안 표준) + 개인정보보호법 시행령 별표1* 인용이 박혀 있습니다.

---

### 4.3 `sandbox_auto_download_attempt` — drive-by download

**학술 근거**:
📖 **Provos et al. (2008)** — [*"All your iFRAMEs point to Us"*](https://www.usenix.org/legacy/event/sec08/tech/full_papers/provos/provos.pdf) (모든 iFRAME 이 우리를 가리킵니다). **USENIX Security 2008** (시스템 보안 최상위 학회)
📖 **Cova, Kruegel, & Vigna (2010)** — *"Detection and analysis of drive-by-download attacks and malicious JavaScript code"*. **WWW '10**. DOI: [10.1145/1772690.1772720](https://doi.org/10.1145/1772690.1772720)

**한국 법령**:
⚖️ 정보통신망법 제48조 제2항 / 제70조의2 — *악성프로그램 전달·유포는 7년 이하 징역 또는 7천만 원 이하 벌금에 해당합니다.*
⚖️ **대법원 2019.12.12. 선고 2017도16520** — 악성프로그램 해당 여부 판단 기준이 됩니다.

**🔗 코드 매핑**: `pipeline/sandbox.py` 가 Playwright Chromium 의 `download` 이벤트를 hook (*걸어둠*) 합니다.

---

### 4.4 `sandbox_excessive_redirects` / 4.5 `sandbox_cloaking_detected`

**학술 근거**:
📖 **Invernizzi et al. (2016)** — *"Cloak of visibility: Detecting when machines browse a different web"* (가시성의 망토: 기계와 사람이 다른 웹을 보는 순간 검출). **IEEE S&P 2016** 743–758쪽. DOI: [10.1109/SP.2016.50](https://doi.org/10.1109/SP.2016.50)
- 풀이: *피싱 사이트가 검색엔진 봇에게는 정상 페이지, 사람에게는 피싱 페이지를 보여주는 cloaking 기법 11종을 분석한 논문입니다.*
📖 **Wang, Savage, & Voelker (2011)** — *"Cloak and dagger: Dynamics of web search cloaking"*. **ACM CCS 2011**. DOI: [10.1145/2046707.2046763](https://doi.org/10.1145/2046707.2046763)
📖 **Oest et al. (2019)** — *"PhishFarm: A scalable framework for measuring the effectiveness of evasion techniques"*. IEEE S&P 2019. DOI: [10.1109/SP.2019.00049](https://doi.org/10.1109/SP.2019.00049)

**🔗 코드 매핑**: `pipeline/sandbox.py` 가 redirect chain (*리디렉션 연쇄*) 을 추적하며 target ≠ final URL 을 비교합니다.

---

### 4.6 `malware_detected` — VirusTotal 다중 엔진 멀웨어 검출

**학술 근거**:
📖 **Peng, Yang, Song, & Wang (2019)** — *"Opening the blackbox of VirusTotal: Analyzing online phishing scan engines"*. **ACM IMC 2019** (*인터넷 측정 학회*) 478–485쪽. DOI: [10.1145/3355369.3355585](https://doi.org/10.1145/3355369.3355585)
📖 **Salem, Banescu, & Pretschner (2021)** — *"Maat: Automatically analyzing virustotal for accurate labeling and effective malware detection"*. ACM TOPS 24(4). DOI: [10.1145/3465361](https://doi.org/10.1145/3465361)

**한국 법령**:
⚖️ 정보통신망법 제48조 제2항 / 제70조의2
⚖️ 형법 제314조 제2항 (컴퓨터등 장애 업무방해)

**🔗 코드 매핑**:
- 신호: `malware_detected`, `phishing_url_confirmed`, `suspicious_file_signal`, `suspicious_url_signal`
- 검출: `pipeline/safety.py` (Phase 0) 가 VirusTotal API v3 클라이언트로 *SHA256* (파일 해시) 을 조회하고 URL 스캔을 수행합니다.
- 학술 근거: `pipeline/config.py:FLAG_RATIONALE["malware_detected"]` 에 *NIST SP 800-83* (미국 표준기술연구원 *멀웨어 사고 예방·대응 가이드*) 인용이 박혀 있습니다.

---

## 5. 카테고리 E — 한국 표적 신호

> **이 카테고리는 *개념 인덱스* 입니다.** 5개 항목은 한국 사기 생태계에서 자주 관찰되는 *공격 시나리오* 이며, 각 시나리오는 코드의 *기존 실존 flag* 한 개 이상으로 검출됩니다. 즉 *"카카오톡 위장"* 자체가 별도 flag 키는 아니지만, 코드의 `apk_suspicious_package_name` + `impersonation_family` 두 flag 가 결합되어 이 시나리오를 커버합니다. 한국 보이스피싱·메신저피싱·스미싱 통계 (금감원·경찰청·KISA·과기정통부) 와 산업 보고서 (S2W TALON SecretCalls·HeadCalls·KrBanker) 의 *지역 특이 (regional-specific) 단서* 가 어떻게 우리 코드의 일반 신호로 environment 되어 있는지 추적하는 섹션입니다.

### 5.1 카카오톡 위장 패턴 (개념: `kakao_impersonation`)

**우리가 검출하는 것**: SMS·메신저·APK 패키지명에서 카카오톡 공식 발송으로 위장한 패턴, 가짜 카카오 도메인, 카카오 사칭 패키지명 (`com.kakao.talk.fake` 등 typo-squatting) 입니다.

**왜 위험한가 (학술 근거)**:

📖 **Kim, J., Kim, J., Wi, S., Kim, Y., & Son, S. (2022)** — *"HearMeOut: Detecting voice phishing activities in Android"* (안드로이드의 보이스피싱 활동 검출). **MobiSys '22** (모바일 시스템 학회) 422–435쪽. DOI: [10.1145/3498361.3538939](https://doi.org/10.1145/3498361.3538939) ⭐
- 한국 1,017개 보이스피싱 앱을 분석한 연구로, 카카오톡 사칭 앱 패턴이 다수 보고되었습니다.

📖 **Cialdini (2021), Chapter 6 "Authority"** — *권위 휴리스틱 (Authority Heuristic)* 적용
- 풀이: *카카오톡은 한국 메신저 시장 점유율 95%+ 의 사실상 표준 채널입니다. 사칭만으로도 *기본 신뢰* 가 부여됩니다.*

**한국 법령**:

⚖️ 「부정경쟁방지 및 영업비밀보호에 관한 법률」 제2조 제1호 가목·나목 (저명상표 혼동 야기)
⚖️ 「상표법」 제108조 (상표권 침해)
⚖️ 통신사기피해환급법 제2조 제2호 — *전기통신금융사기 수단으로서의 메신저 이용*

**정부·산업 보고서**:

📊 금융감독원 [「2023년 보이스피싱 피해현황 분석」](https://www.fss.or.kr/), 2024.03 — 가족·지인 사칭 메신저피싱 **33.7%** (2위)
📊 S2W TALON [*SecretCalls Spotlight*](https://medium.com/s2wblog), 2024 — 카카오톡 사칭 패턴 분석

**🔗 우리 코드의 어디**:

이 시나리오는 다음 *기존 실존 flag* 두 개의 결합으로 검출됩니다:

- **`apk_suspicious_package_name`** (Stage 2 Lv 1) — `pipeline/apk_analyzer.py:_LEGITIMATE_PACKAGE_PATTERNS` 에 `com.kakao.talk` 외 16개 정상 한국 앱 prefix 가 명시되어 있고, `_is_suspicious_impersonation()` 가 이를 기준으로 typo-squatting 을 매칭합니다. 학술 근거는 `pipeline/config.py:FLAG_RATIONALE["apk_suspicious_package_name"]` 에 박혀 있습니다 (S2W TALON KrBanker + Cialdini Authority 인용).
- **`impersonation_family`** (메신저피싱 일반) — `pipeline/config.py:FLAG_RATIONALE["impersonation_family"]` 에 Cialdini Liking + Whitty 2013 + 금감원 메신저피싱 통계 인용이 박혀 있고, `pipeline/verifier.py` 와 `pipeline/llm_assessor.py` 에서 검출됩니다.

**신뢰도**: 강(S) — 학술 (Kim 2022 HearMeOut MobiSys'22) + 법령 (부정경쟁방지법·상표법·통신사기피해환급법) + 통계 (금감원 33.7%) 3축

---

### 5.2 택배 SMS 사기 패턴 (개념: `delivery_sms_pattern`)

**우리가 검출하는 것**: *"[CJ대한통운] 택배 배송 실패. 주소 확인하세요: [단축 URL]"* 형 미끼문자입니다. 한국 1·2위 택배 회사 (CJ대한통운·한진·우체국) 위장이 표준입니다.

**왜 위험한가 (학술 근거)**:

📖 **Maggi et al. (2013)** — *"Two years of short URLs internet measurement"*. **WWW '13** (웹 컨퍼런스), 861–872쪽. DOI: [10.1145/2488388.2488463](https://doi.org/10.1145/2488388.2488463)
- 풀이: *단축 URL 은 도메인을 숨겨 사용자가 도착지를 확인할 수 없게 만듭니다 — 스미싱의 핵심 페이로드 채널입니다.*

⚠️ *학술 정직성*: 택배 SMS 위장 패턴 자체는 *한국 특화 휴리스틱* 입니다. 단축 URL 학술 근거 (Maggi 2013) 가 보조하지만, *"택배 SMS"* 라는 시나리오 자체에 대한 peer-review 학술 논문은 부재합니다 — 정부·산업 보고서가 1차 근거입니다.

**한국 법령**:

⚖️ 「정보통신망 이용촉진 및 정보보호 등에 관한 법률」 제48조 제2항 (악성프로그램 유포 금지) / 제50조 (영리목적 광고성 정보 전송 제한)
⚖️ 통신사기피해환급법 제2조 제2호

**정부·산업 보고서**:

📊 KISA 보호나라 [「택배 등 일상생활 사칭 스미싱 대응」](https://www.boho.or.kr/) — 한국 스미싱 1순위 시나리오로 명시
📊 과기정통부·KISA — *"2024년 미끼문자 24만 건"* 공식 집계
📊 경찰청 사이버수사국 — *2020년 11억 → 2024년 546억* 스미싱 피해액 50배 증가 (김종양 의원실 인용)

**🔗 우리 코드의 어디**:

- **`smishing_link_detected`** — `pipeline/config.py:FLAG_RATIONALE["smishing_link_detected"]` 에 KISA 차단 통계 + 방통위 + APWG 인용이 박혀 있습니다.
- 검출: `pipeline/verifier.py` (URL·발신번호·키워드 매칭) + 카카오 webhook 의 detector (`api_server_pkg/kakao.py:_kakao_detect_input`) 가 단축 URL · 의심 도메인을 분류합니다.
- ⚠️ *현재 코드는 "택배" 키워드 자체를 단독 신호로 가지고 있지 않습니다.* 단축 URL + 의심 도메인 + 사칭 키워드 검색의 *조합* 으로 검출되며, 명시적 "택배 발송 사칭" sub-flag 는 future work 입니다.

**신뢰도**: 중(M) — 정부·산업 보고서 (KISA·과기정통부·경찰청) 강, 학술 보조 (단축 URL 학술 근거 Maggi 2013), *시나리오 자체* 의 학술 인용 약

---

### 5.3 청첩장 피싱 패턴 (개념: `wedding_invitation_phishing`)

**우리가 검출하는 것**: *"[모바일 청첩장] OO과 △△ 결혼합니다. 청첩장 보기: [단축 URL]"* 형 지인 사칭 미끼문자입니다. 30~40대 표적이 표준입니다.

**왜 위험한가**:

⚠️ *학술 정직성*: 청첩장 피싱 자체는 한국 특화 휴리스틱이며, peer-review 학술 인용은 부재합니다. KISA·경찰청 등 정부 자료가 1차 근거입니다.

📖 **Cialdini (2021), Chapter 5 "Liking"** — *호감 원리* — *지인 사칭이 신뢰 형성에 미치는 심리 메커니즘 (보조 학술 근거).*

**한국 법령**:

⚖️ 정보통신망법 제48조 제2항 / 제70조의2 (7년 이하 징역)
⚖️ 통신사기피해환급법 제2조 제2호

**정부·산업 보고서**:

📊 KISA 보호나라 — *"청첩장 등 지인 사칭 스미싱 주의 권고"* (반복 게시)
📊 과기정통부·KISA — *2023년 약 6만 건 → 2024년 약 6배 증가*
📊 경찰청 사이버수사국 — *2020년 11억 → 2024년 546억* (스미싱 전체, 50배 증가, 김종양 의원실)

**🔗 우리 코드의 어디**:

- **`smishing_link_detected`** — 5.2 와 동일한 flag 가 청첩장 시나리오를 커버합니다.
- 사칭 키워드 단서 — `pipeline/apk_analyzer._IMPERSONATION_KEYWORDS` (APK 시) / `pipeline/llm_assessor.py` (텍스트 시) 가 *결혼식·청첩장* 등 지인 사칭 키워드를 LLM 의미 분석으로 잡습니다.
- ⚠️ *현재 코드에 "청첩장 자체" 별도 flag 는 없습니다.* 지인 사칭 + 단축 URL + 의심 도메인의 *조합* 으로 검출되며, 명시적 sub-flag 는 future work 입니다.

**신뢰도**: 중(M) — 정부 자료 강, 학술 약

---

### 5.4 부고장 피싱 패턴 (개념: `obituary_phishing`)

**우리가 검출하는 것**: *"[부고] 故 OOO님 별세. 빈소: ◯◯◯ [단축 URL]"* 형 사칭 미끼문자입니다. 50대 이상 표적 + 검증 어려운 시간대 (심야·새벽) 발송이 표준입니다.

**왜 위험한가**:

⚠️ *학술 정직성*: 부고 피싱은 한국 특화 휴리스틱입니다. peer-review 학술 인용은 부재합니다.

📖 **Stajano & Wilson (2011)** §"Time Principle" — *시간 압박 원리* — *심야 발송 + 부고 정서적 충격 결합 시 의사결정 마비* 메커니즘의 보조 학술 근거. **CACM 54(3)**. DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)

**한국 법령**:

⚖️ 정보통신망법 제48조 제2항
⚖️ 통신사기피해환급법 제2조 제2호

**정부·산업 보고서**:

📊 KISA 보호나라 — *"지인에게 부고안내"* 스미싱 주의 권고
📊 과기정통부·KISA — *부고·청첩장 등 미끼문자 2024년 24만 건* (택배·청첩장과 합산 통계)
📊 금감원 「2023년 보이스피싱 피해현황 분석」 — 메신저피싱·스미싱 사례 집계

**🔗 우리 코드의 어디**:

- **`smishing_link_detected`** — 5.2 / 5.3 와 동일.
- LLM 의미 분석 — `pipeline/llm_assessor.analyze_unified()` 가 *부고·빈소·발인* 등 정서적 충격 어휘 + 단축 URL 결합 패턴을 검출합니다.
- ⚠️ "부고 자체" 별도 flag 는 부재 — future work.

**신뢰도**: 중(M)

---

### 5.5 금융기관 사칭 패턴 (개념: `financial_institution_impersonation`)

**우리가 검출하는 것**: 가짜 은행 (KB국민·신한·우리·NH농협 등) / 가짜 금감원 / 가짜 카드사 / 가짜 캐피탈 명의로 *대출 권유 + 선납 수수료 요구* 또는 *안전계좌 송금 유도* 패턴입니다. 한국 보이스피싱 피해액 1위 시나리오입니다.

**왜 위험한가 (학술 근거)**:

📖 **Kim et al. (2022) HearMeOut** — 한국 1,017개 보이스피싱 앱 분석 — 은행 앱 사칭이 표준 패턴. **MobiSys '22**. DOI: [10.1145/3498361.3538939](https://doi.org/10.1145/3498361.3538939) ⭐

📖 **Stajano & Wilson (2011)** §"Authority/Social Compliance Principle" — *권위·사회적 순응 원칙* (사람들은 권위에 의문을 던지지 않도록 훈련됨). **CACM 54(3)** pp.71–72. DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872) ⭐

📖 **Cialdini (2021), Chapter 6 "Authority"** — *권위 신호 (제복·직함·말투) 만으로 의심을 정지시키는 심리.*

**한국 법령**:

⚖️ 「은행법」 제66조의2 (유사명칭 사용 금지) / 제14조 (유사상호 사용 금지) — *은행 아닌 자가 "은행" 명칭 사용 금지*
⚖️ 「자본시장과 금융투자업에 관한 법률」 제38조 (유사명칭 사용 금지) / 제17조 (미등록 투자자문업)
⚖️ 형법 제225조 (공문서 위조) / 제227조 (허위공문서작성) / 제230조 (공문서 부정행사) / 제347조 (사기)
⚖️ 통신사기피해환급법 제2조 제2호 / 제15조의2 제1항

**정부·산업 보고서**:

📊 금융감독원 [「2023년 보이스피싱 피해현황 분석」](https://www.fss.or.kr/), 2024.03 — **대출빙자형 35.2% (1위)** / 정부기관 사칭형 31.1% (2위)
📊 경찰청 [「2025년 1분기 보이스피싱 현황」](https://www.police.go.kr/), 2025.04.27 — 기관사칭형 51% (2,991건)
📊 S2W TALON [*Detailed Analysis of HeadCalls: Impersonation of Korean Public and Financial Institutions*](https://medium.com/s2wblog), 2025.08

**🔗 우리 코드의 어디**:

이 시나리오는 다음 *기존 실존 flag* 셋의 결합으로 검출됩니다:

- **`prepayment_requested`** — `pipeline/config.py:FLAG_RATIONALE["prepayment_requested"]` 에 대부업법·직업안정법 + Stajano-Wilson Need and Greed 인용. 검출은 `pipeline/verifier.py` + `pipeline/llm_assessor.py`.
- **`fss_not_registered`** — 자본시장법 제11조·제17조 등록 부재. `pipeline/verifier.py` 가 금감원 등록 DB 조회 결과 반영.
- **`fake_government_agency`** — 검찰·경찰·금감원·국세청·은행 사칭의 일반 신호. Cialdini Authority + 형법 제225조 인용 박힘. `pipeline/llm_assessor.py` 가 LLM 의미 분석.
- (추가) **`personal_info_request`** — 주민번호·OTP·계좌번호 요구 (가짜 은행 시나리오에서 동시 발생).
- (추가) **`apk_suspicious_package_name`** — 가짜 은행 APK (`com.kbstar.kbbank.fake` 등) 검출 시 동시 발동.

**신뢰도**: 강(S) — 학술 (Kim 2022 ⭐ + Stajano-Wilson ⭐ + Cialdini) + 법령 (은행법·자본시장법·형법·통신사기피해환급법) + 통계 (금감원 35.2% 1위 + 경찰청 + S2W TALON HeadCalls) 3축 모두 강

---

## 6. 카테고리 F — APK 정적 분석 Lv 1

> **Lv 1 정적 분석** — APK 파일의 *manifest* (선언서) + *권한* + *서명* 만 보는 분석입니다. 코드는 보지 않습니다.

### 6.1 `apk_dangerous_permissions_combo` — 위험 권한 4종 이상 조합

**우리가 검출하는 것**: SEND_SMS (SMS 보내기) + READ_SMS (SMS 읽기) + BIND_ACCESSIBILITY_SERVICE (접근성 서비스 — *다른 앱 화면 가로채기 가능*) + SYSTEM_ALERT_WINDOW (다른 앱 위에 창 띄우기) 등 **위험 권한 4종 이상** 을 동시에 요청하는 패턴입니다.

**왜 위험한가**:

📖 **Arp, Spreitzenbarth, Hübner, Gascon, & Rieck (2014)** — [*"DREBIN: Effective and Explainable Detection of Android Malware in Your Pocket"*](https://www.ndss-symposium.org/wp-content/uploads/2017/09/11_3_1.pdf) (안드로이드 멀웨어의 효율적·설명 가능한 검출). **NDSS 2014**. DOI: [10.14722/ndss.2014.23247](https://doi.org/10.14722/ndss.2014.23247) ⭐
- §III.A "Permissions" feature set — *권한 조합* 만으로도 악성 앱 **94% 검출률** 을 달성한 안드로이드 멀웨어 검출의 표준 baseline 입니다.

📖 **Felt, Chin, Hanna, Song, & Wagner (2011)** — *"Android Permissions Demystified"* (안드로이드 권한 해부). **ACM CCS 2011**. DOI: [10.1145/2046707.2046779](https://doi.org/10.1145/2046707.2046779)

📖 **Mariconti et al. (2017)** — [*"MaMaDroid: Detecting Android malware by building Markov chains of behavioral models"*](https://arxiv.org/abs/1612.04433). **NDSS 2017**. DOI: [10.14722/ndss.2017.23353](https://doi.org/10.14722/ndss.2017.23353)
- 풀이: *권한 + API 호출 시퀀스를 **마코프 연쇄** (Markov chain — 상태 전환 확률 모델) 로 모델링한 차세대 악성 앱 검출 기법입니다.*

**한국 법령**:
⚖️ 정보통신망법 제48조 제2항 (악성프로그램 정의)
⚖️ 개인정보보호법 제15·17·22조 (수집·이용·제3자 제공 동의 원칙)

**정부·산업 자료**:
📊 [Google Play Console — *Use of SMS or Call Log permission groups*](https://support.google.com/googleplay/android-developer/answer/9047303) (구글 플레이 콘솔 — *SMS·통화기록 권한 그룹 사용 정책*)
📊 [Android Open Source Project — *Permissions* 9개 dangerous group](https://developer.android.com/guide/topics/permissions/overview)

**🔗 코드 매핑**:
- 신호: `apk_dangerous_permissions_combo`
- 검출: `pipeline/apk_analyzer.py:_DANGEROUS_PERMISSION_COMBO` (frozenset — *변경 불가능한 집합*) 7종이 정의되어 있습니다: SEND_SMS / READ_SMS / RECEIVE_SMS / READ_CALL_LOG / PROCESS_OUTGOING_CALLS / BIND_ACCESSIBILITY_SERVICE / SYSTEM_ALERT_WINDOW
- 임계: `_DANGEROUS_PERMISSION_THRESHOLD = 4` — *4종 이상 동시* 보유 시 검출됩니다.
- 진입: `pipeline/apk_analyzer.analyze_apk_static()`
- 학술 근거: `pipeline/config.py:FLAG_RATIONALE["apk_dangerous_permissions_combo"]` 에 S2W TALON SecretCalls + DREBIN 인용이 박혀 있습니다.

---

### 6.2 `apk_self_signed` — 자체 서명 인증서 (단독 사용 비권장)

**학술 근거**:
📖 **Truong et al. (2014)** — *"The Company You Keep: Mobile Malware Infection Rates and Inexpensive Risk Indicators"* (어울리는 친구가 누구인가: 모바일 멀웨어 감염률과 저비용 위험 지표). **WWW 2014**. arXiv: [1312.3245](https://arxiv.org/abs/1312.3245)

**산업 자료**:
📊 [Palo Alto Networks Unit42 — *Bad Certificate Management in Google Play Store*](https://unit42.paloaltonetworks.com/bad-certificate-management-google-play-store/), 2014
📊 [Android Partner Vulnerability Initiative](https://bugs.chromium.org/p/apvi/), 2022.11 — Samsung·LG·Mediatek 플랫폼 인증서 유출 사례입니다.

**🔗 코드 매핑**:
- 신호: `apk_self_signed`
- 검출: `pipeline/apk_analyzer._check_self_signed()` 가 `androguard.core.apk.APK.get_certificates_v3/v2/v1()` + asn1crypto 라이브러리로 *subject* (서명자) == *issuer* (발급자) 를 비교합니다.
- ⚠️ 거짓 양성 위험이 있습니다 — 정상 사이드로딩 앱도 자체 서명을 사용하므로 단독 사용은 권장하지 않습니다 (FLAG_RATIONALE 본문에 명시되어 있습니다).

---

### 6.3 `apk_suspicious_package_name` — 패키지명 위장

**학술 근거**:
📖 **Zhou & Jiang (2012)** — *"Dissecting Android malware: Characterization and evolution"*. **IEEE S&P 2012** 95–109쪽. DOI: [10.1109/SP.2012.16](https://doi.org/10.1109/SP.2012.16)
📖 **Truong et al. (2014)** — *"the name `com.facebook.katana` is used in many malware packages"*. arXiv: [1312.3245](https://arxiv.org/abs/1312.3245)

**산업 자료**: S2W TALON SecretCalls·TheftCalls·HeadCalls 보고서

**🔗 코드 매핑**:
- 신호: `apk_suspicious_package_name`
- 검출: `pipeline/apk_analyzer._is_suspicious_impersonation()` 가 typo-squatting 패턴을 매칭합니다.
- 정상 한국 앱 list: `_LEGITIMATE_PACKAGE_PATTERNS` — `com.kakao.talk`, `com.nhn.android.search`, `kr.co.shinhan`, `com.kbstar.kbbank` 등 **16개** 가 들어 있습니다.
- 의심 접미사: `_SUSPICIOUS_PACKAGE_SUFFIXES` — fake/test/_v2/_new/official 등 7종입니다.

---

## 7. 카테고리 G — APK 심화 정적 분석 Lv 2 (bytecode)

> **Lv 2 심화 정적 분석** — APK 의 *dex 바이트코드* (실행 코드) 를 *역어셈블* (disassemble — 기계어에 가까운 코드를 사람이 읽을 수 있게 변환) 해서 *어떤 함수가 어디서 호출되는지* 를 분석합니다. **여전히 코드 실행은 하지 않습니다.**

### 7.1 `apk_sms_auto_send_code` — SMS 자동 발송 코드

**학술 근거**:
📖 **Arp et al. (2014) DREBIN**, §III.B "API calls" feature. DOI: [10.14722/ndss.2014.23247](https://doi.org/10.14722/ndss.2014.23247)
📖 **Mariconti et al. (2017) MaMaDroid**. DOI: [10.14722/ndss.2017.23353](https://doi.org/10.14722/ndss.2017.23353)

**한국 법령**:
⚖️ 정보통신망법 제48조 제2항 / 제70조의2 — *7년 이하 징역에 해당합니다.*
⚖️ 전기통신사업법 제32조의5 / 정보통신망법 제50조

**산업 자료**:
- S2W TALON SecretCalls 보고서 — SMS 가로채기·자동 전송 기능이 확인되었습니다.
- [Corrata — *Dangerous Permissions Android*](https://corrata.com/dangerous-permissions-android/), 2022

**🔗 코드 매핑**:
- 신호: `apk_sms_auto_send_code`
- 검출: `pipeline/apk_analyzer._has_method_xref(analysis, "Landroid/telephony/SmsManager;", "sendTextMessage")` 가 *androguard `AnalyzeAPK` 의 xref* (cross-reference, *코드에서 어떤 함수가 어디서 호출되는지*) 분석으로 SmsManager.sendTextMessage 호출을 검출합니다.

---

### 7.2 `apk_call_state_listener` — 통화 상태 가로채기

**학술 근거**:
📖 **Kim, J., Kim, J., Wi, S., Kim, Y., & Son, S. (2022) HearMeOut** — call redirection (통화 우회) / call screen overlay (통화 화면 가리기) / fake call voice (가짜 통화 음성) **3종 새 기능을 보고했습니다.** **MobiSys '22**. DOI: [10.1145/3498361.3538939](https://doi.org/10.1145/3498361.3538939) ⭐
- *우리 시스템의 한국 보이스피싱 검출 핵심 학술 근거 — 1,017개 앱 분석입니다.*

**한국 법령**:
⚖️ [통신비밀보호법 제3조 제1항](https://www.law.go.kr/법령/통신비밀보호법) (불법 감청 금지), 제16조 — *10년 이하 징역에 해당합니다.*
⚖️ 정보통신망법 제48조 제2항 / 제70조의2

**산업 자료**:
- S2W TALON [*Detailed Analysis of TheftCalls*](https://medium.com/s2wblog) — 강제 forwarding (통화 우회), 통화 기록 변조
- S2W TALON [*HeadCalls*](https://medium.com/s2wblog), 2025

**🔗 코드 매핑**:
- 신호: `apk_call_state_listener`
- 검출: `pipeline/apk_analyzer._has_method_xref(analysis, "Landroid/telephony/TelephonyManager;", "listen")`
- 학술 근거: `pipeline/config.py:FLAG_RATIONALE["apk_call_state_listener"]` 에 Kim et al. 2022 HearMeOut + S2W TALON SecretCalls 인용이 박혀 있습니다.

---

### 7.3 `apk_accessibility_abuse` — 접근성 서비스 악용

**학술 근거**:
📖 **Fratantonio et al. (2017)** — *"Cloak and Dagger: From Two Permissions to Complete Control of the UI Feedback Loop"* (망토와 단검: 두 권한만으로 UI 피드백 루프 완전 장악). **IEEE S&P 2017** 1041–1057쪽. DOI: [10.1109/SP.2017.39](https://doi.org/10.1109/SP.2017.39)
- 풀이: *SYSTEM_ALERT_WINDOW (다른 앱 위에 창 띄우기) + BIND_ACCESSIBILITY_SERVICE (접근성 서비스) 두 권한만으로 사용자 입력 가로채기·가짜 화면 표시·자동 클릭이 모두 가능함을 학술적으로 증명한 논문입니다.*

📖 **Kim et al. (2022) HearMeOut**. DOI: [10.1145/3498361.3538939](https://doi.org/10.1145/3498361.3538939)

**한국 법령**:
⚖️ 정보통신망법 제48조 제2항 / 제70조의2
⚖️ 개인정보보호법 제15·17조

**산업 자료**:
- S2W TALON [*Deep Analysis of SecretCalls (Part 2)*](https://medium.com/s2wblog), 2024 — 접근성 권한 강제 승인, 화면 오버레이, 기본 전화 앱 변경
- [Corrata *Dangerous Permissions Android*](https://corrata.com/dangerous-permissions-android/) — 자격증명 탈취·OTP 가로채기

**🔗 코드 매핑**:
- 검출: `pipeline/apk_analyzer._references_accessibility_service()` 가 `AccessibilityService` 상속 클래스를 탐색합니다.
- ⚠️ 정상 장애인 보조 앱도 사용하므로 단독 신호는 약합니다. *권한 조합·은행 사칭 패키지명* 과 결합 시점에서 강해집니다 (FLAG_RATIONALE 본문에 명시되어 있습니다).

---

### 7.4 `apk_hardcoded_c2_url` — 명령·제어 서버 URL 하드코딩

**학술 근거**:
📖 **Arp et al. (2014) DREBIN** §S5 "Network addresses" — 네트워크 주소 feature 입니다. DOI: [10.14722/ndss.2014.23247](https://doi.org/10.14722/ndss.2014.23247)
📖 **Karbab et al. (2018)** — *"MalDozer: Automatic framework for android malware detection using deep learning"*. Digital Investigation, 24, S48–S59. DOI: [10.1016/j.diin.2018.01.007](https://doi.org/10.1016/j.diin.2018.01.007)

**한국 법령**:
⚖️ 정보통신망법 제48조 제2항
⚖️ 통신비밀보호법

**산업 자료**: S2W TALON 보고서 — 한국 보이스피싱 패밀리는 Firebase Cloud Messaging (구글의 *푸시 알림 서비스*) 을 C&C 채널로 전용합니다.

**🔗 코드 매핑**:
- 검출: `pipeline/apk_analyzer._has_suspicious_url_constants()` 가 APK 안의 *문자열 풀* (string pool) 을 검사합니다.
- 의심 패턴 정규식: `_SUSPICIOUS_URL_PATTERNS` — IP 주소 직접 (`https?://\d+\.\d+\.\d+\.\d+`), 무료 도메인 (.tk·.ml·.ga·.cf·.gq), 비표준 포트가 들어 있습니다.

---

### 7.5 `apk_string_obfuscation` — 난독화 흔적 (단독 비권장)

**학술 근거**:
📖 **Wermke et al. (2018)** — *"A large scale investigation of obfuscation use in Google Play"* (구글 플레이의 난독화 사용 대규모 조사). **ACSAC '18**. DOI: [10.1145/3274694.3274726](https://doi.org/10.1145/3274694.3274726)
📖 **Pendlebury et al. (2019)** — [*"TESSERACT: Eliminating experimental bias in malware classification across space and time"*](https://www.usenix.org/conference/usenixsecurity19/presentation/pendlebury) (시간·공간 편향 제거). **USENIX Security 2019**

**🔗 코드 매핑**:
- 검출: `pipeline/apk_analyzer._looks_obfuscated()` 가 *1-2 글자 클래스명 비율 + 클래스 50개 이상* 임계값 휴리스틱을 적용합니다.
- 임계: `_OBFUSCATION_RATIO_THRESHOLD = 0.30` (30%), `_OBFUSCATION_MIN_CLASSES = 50`
- ⚠️ 정상 ProGuard (안드로이드 표준 난독화 도구) 사용 앱도 가능하므로 단독 사용은 권장하지 않습니다.

---

### 7.6 `apk_device_admin_lock` — 화면 강제 잠금

**학술 근거**:
📖 **Andronio, Zanero, & Maggi (2015)** — *"HelDroid: Dissecting and detecting mobile ransomware"* (안드로이드 랜섬웨어 해부·검출). **RAID 2015** 382–404쪽. DOI: [10.1007/978-3-319-26362-5_18](https://doi.org/10.1007/978-3-319-26362-5_18)
- 풀이: *DevicePolicyManager.lockNow API 가 어떻게 안드로이드 랜섬웨어의 화면 잠금에 악용되는지 분석한 논문입니다.*
📖 **Yang et al. (2015)** — *"Automated detection and analysis for Android ransomware"*. IEEE HPCC 2015. DOI: [10.1109/HPCC-CSS-ICESS.2015.39](https://doi.org/10.1109/HPCC-CSS-ICESS.2015.39)

**한국 법령**:
⚖️ 정보통신망법 제48조 제2항 — *대법원 2017도16520 (2019.12.12) "결과 발생 불요"* 판례 (실제 피해가 없어도 처벌됩니다)
⚖️ 형법 제314조 제2항 (컴퓨터등 장애 업무방해)

**🔗 코드 매핑**: `pipeline/apk_analyzer._has_method_xref(analysis, "Landroid/app/admin/DevicePolicyManager;", "lockNow")` 에서 검출합니다.

---

## 8. 카테고리 H — APK 동적 분석 Lv 3 (interface-first)

> ⚠️ **로컬 실행 절대 금지** (HARD BLOCK) — `APK_DYNAMIC_ENABLED=0` 으로 기본 비활성입니다. 어떤 환경변수 조합으로도 *현재 호스트에서* APK 를 실행할 수 없게 만들어 두었습니다. 격리 가상머신에서만 동작하며, 실제 가상머신 stack 은 future work 입니다.

### 8.0 Lv 3 의 의도 — *interface-first* 설계 (자문·발표용 narrative)

ScamGuardian 의 동적 분석 Lv 3 은 다음과 같은 *다층 방어 (defense in depth)* 의 **마지막 layer** 입니다.

| Layer | 역할 | 구현 상태 |
|-------|------|----------|
| Lv 1 (정적, manifest+권한) | 1차 트리아지 — 권한 조합 패턴 | ✅ 구현 |
| Lv 2 (심화 정적, bytecode) | 2차 분석 — API 호출 패턴 | ✅ 구현 |
| Lv 3 (동적, 가상머신) | 최종 검증 — 실제 행동 관찰 | 🚧 인터페이스만 |

Lv 3 은 격리 가상머신 (sandbox VM) 안에서 APK 를 *실제로* 실행하여 행동을 관찰하는 layer 입니다. 격리 환경 (예: Cuckoo Sandbox · MobSF Dynamic · 자체 구축 Android emulator stack) 의 통합은 본 학부 졸업작품의 범위를 넘어 *future work* 로 분리되었습니다.

**그러나 Lv 3 의 5개 신호 정의·검출 신호화 인터페이스·안전 정책 (HARD BLOCK) 은 v1.5 시점에서 이미 코드에 박혀 있습니다.** 이는 다음 두 가지를 의미합니다.

1. **외부 가상머신 stack 통합 시 즉시 작동**: future work 로 격리 VM 이 통합되는 시점에, `pipeline/apk_analyzer.analyze_apk_dynamic()` 의 결과를 `pipeline/signal_detector.py` 가 그대로 신호화합니다. API contract 와 응답 schema 변경이 필요 없습니다.

2. **로컬 호스트 실행 영구 차단**: `APK_DYNAMIC_ENABLED=0` 기본값과 5단계 enum 정책 (`APKDynamicStatus.{DISABLED, BLOCKED_LOCAL, NOT_CONFIGURED, COMPLETED, ERROR}`) 은 어떤 환경변수 조합으로도 현재 호스트에서 APK 가 실행되지 않도록 설계되었습니다. 이는 학부생 운영 환경의 안전을 위한 의도적 설계입니다 (호스트가 멀웨어에 감염되면 실험·과제 데이터 전체가 손상되기 때문입니다).

**자문·발표 표현 (권장)**:
- ❌ *"Lv 3 동적 분석을 구현했습니다."*
- ✅ *"Lv 3 동적 분석은 interface-first 로 설계되었으며, 외부 격리 가상머신 통합은 future work 입니다. v1.5 시점에서 5개 후보 신호 정의·검출 신호화·안전 정책이 코드에 박혀 있어, 가상머신 통합 시 즉시 작동하는 architecture 입니다."*

---

### Lv 3 5개 신호의 학술 근거 (공통)

📖 **Mavroeidis & Bromander (2017)** — *Cyber Threat Intelligence Model* (사이버 위협 인텔리전스 모델) — *C&C 인프라 기반 검출 모델입니다.*
📖 **Kim et al. (2022) HearMeOut** — SMS 가로채기 / 화면 오버레이 / 자격증명 탈취 동작을 관찰했습니다. **MobiSys '22**. DOI: [10.1145/3498361.3538939](https://doi.org/10.1145/3498361.3538939) ⭐
📖 **Fratantonio et al. (2017) Cloak and Dagger** — UI 가로채기 동작을 학술적으로 검증했습니다. **IEEE S&P 2017**. DOI: [10.1109/SP.2017.39](https://doi.org/10.1109/SP.2017.39)
📖 [**OWASP Mobile Top 10**](https://owasp.org/www-project-mobile-top-10/) — *모바일 보안 위협 10대 카테고리*

**산업 자료**:
- [Frida](https://frida.re/) — *동적 인스트루먼테이션 도구* (실행 중인 앱에 후크를 걸어 동작을 관찰합니다)
- S2W TALON [SecretCalls Part 2](https://medium.com/s2wblog) / [TheftCalls](https://medium.com/s2wblog) / [HeadCalls](https://medium.com/s2wblog)

---

### 8.1 `apk_runtime_c2_network_call` — C&C 도메인 호출 관찰

**구현 상태**: 🚧 인터페이스 정의 완료, 외부 격리 VM 통합 시 작동 (future work)
**현재 동작**: `APKDynamicStatus.NOT_CONFIGURED` 또는 `APKDynamicStatus.DISABLED` 반환

**예정된 검출 의미**: 격리 가상머신에서 APK 를 실행했을 때, hardcoded 또는 dynamic resolved C&C 서버로의 *실제 네트워크 호출* 이 관찰됨. 정적 분석 (`apk_hardcoded_c2_url`) 이 *문자열* 만 보는 데 비해 동적은 *실제 통신* 관찰 — false positive 거의 없음.

**학술·산업 근거**: 위 §8 공통 학술 근거 (특히 Mavroeidis & Bromander 2017 + S2W TALON 한국 보이스피싱 인프라 분석)

**🔗 코드 매핑**: `pipeline/apk_analyzer.analyze_apk_dynamic()` 진입 → 결과를 `pipeline/signal_detector.py` 가 signal 화 → `pipeline/config.py:FLAG_RATIONALE["apk_runtime_c2_network_call"]` 학술 근거 박힘.

---

### 8.2 `apk_runtime_sms_intercepted` — SMS 자동 가로채기 동작 관찰

**구현 상태**: 🚧 인터페이스 정의 완료, 외부 격리 VM 통합 시 작동 (future work)
**현재 동작**: `APKDynamicStatus.NOT_CONFIGURED` / `DISABLED` 반환

**예정된 검출 의미**: 가상 SMS 수신을 에뮬레이터에서 시뮬레이션했을 때 APK 가 자동으로 가로채 외부 서버로 재전송하는 동작 관찰. 정적 분석 (`apk_sms_auto_send_code`) 은 *코드 존재* 만 검증, 동적은 *실제 가로채기 행동* 관찰 — 매우 강한 증거. SecretCalls 류 SMS 인증번호 탈취 핵심 동작.

**학술·산업 근거**: Kim et al. 2022 HearMeOut + S2W TALON SecretCalls + 통신사기피해환급법 제2조 제2호 + 정보통신망법 제48조

**🔗 코드 매핑**: `pipeline/apk_analyzer.analyze_apk_dynamic()` → `pipeline/config.py:FLAG_RATIONALE["apk_runtime_sms_intercepted"]`

---

### 8.3 `apk_runtime_overlay_attack` — 화면 오버레이 공격 관찰

**구현 상태**: 🚧 인터페이스 정의 완료, 외부 격리 VM 통합 시 작동 (future work)
**현재 동작**: `APKDynamicStatus.NOT_CONFIGURED` / `DISABLED` 반환

**예정된 검출 의미**: 에뮬레이터에 정상 은행 앱이 설치된 상태에서 의심 APK 가 SYSTEM_ALERT_WINDOW 권한으로 가짜 로그인 화면을 *실제로* 띄우는 동작 관찰. 정적 분석 (`apk_accessibility_abuse`) 은 *권한 + 코드 존재* 만 봄, 동적은 *실제 오버레이 시도* 관찰 — KrBanker 류 핵심 공격 동작.

**학술·산업 근거**: Fratantonio et al. 2017 Cloak and Dagger + S2W TALON KrBanker + OWASP Mobile Top 10 (M2)

**🔗 코드 매핑**: `pipeline/config.py:FLAG_RATIONALE["apk_runtime_overlay_attack"]`

---

### 8.4 `apk_runtime_credential_exfiltration` — 자격증명 외부 송신 관찰

**구현 상태**: 🚧 인터페이스 정의 완료, 외부 격리 VM 통합 시 작동 (future work)
**현재 동작**: `APKDynamicStatus.NOT_CONFIGURED` / `DISABLED` 반환

**예정된 검출 의미**: 에뮬레이터에 가상 자격증명 (계정·비밀번호·OTP) 입력 시 APK 가 외부 서버로 *실제로* 송신하는 동작 관찰. Frida hook 으로 HTTP/HTTPS payload 관찰. 정상 앱도 자격증명 송신하지만 *서버 도메인 일치* 확인으로 false positive 차단.

**학술·산업 근거**: Frida 동적 인스트루먼테이션 + OWASP Mobile Top 10 (M3 Insecure Communication) + KISA 모바일 자격증명 탈취 동향

**🔗 코드 매핑**: `pipeline/config.py:FLAG_RATIONALE["apk_runtime_credential_exfiltration"]`

---

### 8.5 `apk_runtime_persistence_install` — 부팅 시 자동 시작·DeviceAdmin 활성화 관찰

**구현 상태**: 🚧 인터페이스 정의 완료, 외부 격리 VM 통합 시 작동 (future work)
**현재 동작**: `APKDynamicStatus.NOT_CONFIGURED` / `DISABLED` 반환

**예정된 검출 의미**: 에뮬레이터 재부팅 시뮬레이션 시 APK 가 자동 시작되는지 (`BOOT_COMPLETED` receiver) + DeviceAdmin enable 시도 관찰. 한국 보이스피싱 패밀리는 피해자가 앱을 종료해도 다시 살아나도록 지속성 설치 — 사용자 의도와 어긋나는 자동 실행은 강한 신호.

**학술·산업 근거**: Android `BOOT_COMPLETED` Permission Documentation + Android `DevicePolicyManager` API + KISA 안드로이드 악성앱 동향 + S2W TALON

**🔗 코드 매핑**: `pipeline/config.py:FLAG_RATIONALE["apk_runtime_persistence_install"]`

---

### 8.6 Lv 3 공통 코드 매핑

- 진입: `pipeline/apk_analyzer.analyze_apk_dynamic()`
- 안전 정책 5단계 enum: `APKDynamicStatus.{DISABLED, BLOCKED_LOCAL, NOT_CONFIGURED, COMPLETED, ERROR}` — `pipeline/apk_analyzer.py` 정의
- 검출 신호화: `pipeline/signal_detector.py` 가 *status=COMPLETED* 일 때만 5개 flag 신호화. 그 외 status 는 *"동적 분석 미수행"* 메타데이터로 응답에 포함되지만 신호화되지 않음.
- 환경변수 (모두 옵션, 기본 비활성): `APK_DYNAMIC_ENABLED` / `APK_DYNAMIC_BACKEND` / `APK_DYNAMIC_REMOTE_URL` / `APK_DYNAMIC_REMOTE_TOKEN` / `APK_DYNAMIC_TIMEOUT`. 자세한 내용은 CLAUDE.md "APK Detection Architecture (3-tier)" 섹션 참조.

---

## 9. 신호 사용 가이드라인

**모든 신호는 단독으로 사용하지 않고, 누적·조합 시점에서만 강해집니다.**

특히 **거짓 양성 (false positive) 가 큰 신호** 는 다음과 같습니다.

| 신호 | 정상 사례 |
|---|---|
| `apk_self_signed` | 정상 사이드로딩 앱 |
| `apk_string_obfuscation` | 정상 ProGuard 사용 앱 |
| `apk_accessibility_abuse` (단독) | 정상 장애인 보조 앱 |
| `suspicious_writing_style` | 정상 외국인이 쓴 한국어 |
| `ai_generated_content_suspected` | 정상 AI 활용 콘텐츠 |

이런 신호는 *권한 조합·사칭 키워드·서명 등 다른 강한 신호와 결합 시점에서만* 의미가 있습니다.

**시스템 정체성 (CLAUDE.md)**: 신호 검출 + 학술/법적 근거를 보고만 합니다. 판정 logic 은 통합 기업 (통신사·은행·메신저 앱) 이 자체 위험 허용도 (risk tolerance) 에 따라 구현합니다.

---

## 10. Bibliography (참고 문헌 일람)

### 10.1 학술 논문 / 단행본 (DOI/URL 동반)

| 인용 | 학술지·학회 | DOI / URL |
|---|---|---|
| Andronio, Zanero, & Maggi (2015) HelDroid | RAID 2015 (Springer) | [10.1007/978-3-319-26362-5_18](https://doi.org/10.1007/978-3-319-26362-5_18) |
| Arp et al. (2014) DREBIN ⭐ | NDSS 2014 | [10.14722/ndss.2014.23247](https://doi.org/10.14722/ndss.2014.23247) / [PDF](https://www.ndss-symposium.org/wp-content/uploads/2017/09/11_3_1.pdf) |
| Bilge et al. (2009) EXPOSURE | NDSS 2009 | [PDF](https://www.ndss-symposium.org/wp-content/uploads/2017/09/14_3.pdf) |
| Cialdini (2021) Influence ⭐ | Harper Business 단행본 | — |
| Cova, Kruegel, & Vigna (2010) drive-by | WWW '10 | [10.1145/1772690.1772720](https://doi.org/10.1145/1772690.1772720) |
| Felt et al. (2011) Permissions Demystified | ACM CCS 2011 | [10.1145/2046707.2046779](https://doi.org/10.1145/2046707.2046779) |
| Florêncio & Herley (2013) | Springer | [10.1007/978-1-4614-1981-5_2](https://doi.org/10.1007/978-1-4614-1981-5_2) |
| Frankel (2012) Ponzi Scheme Puzzle | Oxford UP 단행본 | — |
| Fratantonio et al. (2017) Cloak and Dagger | IEEE S&P 2017 | [10.1109/SP.2017.39](https://doi.org/10.1109/SP.2017.39) |
| Hao et al. (2016) PREDATOR | ACM CCS 2016 | [10.1145/2976749.2978317](https://doi.org/10.1145/2976749.2978317) |
| Invernizzi et al. (2016) Cloak of visibility | IEEE S&P 2016 | [10.1109/SP.2016.50](https://doi.org/10.1109/SP.2016.50) |
| Karbab et al. (2018) MalDozer | Digital Investigation | [10.1016/j.diin.2018.01.007](https://doi.org/10.1016/j.diin.2018.01.007) |
| **Kim et al. (2022) HearMeOut** ⭐ | MobiSys '22 | [10.1145/3498361.3538939](https://doi.org/10.1145/3498361.3538939) |
| Kintis et al. (2017) Combosquatting | ACM CCS 2017 | [10.1145/3133956.3134002](https://doi.org/10.1145/3133956.3134002) |
| Klien & Strohmaier (2012) Short links | ACM Hypertext '12 | [10.1145/2309996.2310002](https://doi.org/10.1145/2309996.2310002) |
| Langenderfer & Shimp (2001) | Psychology & Marketing | [10.1002/mar.1029](https://doi.org/10.1002/mar.1029) |
| Lea, Fischer, & Evans (2009) OFT1070 | UK OFT | [PDF](https://webarchive.nationalarchives.gov.uk/ukgwa/20140402142426/http://www.oft.gov.uk/shared_oft/reports/consumer_protection/oft1070.pdf) |
| Loewenstein (1996) | OBHDP | [10.1006/obhd.1996.0028](https://doi.org/10.1006/obhd.1996.0028) |
| Ma et al. (2009) Beyond blacklists | ACM SIGKDD 2009 | [10.1145/1557019.1557153](https://doi.org/10.1145/1557019.1557153) |
| Maggi et al. (2013) Short URLs | WWW '13 | [10.1145/2488388.2488463](https://doi.org/10.1145/2488388.2488463) |
| Marchal et al. (2017) Off-the-Hook | IEEE TC | [10.1109/TC.2017.2703808](https://doi.org/10.1109/TC.2017.2703808) |
| Mariconti et al. (2017) MaMaDroid | NDSS 2017 | [10.14722/ndss.2017.23353](https://doi.org/10.14722/ndss.2017.23353) / [arXiv](https://arxiv.org/abs/1612.04433) |
| Mitchell et al. (2023) DetectGPT | ICML 2023 | [arXiv:2301.11305](https://arxiv.org/abs/2301.11305) |
| Modic & Lea (2013) | SSRN | [10.2139/ssrn.2364464](https://doi.org/10.2139/ssrn.2364464) |
| Nikiforakis et al. (2013) Bitsquatting | WWW '13 | [10.1145/2488388.2488474](https://doi.org/10.1145/2488388.2488474) |
| Oest et al. (2019) PhishFarm | IEEE S&P 2019 | [10.1109/SP.2019.00049](https://doi.org/10.1109/SP.2019.00049) |
| OWASP WSTG v4.2 | 비영리 표준 | [URL](https://owasp.org/www-project-web-security-testing-guide/) |
| Pendlebury et al. (2019) TESSERACT | USENIX Security | [PDF](https://www.usenix.org/conference/usenixsecurity19/presentation/pendlebury) |
| Peng et al. (2019) VirusTotal blackbox | ACM IMC 2019 | [10.1145/3355369.3355585](https://doi.org/10.1145/3355369.3355585) |
| Provos et al. (2008) iFRAMEs | USENIX Security | [PDF](https://www.usenix.org/legacy/event/sec08/tech/full_papers/provos/provos.pdf) |
| Sahoo, Liu, & Hoi (2017) | arXiv | [arXiv:1701.07179](https://arxiv.org/abs/1701.07179) |
| Salem, Banescu, & Pretschner (2021) Maat | ACM TOPS | [10.1145/3465361](https://doi.org/10.1145/3465361) |
| Spaulding et al. (2016) Typosquatting | arXiv | [arXiv:1603.02767](https://arxiv.org/abs/1603.02767) |
| **Stajano & Wilson (2011)** ⭐ | CACM 54(3) | [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872) |
| Truong et al. (2014) Company you keep | WWW 2014 | [arXiv:1312.3245](https://arxiv.org/abs/1312.3245) |
| Tu et al. (2016) SoK Robocalls | IEEE S&P 2016 | [10.1109/SP.2016.27](https://doi.org/10.1109/SP.2016.27) |
| Wang, Savage, & Voelker (2011) | ACM CCS 2011 | [10.1145/2046707.2046763](https://doi.org/10.1145/2046707.2046763) |
| Wermke et al. (2018) Obfuscation | ACSAC 2018 | [10.1145/3274694.3274726](https://doi.org/10.1145/3274694.3274726) |
| **Whitty (2013)** ⭐ Persuasive techniques | BJC 53(4) | [10.1093/bjc/azt009](https://doi.org/10.1093/bjc/azt009) |
| Whitty & Buchanan (2012) Romance scam | CyberPsych & Behavior | [10.1089/cyber.2011.0352](https://doi.org/10.1089/cyber.2011.0352) |
| Whitty & Buchanan (2016) Psych impact | CCJ | [10.1177/1748895815603773](https://doi.org/10.1177/1748895815603773) |
| Witte (1992) Fear appeals EPPM | Comm Monographs | [10.1080/03637759209376276](https://doi.org/10.1080/03637759209376276) |
| Xia et al. (2020) Crypto exchange scams | Computers & Security | [10.1016/j.cose.2020.101993](https://doi.org/10.1016/j.cose.2020.101993) |
| Yang et al. (2015) Android ransomware | IEEE HPCC 2015 | [10.1109/HPCC-CSS-ICESS.2015.39](https://doi.org/10.1109/HPCC-CSS-ICESS.2015.39) |
| Zhou & Jiang (2012) Dissecting Android | IEEE S&P 2012 | [10.1109/SP.2012.16](https://doi.org/10.1109/SP.2012.16) |

⭐ = ScamGuardian 의 핵심 학술 frame work 입니다 — 모든 발표·논문에서 *반드시* 인용해야 합니다.

### 10.2 한국 법령 (현행 2026.05 기준)

모든 법령은 [국가법령정보센터 law.go.kr](https://www.law.go.kr/) 에서 조회 가능합니다.

- 「전기통신금융사기 피해 방지 및 피해금 환급에 관한 특별법」 제1·2·4·9·10·15조의2
- 「정보통신망 이용촉진 및 정보보호 등에 관한 법률」 제23조의2·제48조·제49조·제50조·제70조의2·제71조
- 「전기통신사업법」 제32조의5 (영리목적 광고성 정보 송신 제한 협조 의무) / 제84조의2 (전화번호 거짓표시 금지) — 1년 이하 징역 또는 1천만 원 이하 벌금
- 「전자금융거래법」 제2조·제6조·제9조·제49조
- 「유사수신행위의 규제에 관한 법률」 제1·2·3·6조 (2024.05.28 시행 — 가상자산 포함)
- 「자본시장과 금융투자업에 관한 법률」 제17·38·55·445조
- 「특정금융거래정보의 보고 및 이용 등에 관한 법률」(특정금융정보법) 제2조·제7조 — 가상자산사업자 신고 의무
- 「표시·광고의 공정화에 관한 법률」 제3·17조 / 시행령 제3조
- 「전자상거래 등에서의 소비자보호에 관한 법률」 제8·12·13·17·21·40조
- 「대부업 등의 등록 및 금융이용자 보호에 관한 법률」 — 대출 명목 선납금 요구 금지
- 「직업안정법」 제32조 — 채용 명목 선납금 요구 금지
- 「약사법」 제68조 — 의약품 허위·과대 광고 금지
- 「개인정보 보호법」 제15·16·17·18·22·23·24의2조
- 「형법」 제225·227·230·283·284·285·286·314·347·347의2·350·351조
- 「특정경제범죄 가중처벌 등에 관한 법률」 제3조
- 「통신비밀보호법」 제3·16조
- 「부정경쟁방지 및 영업비밀보호에 관한 법률」 제2조 제1호
- 「상표법」 제108조
- 「은행법」 제14·66의2조
- 「인터넷주소자원에 관한 법률」 제12조
- 「가상자산 이용자 보호 등에 관한 법률」 제2조

### 10.3 정부·산업 보고서

**한국**:
- 금융감독원 [「2023년 보이스피싱 피해현황 분석」](https://www.fss.or.kr/), 2024.03 — *피해액 1,965억 원, 1인당 1,700만 원*
- 경찰청 [「2025년 1분기 보이스피싱 현황」](https://www.police.go.kr/), 2025.04.27 — *위험 키워드 5종 공식 공개*
- KISA (한국인터넷진흥원), [Insight 2024 Vol.07](https://www.kisa.or.kr/) (피싱 대응) / [2025 Vol.01](https://www.kisa.or.kr/) (DeepSeek)
- KISA 보호나라 [청첩장·부고 스미싱 주의 권고](https://www.boho.or.kr/)
- 금융위원회 [유사수신 Q&A](https://www.fsc.go.kr/)
- 헌법재판소 2003.02.27. 선고 2002헌바4 — 유사수신법 합헌
- 대법원 2017도16520 (2019.12.12) / 2024도6831 (2024.10.25)
- S2W TALON [SecretCalls Spotlight](https://medium.com/s2wblog) (2024) / [TheftCalls](https://medium.com/s2wblog) (2024) / [HeadCalls](https://medium.com/s2wblog) (2025.08)
- 안랩 ASEC 분기 동향 / 이스트시큐리티 ESRC

**국외**:
- FBI [*2024 IC3 Report*](https://www.ic3.gov/AnnualReport/Reports/2024_IC3Report.pdf), 2025.04 (859,532건 / $16.6B / +33% YoY)
- FTC [*Consumer Sentinel Data Book 2024*](https://www.ftc.gov/reports/consumer-sentinel-network-data-book-2024), 2025
- APWG (Anti-Phishing Working Group — *반(反)피싱 작업 그룹*) [*Phishing Activity Trends*](https://apwg.org/trendsreports/) (2024 Q1-Q4 / 2025 Q1)
- [Google Play Console — SMS/Call Log permissions](https://support.google.com/googleplay/android-developer/answer/9047303)
- [Android Open Source Project — Permissions](https://developer.android.com/guide/topics/permissions/overview)
- [Android Partner Vulnerability Initiative](https://bugs.chromium.org/p/apvi/), 2022.11
- [Palo Alto Unit42 — Bad Certificate Management](https://unit42.paloaltonetworks.com/bad-certificate-management-google-play-store/) (2014) / [Cybersquatting](https://unit42.paloaltonetworks.com/cybersquatting/) (2020)
- [Google Safe Browsing Transparency Report](https://transparencyreport.google.com/safe-browsing/overview)
- [Frida Dynamic Instrumentation](https://frida.re/)
- [Corrata — Dangerous Permissions Android](https://corrata.com/dangerous-permissions-android/), 2022

---

## 11. 인용 시 주의사항 (Caveats)

1. **법령 개정**: 한국 법령은 빈번하게 개정됩니다. 자문 미팅 직전에 [law.go.kr](https://www.law.go.kr) 에서 재확인하시기 바랍니다. 본 문서는 2026.05 기준입니다.
2. **페이지 번호**: 학술 논문 페이지는 게재본 기준입니다 (Stajano & Wilson CACM 54(3) pp.70–75 등). Cialdini *Influence* 는 판본별로 페이지가 다르므로 Chapter 단위로 인용하는 것을 우선합니다.
3. **거짓 양성 (false positive) 정직 표시**: 위 §0.6 / §9 표를 참조하시기 바랍니다. 단독 사용 비권장 신호 4종이 명시되어 있습니다.
4. **통계 시점**: *"1,965억 원·1인당 1,700만 원"* 은 2023년 (2024.03 발표) 기준입니다. 경찰청 자료에 따르면 *2025년 1분기만 3,116억 원* 으로 급증했습니다.
5. **산업 보고서 인용 정확성**: S2W·안랩·이스트시큐리티 등은 *peer-review (동료 평가)* 가 아니므로 학술 인용 시 *"산업 보고서"* 로 명시합니다. 학술 논문 (특히 **Kim et al. 2022 HearMeOut MobiSys'22**) 을 1차 근거로 사용합니다.
6. **저작권**: 외부 공개·논문 인용 시 각 출처의 저작권·인용 규약을 별도로 확인하시기 바랍니다. ACM/IEEE 논문은 보통 저자 사본 (author preprint) 으로 합법 접근이 가능합니다.
7. **시스템 정체성 일관 강조**: 본 신호 카탈로그는 ScamGuardian 이 *판정자 (verdict-maker) 가 아닌 검출자 (detector)* 임을 전제합니다. 발표·미팅에서 *"이 시스템은 다음 N 개의 위험 신호를 다음 근거로 검출합니다"* 라는 표현을 일관되게 사용합니다.
8. **다층 방어 narrative**: 본 신호 시스템은 **1차 정적 분석 트리아지** (triage — *환자 분류, 우선순위 분류*) 입니다. 동적 분석·사용자 교육·신고 채널 (☎112) 연계는 future work 로 분리되어 있습니다.

---

> 본 문서는 ScamGuardian 졸업작품의 **단일 참고서 (single reference book)** 입니다.
> 인용된 모든 학술 논문·법조항·정부 보고서는 2026년 5월 기준 *실제 존재* 하며 URL/DOI/조항 번호로 검증 가능합니다.
> 각 신호의 학술 근거는 `pipeline/config.py:FLAG_RATIONALE` 에 직접 박혀 있고, `/api/analyze` 응답의 `detected_signals[].rationale` / `.source` 로 외부 클라이언트에 transparent (투명하게) 노출됩니다.
