"""/health 와 /api/methodology — 정적·메타 응답."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/api/methodology")
def get_methodology() -> dict[str, Any]:
    """위험도 점수 산정 방식 메타 정보. /methodology 페이지가 호출."""
    from pipeline import config as pcfg

    flags: list[dict[str, Any]] = []
    for key, score_delta in pcfg.SCORING_RULES.items():
        info = pcfg.FLAG_RATIONALE.get(key, {})
        flags.append({
            "flag": key,
            "label_ko": pcfg.FLAG_LABELS_KO.get(key, key),
            "score_delta": score_delta,
            "rationale": info.get("rationale", ""),
            "source": info.get("source", ""),
        })
    flags.sort(key=lambda x: (-x["score_delta"], x["flag"]))

    risk_bands: list[dict[str, Any]] = []
    prev_threshold = -1
    for threshold, level, description in pcfg.RISK_LEVELS:
        risk_bands.append({
            "min": prev_threshold + 1,
            "max": threshold if threshold < 999 else 100,
            "level": level,
            "description": description,
        })
        prev_threshold = threshold

    return {
        "flags": flags,
        "risk_bands": risk_bands,
        "weights": {
            "llm_flag_score_ratio": pcfg.LLM_FLAG_SCORE_RATIO,
            "llm_entity_merge_threshold": pcfg.LLM_ENTITY_MERGE_THRESHOLD,
            "llm_flag_score_threshold": pcfg.LLM_FLAG_SCORE_THRESHOLD,
            "llm_scam_type_override_threshold": pcfg.LLM_SCAM_TYPE_OVERRIDE_THRESHOLD,
            "classification_threshold": pcfg.CLASSIFICATION_THRESHOLD,
            "gliner_threshold": pcfg.GLINER_THRESHOLD,
            "keyword_boost_weight": pcfg.KEYWORD_BOOST_WEIGHT,
        },
        "models": pcfg.MODELS,
    }
