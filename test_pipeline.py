#!/usr/bin/env python3
"""
ScamGuardian v2 — 통합 테스트
엔티티 추출 정확도(Precision/Recall/F1)를 측정하고
전체 파이프라인이 정상 동작하는지 검증한다.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

load_dotenv()


# ──────────────────────────────────────────────
# 테스트 케이스 정의
# ──────────────────────────────────────────────

TEST_CASES = [
    {
        "text": "일론 머스크가 화성 이민 프로젝트에 300만원 투자하면 연 30% 수익 보장합니다. 문의: 010-1234-5678",
        "expected": {
            "사람 이름": ["일론 머스크"],
            "금액": ["300만원"],
            "수익 퍼센트": ["연 30%"],
            "전화번호": ["010-1234-5678"],
        },
        "expected_scam_type": "투자 사기",
    },
    {
        "text": "저희 바이오헬스 코리아에서 개발한 기적의 환은 암을 완치시킵니다. 서울대 의대 김박사가 직접 개발했으며 식약처 인증을 받았습니다. 지금 전화주시면 50% 할인 가격 29만원에 드립니다. 02-555-1234",
        "expected": {
            "회사명 또는 기관명": ["바이오헬스 코리아"],
            "제품명": ["기적의 환"],
            "치료 효능 주장": ["암을 완치"],
            "전문가 직함": ["김박사"],
            "금액": ["29만원"],
            "전화번호": ["02-555-1234"],
        },
        "expected_scam_type": "건강식품 사기",
    },
    {
        "text": "여기는 금융감독원 수사팀입니다. 귀하의 계좌가 범죄에 연루되어 사건번호 2024-가-12345로 조사 중입니다. 안전계좌로 이체하셔야 합니다. 계좌번호 110-345-678901 국민은행. 주민번호와 비밀번호를 알려주세요.",
        "expected": {
            "사칭 기관명": ["금융감독원"],
            "직함 또는 직책": ["수사팀"],
            "사건번호 또는 공문번호": ["2024-가-12345"],
            "계좌번호": ["110-345-678901"],
            "개인정보 항목": ["주민번호", "비밀번호"],
        },
        "expected_scam_type": "기관 사칭",
    },
]


# ──────────────────────────────────────────────
# F1 측정 함수
# ──────────────────────────────────────────────

def compute_entity_metrics(
    predicted: list[dict],
    expected: dict[str, list[str]],
) -> dict[str, float]:
    """
    추출된 엔티티와 기대값을 비교하여 Precision/Recall/F1을 계산한다.

    비교 기준: 레이블 일치 + 텍스트 부분 일치(predicted text가 expected에 포함되거나 반대)
    """
    pred_set: set[tuple[str, str]] = set()
    for p in predicted:
        pred_set.add((p["label"], p["text"]))

    expected_set: set[tuple[str, str]] = set()
    for label, texts in expected.items():
        for text in texts:
            expected_set.add((label, text))

    tp = 0
    for p_label, p_text in pred_set:
        for e_label, e_text in expected_set:
            if p_label == e_label and (p_text in e_text or e_text in p_text):
                tp += 1
                break

    precision = tp / len(pred_set) if pred_set else 0.0
    recall = tp / len(expected_set) if expected_set else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": len(pred_set) - tp, "fn": len(expected_set) - tp}


# ──────────────────────────────────────────────
# 테스트 실행
# ──────────────────────────────────────────────

def test_classification():
    """스캠 유형 분류 테스트"""
    from pipeline.classifier import classify

    print("=" * 60)
    print("  테스트 1: 스캠 유형 분류")
    print("=" * 60)

    passed = 0
    for i, tc in enumerate(TEST_CASES):
        result = classify(tc["text"])
        ok = result.scam_type == tc["expected_scam_type"]
        status = "PASS" if ok else "FAIL"
        if ok:
            passed += 1
        print(f"\n  [{status}] 케이스 {i + 1}")
        print(f"    예상: {tc['expected_scam_type']}")
        print(f"    실제: {result.scam_type} ({result.confidence:.1%})")
        print(f"    전체: {result.all_scores}")

    print(f"\n  결과: {passed}/{len(TEST_CASES)} 통과\n")
    return passed == len(TEST_CASES)


def test_extraction():
    """엔티티 추출 테스트 + F1 측정"""
    from pipeline.extractor import extract

    print("=" * 60)
    print("  테스트 2: 엔티티 추출 + F1 측정")
    print("=" * 60)

    all_metrics: list[dict[str, float]] = []

    for i, tc in enumerate(TEST_CASES):
        scam_type = tc["expected_scam_type"]
        entities = extract(tc["text"], scam_type)
        predicted = [e.to_dict() for e in entities]
        metrics = compute_entity_metrics(predicted, tc["expected"])
        all_metrics.append(metrics)

        print(f"\n  케이스 {i + 1} ({scam_type}):")
        print(f"    추출됨: {[(e['label'], e['text']) for e in predicted]}")
        print(f"    기대값: {tc['expected']}")
        print(f"    P={metrics['precision']:.2f}  R={metrics['recall']:.2f}  F1={metrics['f1']:.2f}")
        print(f"    TP={metrics['tp']}  FP={metrics['fp']}  FN={metrics['fn']}")

    avg_f1 = sum(m["f1"] for m in all_metrics) / len(all_metrics)
    avg_p = sum(m["precision"] for m in all_metrics) / len(all_metrics)
    avg_r = sum(m["recall"] for m in all_metrics) / len(all_metrics)

    print(f"\n  평균: P={avg_p:.2f}  R={avg_r:.2f}  F1={avg_f1:.2f}")
    target = 0.7
    status = "PASS" if avg_f1 >= target else "FAIL"
    print(f"  [{status}] 목표 F1 >= {target} → 실제 F1 = {avg_f1:.2f}\n")

    return avg_f1 >= target


def test_full_pipeline():
    """전체 파이프라인 통합 테스트 (Serper API 호출 생략)"""
    from pipeline.runner import ScamGuardianPipeline

    print("=" * 60)
    print("  테스트 3: 전체 파이프라인 (검증 생략)")
    print("=" * 60)

    pipe = ScamGuardianPipeline(whisper_model="medium")
    tc = TEST_CASES[0]

    report = pipe.analyze(tc["text"], skip_verification=True)
    print(report.summary())
    pipe.print_step_log()

    assert report.scam_type != "", "스캠 유형이 비어있음"
    assert len(report.entities) > 0, "엔티티가 추출되지 않음"
    print("\n  [PASS] 전체 파이프라인 정상 동작\n")
    return True


def test_llm_merge_and_score():
    """LLM 보조 엔티티 병합 및 점수 반영 테스트"""
    from pipeline import llm_assessor, scorer
    from pipeline.extractor import Entity

    @dataclass
    class DummyClassification:
        scam_type: str
        confidence: float
        is_uncertain: bool

    print("=" * 60)
    print("  테스트 4: LLM 보조 병합/점수 반영")
    print("=" * 60)

    base_entities = [
        Entity(text="300만원", label="금액", score=1.0, start=0, end=4),
    ]
    assessment = llm_assessor.LLMAssessment(
        model="test-model",
        summary="추가 근거가 보입니다.",
        suggested_entities=[
            llm_assessor.SuggestedEntity(
                text="오늘만",
                label="날짜 또는 기간",
                reason="긴박감을 조성합니다.",
                confidence=0.91,
            )
        ],
        suggested_flags=[
            llm_assessor.SuggestedFlag(
                flag="abnormal_return_rate",
                reason="과도한 수익 보장 문구입니다.",
                evidence="연 30% 수익 보장",
                confidence=0.92,
            )
        ],
    )

    merged_entities = llm_assessor.merge_suggested_entities(base_entities, assessment)
    report = scorer.score(
        verification_results=[],
        classification=DummyClassification("투자 사기", 0.8, False),
        entities=merged_entities,
        source="dummy",
        transcript="오늘만 300만원 넣으면 연 30% 수익 보장",
        llm_assessment=assessment,
    )

    assert len(merged_entities) == 2, "LLM 엔티티 병합 실패"
    assert any(e.source == "llm" for e in merged_entities), "LLM 엔티티 source 누락"
    assert any(f.source == "llm" for f in report.triggered_flags), "LLM 플래그 점수 반영 실패"
    print("\n  [PASS] LLM 보조 병합/점수 반영 정상 동작\n")
    return True


def test_eval_metrics():
    """사람 라벨 기반 메트릭 집계 테스트"""
    from pipeline import eval as pipeline_eval

    print("=" * 60)
    print("  테스트 5: 저장 라벨 메트릭 집계")
    print("=" * 60)

    records = [
        {
            "run_id": "run-1",
            "classification_scanner": {"scam_type": "투자 사기"},
            "scam_type_gt": "투자 사기",
            "entities_predicted": [
                {"label": "금액", "text": "300만원"},
                {"label": "수익 퍼센트", "text": "연 30%"},
            ],
            "entities_gt": [
                {"label": "금액", "text": "300만원"},
                {"label": "수익 퍼센트", "text": "연 30%"},
            ],
            "triggered_flags_predicted": [
                {"flag": "abnormal_return_rate"},
            ],
            "triggered_flags_gt": [
                {"flag": "abnormal_return_rate"},
            ],
        },
        {
            "run_id": "run-2",
            "classification_scanner": {"scam_type": "기관 사칭"},
            "scam_type_gt": "기관 사칭",
            "entities_predicted": [
                {"label": "사칭 기관명", "text": "금융감독원"},
            ],
            "entities_gt": [
                {"label": "사칭 기관명", "text": "금융감독원"},
                {"label": "개인정보 항목", "text": "주민번호"},
            ],
            "triggered_flags_predicted": [],
            "triggered_flags_gt": [
                {"flag": "personal_info_request"},
            ],
        },
    ]

    metrics = pipeline_eval.evaluate_annotated_runs(records)
    assert metrics["sample_count"] == 2, "샘플 수 집계 오류"
    assert metrics["classification_accuracy"] == 1.0, "분류 정확도 집계 오류"
    assert metrics["entity_micro"]["tp"] == 3, "엔티티 TP 집계 오류"
    assert metrics["entity_micro"]["fn"] == 1, "엔티티 FN 집계 오류"
    assert metrics["flag_micro"]["tp"] == 1, "플래그 TP 집계 오류"
    assert metrics["flag_micro"]["fn"] == 1, "플래그 FN 집계 오류"
    print("\n  [PASS] 저장 라벨 메트릭 집계 정상 동작\n")
    return True


def test_scam_type_taxonomy_merge():
    """사용자 추가 스캠 유형이 런타임 taxonomy에 합쳐지는지 테스트"""
    from pipeline.config import BASE_LABELS, build_scam_taxonomy

    print("=" * 60)
    print("  테스트 6: 사용자 스캠 유형 taxonomy 병합")
    print("=" * 60)

    taxonomy = build_scam_taxonomy(
        [
            {
                "name": "대출 사기",
                "description": "급전 대출 승인과 선입금 수수료를 요구",
                "labels": ["대출 기관명", "수수료 금액"],
            }
        ]
    )

    assert "대출 사기" in taxonomy["scam_types"], "사용자 스캠 유형 추가 실패"
    assert taxonomy["descriptions"]["급전 대출 승인과 선입금 수수료를 요구"] == "대출 사기"
    assert taxonomy["label_sets"]["대출 사기"] == ["대출 기관명", "수수료 금액"]

    fallback_taxonomy = build_scam_taxonomy([{"name": "로맨스 스캠"}])
    assert fallback_taxonomy["label_sets"]["로맨스 스캠"] == BASE_LABELS, "기본 라벨셋 fallback 오류"
    print("\n  [PASS] 사용자 스캠 유형 taxonomy 병합 정상 동작\n")
    return True


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("  ScamGuardian v2 — 통합 테스트")
    print("=" * 60 + "\n")

    results = {}

    results["분류"] = test_classification()
    results["추출"] = test_extraction()
    results["파이프라인"] = test_full_pipeline()
    results["LLM 보조"] = test_llm_merge_and_score()
    results["메트릭"] = test_eval_metrics()
    results["유형 카탈로그"] = test_scam_type_taxonomy_merge()

    print("\n" + "=" * 60)
    print("  최종 결과")
    print("=" * 60)
    for name, passed in results.items():
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {name}")

    all_passed = all(results.values())
    print(f"\n  {'모든 테스트 통과!' if all_passed else '일부 테스트 실패'}")
    print("=" * 60)

    sys.exit(0 if all_passed else 1)
