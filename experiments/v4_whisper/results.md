# v4 exp2 — Whisper API 5초 chunk 한국어 정확도 측정

- 모델: OpenAI Whisper API (`whisper-1`)
- chunk: 5s
- 샘플: 5 (TTS 합성, edge-tts 한국어 3개 voice)
- 평균 WER: **0.307** (임계 0.20 → FAIL ❌)
- PASS: 2/5
- chunk 평균 latency: 1985ms

## 샘플별 결과

| ID | variant | 시나리오 | WER | 판정 | chunks | 평균 latency |
|---|---|---|---|---|---|---|
| `s1_prosecutor` | clean | 검찰사칭(권위) | 0.462 | FAIL ❌ | 3 | 1902ms |
| `s2_bank` | clean | 금융사칭(친절) | 0.077 | PASS ✅ | 2 | 2525ms |
| `s3_meta_aware` | clean | 사용자 메타인식 | 0.500 | FAIL ❌ | 2 | 2025ms |
| `s4_transfer_agree` | clean | 사용자 송금 동의 | 0.111 | PASS ✅ | 2 | 1912ms |
| `s5_normal` | clean | 일반 대화 대조군 | 0.385 | FAIL ❌ | 2 | 1559ms |

## 발화별 reference vs hypothesis

### `s1_prosecutor` (clean) — 검찰사칭(권위)

- reference: 안녕하십니까 서울중앙지방검찰청 김재호 검사입니다. 본인 명의로 대포통장 개설 사건이 접수되어 긴급 통화 드립니다.
- hypothesis: 안녕하십니까? 서울중앙지방검찰청 김재호 검사입니다. 본인 명의로 대포 통장 개설 사건이 접수되어 긴급 통화드립니다. MBC 뉴스 이덕영입니다.
- WER: **0.462** | FAIL ❌

### `s2_bank` (clean) — 금융사칭(친절)

- reference: 안녕하세요 고객님 신한은행 보안팀입니다. 본인 명의로 의심 거래가 발생해서요 보안카드 일련번호 확인 부탁드릴게요.
- hypothesis: 안녕하세요 고객님 신한은행 보안팀입니다 본인 명의로 의심 심거래가 발생해서요 보안카드 일련번호 확인 부탁드릴게요
- WER: **0.077** | PASS ✅

### `s3_meta_aware` (clean) — 사용자 메타인식

- reference: 잠깐만요 이거 사기 같은데요. 어느 부서에서 전화하셨다고 하셨죠?
- hypothesis: 잠깐만요 이거 사기같은데요 어느 부서에서 전화하셨나요? 있다고 하셨죠?
- WER: **0.500** | FAIL ❌

### `s4_transfer_agree` (clean) — 사용자 송금 동의

- reference: 네 알겠어요. 그럼 지금 바로 안전계좌로 이체하면 되는 건가요?
- hypothesis: 네 알겠어요. 그럼 지금 바로 안전계좌로 이체하면 되는 겁니까? 건가요?
- WER: **0.111** | PASS ✅

### `s5_normal` (clean) — 일반 대화 대조군

- reference: 오늘 점심은 회사 근처 칼국수집에서 먹기로 했어요. 두 시쯤 회의 끝나고 바로 갈게요.
- hypothesis: 오늘 점심은 회사 근처 칼국수 집에서 먹기로 했어요. 2시쯤 회 끝나고 바로 갈게요.
- WER: **0.385** | FAIL ❌

## 비고

- **WER 정의**: word error rate (Levenshtein 토큰 거리). 한국어는 공백 분리 토큰.
- **임계 0.20**: 통화 환경 잡음 가정. 실전 마이크 녹음에서 합성 음성 대비 WER 1.5~2배 증가하는 게 일반적이라 클린 합성에서는 0.10~0.15 정도면 안전.
- **다음 검증**: 실제 한국어 통화 녹음 (스피커폰 + 배경잡음) 으로 동일 측정 — `--speakerphone` 옵션이 1차 시뮬.

## 핵심 발견 — 단순 5초 고정 chunk 는 v4 production 에 부적합

평균 WER 0.307 / 5개 중 2개만 PASS. **임계 미달이지만 이 결과가 v4 의 valuable input** — 실패 원인 3가지가 명확하고, 각각 알려진 해법이 존재.

### 실패 패턴 (3종)

#### 1. 침묵 chunk 환각 (`s1_prosecutor`)

```
[10.0-15.0s] (1699ms) MBC 뉴스 이덕영입니다.
```

발화는 ~10초로 끝나고 마지막 5초 chunk 는 거의 침묵 — Whisper 가 학습 데이터(KBS/MBC 뉴스 종영 멘트)로 환각. 이건 **Whisper-large-v3 까지도 알려진 issue** (OpenAI cookbook + GitHub issue #2106 다수 보고).

**해결**:
- VAD (Silero / WebRTC VAD) 로 침묵 chunk 사전 필터
- 또는 `prompt` 파라미터에 직전 발화 주입 — 환각 방향 제약
- 또는 chunk RMS energy 임계값으로 < 0.01 면 skip

#### 2. Chunk 경계 단어 절단 (`s3_meta_aware`, `s4_transfer_agree`, `s5_normal`)

5초 경계가 단어 중간에 떨어짐:
- `s3`: "전화하셨다고 하셨죠" → "전화하셨나요? | 있다고 하셨죠?"
- `s4`: "되는 건가요" → "되는 겁니까? | 건가요?"
- `s5`: "회의 끝나고" → "회 | 끝나고"

5초 경계가 두 문장 또는 한 단어를 자르면 두 chunk 모두 인식 오류 + 중복 토큰.

**해결**:
- **Overlapping window** (3.5~4초 hop, 5초 window) — 경계 부근 토큰 양쪽 chunk 에 모두 포함, dedupe 후 합본
- **streaming Whisper** (whisper-streaming 라이브러리) — local backend 가 chunk 경계 컨텍스트 유지

#### 3. 한국어 신조어/숫자 표기 (`s5_normal`)

`두 시쯤` → `2시쯤` (의미 동일하지만 토큰 WER 잡힘). 이건 사람 평가에서는 OK 지만 우리 WER metric 이 너무 엄격.

**해결**:
- 평가 시 번호↔한글 정규화 (regex 기반 후처리)
- 또는 metric 을 **CER** (글자 단위) 또는 **semantic similarity** 로 변경

### v4 설계 결론

**5초 고정 chunk + 후처리 없음 → v4 production 에 부적합**. 그러나 **3가지 처방이 명확**:
1. VAD pre-filter (침묵 환각 차단)
2. Overlapping window + dedupe (경계 절단 완화)
3. WER 대신 의미 기준 평가 (또는 CER + 한글-숫자 정규화)

**다음 액션**:
- VAD + 2초 오버랩 추가 한 chunker v2 → 재측정
- 평균 WER < 0.15 또는 CER < 0.10 까지 끌어내야 v4 진입 가능
