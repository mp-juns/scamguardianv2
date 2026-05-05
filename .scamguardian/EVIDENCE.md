# ScamGuardian — 검출 신호 학술·법적 근거 + 프로젝트 매핑 (EVIDENCE.md)

**문서 버전**: v1.2 (2026-05-05)
**용도**: 자문 미팅 / 학부 졸업 발표 / 졸업 심사용 단일 reference book — *각 근거 → 코드 연결 명시*
**최종 검토자**: ScamGuardian 팀

---

## 0. 개요

### 0.1 이 문서의 목적

ScamGuardian 이 검출하는 모든 위험 신호 (`detected_signals`) 각각에 대해:

1. **학술 근거** (peer-review 논문 / 단행본)
2. **한국 법령 근거**
3. **정부·산업 보고서 근거**
4. **🔗 프로젝트 매핑** — 이 근거가 *어떤 코드 파일·어떤 flag 에 박혀 있는지*

자문 미팅·발표·README 인용 시 그대로 사용 가능한 quality + 코드와의 추적성을 동시에 확보.

### 0.2 시스템 정체성 (가장 중요한 boundary)

ScamGuardian 은 **사기 여부를 최종 판정하지 않는다** — VirusTotal 이 70+ 백신 결과를 *집계만* 하고 판정 안 하는 모델과 동일.

```
❌ "이 메시지는 사기다"
✅ "이 메시지는 urgent_transfer_demand · authority_impersonation 등
    N 개의 위험 신호를 포함하며, 각 신호의 학술·법적 근거는 다음과 같다"
```

### 0.3 공통 프로젝트 매핑 (모든 신호에 적용)

각 신호의 *학술/법적 근거* 가 코드에서 다음 흐름으로 흐름:

```
①  학술 논문·법령 인용 ──→  pipeline/config.py:FLAG_RATIONALE[flag]
                            { "rationale": "...", "source": "..." }
②  검출 모듈 (Phase 별) ──→  pipeline/signal_detector.py:_make_signal()
                            DetectedSignal(flag, label_ko, rationale, source, ...)
③  파이프라인 종합 ────→  pipeline/runner.py:analyze()
                            → DetectionReport.detected_signals[]
④  외부 API 응답 ──────→  /api/analyze (DetectionReport JSON)
                            /api/result/{token}.flag_rationale (근거 별도 dict)
                            /api/methodology (검출 가능 카탈로그 전체)
⑤  사용자 표시 ────────→  apps/web/src/app/result/[token]/page.tsx
                            (신호별 학술/법적 근거 카드)
                            kakao_formatter.format_result()
                            (카카오 카드의 신호 list)
```

**검출 단계별 코드 위치**:

| 단계 | 모듈 | 신호 |
|---|---|---|
| Phase 0 안전성 | `pipeline/safety.py` | malware_detected, phishing_url_confirmed, suspicious_*_signal |
| Phase 0.5 sandbox | `pipeline/sandbox.py` | sandbox_password_form_detected, sandbox_auto_download_attempt 외 |
| Phase 0.6 APK Lv 1 | `pipeline/apk_analyzer.analyze_apk_static` | apk_dangerous_permissions_combo, apk_self_signed, apk_suspicious_package_name |
| Phase 0.6 APK Lv 2 | `pipeline/apk_analyzer.analyze_apk_bytecode` | apk_sms_auto_send_code, apk_call_state_listener, apk_accessibility_abuse 외 |
| Phase 0.6 APK Lv 3 *(인터페이스만)* | `pipeline/apk_analyzer.analyze_apk_dynamic` | apk_runtime_* 5종 — 격리 VM 호출만, 로컬 실행 HARD BLOCK |
| Phase 4 검증 | `pipeline/verifier.py` | urgent_transfer_demand, authority_impersonation 외 텍스트 신호 다수 |
| LLM 보조 검출 | `pipeline/llm_assessor.py` | LLM 이 추가 제안 — confidence 임계 통과 시 채택 |

---

## 1. 카테고리 A — 사기 행동 패턴 (심리학·범죄학)

### 1.1 `urgent_transfer_demand` — 즉각 송금·이체 요구

**검출 의미**: "지금 즉시 송금/이체" 요구 패턴.

**학술 근거**:
- Stajano, F., & Wilson, P. (2011). *Understanding scam victims: seven principles for systems security.* CACM, 54(3), 70–75 — §"Time Principle" (p.73). DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)
  > *"When under time pressure to make an important choice, we use a different decision strategy, and hustlers steer us toward one involving less reasoning."*
- Cialdini, R. B. (2021). *Influence: The Psychology of Persuasion*. Harper Business — Chapter 7 "Scarcity"
- Loewenstein, G. (1996). *Out of control: Visceral influences on behavior.* OBHDP, 65(3). DOI: [10.1006/obhd.1996.0028](https://doi.org/10.1006/obhd.1996.0028)

**법적 근거**:
- [통신사기피해환급법 제2조 제2호](https://www.law.go.kr/법령/전기통신금융사기피해방지및피해금환급에관한특별법) (전기통신금융사기 정의)
- [형법 제347조 제1항](https://www.law.go.kr/법령/형법) (사기)
- 통신사기피해환급법 제15조의2 제1항 (1년 이상 유기징역)

**정부/산업 보고서**:
- 금융감독원 [「2023년 보이스피싱 피해현황 분석」](https://www.fss.or.kr/), 2024.03 — 피해액 1,965억 원
- FBI [*2024 IC3 Report*](https://www.ic3.gov/AnnualReport/Reports/2024_IC3Report.pdf), 2025.04 — $16.6B (+33% YoY)

**🔗 프로젝트 매핑**:
- flag: `urgent_transfer_demand`
- `pipeline/config.py:FLAG_RATIONALE["urgent_transfer_demand"]` — 위 학술·법적 근거 직접 인용
- 검출: `pipeline/verifier.py` (Phase 4) — 키워드·패턴 매칭. `pipeline/llm_assessor.py` 가 보조 제안
- 응답: `DetectionReport.detected_signals[]` 의 한 항목, `rationale` + `source` 동반

---

### 1.2 `authority_impersonation` (≈ `fake_government_agency`) — 공권력·금융기관 사칭

**검출 의미**: 검찰·경찰·금감원·국세청·은행 등 사칭.

**학술 근거**:
- Cialdini (2021), Chapter 6 "Authority: Directed Deference" — Titles, Clothes, Trappings
- Stajano & Wilson (2011) §"Social Compliance Principle", pp.71–72. DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)
- Modic, D., & Lea, S. E. G. (2013). *Scam compliance and the psychology of persuasion.* SSRN. DOI: [10.2139/ssrn.2364464](https://doi.org/10.2139/ssrn.2364464)

**법적 근거**:
- [형법 제225조](https://www.law.go.kr/법령/형법) (공문서 위조), 제227조 (허위공문서), 제230조 (부정행사)
- 통신사기피해환급법 제2조 제2호 / 제15조의2 제1항
- 「특정경제범죄 가중처벌 등에 관한 법률」 제3조

**정부/산업 보고서**:
- 경찰청 [「2025년 1분기 보이스피싱 현황」](https://www.police.go.kr/), 2025.04.27 — 기관사칭형 51%
- 금융감독원 「2023년 보이스피싱 피해현황 분석」 — 정부기관 사칭형 31.1%
- S2W TALON, [*Detailed Analysis of HeadCalls*](https://medium.com/s2wblog), 2025.08

**🔗 프로젝트 매핑**:
- flag: `fake_government_agency` (한국어 라벨 "정부기관 사칭")
- `pipeline/config.py:FLAG_RATIONALE["fake_government_agency"]` — Cialdini Authority + 학술 인용
- 검출: `pipeline/verifier.py` (Phase 4) + `pipeline/llm_assessor.py`

---

### 1.3 `fear_appeal` (≈ `threat_or_coercion`) — 공포 유발

**검출 의미**: "체포된다·계좌 동결·고발" 등 공포 고지.

**학술 근거**:
- Whitty, M. T. (2013). *The scammers persuasive techniques model.* BJC, 53(4), 665–684 — §"The Sting". DOI: [10.1093/bjc/azt009](https://doi.org/10.1093/bjc/azt009)
- Stajano & Wilson (2011), §"Need and Greed" + §"Time Principle". DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)
- Witte, K. (1992). *Putting the fear back into fear appeals: EPPM.* Communication Monographs, 59(4). DOI: [10.1080/03637759209376276](https://doi.org/10.1080/03637759209376276)
- Langenderfer, J., & Shimp, T. A. (2001). *Consumer vulnerability to scams: A new theory of visceral influences.* Psychology & Marketing, 18(7). DOI: [10.1002/mar.1029](https://doi.org/10.1002/mar.1029)

**법적 근거**:
- [형법 제283조](https://www.law.go.kr/법령/형법) (협박, 3년 이하 징역)
- 형법 제350조 (공갈)
- 통신사기피해환급법 제2조 제2호

**🔗 프로젝트 매핑**:
- flag: `threat_or_coercion`
- `pipeline/config.py:FLAG_RATIONALE["threat_or_coercion"]` — 형법 제283조 + Witte EPPM 인용
- 검출: `pipeline/verifier.py`, LLM 보조

---

### 1.4 `urgency_time_pressure` — 시간 압박 ("지금 당장")

**검출 의미**: "10분 안에·오늘만·즉시" 시간 제한 강조.

**학술 근거**:
- Stajano & Wilson (2011) §"Time Principle" (p.74) — Simon (1956) satisficing, Tversky-Kahneman (1974) heuristics. DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)
- Cialdini (2021), Chapter 7 "Scarcity" §"Time Limits"
- Whitty (2013) — "The Sting" 단계 긴급성. DOI: [10.1093/bjc/azt009](https://doi.org/10.1093/bjc/azt009)

**법적 근거**:
- 통신사기피해환급법 제2조 제2호 (간접: 시간 압박은 기망의 한 양태)
- [표시·광고의 공정화에 관한 법률 제3조 제1항 제1호](https://www.law.go.kr/법령/표시·광고의공정화에관한법률) (한정 시간 허위 강조)

**🔗 프로젝트 매핑**:
- flag: `urgent_transfer_demand` 와 통합 검출 (시간 압박 + 송금 요구가 거의 항상 동반)
- LLM 이 별도 제안 시 `pipeline/llm_assessor.py` 가 confidence 임계 (`LLM_FLAG_DETECTION_CONFIDENCE_THRESHOLD = 0.75`) 통과 시 채택

---

### 1.5 `social_proof_manipulation` — 사회적 증거 조작

**검출 의미**: 가짜 리뷰·다중 가명 계정.

**학술 근거**:
- Cialdini (2021), Chapter 4 "Social Proof: Truths Are Us"
- Stajano & Wilson (2011), §"Herd Principle" (p.72) — shills, sock-puppets, astroturfing, Sybil attack. DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)

**법적 근거**:
- 표시·광고법 제3조 제1항 제1·2호 / 제17조 제1호 (2년 이하 징역 또는 1억5천만 원 벌금)
- [전자상거래법 제21조 제1항](https://www.law.go.kr/법령/전자상거래등에서의소비자보호에관한법률)

**정부/산업 보고서**:
- APWG [*Phishing Activity Trends Report Q4 2024*](https://apwg.org/trendsreports/), 2025.03

**🔗 프로젝트 매핑**:
- flag: `medical_claim_unverified`, `query_c_scam_pattern_found` 등에 부분 반영 (Cialdini Social Proof 인용)
- 검출: `pipeline/verifier.py` Serper 검색 — 동일/유사 사기 패턴 단서 발견 시

---

### 1.6 `reciprocity_exploitation` — 호혜성 남용

**검출 의미**: 무료 선물·도움 후 부담감 형성하여 결제 유도.

**학술 근거**:
- Cialdini (2021), Chapter 2 "Reciprocation"
- Stajano & Wilson (2011), §"Kindness Principle" (p.73). DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)

**법적 근거**:
- 형법 제347조 사기
- 「방문판매 등에 관한 법률」 제8조 (선물·할인 미끼 후 강매 시 청약철회권)

**정부/산업 보고서**:
- FTC [*Consumer Sentinel Data Book 2024*](https://www.ftc.gov/reports/consumer-sentinel-network-data-book-2024)

**🔗 프로젝트 매핑**:
- 단독 flag 미할당 — LLM 보조 분류 (`pipeline/llm_assessor.py`) 가 텍스트 컨텍스트로 검출 가능. 다른 신호 (`prepayment_requested`, `medical_claim_unverified`) 와 결합 평가

---

### 1.7 `scarcity_pressure` — 희소성 압박

**검출 의미**: "선착순 N명·한정판·오늘 마감".

**학술 근거**:
- Cialdini (2021), Chapter 7 "Scarcity: The Rule of the Few"
- Stajano & Wilson (2011), Table 1. DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)

**법적 근거**:
- 표시·광고법 제3조 제1항 제1호
- 전자상거래법 제21조 제1항 제1호

**🔗 프로젝트 매핑**: `abnormal_return_rate` (투자 사기 — 한정 수익 약속) 의 rationale 에 Cialdini Scarcity 인용

---

### 1.8 `emotional_manipulation` (≈ `impersonation_family`, `romance_foreign_identity`)

**검출 의미**: 가족·연인 위장 ("엄마, 나야"형 / 로맨스 스캠).

**학술 근거**:
- Whitty, M. T. (2013). *The Scammers Persuasive Techniques Model* — 7-stage 모델. DOI: [10.1093/bjc/azt009](https://doi.org/10.1093/bjc/azt009)
- Whitty, M. T., & Buchanan, T. (2012). *The online romance scam: A serious cybercrime.* CyberPsych & Behavior, 15(3). DOI: [10.1089/cyber.2011.0352](https://doi.org/10.1089/cyber.2011.0352)
- Whitty, M. T., & Buchanan, T. (2016). *The online dating romance scam: psychological impact.* Criminology & Criminal Justice, 16(2). DOI: [10.1177/1748895815603773](https://doi.org/10.1177/1748895815603773)
- Cialdini (2021), Chapter 5 "Liking"

**법적 근거**:
- 통신사기피해환급법 제2조 제2호 (메신저피싱 포섭)
- 형법 제347조 사기

**정부/산업 보고서**:
- 금융감독원 「2023년 보이스피싱 피해현황 분석」 — 가족·지인 사칭형 33.7%
- FBI IC3 2024 — Romance/Confidence 카테고리

**🔗 프로젝트 매핑**:
- flag: `impersonation_family` — `pipeline/config.py:FLAG_RATIONALE["impersonation_family"]` (Cialdini Liking + Whitty 인용)
- flag: `romance_foreign_identity` — `pipeline/config.py:FLAG_RATIONALE["romance_foreign_identity"]` (Whitty 2013 7-stage 모델 + FBI IC3 인용)
- 검출: `pipeline/verifier.py` + `pipeline/llm_assessor.py`

---

## 2. 카테고리 B — 거래·상거래 신호

### 2.1 `abnormal_return_rate` — 비정상 수익률 약속

**검출 의미**: "월 10%·일 1%" 시장 평균 초과.

**학술 근거**:
- Stajano & Wilson (2011), §"Need and Greed Principle" (p.73). DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)
- Lea, Fischer, & Evans (2009). [*The Psychology of Scams (OFT1070)*](https://webarchive.nationalarchives.gov.uk/ukgwa/20140402142426/http://www.oft.gov.uk/shared_oft/reports/consumer_protection/oft1070.pdf). UK OFT
- Frankel, T. (2012). *The Ponzi Scheme Puzzle*. Oxford UP

**법적 근거**:
- [유사수신행위법 제2조 제1·2호 / 제3조 / 제6조 제1항](https://www.law.go.kr/법령/유사수신행위의규제에관한법률) (2024.05.28 시행 — 가상자산 포함)
- 자본시장법 제17조 / 제445조
- 형법 제347조 사기

**정부/산업 보고서**:
- 금융감독원·금융위 「유사수신행위 Q&A」
- FTC [*Sentinel Data Book 2024*](https://www.ftc.gov/reports/consumer-sentinel-network-data-book-2024) — Investment fraud $5.7B (1위)

**🔗 프로젝트 매핑**:
- flag: `abnormal_return_rate`
- `pipeline/config.py:FLAG_RATIONALE["abnormal_return_rate"]` — *"연 20% 이상 수익 보장은 자본시장법상 불법 권유 신호. 정상 주식·채권 펀드 장기 평균 5~10%. 보장형 + 고수익은 Ponzi 사기 핵심 패턴"* — Frankel 2012 / SEC Investor Bulletin / 금감원 인용
- 검출: `pipeline/verifier.py` 키워드·정규식 매칭

---

### 2.2 `unrealistic_promise` — 비현실적 보장

**검출 의미**: "원금보장·100% 수익".

**학술 근거**: Stajano & Wilson (2011), §"Need and Greed" — *"If it sounds too good to be true, it probably is."* DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)

**법적 근거**:
- 유사수신행위법 제2조 (전액·초과 지급 약정 또는 손실보전 약정) — 헌재 2003.02.27. 선고 2002헌바4 (합헌)
- 자본시장법 제55조 (손실보전 약정 금지)

**🔗 프로젝트 매핑**: `abnormal_return_rate` 와 동일 flag 매핑 (LLM 이 의미적 유사성 검출 시 통합)

---

### 2.3 `business_not_registered` — 사업자 미등록

**법적 근거**:
- [전자상거래법 제12조 제1항](https://www.law.go.kr/법령/전자상거래등에서의소비자보호에관한법률) — 통신판매업자 신고
- 부가가치세법 제8조 (사업자등록)
- 유사수신행위법 제2조 (인가·등록·신고 X)

**정부/산업 보고서**:
- 공정거래위원회 [통신판매업자 정보공개시스템](https://www.ftc.go.kr/) — 신고번호 조회

**🔗 프로젝트 매핑**:
- flag: `business_not_registered`
- `pipeline/config.py:FLAG_RATIONALE["business_not_registered"]` — Stajano-Wilson Distraction (위장된 정상성) 인용
- 검출: `pipeline/verifier.py` Serper 교차 검증 (사업자등록 조회 결과 부재)

---

### 2.4 `suspicious_account_pattern` (≈ `account_scam_reported`) — 의심 계좌 / 대포통장

**학술 근거**: Florêncio, D., & Herley, C. (2013). *Where do all the attacks go?* Springer. DOI: [10.1007/978-1-4614-1981-5_2](https://doi.org/10.1007/978-1-4614-1981-5_2)

**법적 근거**:
- [전자금융거래법 제6조 제3항 / 제49조 제4항](https://www.law.go.kr/법령/전자금융거래법) (접근매체 양도·양수·대여 — 5년 이하 징역)
- 통신사기피해환급법 제2조 제4호 (사기이용계좌 정의), 제4조 (지급정지), 제9조
- 대법원 2012.07.05. 선고 2011도16167 — '양도'의 의미

**정부/산업 보고서**: 금융감독원 「2023년 보이스피싱 피해현황 분석」

**🔗 프로젝트 매핑**:
- flag: `account_scam_reported`
- `pipeline/config.py:FLAG_RATIONALE["account_scam_reported"]` — 통신사기피해환급법 + 금감원 통계 인용
- 검출: `pipeline/verifier.py` Serper API (계좌번호 신고 이력 검색)

---

### 2.5 `urgent_payment_method_change` — 결제 수단 갑작스러운 변경

**법적 근거**:
- 전자상거래법 제8조·제13조
- 통신사기피해환급법 제2조 제2호

**정부/산업 보고서**:
- FTC [*Sentinel Data Book 2024*](https://www.ftc.gov/reports/consumer-sentinel-network-data-book-2024) — bank transfer $2B + cryptocurrency $1.4B
- APWG [*Q4 2024 Report*](https://apwg.org/trendsreports/) — gift card 49%, cryptocurrency 12%

**🔗 프로젝트 매핑**: LLM 보조 검출 — `pipeline/llm_assessor.py` 가 컨텍스트 변화 감지

---

### 2.6 `cryptocurrency_payment_demand` — 암호화폐 결제 요구

**학술 근거**: Xia, P., et al. (2020). *Characterizing cryptocurrency exchange scams.* Computers & Security, 98. DOI: [10.1016/j.cose.2020.101993](https://doi.org/10.1016/j.cose.2020.101993)

**법적 근거**:
- 유사수신행위법 제2조 (2024.05.28 — 가상자산 포함)
- 「가상자산 이용자 보호 등에 관한 법률」 제2조 제1호
- 「특정금융거래정보법」 — 가상자산사업자 신고 의무

**정부/산업 보고서**:
- FBI [*IC3 2024*](https://www.ic3.gov/AnnualReport/Reports/2024_IC3Report.pdf) — crypto 손실 $9.3B (+66%)
- FTC [*Crypto payment scam alert*](https://consumer.ftc.gov/) — *"정부·법 집행기관·공공요금 회사는 결코 암호화폐로 결제를 요구하지 않는다"*

**🔗 프로젝트 매핑**:
- flag: `fake_exchange` (한국어 "가짜 거래소") — `FLAG_RATIONALE["fake_exchange"]` 에 FBI IC3 + Cross 2023 인용
- 검출: `pipeline/verifier.py` + LLM 보조

---

### 2.7 `gift_card_payment_demand` — 기프트카드 결제 요구

**법적 근거**: 형법 제347조 사기

**정부/산업 보고서**:
- FTC [*Only scammers tell you to buy a gift card*](https://consumer.ftc.gov/articles/avoiding-and-reporting-gift-card-scams), 2024.10
- APWG [Q4 2024](https://apwg.org/trendsreports/) — gift card 49%

**🔗 프로젝트 매핑**: LLM 보조 검출 — `pipeline/llm_assessor.py`

---

## 3. 카테고리 C — 디지털 콘텐츠 신호

### 3.1 `phone_scam_reported` — 전화번호 신고 이력

**학술 근거**: Tu, H., et al. (2016). *SoK: Everyone hates robocalls.* IEEE S&P 2016, pp. 320–338. DOI: [10.1109/SP.2016.27](https://doi.org/10.1109/SP.2016.27)

**법적 근거**:
- 전기통신사업법 제84조의2 (전화번호 거짓표시 금지)
- 정보통신망법 제50조

**정부/산업 보고서**: [전기통신금융사기 통합신고대응센터 ☎112](https://counterscam112.go.kr/)

**🔗 프로젝트 매핑**:
- flag: `phone_scam_reported`
- `pipeline/config.py:FLAG_RATIONALE["phone_scam_reported"]` — KISA 통계 + Anderson 베이지안 사전확률 인용
- 검출: `pipeline/verifier.py` Serper API

---

### 3.2 `url_shortener_used` — 단축 URL

**학술 근거**:
- Maggi, F., et al. (2013). *Two years of short URLs internet measurement.* WWW '13. DOI: [10.1145/2488388.2488463](https://doi.org/10.1145/2488388.2488463)
- Klien, F., & Strohmaier, M. (2012). ACM Hypertext '12. DOI: [10.1145/2309996.2310002](https://doi.org/10.1145/2309996.2310002)

**🔗 프로젝트 매핑**: Phase 0.5 sandbox (`pipeline/sandbox.py`) 가 URL 디토네이션 시 redirect chain 분석 → `sandbox_excessive_redirects` 또는 `sandbox_cloaking_detected`

---

### 3.3 `typosquatting_detected` — 도메인 오타 위장

**학술 근거**:
- Spaulding, J., Upadhyaya, S., & Mohaisen, A. (2016). arXiv: [1603.02767](https://arxiv.org/abs/1603.02767)
- Nikiforakis, N., et al. (2013). *Bitsquatting.* WWW '13. DOI: [10.1145/2488388.2488474](https://doi.org/10.1145/2488388.2488474)
- Kintis, P., et al. (2017). *Combosquatting.* ACM CCS 2017. DOI: [10.1145/3133956.3134002](https://doi.org/10.1145/3133956.3134002)

**법적 근거**:
- [인터넷주소자원법 제12조](https://www.law.go.kr/법령/인터넷주소자원에관한법률)
- 「부정경쟁방지법」 제2조 제1호 아목

**🔗 프로젝트 매핑**:
- flag: `apk_suspicious_package_name` (APK 패키지명 typo-squatting 검출 — Stage 2 Lv 1) → `pipeline/apk_analyzer._is_suspicious_impersonation()`
- 정상 한국 앱 list (kakao/naver/은행 등) 명시적 비교

---

### 3.4 `recently_registered_domain` — 신생 도메인

**학술 근거**: Hao, S., et al. (2016). *PREDATOR.* ACM CCS 2016. DOI: [10.1145/2976749.2978317](https://doi.org/10.1145/2976749.2978317)

**정부/산업 보고서**: APWG [*Q4 2024*](https://apwg.org/trendsreports/) — .TOP/.CYOU/.XIN 등 저비용 신생 TLD 악용

**🔗 프로젝트 매핑**: Phase 0.5 sandbox (`pipeline/sandbox.py`) 가 URL 분석 시 도메인 등록일 휴리스틱

---

### 3.5 `suspicious_writing_style` — 비정상 문체

**학술 근거**: Drouin, M., et al. (2016). *Why do people lie online?* Computers in Human Behavior, 64. DOI: [10.1016/j.chb.2016.06.052](https://doi.org/10.1016/j.chb.2016.06.052)

**산업 보고서**: S2W TALON 분석 보고서 시리즈 — 외국어 환경 그룹 식별

**🔗 프로젝트 매핑**: LLM 보조 (`pipeline/llm_assessor.py`) — 단독 flag 없음, 컨텍스트 신호로만 사용. **false positive 위험 — 단독 비권장.**

---

### 3.6 `ai_generated_content_suspected` — AI 생성 의심

**학술 근거**:
- Mitchell, E., et al. (2023). [*DetectGPT.*](https://arxiv.org/abs/2301.11305) ICML 2023
- Champa, A., et al. (2025). *Trick or Treat: Manipulative Tactics in Phishing Emails.* SAFECOMP 2025 — Stajano-Wilson 인용

**법적 근거**: 「인공지능의 발전과 신뢰 기반 조성 등에 관한 기본법」 (2024.12.26 국회 통과)

**정부/산업 보고서**: KISA [Insight 2024 Vol.07](https://www.kisa.or.kr/) (피싱 대응) / [2025 Vol.01](https://www.kisa.or.kr/) (DeepSeek)

**🔗 프로젝트 매핑**: 미구현 — future work. **false positive 위험 매우 높음 — 단독 사용 X.**

---

### 3.7 `impersonation_keywords_detected` — 사칭 키워드

**학술 근거**: Stajano & Wilson (2011), §"Social Compliance" (Authority cue). DOI: [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872)

**법적 근거**: 형법 제225·227·230조 / 통신사기피해환급법 제2조 제2호

**정부/산업 보고서**:
- **경찰청 [「2025년 1분기 보이스피싱 현황」](https://www.police.go.kr/), 2025.04.27 — 위험 키워드 공식 공개**: 사건조회·특급보안·엠바고·약식조사·자산검수·자산이전·감상문 제출

**🔗 프로젝트 매핑**:
- flag: `apk_impersonation_keywords` (APK Lv 2 dex string 분석) — `pipeline/apk_analyzer._contains_string_keywords()`
- 정의: `pipeline/apk_analyzer._IMPERSONATION_KEYWORDS` — frozenset {"검찰", "경찰", "금감원", "금융감독원", "수사", "구속", "체포", "고소", "안전계좌", "보안승급", "보안카드", "사칭", "피해자", "압수수색"}
- 학술/법적 근거: `pipeline/config.py:FLAG_RATIONALE["apk_impersonation_keywords"]`

---

## 4. 카테고리 D — Sandbox·웹 신호

### 4.1 `sandbox_password_form_detected` — 비밀번호 폼

**학술 근거**:
- [OWASP *Web Security Testing Guide v4.2*](https://owasp.org/www-project-web-security-testing-guide/) §4.4
- Marchal, S., et al. (2017). *Off-the-Hook.* IEEE TC 66(10). DOI: [10.1109/TC.2017.2703808](https://doi.org/10.1109/TC.2017.2703808)

**법적 근거**: 정보통신망법 제49조 / 개인정보보호법 제15·17조

**🔗 프로젝트 매핑**:
- flag: `sandbox_password_form_detected`
- `pipeline/sandbox.py` (Phase 0.5) — 격리 Chromium 으로 URL navigate 후 `<input type="password">` 검출
- `pipeline/config.py:FLAG_RATIONALE["sandbox_password_form_detected"]` — OWASP A07 + APWG 2024 인용

---

### 4.2 `sandbox_sensitive_form_detected` — 민감 정보 폼

**학술 근거**: Bilge, L., et al. (2009). [*EXPOSURE.*](https://www.ndss-symposium.org/wp-content/uploads/2017/09/14_3.pdf) NDSS 2009

**법적 근거**:
- [개인정보보호법 제24조의2](https://www.law.go.kr/법령/개인정보보호법) (주민등록번호 처리 제한), 제23조 (민감정보)
- 정보통신망법 제23조의2

**🔗 프로젝트 매핑**:
- flag: `sandbox_sensitive_form_detected`
- `pipeline/sandbox_detonate.py:_detect_sensitive_fields()` — 주민번호·OTP·CVC·계좌·카드 필드 검출
- `FLAG_RATIONALE["sandbox_sensitive_form_detected"]` — PCI DSS 4.0 + 개인정보보호법 시행령 별표1 인용

---

### 4.3 `sandbox_auto_download_attempt` — drive-by download

**학술 근거**:
- Provos, N., et al. (2008). [*All your iFRAMEs point to Us.*](https://www.usenix.org/legacy/event/sec08/tech/full_papers/provos/provos.pdf) USENIX Security 2008
- Cova, M., Kruegel, C., & Vigna, G. (2010). WWW '10. DOI: [10.1145/1772690.1772720](https://doi.org/10.1145/1772690.1772720)

**법적 근거**:
- 정보통신망법 제48조 제2항 / 제70조의2 (7년 이하)
- 대법원 2019.12.12. 선고 2017도16520

**🔗 프로젝트 매핑**:
- flag: `sandbox_auto_download_attempt`
- `pipeline/sandbox.py` — Playwright Chromium 의 `download` 이벤트 hook

---

### 4.4 `sandbox_excessive_redirect` / 4.5 `sandbox_cloaking_detected`

**학술 근거**:
- Invernizzi, L., et al. (2016). *Cloak of visibility.* IEEE S&P 2016. DOI: [10.1109/SP.2016.50](https://doi.org/10.1109/SP.2016.50)
- Wang, D. Y., Savage, S., & Voelker, G. M. (2011). ACM CCS 2011. DOI: [10.1145/2046707.2046763](https://doi.org/10.1145/2046707.2046763)
- Oest, A., et al. (2019). *PhishFarm.* IEEE S&P 2019. DOI: [10.1109/SP.2019.00049](https://doi.org/10.1109/SP.2019.00049)

**🔗 프로젝트 매핑**:
- `sandbox_excessive_redirects` / `sandbox_cloaking_detected`
- `pipeline/sandbox.py` — redirect chain 추적, target ≠ final URL 비교

---

### 4.6 `malware_detected` — VirusTotal 멀웨어 검출

**학술 근거**:
- Peng, P., et al. (2019). *Opening the blackbox of VirusTotal.* ACM IMC 2019. DOI: [10.1145/3355369.3355585](https://doi.org/10.1145/3355369.3355585)
- Salem, A., et al. (2021). *Maat.* ACM TOPS 24(4). DOI: [10.1145/3465361](https://doi.org/10.1145/3465361)

**법적 근거**:
- 정보통신망법 제48조 제2항 / 제70조의2
- 형법 제314조 제2항

**🔗 프로젝트 매핑**:
- flag: `malware_detected`, `phishing_url_confirmed`, `suspicious_file_signal`, `suspicious_url_signal`
- `pipeline/safety.py` (Phase 0) — VT API v3 client, SHA256 lookup + URL scan
- `FLAG_RATIONALE["malware_detected"]` — VT API v3 + NIST SP 800-83 인용

---

### 4.7 `suspicious_url_pattern` — 의심 URL

**학술 근거**:
- Ma, J., et al. (2009). ACM SIGKDD 2009. DOI: [10.1145/1557019.1557153](https://doi.org/10.1145/1557019.1557153)
- Sahoo, D., et al. (2017). arXiv: [1701.07179](https://arxiv.org/abs/1701.07179)

**🔗 프로젝트 매핑**:
- flag: `apk_hardcoded_c2_url` — APK Lv 2 (`pipeline/apk_analyzer._has_suspicious_url_constants()`)
- 정의: `pipeline/apk_analyzer._SUSPICIOUS_URL_PATTERNS` — IP 직접 / .tk·.ml·.ga·.cf·.gq / 비표준 포트 regex
- `suspicious_url_signal` (Phase 0 VT) 와 결합 평가

---

## 5. 카테고리 E — 한국 표적 신호

### 5.1 `kakao_impersonation` — 카카오톡 위장

**학술 근거**: Kim, J., Kim, J., Wi, S., Kim, Y., & Son, S. (2022). *HearMeOut: Detecting voice phishing activities in Android.* MobiSys '22, pp. 422–435 — **1,017 voice phishing 앱 분석**. DOI: [10.1145/3498361.3538939](https://doi.org/10.1145/3498361.3538939)

**법적 근거**:
- 부정경쟁방지법 제2조 제1호 가·나목
- 상표법 제108조
- 통신사기피해환급법 제2조 제2호

**정부/산업 보고서**:
- 금융감독원 「2023년 보이스피싱 피해현황 분석」 — 메신저피싱 33.7%
- S2W TALON [*SecretCalls Spotlight*](https://medium.com/s2wblog), 2024

**🔗 프로젝트 매핑**:
- flag: `apk_suspicious_package_name` (Stage 2 Lv 1) — `pipeline/apk_analyzer._LEGITIMATE_PACKAGE_PATTERNS` 에 `com.kakao.talk` 등 명시적 list
- flag: `impersonation_family` (메신저 피싱 일반) — `FLAG_RATIONALE["impersonation_family"]`

---

### 5.2 `delivery_sms_pattern` / 5.3 `wedding_invitation_phishing` / 5.4 `obituary_phishing`

**법적 근거**: 정보통신망법 제48조 제2항 / 제50조 / 통신사기피해환급법 제2조 제2호

**정부/산업 보고서**:
- KISA 보호나라, [택배 등 일상생활 사칭 스미싱 대응](https://www.kisa.or.kr/1020601)
- KISA, [「청첩장 등 지인 사칭 스미싱 주의 권고」](https://www.boho.or.kr/) (게시 다수)
- 과기정통부·KISA: 청첩장·부고장 스미싱 2023년 약 6만 건 → 2024년 약 6배 증가
- 경찰청 자료: 스미싱 피해액 2020년 11억 → 2024년 546억 (약 50배)

**🔗 프로젝트 매핑**:
- flag: `smishing_link_detected`
- `pipeline/config.py:FLAG_RATIONALE["smishing_link_detected"]` — KISA 통계 + APWG 인용
- 검출: `pipeline/verifier.py` (URL · 발신번호 · 키워드 매칭)

---

### 5.5 `financial_institution_impersonation` — 금융기관 사칭

**학술 근거**: Kim et al. (2022) HearMeOut. DOI: [10.1145/3498361.3538939](https://doi.org/10.1145/3498361.3538939)

**법적 근거**:
- 은행법 제66조의2 (유사명칭 사용 금지), 제14조
- 자본시장법 제38조
- 형법 제225조·제227조·제347조

**정부/산업 보고서**:
- 금융감독원 「2023년 보이스피싱 피해현황 분석」 — 대출빙자형 35.2% 1위
- S2W TALON [*HeadCalls*](https://medium.com/s2wblog), 2025.08

**🔗 프로젝트 매핑**:
- flag: `prepayment_requested`, `fss_not_registered`, `fake_government_agency` — 모두 `pipeline/config.py:FLAG_RATIONALE` 에 학술/법적 근거 박힘
- 검출: `pipeline/verifier.py` + `pipeline/llm_assessor.py`

---

## 6. 카테고리 F — APK 정적 분석 Lv 1

### 6.1 `apk_dangerous_permissions_combo` — 위험 권한 4종+ 조합

**학술 근거**:
- Arp, D., et al. (2014). [*DREBIN.*](https://www.ndss-symposium.org/wp-content/uploads/2017/09/11_3_1.pdf) NDSS 2014 — §III.A "Permissions" feature, 94% detection. DOI: [10.14722/ndss.2014.23247](https://doi.org/10.14722/ndss.2014.23247)
- Felt, A. P., et al. (2011). *Android Permissions Demystified.* ACM CCS 2011. DOI: [10.1145/2046707.2046779](https://doi.org/10.1145/2046707.2046779)
- Mariconti, E., et al. (2017). [*MaMaDroid.*](https://arxiv.org/abs/1612.04433) NDSS 2017. DOI: [10.14722/ndss.2017.23353](https://doi.org/10.14722/ndss.2017.23353)

**법적 근거**: 정보통신망법 제48조 제2항 / 개인정보보호법 제15·17·22조

**정부/산업 보고서**:
- [Google Play Console — *Use of SMS or Call Log permission groups*](https://support.google.com/googleplay/android-developer/answer/9047303)
- [Android Open Source Project — *Permissions*](https://developer.android.com/guide/topics/permissions/overview)

**🔗 프로젝트 매핑**:
- flag: `apk_dangerous_permissions_combo`
- `pipeline/apk_analyzer.py:_DANGEROUS_PERMISSION_COMBO` — frozenset 7종 (SEND_SMS, READ_SMS, RECEIVE_SMS, READ_CALL_LOG, PROCESS_OUTGOING_CALLS, BIND_ACCESSIBILITY_SERVICE, SYSTEM_ALERT_WINDOW)
- `pipeline/apk_analyzer.py:_DANGEROUS_PERMISSION_THRESHOLD = 4` — 4종 이상 동시 보유 시 검출
- `pipeline/apk_analyzer.analyze_apk_static()` — 호출 진입
- `pipeline/config.py:FLAG_RATIONALE["apk_dangerous_permissions_combo"]` — S2W TALON SecretCalls + DREBIN 인용

---

### 6.2 `apk_self_signed` — 자체 서명 인증서

**학술 근거**:
- Truong, H. T. T., et al. (2014). *The Company You Keep.* arXiv: [1312.3245](https://arxiv.org/abs/1312.3245)
- Palo Alto Unit42, [*Bad Certificate Management*](https://unit42.paloaltonetworks.com/bad-certificate-management-google-play-store/), 2014

**산업 보고서**: [APVI](https://bugs.chromium.org/p/apvi/) (2022.11) — Samsung·LG 플랫폼 인증서 유출

**🔗 프로젝트 매핑**:
- flag: `apk_self_signed`
- `pipeline/apk_analyzer._check_self_signed()` — `androguard.core.apk.APK.get_certificates_v3/v2/v1()` + asn1crypto subject == issuer 비교
- ⚠️ false positive — 정상 사이드로딩 앱도 가능. 단독 비권장 (`FLAG_RATIONALE["apk_self_signed"]` 본문 명시)

---

### 6.3 `apk_suspicious_package_name` — 패키지명 위장

**학술 근거**:
- Zhou, Y., & Jiang, X. (2012). IEEE S&P 2012. DOI: [10.1109/SP.2012.16](https://doi.org/10.1109/SP.2012.16)
- Truong et al. (2014). arXiv: [1312.3245](https://arxiv.org/abs/1312.3245)

**산업 보고서**: S2W TALON SecretCalls/TheftCalls/HeadCalls

**🔗 프로젝트 매핑**:
- flag: `apk_suspicious_package_name`
- `pipeline/apk_analyzer._is_suspicious_impersonation()` — typo-squatting 패턴 매칭
- `pipeline/apk_analyzer._LEGITIMATE_PACKAGE_PATTERNS` — 정상 한국 앱 16개 list (com.kakao.talk, com.nhn.android.search, kr.co.shinhan, com.kbstar.kbbank 등)
- `pipeline/apk_analyzer._SUSPICIOUS_PACKAGE_SUFFIXES` — fake/test/_v2/_new/official 등 7종

---

## 7. 카테고리 G — APK 심화 정적 분석 Lv 2 (bytecode)

### 7.1 `apk_sms_auto_send_code` — SmsManager.sendTextMessage

**학술 근거**:
- Arp et al. (2014) DREBIN, §III.B "API calls". DOI: [10.14722/ndss.2014.23247](https://doi.org/10.14722/ndss.2014.23247)
- Mariconti et al. (2017) MaMaDroid. DOI: [10.14722/ndss.2017.23353](https://doi.org/10.14722/ndss.2017.23353)

**법적 근거**:
- 정보통신망법 제48조 제2항 / 제70조의2 (7년 이하)
- 전기통신사업법 제32조의5 / 정보통신망법 제50조

**산업 보고서**: S2W TALON SecretCalls / [Corrata *Dangerous Permissions Android*](https://corrata.com/dangerous-permissions-android/)

**🔗 프로젝트 매핑**:
- flag: `apk_sms_auto_send_code`
- `pipeline/apk_analyzer._has_method_xref(analysis, "Landroid/telephony/SmsManager;", "sendTextMessage")` — androguard `AnalyzeAPK` xref 분석
- `pipeline/apk_analyzer.analyze_apk_bytecode()` — 호출 진입

---

### 7.2 `apk_call_state_listener` — TelephonyManager.listen

**학술 근거**: Kim, J., et al. (2022). *HearMeOut.* MobiSys '22 — call redirection / call screen overlay / fake call voice 보고. DOI: [10.1145/3498361.3538939](https://doi.org/10.1145/3498361.3538939)

**법적 근거**:
- 통신비밀보호법 제3조 제1항 (불법 감청 금지), 제16조 (10년 이하 징역)
- 정보통신망법 제48조 제2항 / 제70조의2

**산업 보고서**:
- S2W TALON [*Detailed Analysis of TheftCalls*](https://medium.com/s2wblog) — 강제 forwarding, 통화 기록 변조
- S2W TALON [*HeadCalls*](https://medium.com/s2wblog), 2025

**🔗 프로젝트 매핑**:
- flag: `apk_call_state_listener`
- `pipeline/apk_analyzer._has_method_xref(analysis, "Landroid/telephony/TelephonyManager;", "listen")`
- `FLAG_RATIONALE["apk_call_state_listener"]` — Kim 2022 HearMeOut + S2W TALON SecretCalls 인용

---

### 7.3 `apk_accessibility_abuse` — AccessibilityService 악용

**학술 근거**:
- Fratantonio, Y., et al. (2017). *Cloak and Dagger.* IEEE S&P 2017. DOI: [10.1109/SP.2017.39](https://doi.org/10.1109/SP.2017.39)
- Kim et al. (2022) HearMeOut. DOI: [10.1145/3498361.3538939](https://doi.org/10.1145/3498361.3538939)

**산업 보고서**:
- S2W TALON [*Deep Analysis of SecretCalls Part 2*](https://medium.com/s2wblog), 2024
- [Corrata *Dangerous Permissions Android*](https://corrata.com/dangerous-permissions-android/)

**🔗 프로젝트 매핑**:
- flag: `apk_accessibility_abuse`
- `pipeline/apk_analyzer._references_accessibility_service()` — `AccessibilityService` 상속 클래스 탐색
- ⚠️ 정상 장애인 보조 앱도 사용 — 단독 신호 약함, 권한 조합·은행 사칭 패키지명과 결합 시 강함 (`FLAG_RATIONALE` 본문 명시)

---

### 7.4 `apk_hardcoded_c2_url` — C&C URL hardcode

**학술 근거**:
- Arp et al. (2014) DREBIN §S5 "Network addresses". DOI: [10.14722/ndss.2014.23247](https://doi.org/10.14722/ndss.2014.23247)
- Karbab, E. B., et al. (2018). *MalDozer.* Digital Investigation, 24, S48–S59. DOI: [10.1016/j.diin.2018.01.007](https://doi.org/10.1016/j.diin.2018.01.007)

**법적 근거**: 정보통신망법 제48조 제2항 / 통신비밀보호법

**산업 보고서**: S2W TALON 보고서 — Firebase Cloud Messaging 을 C2 로 사용

**🔗 프로젝트 매핑**:
- flag: `apk_hardcoded_c2_url`
- `pipeline/apk_analyzer._has_suspicious_url_constants()` — dex string pool 검사
- `pipeline/apk_analyzer._SUSPICIOUS_URL_PATTERNS` — IP 직접 (`https?://\d+\.\d+\.\d+\.\d+`), 무료 도메인 (.tk·.ml·.ga·.cf·.gq), 비표준 포트 regex

---

### 7.5 `apk_string_obfuscation` — 난독화 흔적

**학술 근거**:
- Wermke, D., et al. (2018). ACSAC '18. DOI: [10.1145/3274694.3274726](https://doi.org/10.1145/3274694.3274726)
- Pendlebury, F., et al. (2019). [*TESSERACT.*](https://www.usenix.org/conference/usenixsecurity19/presentation/pendlebury) USENIX Security 2019

**🔗 프로젝트 매핑**:
- flag: `apk_string_obfuscation`
- `pipeline/apk_analyzer._looks_obfuscated()` — 1-2글자 클래스명 비율 + 클래스 50개 이상 임계
- `_OBFUSCATION_RATIO_THRESHOLD = 0.30`, `_OBFUSCATION_MIN_CLASSES = 50`
- ⚠️ 정상 ProGuard 사용 앱도 가능 — 단독 비권장

---

### 7.6 `apk_impersonation_keywords` — 사칭 키워드 hardcode

**학술 근거**: Kim et al. (2022) HearMeOut. DOI: [10.1145/3498361.3538939](https://doi.org/10.1145/3498361.3538939)

**법적 근거**:
- 형법 제225·227·230조
- 상표법 제108조 / 부정경쟁방지법 제2조
- 은행법 제66조의2

**정부/산업 보고서**: 경찰청 [「2025년 1분기 보이스피싱 현황」](https://www.police.go.kr/) — 위험 키워드 공식 공개

**🔗 프로젝트 매핑**:
- flag: `apk_impersonation_keywords`
- `pipeline/apk_analyzer._contains_string_keywords()` — dex string pool 검사
- `pipeline/apk_analyzer._IMPERSONATION_KEYWORDS` — 14종 키워드 (검찰·경찰·금감원·금융감독원·수사·구속·체포·고소·안전계좌·보안승급·보안카드·사칭·피해자·압수수색)
- `FLAG_RATIONALE["apk_impersonation_keywords"]` — Cialdini Authority + Stajano-Wilson Time Pressure + S2W TALON 인용

---

### 7.7 `apk_device_admin_lock` — DevicePolicyManager.lockNow

**학술 근거**:
- Andronio, N., Zanero, S., & Maggi, F. (2015). *HelDroid.* RAID 2015. DOI: [10.1007/978-3-319-26362-5_18](https://doi.org/10.1007/978-3-319-26362-5_18)
- Yang, T., et al. (2015). IEEE HPCC 2015. DOI: [10.1109/HPCC-CSS-ICESS.2015.39](https://doi.org/10.1109/HPCC-CSS-ICESS.2015.39)

**법적 근거**:
- 정보통신망법 제48조 제2항 — 대법원 2017도16520 (2019.12.12) "결과 발생 불요"
- 형법 제314조 제2항

**🔗 프로젝트 매핑**:
- flag: `apk_device_admin_lock`
- `pipeline/apk_analyzer._has_method_xref(analysis, "Landroid/app/admin/DevicePolicyManager;", "lockNow")`

---

## 8. 카테고리 H — APK 동적 분석 Lv 3 (인터페이스만, 격리 VM 필요)

⚠️ **로컬 실행 절대 금지 (HARD BLOCK)** — `APK_DYNAMIC_ENABLED=0` 기본 비활성. `backend=local` 어떤 env 조합으로도 풀리지 않음. 실제 remote VM 측 stack 은 future work.

### 8.1 `apk_runtime_c2_network_call`

**학술 근거**: Mavroeidis & Bromander (2017) Cyber Threat Intelligence Model — 인프라 기반 검출

**산업 보고서**: S2W TALON 보이스피싱 인프라 분석 / [Frida 동적 인스트루먼테이션](https://frida.re/)

**🔗 프로젝트 매핑**:
- flag: `apk_runtime_c2_network_call`
- `pipeline/apk_analyzer.analyze_apk_dynamic()` — remote VM 호출만 허용 (`APK_DYNAMIC_BACKEND=remote` + REMOTE_URL+TOKEN)
- 응답: `APKDynamicReport.detected_flags` — status=COMPLETED 시에만 채택

### 8.2 `apk_runtime_sms_intercepted` / 8.3 `apk_runtime_overlay_attack` / 8.4 `apk_runtime_credential_exfiltration` / 8.5 `apk_runtime_persistence_install`

**학술 근거**: Kim et al. (2022) HearMeOut / Fratantonio et al. (2017) Cloak and Dagger / [OWASP Mobile Top 10](https://owasp.org/www-project-mobile-top-10/)

**산업 보고서**: S2W TALON [SecretCalls Part 2](https://medium.com/s2wblog) / [TheftCalls](https://medium.com/s2wblog) / [HeadCalls](https://medium.com/s2wblog)

**🔗 프로젝트 매핑**:
- 5 종 flag (`apk_runtime_*`) 모두 `pipeline/config.py:FLAG_RATIONALE` 박힘
- `signal_detector.detect()` 의 `apk_dynamic_result` 인자가 status=COMPLETED 일 때만 검출 신호화
- 안전 정책: `pipeline/apk_analyzer.py:APKDynamicStatus.{DISABLED, BLOCKED_LOCAL, NOT_CONFIGURED, COMPLETED, ERROR}` 5 단계 enum

---

## 9. 신호 사용 가이드라인

**모든 신호는 단일 사용 X — 누적·조합 시점에서만 강함**.

특히 **false positive 큰 신호** (단독 사용 비권장):
- `apk_self_signed` — 정상 사이드로딩 앱
- `apk_string_obfuscation` — 정상 ProGuard
- `suspicious_writing_style` — 정상 외국인 한국어
- `ai_generated_content_suspected` — 정상 AI 활용
- `apk_accessibility_abuse` (단독) — 정상 장애인 보조 앱

이런 신호는 **권한 조합·사칭 키워드·서명 등 다른 강한 신호와 결합 시점에서만** 의미.

ScamGuardian 의 정체성 (CLAUDE.md): 신호 검출 + 학술/법적 근거 → 보고만. 판정 logic 은 통합 기업이 자체 risk tolerance 에 따라 구현.

---

## 10. Bibliography

### 10.1 학술 논문 / 단행본

| 인용 | DOI / URL |
|---|---|
| Andronio et al. (2015) HelDroid, RAID | [10.1007/978-3-319-26362-5_18](https://doi.org/10.1007/978-3-319-26362-5_18) |
| Arp et al. (2014) DREBIN, NDSS | [10.14722/ndss.2014.23247](https://doi.org/10.14722/ndss.2014.23247) / [PDF](https://www.ndss-symposium.org/wp-content/uploads/2017/09/11_3_1.pdf) |
| Bilge et al. (2009) EXPOSURE, NDSS | [PDF](https://www.ndss-symposium.org/wp-content/uploads/2017/09/14_3.pdf) |
| Cialdini (2021) Influence | Harper Business |
| Cova, Kruegel, & Vigna (2010) drive-by, WWW | [10.1145/1772690.1772720](https://doi.org/10.1145/1772690.1772720) |
| Drouin et al. (2016) Lying online, CHB | [10.1016/j.chb.2016.06.052](https://doi.org/10.1016/j.chb.2016.06.052) |
| Felt et al. (2011) Android Permissions, ACM CCS | [10.1145/2046707.2046779](https://doi.org/10.1145/2046707.2046779) |
| Florêncio & Herley (2013) Where attacks go | [10.1007/978-1-4614-1981-5_2](https://doi.org/10.1007/978-1-4614-1981-5_2) |
| Frankel (2012) Ponzi Scheme Puzzle | Oxford UP |
| Fratantonio et al. (2017) Cloak and Dagger, S&P | [10.1109/SP.2017.39](https://doi.org/10.1109/SP.2017.39) |
| Hao et al. (2016) PREDATOR, CCS | [10.1145/2976749.2978317](https://doi.org/10.1145/2976749.2978317) |
| Invernizzi et al. (2016) Cloak of visibility, S&P | [10.1109/SP.2016.50](https://doi.org/10.1109/SP.2016.50) |
| Karbab et al. (2018) MalDozer | [10.1016/j.diin.2018.01.007](https://doi.org/10.1016/j.diin.2018.01.007) |
| **Kim et al. (2022) HearMeOut, MobiSys** ⭐ | [10.1145/3498361.3538939](https://doi.org/10.1145/3498361.3538939) |
| Kintis et al. (2017) Combosquatting, CCS | [10.1145/3133956.3134002](https://doi.org/10.1145/3133956.3134002) |
| Klien & Strohmaier (2012) Short links, HT | [10.1145/2309996.2310002](https://doi.org/10.1145/2309996.2310002) |
| Langenderfer & Shimp (2001) Visceral influences | [10.1002/mar.1029](https://doi.org/10.1002/mar.1029) |
| Lea, Fischer, & Evans (2009) OFT1070 | [PDF](https://webarchive.nationalarchives.gov.uk/ukgwa/20140402142426/http://www.oft.gov.uk/shared_oft/reports/consumer_protection/oft1070.pdf) |
| Loewenstein (1996) Out of control | [10.1006/obhd.1996.0028](https://doi.org/10.1006/obhd.1996.0028) |
| Ma et al. (2009) Beyond blacklists, KDD | [10.1145/1557019.1557153](https://doi.org/10.1145/1557019.1557153) |
| Maggi et al. (2013) Short URLs, WWW | [10.1145/2488388.2488463](https://doi.org/10.1145/2488388.2488463) |
| Marchal et al. (2017) Off-the-Hook, IEEE TC | [10.1109/TC.2017.2703808](https://doi.org/10.1109/TC.2017.2703808) |
| Mariconti et al. (2017) MaMaDroid, NDSS | [10.14722/ndss.2017.23353](https://doi.org/10.14722/ndss.2017.23353) / [arXiv](https://arxiv.org/abs/1612.04433) |
| Mitchell et al. (2023) DetectGPT, ICML | [arXiv:2301.11305](https://arxiv.org/abs/2301.11305) |
| Modic & Lea (2013) Scam compliance, SSRN | [10.2139/ssrn.2364464](https://doi.org/10.2139/ssrn.2364464) |
| Nikiforakis et al. (2013) Bitsquatting, WWW | [10.1145/2488388.2488474](https://doi.org/10.1145/2488388.2488474) |
| Oest et al. (2019) PhishFarm, S&P | [10.1109/SP.2019.00049](https://doi.org/10.1109/SP.2019.00049) |
| OWASP WSTG v4.2 | [URL](https://owasp.org/www-project-web-security-testing-guide/) |
| Pendlebury et al. (2019) TESSERACT, USENIX | [PDF](https://www.usenix.org/conference/usenixsecurity19/presentation/pendlebury) |
| Peng et al. (2019) Blackbox of VirusTotal, IMC | [10.1145/3355369.3355585](https://doi.org/10.1145/3355369.3355585) |
| Provos et al. (2008) iFRAMEs, USENIX | [PDF](https://www.usenix.org/legacy/event/sec08/tech/full_papers/provos/provos.pdf) |
| Sahoo, Liu, & Hoi (2017) Malicious URL ML | [arXiv:1701.07179](https://arxiv.org/abs/1701.07179) |
| Salem, Banescu, & Pretschner (2021) Maat, TOPS | [10.1145/3465361](https://doi.org/10.1145/3465361) |
| Spaulding, Upadhyaya, & Mohaisen (2016) Typosquatting | [arXiv:1603.02767](https://arxiv.org/abs/1603.02767) |
| **Stajano & Wilson (2011) Seven principles, CACM** ⭐ | [10.1145/1897852.1897872](https://doi.org/10.1145/1897852.1897872) |
| Truong et al. (2014) Company you keep, WWW | [arXiv:1312.3245](https://arxiv.org/abs/1312.3245) |
| Tu et al. (2016) Robocalls SoK, S&P | [10.1109/SP.2016.27](https://doi.org/10.1109/SP.2016.27) |
| Wang, Savage, & Voelker (2011) Web cloaking, CCS | [10.1145/2046707.2046763](https://doi.org/10.1145/2046707.2046763) |
| Wermke et al. (2018) Obfuscation Google Play, ACSAC | [10.1145/3274694.3274726](https://doi.org/10.1145/3274694.3274726) |
| **Whitty (2013) Persuasive techniques model, BJC** ⭐ | [10.1093/bjc/azt009](https://doi.org/10.1093/bjc/azt009) |
| Whitty & Buchanan (2012) Romance scam, CyberPsych | [10.1089/cyber.2011.0352](https://doi.org/10.1089/cyber.2011.0352) |
| Whitty & Buchanan (2016) Psychological impact, CCJ | [10.1177/1748895815603773](https://doi.org/10.1177/1748895815603773) |
| Witte (1992) Fear appeals EPPM | [10.1080/03637759209376276](https://doi.org/10.1080/03637759209376276) |
| Xia et al. (2020) Crypto exchange scams | [10.1016/j.cose.2020.101993](https://doi.org/10.1016/j.cose.2020.101993) |
| Yang et al. (2015) Android ransomware, HPCC | [10.1109/HPCC-CSS-ICESS.2015.39](https://doi.org/10.1109/HPCC-CSS-ICESS.2015.39) |
| Zhou & Jiang (2012) Dissecting Android malware, S&P | [10.1109/SP.2012.16](https://doi.org/10.1109/SP.2012.16) |

⭐ = ScamGuardian 의 핵심 frame work 인용

### 10.2 한국 법령 (현행 2026.05 기준)

모든 법령 [국가법령정보센터 law.go.kr](https://www.law.go.kr/) 에서 조회 가능.

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

### 10.3 정부·산업 보고서

**한국**:
- 금융감독원 [「2023년 보이스피싱 피해현황 분석」](https://www.fss.or.kr/), 2024.03 — 1,965억 원, 1인당 1,700만 원
- 경찰청 [「2025년 1분기 보이스피싱 현황」](https://www.police.go.kr/), 2025.04.27 — 위험 키워드 5종 공식 공개
- KISA, [Insight 2024 Vol.07](https://www.kisa.or.kr/), 2024.10.31 / [Insight 2025 Vol.01](https://www.kisa.or.kr/), 2025.02
- KISA 보호나라, [청첩장·부고 스미싱 주의 권고](https://www.boho.or.kr/)
- 금융위원회, [유사수신 Q&A](https://www.fsc.go.kr/)
- 헌법재판소 2003.02.27. 선고 2002헌바4 (유사수신법 합헌)
- 대법원 2017도16520 (2019.12.12) / 2024도6831 (2024.10.25)
- S2W TALON, [SecretCalls Spotlight](https://medium.com/s2wblog) (2024) / [TheftCalls](https://medium.com/s2wblog) (2024) / [HeadCalls](https://medium.com/s2wblog) (2025.08)
- 안랩 ASEC 분기 동향 / 이스트시큐리티 ESRC

**국외**:
- FBI, [*2024 IC3 Report*](https://www.ic3.gov/AnnualReport/Reports/2024_IC3Report.pdf), 2025.04 (859,532건, $16.6B, +33% YoY)
- FTC, [*Consumer Sentinel Data Book 2024*](https://www.ftc.gov/reports/consumer-sentinel-network-data-book-2024), 2025
- APWG, [*Phishing Activity Trends Reports*](https://apwg.org/trendsreports/) (2024 Q1-Q4 / 2025 Q1)
- [Google Play Console Help — SMS/Call Log permissions](https://support.google.com/googleplay/android-developer/answer/9047303)
- [Android Open Source Project — Permissions](https://developer.android.com/guide/topics/permissions/overview)
- [Android Partner Vulnerability Initiative](https://bugs.chromium.org/p/apvi/) (2022.11)
- Palo Alto Unit42, [Bad Certificate Management](https://unit42.paloaltonetworks.com/bad-certificate-management-google-play-store/) (2014) / [Cybersquatting](https://unit42.paloaltonetworks.com/cybersquatting/) (2020)
- [Google Safe Browsing Transparency Report](https://transparencyreport.google.com/safe-browsing/overview)
- [Frida Dynamic Instrumentation](https://frida.re/)
- [Corrata, Dangerous Permissions Android](https://corrata.com/dangerous-permissions-android/) (2022)

---

## 11. Caveats (인용 시 주의)

1. **법령 개정**: 한국 법령은 빈번 개정. 자문 미팅 직전 [law.go.kr](https://www.law.go.kr) 재확인. 본 문서는 2026.05 기준
2. **페이지 번호**: 학술 논문 페이지는 게재본 기준 (Stajano & Wilson CACM 54(3) pp.70–75 등). Cialdini 는 판본별 다름 → Chapter 단위
3. **false positive 정직 표시**: 9 신호 카테고리 중 4개 (`apk_self_signed`, `apk_string_obfuscation`, `suspicious_writing_style`, `ai_generated_content_suspected`) 는 정상 콘텐츠에서도 흔함 → 단독 사용 비권장. **EVIDENCE.md §9 참조**
4. **통계 시점**: "1,965억 원·1인당 1,700만 원" = 2023년 (2024.03 발표). 경찰청 자료 — 2025년 1분기 3,116억 원으로 급증
5. **산업 보고서 인용**: S2W·안랩·이스트시큐리티 등은 peer-review 가 아니므로 학술 인용 시 *"산업 보고서"* 명시. 학술 논문 (특히 Kim et al. 2022 HearMeOut MobiSys'22) 을 1차 근거로 사용
6. **저작권**: 외부 공개·논문 인용 시 각 출처의 저작권·인용 규약 별도 확인. ACM/IEEE 논문은 보통 author preprint 로 합법 접근 가능
7. **시스템 정체성**: ScamGuardian 은 *판정자 (verdict)* 가 아닌 *검출자 (detector)*. 발표·미팅에서 *"이 시스템은 다음 N 개의 위험 신호를 다음 근거로 검출합니다"* 표현 일관 사용
8. **다층 방어**: 본 신호 시스템은 **1차 정적 분석 트리아지**. 동적 분석·사용자 교육·신고 채널 (☎112) 연계는 future work

---

> 본 문서는 ScamGuardian 졸업작품의 단일 reference book.
> 인용된 모든 학술 논문·법조항·정부 보고서는 2026년 5월 기준 실제 존재하며, URL/DOI/조항 번호로 검증 가능.
> 각 신호의 학술 근거는 `pipeline/config.py:FLAG_RATIONALE` 에 직접 박혀 있고, `/api/analyze` 응답의 `detected_signals[].rationale` / `.source` 로 외부 클라이언트에 transparent 노출된다.
