from __future__ import annotations

from typing import Any


def _normalize_pairs(items: list[dict[str, Any]], key_name: str) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for item in items:
        label = str(item.get(key_name, "")).strip()
        text = str(item.get("text", "")).strip()
        if label and text:
            pairs.add((label, text))
    return pairs


def compute_entity_metrics(
    predicted: list[dict[str, Any]],
    expected: list[dict[str, Any]],
) -> dict[str, float]:
    pred_set = _normalize_pairs(predicted, "label")
    expected_set = _normalize_pairs(expected, "label")

    tp = 0
    matched_expected: set[tuple[str, str]] = set()
    for p_label, p_text in pred_set:
        for e_label, e_text in expected_set:
            if (e_label, e_text) in matched_expected:
                continue
            if p_label == e_label and (p_text in e_text or e_text in p_text):
                tp += 1
                matched_expected.add((e_label, e_text))
                break

    fp = len(pred_set) - tp
    fn = len(expected_set) - tp
    precision = tp / len(pred_set) if pred_set else 0.0
    recall = tp / len(expected_set) if expected_set else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def compute_flag_metrics(
    predicted: list[dict[str, Any]],
    expected: list[dict[str, Any]],
) -> dict[str, float]:
    pred_flags = {str(item.get("flag", "")).strip() for item in predicted if item.get("flag")}
    gt_flags = {str(item.get("flag", "")).strip() for item in expected if item.get("flag")}
    tp = len(pred_flags & gt_flags)
    fp = len(pred_flags - gt_flags)
    fn = len(gt_flags - pred_flags)
    precision = tp / len(pred_flags) if pred_flags else 0.0
    recall = tp / len(gt_flags) if gt_flags else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    return {
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def evaluate_annotated_runs(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {
            "sample_count": 0,
            "classification_accuracy": 0.0,
            "entity_micro": compute_entity_metrics([], []),
            "flag_micro": compute_flag_metrics([], []),
            "per_run": [],
        }

    classification_hits = 0
    entity_tp = entity_fp = entity_fn = 0
    flag_tp = flag_fp = flag_fn = 0
    per_run: list[dict[str, Any]] = []

    for record in records:
        predicted_type = str(record.get("classification_scanner", {}).get("scam_type", "")).strip()
        expected_type = str(record.get("scam_type_gt", "")).strip()
        if predicted_type and predicted_type == expected_type:
            classification_hits += 1

        entity_metrics = compute_entity_metrics(
            record.get("entities_predicted", []),
            record.get("entities_gt", []),
        )
        flag_metrics = compute_flag_metrics(
            record.get("triggered_flags_predicted", []),
            record.get("triggered_flags_gt", []),
        )
        entity_tp += int(entity_metrics["tp"])
        entity_fp += int(entity_metrics["fp"])
        entity_fn += int(entity_metrics["fn"])
        flag_tp += int(flag_metrics["tp"])
        flag_fp += int(flag_metrics["fp"])
        flag_fn += int(flag_metrics["fn"])

        per_run.append(
            {
                "run_id": record.get("run_id"),
                "predicted_scam_type": predicted_type,
                "scam_type_gt": expected_type,
                "entity_metrics": entity_metrics,
                "flag_metrics": flag_metrics,
            }
        )

    entity_precision = entity_tp / (entity_tp + entity_fp) if (entity_tp + entity_fp) else 0.0
    entity_recall = entity_tp / (entity_tp + entity_fn) if (entity_tp + entity_fn) else 0.0
    entity_f1 = (
        2 * entity_precision * entity_recall / (entity_precision + entity_recall)
        if (entity_precision + entity_recall)
        else 0.0
    )

    flag_precision = flag_tp / (flag_tp + flag_fp) if (flag_tp + flag_fp) else 0.0
    flag_recall = flag_tp / (flag_tp + flag_fn) if (flag_tp + flag_fn) else 0.0
    flag_f1 = (
        2 * flag_precision * flag_recall / (flag_precision + flag_recall)
        if (flag_precision + flag_recall)
        else 0.0
    )

    return {
        "sample_count": len(records),
        "classification_accuracy": classification_hits / len(records),
        "entity_micro": {
            "precision": entity_precision,
            "recall": entity_recall,
            "f1": entity_f1,
            "tp": entity_tp,
            "fp": entity_fp,
            "fn": entity_fn,
        },
        "flag_micro": {
            "precision": flag_precision,
            "recall": flag_recall,
            "f1": flag_f1,
            "tp": flag_tp,
            "fp": flag_fp,
            "fn": flag_fn,
        },
        "per_run": per_run,
    }

