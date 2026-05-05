"""Pydantic 모델 — 요청 페이로드 정의 모음."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class AnalyzeRequest(BaseModel):
    source: str | None = None
    text: str | None = None
    whisper_model: str = Field(
        default="medium",
        pattern="^(tiny|base|small|medium|large)$",
    )
    skip_verification: bool = True
    use_llm: bool = True
    use_rag: bool = False


class HumanAnnotationRequest(BaseModel):
    labeler: str | None = None
    scam_type_gt: str
    entities_gt: list[dict[str, Any]] = Field(default_factory=list)
    triggered_flags_gt: list[dict[str, Any]] = Field(default_factory=list)
    transcript_corrected_text: str | None = None
    stt_quality: int | None = Field(default=None, ge=1, le=5)
    notes: str = ""


class ScamTypeCatalogRequest(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=200)
    labels: list[str] = Field(default_factory=list)


class ClaimRunRequest(BaseModel):
    labeler: str


class AdminLoginRequest(BaseModel):
    token: str


class CreateApiKeyRequest(BaseModel):
    label: str
    monthly_quota: int = 1000
    rpm_limit: int = 30
    monthly_usd_quota: float = 5.0


class StartTrainingRequest(BaseModel):
    model: str
    epochs: int = 3
    batch_size: int = 8
    lora: bool = False
    extra_jsonl: str | None = None
    val_ratio: float = 0.1
    seed: int = 17
    base_model: str | None = None
