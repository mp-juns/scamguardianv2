# ScamGuardian — 검출 신호 학술·법적 근거 + 코드 매핑

**문서 버전**: v1.3 (2026-05-05) — 자문·심사용 친절판
**용도**: 자문 미팅 · 학부 졸업 발표 · 졸업 심사용 *단일 참고서*
**작성 원칙**: 영어 줄임말·전문 용어가 처음 등장할 때마다 한국어로 풀어쓰고, 각 학술·법령 인용이 *우리 코드의 어디에 박혀 있는지* 끝에 명시한다.

---

## 0. 개요

### 0.1 이 문서의 목적

ScamGuardian 이 검출하는 모든 위험 신호 (`detected_signals` — *"검출된 신호 목록"*) 각각에 대해:

1. **학술 근거** — 동료 평가(peer-review·*전문가 심사를 거친 학술지*) 논문 또는 단행본
2. **한국 법령 근거** — 위반 시 처벌 조항
3. **정부·산업 보고서 근거** — 통계·사례
4. **🔗 코드 매핑** — 이 근거가 *어떤 파일·어떤 검출 신호에 박혀 있는지*

### 0.2 이 시스템의 정체성 (가장 중요)

**ScamGuardian 은 "사기다/아니다" 판정을 내리는 시스템이 아니다.**

VirusTotal (*바이러스토탈* — 한 번에 70개 백신 엔진 결과를 모아 보여주는 무료 사이트) 이 "이 파일은 멀웨어다" 라고 단정하지 않고 *각 백신의 검출 결과만 모아서 표시* 하는 것과 똑같다.

```
❌ "이 메시지는 사기다"
✅ "이 메시지에서 다음 N 개의 위험 신호가 검출되었습니다.
    각 신호의 학술·법적 근거는 다음과 같습니다."
```

판정 (verdict — *"이건 사기다" 같은 결론*) 은 우리 시스템을 통합한 기업 (예: 통신사·은행·메신저 앱) 이 자기 서비스 정책에 맞게 한다.

### 0.3 본 문서 인용 표준

- **학술 논문** — 저자(연도). 제목. 학술지명, 권(호), 쪽수. DOI/URL 동반.
  - DOI (Digital Object Identifier · *논문 영구 식별자*) 는 [doi.org](https://doi.org/) 통해 항상 원문 접근 가능
- **단행본** — 저자(연도). 제목 (판). 출판사 — Chapter (장) 단위
- **한국 법조항** — 「법명」 제N조 제M항 — [국가법령정보센터(law.go.kr)](https://www.law.go.kr/) 에서 조회 가능
- **정부·산업 보고서** — 기관 / 보고서명 / 발간연월 — 가능한 한 원문 URL 동반

### 0.4 학회·저널 약어 풀이 (이 문서에서 자주 등장)

| 약어 | 풀이 | 분야 |
|---|---|---|
| **CACM** | Communications of the ACM (美 컴퓨터학회 *월간 회보*) | 컴퓨터과학 종합 |
| **ACM CCS** | Conference on Computer and Communications Security (ACM *컴퓨터·통신 보안 학회*) | 시스템 보안 최상위 |
| **NDSS** | Network and Distributed System Security *Symposium* (네트워크·분산시스템 보안 심포지엄) | 네트워크 보안 최상위 |
| **IEEE S&P** | IEEE Symposium on Security and Privacy (*"오클랜드 학회"* 로도 불림) | 보안·프라이버시 최상위 |
| **USENIX Security** | USENIX Security *Symposium* | 시스템 보안 최상위 4대 |
| **WWW** | The Web Conference (*"웹 컨퍼런스"*, 옛 WWW Conference) | 웹 기술 최상위 |
| **ACSAC** | Annual Computer Security Applications Conference (연례 *응용 보안 학회*) | 산업 응용 보안 |
| **MobiSys** | International Conference on Mobile Systems, Applications, and Services (*모바일 시스템 응용 학회*) | 모바일 시스템 최상위 |
| **ICML** | International Conference on Machine Learning (*머신러닝 국제 학회*) | AI/머신러닝 최상위 |
| **RAID** | International Symposium on Research in Attacks, Intrusions, and Defenses (*공격·침입·방어 연구 심포지엄*) | 침입탐지 |
| **BJC** | The British Journal of Criminology (*영국 범죄학 저널*) | 범죄학 최상위 |
| **OBHDP** | Organizational Behavior and Human Decision Processes (*조직 행동과 인간 의사결정 학술지*) | 행동경제학 |
| **SSRN** | Social Science Research Network (*사회과학 연구 네트워크*, 사전논문 저장소) | 학제 간 |

> 이 약어들은 모두 컴퓨터·범죄학·심리학 분야의 *최상위 학회/저널* 이다. 학술 인용에서 가장 권위 있는 출처.

### 0.5 자주 쓰는 전문 용어 풀이

| 용어 | 풀이 |
|---|---|
| **API** (Application Programming Interface) | *프로그램끼리 통신할 때 사용하는 약속된 인터페이스* |
| **OTP** (One-Time Password) | *일회용 비밀번호* — 은행 인증 시 받는 6자리 숫자 |
| **C&C 서버** (Command-and-Control) | *해커가 멀웨어를 원격 조종하는 명령·제어 서버* |
| **APK** (Android Package) | *안드로이드 앱 설치 파일* (`.apk` 확장자) |
| **dex** (Dalvik Executable) | *안드로이드 앱 안의 실행 코드* — 자바 컴파일 결과 |
| **bytecode** | *기계어 직전의 중간 코드* — 사람도 어느 정도 읽을 수 있음 |
| **xref** (Cross-Reference) | *코드 안에서 어떤 함수가 호출되는 지점들* |
| **manifest** (`AndroidManifest.xml`) | *앱이 요구하는 권한·구성 요소를 선언한 파일* |
| **CA** (Certificate Authority) | *공인 인증서를 발급하는 기관* (예: 한국정보인증) |
| **typosquatting** | *오타 유도 위장 도메인* — 예: `kakaotalkk.com` (가짜) vs `kakaotalk.com` (진짜) |
| **smishing** (SMS + phishing) | *문자 메시지 피싱* — 가짜 링크 클릭 유도 |
| **drive-by download** | *클릭 안 해도 페이지 열리자마자 자동 다운로드* — 악성 |
| **cloaking** | *봇과 사람에게 다른 페이지 보여주기* — 검색엔진을 속이는 수법 |
| **obfuscation** | *난독화* — 코드를 일부러 읽기 어렵게 변환 |
| **peer-review** | *동료 평가* — 학술 논문의 표준. 같은 분야 전문가 2-3명이 *익명으로* 검증 |
| **defense in depth** | *다층 방어* — 여러 층의 검사가 겹쳐서 한 층이 뚫려도 다음 층이 잡음 |

### 0.6 false positive 의 정직한 표시

검출 신호 중 일부는 *정상 콘텐츠에서도 흔히 나타남*. 단독 사용 시 **거짓 양성** (false positive — *정상인데 위험으로 잘못 판단*) 위험이 큼:

- `apk_self_signed` (자체 서명) — 정상 사이드로딩 앱도 자체 서명 사용
- `apk_string_obfuscation` (난독화) — 정상 앱도 ProGuard 같은 표준 도구 사용
- `suspicious_writing_style` (이상한 문체) — 정상 외국인이 쓴 한국어
- `ai_generated_content_suspected` (AI 생성 의심) — 정상 AI 활용 콘텐츠

이런 신호는 **다른 강한 신호와 결합 시점에서만** 의미가 있다 — *예: 자체 서명 + 위험 권한 4개 + 사칭 키워드 동시* 면 신뢰도 매우 높음.

### 0.7 코드에서 학술 근거가 어떻게 흐르는가

```
①  학술 논문·법령 인용
        ↓
②  pipeline/config.py 의 FLAG_RATIONALE 사전(dictionary)에 박힘
    예: FLAG_RATIONALE["urgent_transfer_demand"] = {
            "rationale": "Stajano-Wilson 2011 의 Time Principle ...",
            "source": "CACM 54(3) / 통신사기피해환급법 제2조 제2호"
        }
        ↓
③  pipeline/signal_detector.py 가 검출 결과를
    DetectedSignal(flag, label_ko, rationale, source, ...) 객체로 변환
        ↓
④  pipeline/runner.py 가 전체 분석을 실행하고
    DetectionReport.detected_signals[] 로 모음
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
| Phase 0.6 — APK 동적 Lv 3 *(인터페이스만)* | `pipeline/apk_analyzer.analyze_apk_dynamic` | `apk_runtime_*` 5종 — 격리 가상머신에서만 동작, 로컬 실행은 어떤 경우에도 차단 |
| Phase 4 (인터넷 교차 검증) | `pipeline/verifier.py` | `urgent_transfer_demand`, `fake_government_agency`, `phone_scam_reported` 외 텍스트 신호 |
| LLM 보조 검출 | `pipeline/llm_assessor.py` | LLM 이 추가 제안 — 신뢰도 임계값 (0.75) 통과 시 채택 |

---

## 1. 카테고리 A — 사기범의 행동 패턴 (심리학·범죄학 기반)

### 1.1 `urgent_transfer_demand` — 즉각 송금·이체 요구

**우리가 검출하는 것**: 통화·메시지에서 *"지금 즉시 송금하세요" / "10분 안에 이체"* 같은 패턴.

**왜 위험한가 (학술 근거)**:

📖 **Stajano & Wilson (2011)** — *"Understanding scam victims: seven principles for systems security"* (사기 피해자 이해: 시스템 보안의 7원칙)
- 학술지: **CACM** (美 컴퓨터학회 월간 회보), 54권 3호, 70–75쪽
- DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)
- 핵심 인용 (저자의 §"Time Principle" — 시간 원칙):
  > *"중요한 결정을 시간 압박 아래에서 내릴 때, 사람은 평소와 다른 *덜 합리적인* 의사결정 전략을 쓰게 되며, 사기범은 피해자를 그 방향으로 유도한다."*
- 풀이: *시간이 없다고 생각하면 머리가 멈춤. 사기꾼은 일부러 그 상태로 몰아넣음.*

📖 **Cialdini (2021)** — *"Influence: The Psychology of Persuasion"* (영향력: 설득의 심리학, 신판 확장본)
- 단행본, Harper Business 출판
- Chapter 7 "Scarcity" (희소성) — *"한정 시간 압박"* 절
- 풀이: *"오늘만 할인" 같은 한정 시간 표현이 왜 사람을 움직이게 만드는지의 심리학적 메커니즘.*

📖 **Loewenstein (1996)** — *"Out of control: Visceral influences on behavior"* (통제 불능: 의사결정에 미치는 본능적 영향)
- 학술지: **OBHDP** (조직 행동과 인간 의사결정 학술지), 65권 3호
- DOI: [10.1006/obhd.1996.0028](https://doi.org/10.1006/obhd.1996.0028)
- 풀이: *공포·욕망·시간 압박 같은 "본능적 자극(visceral)" 이 합리적 판단을 어떻게 마비시키는지 행동경제학 모델.*

**한국 법령**:

⚖️ [통신사기피해환급법 제2조 제2호](https://www.law.go.kr/법령/전기통신금융사기피해방지및피해금환급에관한특별법) — *"전기통신금융사기란 전기통신을 이용해 타인을 기망(속임)·공갈(협박)하여 자금을 송금·이체하도록 하는 행위"*
⚖️ [형법 제347조 제1항(사기)](https://www.law.go.kr/법령/형법) — *"사람을 속여 재물을 받거나 재산상 이익을 취득"* — 10년 이하 징역
⚖️ 통신사기피해환급법 제15조의2 제1항 — *전기통신금융사기 가해자: 1년 이상 유기징역*

**정부·산업 보고서**:

📊 **금융감독원** [「2023년 보이스피싱 피해현황 분석」](https://www.fss.or.kr/), 2024.03 — 피해액 **1,965억 원** (전년 대비 +35.4%), 1인당 평균 1,700만 원
📊 **FBI** [*2024 Internet Crime Report*](https://www.ic3.gov/AnnualReport/Reports/2024_IC3Report.pdf) (미국 연방수사국 *인터넷 범죄 신고센터* 연간 보고서), 2025.04 — 피싱·사칭 피해 $16.6B (33% 증가)

**🔗 우리 코드의 어디**:
- 검출 신호 키: `urgent_transfer_demand` (한국어 라벨: *"즉각 송금·이체 요구"*)
- 학술 근거 박힘: `pipeline/config.py` 의 `FLAG_RATIONALE["urgent_transfer_demand"]` 사전
- 검출 코드: `pipeline/verifier.py` — Serper 검색으로 키워드·패턴 매칭
- 응답 노출: `/api/analyze` 결과의 `detected_signals[]` 항목 — 각각 학술 근거(`rationale`) 와 출처(`source`) 동반

---

### 1.2 `fake_government_agency` — 공권력·금융기관 사칭

**우리가 검출하는 것**: 검찰·경찰·금감원·국세청·은행 등 *공적 권위 기관* 을 사칭하는 패턴.

**왜 위험한가**:

📖 **Cialdini (2021), Chapter 6 "Authority: Directed Deference"** — *"권위: 지시받은 복종"*
- 풀이: *제복·직함·말투만으로 사람들이 의심을 멈추는 심리* (예: 경찰관이라며 신분증을 보여주면 진위 확인을 안 하게 됨).

📖 **Stajano & Wilson (2011)** — §"Social Compliance Principle" (사회적 순응 원칙, **CACM 54권 3호** pp.71–72). DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)
- 핵심 인용:
  > *"사회는 사람들에게 권위에 의문을 던지지 않도록 훈련시킨다. 사기꾼은 이 '의심 정지' 를 악용한다."*

📖 **Modic & Lea (2013)** — *"Scam compliance and the psychology of persuasion"* (사기 순응과 설득의 심리학)
- **SSRN** (사회과학 연구 네트워크 사전논문 저장소). DOI: [10.2139/ssrn.2364464](https://doi.org/10.2139/ssrn.2364464)

**한국 법령**:

⚖️ [형법 제225조 (공문서 위조)](https://www.law.go.kr/법령/형법), 제227조 (허위공문서작성), 제230조 (공문서 부정행사)
⚖️ 통신사기피해환급법 제2조 제2호 / 제15조의2 제1항
⚖️ 「특정경제범죄 가중처벌 등에 관한 법률」 제3조 — *피해 5억 원 이상이면 가중처벌*

**정부·산업 보고서**:

📊 **경찰청 국가수사본부** [「2025년 1분기 보이스피싱 현황」](https://www.police.go.kr/), 2025.04.27 — 기관사칭형 **51%** (2,991건), 50대 이상 피해자 53%
📊 **금융감독원** 「2023년 보이스피싱 피해현황 분석」 — 정부기관 사칭형 **31.1%**
📊 **S2W TALON** (한국 보안 회사 *위협 인텔리전스* 팀) [*"Detailed Analysis of HeadCalls: Impersonation of Korean Public and Financial Institutions"*](https://medium.com/s2wblog), 2025.08

**🔗 우리 코드의 어디**:
- 신호: `fake_government_agency` (*"정부기관 사칭"*)
- 학술 근거: `pipeline/config.py:FLAG_RATIONALE["fake_government_agency"]` — Cialdini Authority + 형법 제225조 인용
- 검출: `pipeline/verifier.py` (인터넷 검색 교차 검증) + `pipeline/llm_assessor.py` (LLM 의미 분석)

---

### 1.3 `threat_or_coercion` — 협박·강요 발화

**우리가 검출하는 것**: *"체포된다 / 계좌 동결된다 / 고발하겠다"* 등 공포 고지로 의사결정을 마비시키는 패턴.

**왜 위험한가**:

📖 **Whitty (2013)** — *"The scammers persuasive techniques model"* (사기꾼의 설득 기법 모델)
- 학술지: **BJC** (영국 범죄학 저널), 53권 4호, 665–684쪽
- DOI: [10.1093/bjc/azt009](https://doi.org/10.1093/bjc/azt009)
- §"Stage 4: The Sting" (4단계: 결정타) — *위기를 만들어 즉시 행동하게 만듦*

📖 **Witte (1992)** — *"Putting the fear back into fear appeals"* (공포 호소에 공포를 다시 넣다)
- *EPPM* (Extended Parallel Process Model — 확장 병렬 처리 모형) 이론
- 학술지: Communication Monographs (커뮤니케이션 학술지), 59권 4호
- DOI: [10.1080/03637759209376276](https://doi.org/10.1080/03637759209376276)
- 풀이: *공포 메시지가 어떤 조건에서 행동을 *강제* 하는지의 표준 모형.*

📖 **Langenderfer & Shimp (2001)** — *"Consumer vulnerability to scams, swindles, and fraud: A new theory of visceral influences on persuasion"* (소비자의 사기 취약성: 본능적 영향이 설득에 미치는 새 이론)
- 학술지: Psychology & Marketing (심리학과 마케팅), 18권 7호. DOI: [10.1002/mar.1029](https://doi.org/10.1002/mar.1029)

**한국 법령**:

⚖️ [형법 제283조 (협박)](https://www.law.go.kr/법령/형법) — *3년 이하 징역, 500만 원 이하 벌금*
⚖️ 형법 제350조 (공갈) — *협박 + 재산상 이익 = 가중처벌*
⚖️ 통신사기피해환급법 제2조 제2호 (기망·공갈 명시 포함)

**🔗 코드 매핑**:
- 신호: `threat_or_coercion`
- `pipeline/config.py:FLAG_RATIONALE["threat_or_coercion"]` — *형법 제283조 + Witte EPPM 인용*
- 검출: `pipeline/verifier.py` + LLM 보조

---

### 1.4 시간 압박 (`urgent_transfer_demand` 와 통합)

학술 근거는 위 1.1 과 동일 (Stajano-Wilson Time Principle / Cialdini Scarcity / Loewenstein visceral). 별도 flag 없이 LLM 이 컨텍스트로 검출.

---

### 1.5 `medical_claim_unverified` — 미인증 의료 효능 주장 (사회적 증거 조작 포함)

**우리가 검출하는 것**: *"이 약 먹으면 암이 낫는다 / 당뇨가 사라진다"* 같은 식약처 미인증 효능 주장 + *가짜 후기·추천* 결합.

**왜 위험한가**:

📖 **Cialdini (2021), Chapter 4 "Social Proof: Truths Are Us"** — *사회적 증거: 다른 사람들이 그렇다 하면 우리도 그렇다고 믿는 심리*
📖 **Stajano & Wilson (2011)** §"Herd Principle" (군중 원칙, **CACM 54(3)** p.72) — *짜고 친 가짜 계정* (shills, sock-puppets, astroturfing, Sybil attack 등). DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)

**한국 법령**:

⚖️ 약사법 제68조 — *허위·과대 광고 금지*
⚖️ 식품의약품안전처 부당 광고 단속 지침
⚖️ 표시·광고 공정화법 제3조 제1항 제1·2호 / 제17조 제1호 (2년 이하 징역 / 1억5천만 원 이하 벌금)

**🔗 코드 매핑**: `medical_claim_unverified` — `pipeline/config.py:FLAG_RATIONALE["medical_claim_unverified"]` 에 약사법 + Cialdini Social Proof 인용

---

### 1.6 `impersonation_family` / `romance_foreign_identity` — 가족·연인 위장

**우리가 검출하는 것**:
- `impersonation_family`: *"엄마 나야"* 형 메신저피싱
- `romance_foreign_identity`: 해외 군인·의사·외교관 등 신분 위장 로맨스 스캠

**왜 위험한가**:

📖 **Whitty (2013)** — *"The Scammers Persuasive Techniques Model"* — *7단계 모델*: 동기부여 → 프로파일링 → 그루밍(친밀감 형성) → 결정타 → 지속 → (성적 학대) → 재피해. **BJC 53(4)**. DOI: [10.1093/bjc/azt009](https://doi.org/10.1093/bjc/azt009)
- 풀이: *로맨스 스캠이 짧은 사기가 아니라 몇 달에 걸친 **단계적 설득** 임을 학술적으로 모델링.*

📖 **Whitty & Buchanan (2012)** — *"The online romance scam: A serious cybercrime"*. CyberPsych & Behavior, 15(3). DOI: [10.1089/cyber.2011.0352](https://doi.org/10.1089/cyber.2011.0352)
📖 **Whitty & Buchanan (2016)** — *"The online dating romance scam: psychological impact"*. Criminology & Criminal Justice, 16(2). DOI: [10.1177/1748895815603773](https://doi.org/10.1177/1748895815603773)
📖 **Cialdini (2021), Chapter 5 "Liking"** — *"호감 원칙"* — *공통점·칭찬·협력으로 신뢰 형성*

**한국 법령**:
⚖️ 통신사기피해환급법 제2조 제2호 (메신저피싱 포섭)
⚖️ 형법 제347조 사기

**정부·산업 보고서**:
📊 금감원 「2023년 보이스피싱 피해현황 분석」 — 가족·지인 사칭 메신저피싱 **33.7%** (2위)
📊 FBI [*IC3 2024*](https://www.ic3.gov/AnnualReport/Reports/2024_IC3Report.pdf) — Romance/Confidence 별도 카테고리, 60대 이상 최다 피해

**🔗 코드 매핑**:
- `impersonation_family` → `pipeline/config.py:FLAG_RATIONALE["impersonation_family"]` (Cialdini Liking + Whitty 인용)
- `romance_foreign_identity` → `FLAG_RATIONALE["romance_foreign_identity"]` (Whitty 7-stage 모델 + FBI IC3)
- 검출: `pipeline/verifier.py` + `pipeline/llm_assessor.py`

---

## 2. 카테고리 B — 거래·상거래 신호

### 2.1 `abnormal_return_rate` — 비정상 수익률 약속

**우리가 검출하는 것**: *"월 10% 수익 / 일 1% 보장"* 등 시장 평균을 크게 초과하는 수익률 약속.

**왜 위험한가**:

📖 **Stajano & Wilson (2011)** §"Need and Greed Principle" (필요와 욕심 원칙, **CACM 54(3)** p.73). DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)
- 핵심 인용: *"너무 좋아 보이면, 사실은 사기일 가능성이 매우 높다."* — 사기 인식의 표준 격언

📖 **Lea, Fischer, & Evans (2009)** — [*"The Psychology of Scams: Provoking and Committing Errors of Judgement"*](https://webarchive.nationalarchives.gov.uk/ukgwa/20140402142426/http://www.oft.gov.uk/shared_oft/reports/consumer_protection/oft1070.pdf) (OFT1070)
- **OFT** (Office of Fair Trading — *영국 공정거래청*) 보고서

📖 **Frankel (2012)** — *"The Ponzi Scheme Puzzle"* (폰지 사기의 수수께끼). Oxford University Press 단행본
- 풀이: *원금보장 + 고수익 = 폰지 사기 (Ponzi scheme — 후속 투자금으로 앞 투자자에게 수익 지급) 의 핵심 패턴.*

**한국 법령**:

⚖️ [유사수신행위의 규제에 관한 법률 제2조 제1·2호](https://www.law.go.kr/법령/유사수신행위의규제에관한법률) — *원금 또는 그 이상 지급 약정 금지*. 제3조 (금지) / 제6조 제1항 (5년 이하 징역 또는 5천만 원 이하 벌금) — **2024.05.28 시행 개정으로 가상자산 포함**
⚖️ 자본시장법 제17조 (미등록 투자자문업) / 제445조 (벌칙)
⚖️ 형법 제347조 사기

**정부·산업 보고서**:
📊 금감원·금융위 「유사수신행위 Q&A」
📊 미국 **FTC** (Federal Trade Commission — *연방거래위원회*) [*Consumer Sentinel Data Book 2024*](https://www.ftc.gov/reports/consumer-sentinel-network-data-book-2024) — *"투자 사기 $5.7B 1위 카테고리"*

**🔗 코드 매핑**:
- `abnormal_return_rate`
- `pipeline/config.py:FLAG_RATIONALE["abnormal_return_rate"]` — *"연 20% 이상 수익 보장은 자본시장법상 불법 권유. 정상 주식·채권 펀드 장기 평균 5~10%. 보장형 + 고수익은 폰지 사기 핵심 패턴"* — Frankel 2012 / SEC Investor Bulletin / 금감원 인용
- 검출: `pipeline/verifier.py` 키워드·정규식 매칭

---

### 2.2 `business_not_registered` — 사업자 미등록

**한국 법령**:
⚖️ [전자상거래법 제12조 제1항](https://www.law.go.kr/법령/전자상거래등에서의소비자보호에관한법률) — 통신판매업자 신고. 위반 시 제40조 제1항 제4호 과태료
⚖️ 부가가치세법 제8조 (사업자등록)

**정부 자료**:
📊 [공정거래위원회 통신판매업자 정보공개시스템](https://www.ftc.go.kr/) — 신고번호 조회 가능

**🔗 코드 매핑**: `pipeline/config.py:FLAG_RATIONALE["business_not_registered"]` — Stajano-Wilson Distraction (위장된 정상성) 인용. `pipeline/verifier.py` 가 Serper 검색으로 사업자등록 부재 검증

---

### 2.3 `account_scam_reported` — 의심 계좌 (대포통장)

**우리가 검출하는 것**: *짧은 기간 내 다중 입출금, 신생 계좌, 명의자/사용자 불일치* 등 대포통장 의심 패턴.

**학술 근거**:
📖 **Florêncio & Herley (2013)** — *"Where do all the attacks go?"* (공격은 어디로 가는가?). *Economics of Information Security and Privacy III* 단행본 13–33쪽. DOI: [10.1007/978-1-4614-1981-5_2](https://doi.org/10.1007/978-1-4614-1981-5_2)
- 풀이: *돈세탁 통로 (money mule — *돈 운반책*) 의 경제학적 분석*

**한국 법령**:
⚖️ [전자금융거래법 제6조 제3항](https://www.law.go.kr/법령/전자금융거래법) — *접근매체 (통장·카드) 양도·양수·대여 금지*. 제49조 제4항 — *5년 이하 징역 또는 3천만 원 이하 벌금*
⚖️ 통신사기피해환급법 제2조 제4호 (사기이용계좌 정의), 제4조 (지급정지), 제9조 (채권소멸)
⚖️ **대법원 2012.07.05. 선고 2011도16167** — *'양도'의 의미: 소유권/처분권의 확정적 이전*

**🔗 코드 매핑**: `pipeline/config.py:FLAG_RATIONALE["account_scam_reported"]` (통신사기피해환급법 + 금감원 통계)

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
📊 FTC [*New crypto payment scam alert*](https://consumer.ftc.gov/) — *"정부·법 집행기관·공공요금 회사는 결코 암호화폐로 결제를 요구하지 않는다"*

**🔗 코드 매핑**: `pipeline/config.py:FLAG_RATIONALE["fake_exchange"]` — FBI IC3 + Cross 2023 인용

---

### 2.5 `prepayment_requested` — 선납금·수수료 먼저 요구

**우리가 검출하는 것**: 대출·취업·거래 *전에* 보증금·수수료·교육비 등을 먼저 요구하는 패턴.

**왜 위험한가**:
📖 **Stajano & Wilson (2011)** — Principle 4: *"Need and Greed"* (절박한 상황 표적). DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)

**한국 법령**:
⚖️ 「대부업 등의 등록 및 금융이용자 보호에 관한 법률」 / 「직업안정법」 제32조 — *채용·대출 명목 선납금 요구는 불법*

**🔗 코드 매핑**: `pipeline/config.py:FLAG_RATIONALE["prepayment_requested"]` — Stajano-Wilson + 직업안정법 인용

---

## 3. 카테고리 C — 디지털 콘텐츠 신호

### 3.1 `phone_scam_reported` — 전화번호 신고 이력

**학술 근거**:
📖 **Tu et al. (2016)** — *"SoK: Everyone hates robocalls"* (모두가 로보콜을 미워한다 — 시스템적 지식 정리). **IEEE S&P 2016**, 320–338쪽. DOI: [10.1109/SP.2016.27](https://doi.org/10.1109/SP.2016.27)
- *SoK* (Systematization of Knowledge — *지식 체계화*) — 한 분야의 모든 연구를 정리한 종합 논문

**한국 법령**:
⚖️ 전기통신사업법 제84조의2 — *전화번호 거짓표시 금지* (발신번호 변작). 1년 이하 징역 또는 1천만 원 이하 벌금
⚖️ 정보통신망법 제50조 (영리목적 광고성 정보 전송 제한)

**정부 자료**:
📊 [전기통신금융사기 통합신고대응센터 ☎112 / counterscam112.go.kr](https://counterscam112.go.kr/)
📊 경찰청 — *"강제수신·강제발신 (강수강발) 기능"* 80여 개 기관 번호 매핑 분석 (2025.04.27)

**🔗 코드 매핑**: `pipeline/config.py:FLAG_RATIONALE["phone_scam_reported"]` — KISA 통계 + Anderson *Security Engineering* 베이지안 사전확률 인용. 검출: `pipeline/verifier.py` Serper API

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

**🔗 코드 매핑**: `pipeline/config.py:FLAG_RATIONALE["smishing_link_detected"]`

---

### 3.3 도메인 위장 검출 (typosquatting)

**학술 근거**:
📖 **Spaulding, Upadhyaya, & Mohaisen (2016)** — *"The landscape of domain name typosquatting"* (오타 도메인 위장의 현황). arXiv: [1603.02767](https://arxiv.org/abs/1603.02767)
📖 **Nikiforakis et al. (2013)** — *"Bitsquatting: Exploiting bit-flips for fun, or profit?"* (비트 뒤집기 도메인 위장). **WWW '13**. DOI: [10.1145/2488388.2488474](https://doi.org/10.1145/2488388.2488474)
📖 **Kintis et al. (2017)** — *"Hiding in plain sight: A longitudinal study of combosquatting abuse"* (눈에 띄게 숨기: 조합 도메인 위장 종단연구). **ACM CCS 2017**. DOI: [10.1145/3133956.3134002](https://doi.org/10.1145/3133956.3134002)

**한국 법령**:
⚖️ [인터넷주소자원법 제12조](https://www.law.go.kr/법령/인터넷주소자원에관한법률) — 부정한 목적의 도메인 등록 금지
⚖️ 「부정경쟁방지 및 영업비밀보호에 관한 법률」 제2조 제1호 아목

**🔗 코드 매핑**: 우리는 *APK 패키지명 위장* 검출 (`apk_suspicious_package_name`) 에 이 학술 근거 적용 — `pipeline/apk_analyzer._is_suspicious_impersonation()` + 정상 한국 앱 list (kakao/naver/은행) 명시적 비교

---

### 3.4 `apk_impersonation_keywords` — 사칭 키워드

**학술 근거**:
📖 **Kim et al. (2022) HearMeOut** — *"Detecting voice phishing activities in Android"* (안드로이드의 보이스피싱 활동 검출). **MobiSys '22** (*모바일 시스템 학회*) 422–435쪽 — **한국 1,017개 보이스피싱 앱 분석**. DOI: [10.1145/3498361.3538939](https://doi.org/10.1145/3498361.3538939) ⭐ *우리 시스템의 한국 표적 검출의 핵심 학술 근거*
📖 **Stajano & Wilson (2011)** §"Social Compliance Principle" — *권위 신호* 활용. DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)

**한국 법령**:
⚖️ 형법 제225·227·230조 (공문서 위조·허위·부정행사)
⚖️ 통신사기피해환급법 제2조 제2호

**정부 자료**:
📊 **경찰청 [「2025년 1분기 보이스피싱 현황」](https://www.police.go.kr/), 2025.04.27 — 위험 키워드 공식 공개**: 사건조회·특급보안·엠바고·약식조사·자산검수·자산이전·감상문 제출

**🔗 코드 매핑**:
- 신호: `apk_impersonation_keywords`
- 검출: `pipeline/apk_analyzer._contains_string_keywords()` — APK 의 *dex 문자열 풀* (앱 안에 박힌 문자열) 검사
- 키워드 정의: `pipeline/apk_analyzer._IMPERSONATION_KEYWORDS` (frozenset 14종): 검찰·경찰·금감원·금융감독원·수사·구속·체포·고소·안전계좌·보안승급·보안카드·사칭·피해자·압수수색
- 학술 근거 동반: `pipeline/config.py:FLAG_RATIONALE["apk_impersonation_keywords"]` (Cialdini Authority + Stajano-Wilson + S2W TALON 인용)

---

## 4. 카테고리 D — 격리 브라우저 분석 (Sandbox)

> **Sandbox** (모래상자·격리 환경) — *의심 URL 을 평소 컴퓨터에서 열면 위험하니, 격리된 가상 브라우저에서 열어 행동만 관찰*. 우리는 v3.5 부터 격리 Chromium 으로 의심 URL 직접 navigate 하는 기능을 추가함.

### 4.1 `sandbox_password_form_detected` — 비밀번호 입력란 발견

**학술 근거**:
📖 [**OWASP** *Web Security Testing Guide v4.2*](https://owasp.org/www-project-web-security-testing-guide/) (Open Web Application Security Project — *오픈 웹앱 보안 프로젝트*, 비영리), §4.4 *Identity Management Testing*
📖 **Marchal et al. (2017)** — *"Off-the-Hook: An efficient and usable client-side phishing prevention application"* (낚시바늘 빼기 — 효율적이고 쓸 만한 클라이언트 측 피싱 방어 앱). IEEE Transactions on Computers 66(10), 1717–1733. DOI: [10.1109/TC.2017.2703808](https://doi.org/10.1109/TC.2017.2703808)

**한국 법령**:
⚖️ 정보통신망법 제49조 (비밀 침해·도용·누설 금지)
⚖️ 개인정보보호법 제15조 제1항·제17조

**🔗 코드 매핑**:
- 신호: `sandbox_password_form_detected`
- 검출: `pipeline/sandbox.py` (Phase 0.5) — 격리 Chromium 으로 URL 열고 `<input type="password">` (비밀번호 필드) 검출
- 학술 근거: `pipeline/config.py:FLAG_RATIONALE["sandbox_password_form_detected"]` — *OWASP A07 (Identification & Authentication Failures) + APWG 2024* 인용

---

### 4.2 `sandbox_sensitive_form_detected` — 민감 정보 입력란

**학술 근거**:
📖 **Bilge et al. (2009)** — [*"EXPOSURE: Finding malicious domains using passive DNS analysis"*](https://www.ndss-symposium.org/wp-content/uploads/2017/09/14_3.pdf). **NDSS 2009**

**한국 법령**:
⚖️ [개인정보보호법 제24조의2](https://www.law.go.kr/법령/개인정보보호법) — *주민등록번호 처리 제한 (법령 근거 없는 한 처리 금지)*
⚖️ 개인정보보호법 제23조 (민감정보 처리 제한)
⚖️ 정보통신망법 제23조의2 (주민등록번호 사용 제한)

**🔗 코드 매핑**: 검출: `pipeline/sandbox_detonate.py:_detect_sensitive_fields()` — 주민번호·OTP·CVC(카드 보안코드)·계좌·카드번호 필드 검출. *PCI DSS 4.0 (Payment Card Industry Data Security Standard — 카드결제업계 보안 표준) + 개인정보보호법 시행령 별표1 인용*

---

### 4.3 `sandbox_auto_download_attempt` — drive-by download

**학술 근거**:
📖 **Provos et al. (2008)** — [*"All your iFRAMEs point to Us"*](https://www.usenix.org/legacy/event/sec08/tech/full_papers/provos/provos.pdf) (모든 iFRAME 이 우리를 가리킨다). **USENIX Security 2008** (시스템 보안 최상위 학회)
📖 **Cova, Kruegel, & Vigna (2010)** — *"Detection and analysis of drive-by-download attacks and malicious JavaScript code"*. **WWW '10**. DOI: [10.1145/1772690.1772720](https://doi.org/10.1145/1772690.1772720)

**한국 법령**:
⚖️ 정보통신망법 제48조 제2항 / 제70조의2 — *악성프로그램 전달·유포: 7년 이하 징역 또는 7천만 원 이하 벌금*
⚖️ **대법원 2019.12.12. 선고 2017도16520** — 악성프로그램 해당 여부 판단 기준

**🔗 코드 매핑**: `pipeline/sandbox.py` 가 Playwright Chromium 의 `download` 이벤트 hook (*걸어둠*)

---

### 4.4 `sandbox_excessive_redirects` / 4.5 `sandbox_cloaking_detected`

**학술 근거**:
📖 **Invernizzi et al. (2016)** — *"Cloak of visibility: Detecting when machines browse a different web"* (가시성의 망토: 기계와 사람이 다른 웹을 보는 순간 검출). **IEEE S&P 2016** 743–758쪽. DOI: [10.1109/SP.2016.50](https://doi.org/10.1109/SP.2016.50)
- 풀이: *피싱 사이트가 검색엔진 봇에게는 정상 페이지, 사람에게는 피싱 페이지를 보여주는 cloaking 기법 11종 분석*
📖 **Wang, Savage, & Voelker (2011)** — *"Cloak and dagger: Dynamics of web search cloaking"*. **ACM CCS 2011**. DOI: [10.1145/2046707.2046763](https://doi.org/10.1145/2046707.2046763)
📖 **Oest et al. (2019)** — *"PhishFarm: A scalable framework for measuring the effectiveness of evasion techniques"*. IEEE S&P 2019. DOI: [10.1109/SP.2019.00049](https://doi.org/10.1109/SP.2019.00049)

**🔗 코드 매핑**: `pipeline/sandbox.py` 가 redirect chain (*리디렉션 연쇄*) 추적 + target ≠ final URL 비교

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
- 검출: `pipeline/safety.py` (Phase 0) — VirusTotal API v3 클라이언트, *SHA256* (파일 해시) 조회 + URL 스캔
- 학술 근거: `pipeline/config.py:FLAG_RATIONALE["malware_detected"]` — *NIST SP 800-83* (미국 표준기술연구원 *멀웨어 사고 예방·대응 가이드*) 인용

---

## 5. 카테고리 E — APK 정적 분석 Lv 1

> **Lv 1 정적 분석** — APK 파일의 *manifest* (선언서) + *권한* + *서명* 만 보는 분석. 코드는 안 봄.

### 5.1 `apk_dangerous_permissions_combo` — 위험 권한 4종 이상 조합

**우리가 검출하는 것**: SEND_SMS (SMS 보내기) + READ_SMS (SMS 읽기) + BIND_ACCESSIBILITY_SERVICE (접근성 서비스 — *다른 앱 화면 가로채기 가능*) + SYSTEM_ALERT_WINDOW (다른 앱 위에 창 띄우기) 등 **위험 권한 4종 이상 동시** 요청.

**왜 위험한가**:

📖 **Arp, Spreitzenbarth, Hübner, Gascon, & Rieck (2014)** — [*"DREBIN: Effective and Explainable Detection of Android Malware in Your Pocket"*](https://www.ndss-symposium.org/wp-content/uploads/2017/09/11_3_1.pdf) (안드로이드 멀웨어의 효율적·설명 가능한 검출). **NDSS 2014**. DOI: [10.14722/ndss.2014.23247](https://doi.org/10.14722/ndss.2014.23247) ⭐
- §III.A "Permissions" feature set — *권한 조합* 만으로도 악성 앱 **94% 검출률** 달성 (안드로이드 멀웨어 검출 표준 baseline)

📖 **Felt, Chin, Hanna, Song, & Wagner (2011)** — *"Android Permissions Demystified"* (안드로이드 권한 해부). **ACM CCS 2011**. DOI: [10.1145/2046707.2046779](https://doi.org/10.1145/2046707.2046779)

📖 **Mariconti et al. (2017)** — [*"MaMaDroid: Detecting Android malware by building Markov chains of behavioral models"*](https://arxiv.org/abs/1612.04433). **NDSS 2017**. DOI: [10.14722/ndss.2017.23353](https://doi.org/10.14722/ndss.2017.23353)
- 풀이: *권한 + API 호출 시퀀스를 **마코프 연쇄** (Markov chain — 상태 전환 확률 모델) 로 모델링한 차세대 악성 앱 검출*

**한국 법령**:
⚖️ 정보통신망법 제48조 제2항 (악성프로그램 정의)
⚖️ 개인정보보호법 제15·17·22조 (수집·이용·제3자 제공 동의 원칙)

**정부·산업 자료**:
📊 [Google Play Console — *Use of SMS or Call Log permission groups*](https://support.google.com/googleplay/android-developer/answer/9047303) (구글 플레이 콘솔 — *SMS·통화기록 권한 그룹 사용 정책*)
📊 [Android Open Source Project — *Permissions* 9개 dangerous group](https://developer.android.com/guide/topics/permissions/overview)

**🔗 코드 매핑**:
- 신호: `apk_dangerous_permissions_combo`
- 검출: `pipeline/apk_analyzer.py:_DANGEROUS_PERMISSION_COMBO` (frozenset — *변경 불가능한 집합*) 7종: SEND_SMS / READ_SMS / RECEIVE_SMS / READ_CALL_LOG / PROCESS_OUTGOING_CALLS / BIND_ACCESSIBILITY_SERVICE / SYSTEM_ALERT_WINDOW
- 임계: `_DANGEROUS_PERMISSION_THRESHOLD = 4` — *4종 이상 동시* 보유 시 검출
- 진입: `pipeline/apk_analyzer.analyze_apk_static()`
- 학술 근거: `pipeline/config.py:FLAG_RATIONALE["apk_dangerous_permissions_combo"]` — S2W TALON SecretCalls + DREBIN 인용

---

### 5.2 `apk_self_signed` — 자체 서명 인증서 (단독 사용 비권장)

**학술 근거**:
📖 **Truong et al. (2014)** — *"The Company You Keep: Mobile Malware Infection Rates and Inexpensive Risk Indicators"* (어울리는 친구가 누구인가: 모바일 멀웨어 감염률과 저비용 위험 지표). **WWW 2014**. arXiv: [1312.3245](https://arxiv.org/abs/1312.3245)

**산업 자료**:
📊 [Palo Alto Networks Unit42 — *Bad Certificate Management in Google Play Store*](https://unit42.paloaltonetworks.com/bad-certificate-management-google-play-store/), 2014
📊 [Android Partner Vulnerability Initiative](https://bugs.chromium.org/p/apvi/), 2022.11 — Samsung·LG·Mediatek 플랫폼 인증서 유출 사례

**🔗 코드 매핑**:
- 신호: `apk_self_signed`
- 검출: `pipeline/apk_analyzer._check_self_signed()` — `androguard.core.apk.APK.get_certificates_v3/v2/v1()` + asn1crypto 라이브러리로 *subject* (서명자) == *issuer* (발급자) 비교
- ⚠️ false positive 위험 — 정상 사이드로딩 앱도 자체 서명 가능. 단독 비권장 (FLAG_RATIONALE 본문 명시)

---

### 5.3 `apk_suspicious_package_name` — 패키지명 위장

**학술 근거**:
📖 **Zhou & Jiang (2012)** — *"Dissecting Android malware: Characterization and evolution"*. **IEEE S&P 2012** 95–109쪽. DOI: [10.1109/SP.2012.16](https://doi.org/10.1109/SP.2012.16)
📖 **Truong et al. (2014)** — *"the name `com.facebook.katana` is used in many malware packages"*. arXiv: [1312.3245](https://arxiv.org/abs/1312.3245)

**산업 자료**: S2W TALON SecretCalls·TheftCalls·HeadCalls 보고서

**🔗 코드 매핑**:
- 신호: `apk_suspicious_package_name`
- 검출: `pipeline/apk_analyzer._is_suspicious_impersonation()` — typo-squatting 패턴 매칭
- 정상 한국 앱 list: `_LEGITIMATE_PACKAGE_PATTERNS` — `com.kakao.talk`, `com.nhn.android.search`, `kr.co.shinhan`, `com.kbstar.kbbank` 등 **16개**
- 의심 접미사: `_SUSPICIOUS_PACKAGE_SUFFIXES` — fake/test/_v2/_new/official 등 7종

---

## 6. 카테고리 F — APK 심화 정적 분석 Lv 2 (bytecode)

> **Lv 2 심화 정적 분석** — APK 의 *dex 바이트코드* (실행 코드) 를 *역어셈블* (disassemble — 기계어 가까운 코드를 사람이 읽을 수 있게 변환) 해서 *어떤 함수가 어디서 호출되는지* 분석. **여전히 코드 실행 X.**

### 6.1 `apk_sms_auto_send_code` — SMS 자동 발송 코드

**학술 근거**:
📖 **Arp et al. (2014) DREBIN**, §III.B "API calls" feature. DOI: [10.14722/ndss.2014.23247](https://doi.org/10.14722/ndss.2014.23247)
📖 **Mariconti et al. (2017) MaMaDroid**. DOI: [10.14722/ndss.2017.23353](https://doi.org/10.14722/ndss.2017.23353)

**한국 법령**:
⚖️ 정보통신망법 제48조 제2항 / 제70조의2 — *7년 이하*
⚖️ 전기통신사업법 제32조의5 / 정보통신망법 제50조

**산업 자료**:
- S2W TALON SecretCalls 보고서 — SMS 가로채기·자동 전송 기능 확인
- [Corrata — *Dangerous Permissions Android*](https://corrata.com/dangerous-permissions-android/), 2022

**🔗 코드 매핑**:
- 신호: `apk_sms_auto_send_code`
- 검출: `pipeline/apk_analyzer._has_method_xref(analysis, "Landroid/telephony/SmsManager;", "sendTextMessage")` — *androguard `AnalyzeAPK` 의 xref* (cross-reference, *코드에서 어떤 함수가 어디서 호출되는지*) 분석으로 SmsManager.sendTextMessage 호출 검출

---

### 6.2 `apk_call_state_listener` — 통화 상태 가로채기

**학술 근거**:
📖 **Kim, J., Kim, J., Wi, S., Kim, Y., & Son, S. (2022) HearMeOut** — call redirection (통화 우회) / call screen overlay (통화 화면 가리기) / fake call voice (가짜 통화 음성) **3종 새 기능 보고**. **MobiSys '22**. DOI: [10.1145/3498361.3538939](https://doi.org/10.1145/3498361.3538939) ⭐
- *우리 시스템의 한국 보이스피싱 검출 핵심 학술 근거 — 1,017개 앱 분석*

**한국 법령**:
⚖️ [통신비밀보호법 제3조 제1항](https://www.law.go.kr/법령/통신비밀보호법) (불법 감청 금지), 제16조 — *10년 이하 징역*
⚖️ 정보통신망법 제48조 제2항 / 제70조의2

**산업 자료**:
- S2W TALON [*Detailed Analysis of TheftCalls*](https://medium.com/s2wblog) — 강제 forwarding (통화 우회), 통화 기록 변조
- S2W TALON [*HeadCalls*](https://medium.com/s2wblog), 2025

**🔗 코드 매핑**:
- 신호: `apk_call_state_listener`
- 검출: `pipeline/apk_analyzer._has_method_xref(analysis, "Landroid/telephony/TelephonyManager;", "listen")`
- 학술 근거: `pipeline/config.py:FLAG_RATIONALE["apk_call_state_listener"]` — Kim et al. 2022 HearMeOut + S2W TALON SecretCalls 인용

---

### 6.3 `apk_accessibility_abuse` — 접근성 서비스 악용

**학술 근거**:
📖 **Fratantonio et al. (2017)** — *"Cloak and Dagger: From Two Permissions to Complete Control of the UI Feedback Loop"* (망토와 단검: 두 권한만으로 UI 피드백 루프 완전 장악). **IEEE S&P 2017** 1041–1057쪽. DOI: [10.1109/SP.2017.39](https://doi.org/10.1109/SP.2017.39)
- 풀이: *SYSTEM_ALERT_WINDOW (다른 앱 위에 창 띄우기) + BIND_ACCESSIBILITY_SERVICE (접근성 서비스) 두 권한만으로 사용자 입력 가로채기·가짜 화면 표시·자동 클릭 모두 가능함을 학술적으로 증명*

📖 **Kim et al. (2022) HearMeOut**. DOI: [10.1145/3498361.3538939](https://doi.org/10.1145/3498361.3538939)

**한국 법령**:
⚖️ 정보통신망법 제48조 제2항 / 제70조의2
⚖️ 개인정보보호법 제15·17조

**산업 자료**:
- S2W TALON [*Deep Analysis of SecretCalls (Part 2)*](https://medium.com/s2wblog), 2024 — 접근성 권한 강제 승인, 화면 오버레이, 기본 전화 앱 변경
- [Corrata *Dangerous Permissions Android*](https://corrata.com/dangerous-permissions-android/) — 자격증명 탈취·OTP 가로채기

**🔗 코드 매핑**:
- 검출: `pipeline/apk_analyzer._references_accessibility_service()` — `AccessibilityService` 상속 클래스 탐색
- ⚠️ 정상 장애인 보조 앱도 사용 — 단독 신호 약함, *권한 조합·은행 사칭 패키지명* 과 결합 시 강함 (FLAG_RATIONALE 본문에 명시)

---

### 6.4 `apk_hardcoded_c2_url` — 명령·제어 서버 URL 하드코딩

**학술 근거**:
📖 **Arp et al. (2014) DREBIN** §S5 "Network addresses" — 네트워크 주소 feature. DOI: [10.14722/ndss.2014.23247](https://doi.org/10.14722/ndss.2014.23247)
📖 **Karbab et al. (2018)** — *"MalDozer: Automatic framework for android malware detection using deep learning"*. Digital Investigation, 24, S48–S59. DOI: [10.1016/j.diin.2018.01.007](https://doi.org/10.1016/j.diin.2018.01.007)

**한국 법령**:
⚖️ 정보통신망법 제48조 제2항
⚖️ 통신비밀보호법

**산업 자료**: S2W TALON 보고서 — 한국 보이스피싱 패밀리는 Firebase Cloud Messaging (구글의 *푸시 알림 서비스*) 을 C&C 채널로 전용

**🔗 코드 매핑**:
- 검출: `pipeline/apk_analyzer._has_suspicious_url_constants()` — APK 안의 *문자열 풀* (string pool) 검사
- 의심 패턴 정규식: `_SUSPICIOUS_URL_PATTERNS` — IP 주소 직접 (`https?://\d+\.\d+\.\d+\.\d+`), 무료 도메인 (.tk·.ml·.ga·.cf·.gq), 비표준 포트

---

### 6.5 `apk_string_obfuscation` — 난독화 흔적 (단독 비권장)

**학술 근거**:
📖 **Wermke et al. (2018)** — *"A large scale investigation of obfuscation use in Google Play"* (구글 플레이의 난독화 사용 대규모 조사). **ACSAC '18**. DOI: [10.1145/3274694.3274726](https://doi.org/10.1145/3274694.3274726)
📖 **Pendlebury et al. (2019)** — [*"TESSERACT: Eliminating experimental bias in malware classification across space and time"*](https://www.usenix.org/conference/usenixsecurity19/presentation/pendlebury) (시간·공간 편향 제거). **USENIX Security 2019**

**🔗 코드 매핑**:
- 검출: `pipeline/apk_analyzer._looks_obfuscated()` — *1-2 글자 클래스명 비율 + 클래스 50개 이상* 임계값 휴리스틱
- 임계: `_OBFUSCATION_RATIO_THRESHOLD = 0.30` (30%), `_OBFUSCATION_MIN_CLASSES = 50`
- ⚠️ 정상 ProGuard (안드로이드 표준 난독화 도구) 사용 앱도 가능 — 단독 비권장

---

### 6.6 `apk_device_admin_lock` — 화면 강제 잠금

**학술 근거**:
📖 **Andronio, Zanero, & Maggi (2015)** — *"HelDroid: Dissecting and detecting mobile ransomware"* (안드로이드 랜섬웨어 해부·검출). **RAID 2015** 382–404쪽. DOI: [10.1007/978-3-319-26362-5_18](https://doi.org/10.1007/978-3-319-26362-5_18)
- 풀이: *DevicePolicyManager.lockNow API 가 어떻게 안드로이드 랜섬웨어의 화면 잠금에 악용되는지 분석*
📖 **Yang et al. (2015)** — *"Automated detection and analysis for Android ransomware"*. IEEE HPCC 2015. DOI: [10.1109/HPCC-CSS-ICESS.2015.39](https://doi.org/10.1109/HPCC-CSS-ICESS.2015.39)

**한국 법령**:
⚖️ 정보통신망법 제48조 제2항 — *대법원 2017도16520 (2019.12.12) "결과 발생 불요"* 판례 (실제 피해 없어도 처벌)
⚖️ 형법 제314조 제2항 (컴퓨터등 장애 업무방해)

**🔗 코드 매핑**: `pipeline/apk_analyzer._has_method_xref(analysis, "Landroid/app/admin/DevicePolicyManager;", "lockNow")`

---

## 7. 카테고리 G — APK 동적 분석 Lv 3 (인터페이스만)

> ⚠️ **로컬 실행 절대 금지** (HARD BLOCK) — `APK_DYNAMIC_ENABLED=0` 기본 비활성. 어떤 환경변수 조합으로도 *현재 호스트에서* APK 를 실행할 수 없게 만들어 둠. 격리 가상머신에서만 동작 (실제 가상머신 stack 은 future work).

### 7.1 ~ 7.5 — Lv 3 Candidate Flag 5종

**학술 근거**:
📖 **Mavroeidis & Bromander (2017)** — *Cyber Threat Intelligence Model* (사이버 위협 인텔리전스 모델) — *C&C 인프라 기반 검출*
📖 **Kim et al. (2022) HearMeOut** — SMS 가로채기 / 화면 오버레이 / 자격증명 탈취 동작 관찰. DOI: [10.1145/3498361.3538939](https://doi.org/10.1145/3498361.3538939)
📖 **Fratantonio et al. (2017) Cloak and Dagger** — UI 가로채기 동작 학술 검증. DOI: [10.1109/SP.2017.39](https://doi.org/10.1109/SP.2017.39)
📖 [**OWASP Mobile Top 10**](https://owasp.org/www-project-mobile-top-10/) — *모바일 보안 위협 10대 카테고리*

**산업 자료**:
- [Frida](https://frida.re/) — *동적 인스트루먼테이션 도구* (실행 중인 앱에 후크 걸어 동작 관찰)
- S2W TALON [SecretCalls Part 2](https://medium.com/s2wblog) / [TheftCalls](https://medium.com/s2wblog) / [HeadCalls](https://medium.com/s2wblog)

**5 종 신호**:
- `apk_runtime_c2_network_call` — 격리 환경에서 *실제로* C&C 도메인 호출 관찰
- `apk_runtime_sms_intercepted` — *가상* SMS 시뮬레이션 시 자동 가로채기·재전송 동작 관찰
- `apk_runtime_overlay_attack` — 가상 은행 앱 위에 가짜 화면 *실제로* 띄움
- `apk_runtime_credential_exfiltration` — 자격증명·민감정보 외부 송신 관찰 (Frida 후크)
- `apk_runtime_persistence_install` — 재부팅 시 자동 시작 / DeviceAdmin 활성화 관찰

**🔗 코드 매핑**:
- 진입: `pipeline/apk_analyzer.analyze_apk_dynamic()`
- 안전 정책 5단계 enum: `APKDynamicStatus.{DISABLED, BLOCKED_LOCAL, NOT_CONFIGURED, COMPLETED, ERROR}`
- 검출 신호화: `pipeline/signal_detector.py` 가 *status=COMPLETED* 일 때만 처리

---

## 8. 신호 사용 가이드라인

**모든 신호는 단독 사용 X — 누적·조합 시점에서만 강함**.

특히 **거짓 양성 (false positive) 큰 신호**:

| 신호 | 정상 사례 |
|---|---|
| `apk_self_signed` | 정상 사이드로딩 앱 |
| `apk_string_obfuscation` | 정상 ProGuard 사용 앱 |
| `apk_accessibility_abuse` (단독) | 정상 장애인 보조 앱 |
| `suspicious_writing_style` | 정상 외국인이 쓴 한국어 |
| `ai_generated_content_suspected` | 정상 AI 활용 콘텐츠 |

이런 신호는 *권한 조합·사칭 키워드·서명 등 다른 강한 신호와 결합 시점에서만* 의미.

**시스템 정체성 (CLAUDE.md)**: 신호 검출 + 학술/법적 근거 → 보고만. 판정 logic 은 통합 기업 (통신사·은행·메신저 앱) 이 자체 위험 허용도 (risk tolerance) 에 따라 구현.

---

## 9. Bibliography (참고 문헌 일람)

### 9.1 학술 논문 / 단행본 (DOI/URL 동반)

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

⭐ = ScamGuardian 의 핵심 학술 frame work — 모든 발표·논문에서 *반드시* 인용

### 9.2 한국 법령 (현행 2026.05 기준)

모두 [국가법령정보센터 law.go.kr](https://www.law.go.kr/) 에서 조회 가능.

- 「전기통신금융사기 피해 방지 및 피해금 환급에 관한 특별법」 제1·2·4·9·10·15조의2
- 「정보통신망 이용촉진 및 정보보호 등에 관한 법률」 제23조의2·제48조·제49조·제50조·제70조의2·제71조
- 「전자금융거래법」 제2조·제6조·제9조·제49조
- 「유사수신행위의 규제에 관한 법률」 제1·2·3·6조 (2024.05.28 시행 — 가상자산 포함)
- 「자본시장과 금융투자업에 관한 법률」 제17·38·55·445조
- 「표시·광고의 공정화에 관한 법률」 제3·17조 / 시행령 제3조
- 「전자상거래 등에서의 소비자보호에 관한 법률」 제8·12·13·17·21·40조
- 「개인정보 보호법」 제15·16·17·18·22·23·24의2조
- 「형법」 제225·227·230·283·284·285·286·314·347·347의2·350·351조
- 「특정경제범죄 가중처벌 등에 관한 법률」 제3조
- 「통신비밀보호법」 제3·16조
- 「부정경쟁방지 및 영업비밀보호에 관한 법률」 제2조 제1호
- 「상표법」 제108조
- 「은행법」 제14·66의2조
- 「인터넷주소자원에 관한 법률」 제12조
- 「가상자산 이용자 보호 등에 관한 법률」 제2조

### 9.3 정부·산업 보고서

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

## 10. 인용 시 주의사항 (Caveats)

1. **법령 개정**: 한국 법령은 빈번 개정. 자문 미팅 직전 [law.go.kr](https://www.law.go.kr) 재확인. 본 문서는 2026.05 기준
2. **페이지 번호**: 학술 논문 페이지는 게재본 기준 (Stajano & Wilson CACM 54(3) pp.70–75 등). Cialdini *Influence* 는 판본별 페이지 다름 → Chapter 단위 우선
3. **거짓 양성 (false positive) 정직 표시**: 위 §0.6 / §8 표 참조. 단독 사용 비권장 신호 4종 명시
4. **통계 시점**: *"1,965억 원·1인당 1,700만 원"* = 2023년 (2024.03 발표). 경찰청 자료 — *2025년 1분기만 3,116억 원* 으로 급증
5. **산업 보고서 인용 정확성**: S2W·안랩·이스트시큐리티 등은 *peer-review (동료 평가)* 가 아니므로 학술 인용 시 *"산업 보고서"* 명시. 학술 논문 (특히 **Kim et al. 2022 HearMeOut MobiSys'22**) 을 1차 근거로 사용
6. **저작권**: 외부 공개·논문 인용 시 각 출처의 저작권·인용 규약 별도 확인. ACM/IEEE 논문은 보통 저자 사본 (author preprint) 으로 합법 접근 가능
7. **시스템 정체성 일관 강조**: 본 신호 카탈로그는 ScamGuardian 이 *판정자 (verdict-maker) 가 아닌 검출자 (detector)* 임을 전제. 발표·미팅에서 *"이 시스템은 다음 N 개의 위험 신호를 다음 근거로 검출합니다"* 표현 일관 사용
8. **다층 방어 narrative**: 본 신호 시스템은 **1차 정적 분석 트리아지** (triage — *환자 분류, 우선순위 분류*). 동적 분석·사용자 교육·신고 채널 (☎112) 연계는 future work 로 분리

---

> 본 문서는 ScamGuardian 졸업작품의 **단일 참고서 (single reference book)**.
> 인용된 모든 학술 논문·법조항·정부 보고서는 2026년 5월 기준 *실제 존재* 하며 URL/DOI/조항 번호로 검증 가능.
> 각 신호의 학술 근거는 `pipeline/config.py:FLAG_RATIONALE` 에 직접 박혀 있고, `/api/analyze` 응답의 `detected_signals[].rationale` / `.source` 로 외부 클라이언트에 transparent (투명하게) 노출된다.
