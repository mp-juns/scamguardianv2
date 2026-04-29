# v4 exp1 — Haiku 의도 분류 평가

- 모델: `claude-haiku-4-5-20251001`
- 샘플 수: 32
- 평균 latency: 877ms
- 정확도: **1.000**
- macro F1: **1.000** (임계 0.85 → PASS ✅)

## per-class metrics

| label | precision | recall | F1 | support |
|---|---|---|---|---|
| META_AWARE | 1.000 | 1.000 | 1.000 | 8 |
| SENSITIVE_INFO | 1.000 | 1.000 | 1.000 | 8 |
| TRANSFER_AGREE | 1.000 | 1.000 | 1.000 | 8 |
| NORMAL | 1.000 | 1.000 | 1.000 | 8 |

## confusion matrix (행=정답, 열=예측)

| GT \ pred | META_AWARE | SENSITIVE_INFO | TRANSFER_AGREE | NORMAL |
|---|---|---|---|---|
| META_AWARE | 8 | 0 | 0 | 0 |
| SENSITIVE_INFO | 0 | 8 | 0 | 0 |
| TRANSFER_AGREE | 0 | 0 | 8 | 0 |
| NORMAL | 0 | 0 | 0 | 8 |
