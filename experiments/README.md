# v4 검증 실험

v4.0 (Live Call Guard) 진입 전에 두 가지 핵심 가정을 빠르게 검증한다.

## v4_intent — Haiku 의도 분류 (✅ 완료)

사용자(피해자) 발화에서 즉시 경보 신호 3종(메타인식·민감정보 누설·송금동의) 을
NORMAL 과 분리할 수 있는지.

```bash
python experiments/v4_intent/run_eval.py
# → results.md, raw_predictions.jsonl
```

**현재 결과**: 합성 32샘플 macro F1 = 1.000 (PASS, 임계 0.85). ⚠️ 합성 데이터라 실전
정확도 과대평가 가능 — v4.0 알파에서 실제 통화 transcript 로 재검증 필요.

## v4_whisper — 5초 chunk Whisper STT (인프라만)

ffmpeg 으로 오디오 5초 분할 → OpenAI Whisper API 순차 호출 → 누적 transcript +
WER 계산.

```bash
# 오디오만
python experiments/v4_whisper/run_eval.py path/to/sample.wav

# 정답 transcript 있으면 WER 자동 계산
python experiments/v4_whisper/run_eval.py sample.wav --reference sample.txt

# chunk 길이 변경
python experiments/v4_whisper/run_eval.py sample.wav --chunk 3
```

**WER 임계**: 0.20 (실전 통화 잡음·압축 환경 기준 너그럽게).

**다음 단계** (오디오 수집 후):
1. 본인이 스피커폰으로 보이스피싱 시나리오 5개 발화 (각 30~60초) 녹음 → wav 로 저장
2. 같은 발화의 ground truth transcript 를 `*.txt` 로 옆에 저장
3. 위 명령 실행 → WER 측정
4. WER ≤ 0.20 이면 v4.0 진입 OK. 초과면:
   - chunk 크기 조정 (3s vs 7s)
   - Deepgram 한국어 모델로 교체 검토
   - 노이즈 게이팅 전처리 추가

**검증할 가정**:
- 사용자 발화는 마이크 가까이 → 깨끗할 것 → Whisper 가 잘 잡음
- 5초 chunk 가 한국어 단어 경계 자르는 빈도 (chunk 사이 단어 잘림이 WER 에 큰 영향이면 Voice Activity Detection 필요)
- 누적 latency: chunk 당 ~1초 × 통화 5분 = 60 chunk × ~1s = 60s 합산. 비동기 호출이면 실시간 가능
