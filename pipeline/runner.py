"""
ScamGuardian v2 — 파이프라인 오케스트레이터
전체 분석 흐름을 조율하며 각 단계를 순차 실행한다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from pipeline import classifier, extractor, scorer, stt, verifier
from pipeline.config import LABEL_SETS
from pipeline.scorer import ScamReport


@dataclass
class StepLog:
    name: str
    duration_ms: float
    detail: Any = None


class ScamGuardianPipeline:
    """
    ScamGuardian v2 전체 파이프라인.

    사용법:
        pipe = ScamGuardianPipeline()
        report = pipe.analyze("https://youtube.com/watch?v=...")
        print(report.summary())
    """

    def __init__(self, whisper_model: str = "medium", debug: bool = False):
        self.whisper_model = whisper_model
        self.debug = debug
        self.steps: list[StepLog] = []

    def _debug(self, message: str):
        if self.debug:
            print(f"[DEBUG] {message}")

    def _log_step(self, name: str, start: float, detail: Any = None):
        elapsed = (time.time() - start) * 1000
        self.steps.append(StepLog(name=name, duration_ms=round(elapsed, 1), detail=detail))

    # ──────────────────────────────────
    # 개별 단계 (독립 호출 가능)
    # ──────────────────────────────────

    def transcribe(self, source: str) -> stt.TranscriptResult:
        t0 = time.time()
        self._debug(f"transcribe() 시작: model={self.whisper_model}, source={source[:80]}")
        result = stt.transcribe(
            source,
            model_size=self.whisper_model,
            debug=self.debug,
            logger=self._debug,
        )
        self._log_step("STT", t0, {"source_type": result.source_type, "text_length": len(result.text)})
        return result

    def classify(self, text: str) -> classifier.ClassificationResult:
        t0 = time.time()
        self._debug(f"classify() 시작: text_length={len(text)}")
        result = classifier.classify(text)
        self._log_step("분류", t0, {"scam_type": result.scam_type, "confidence": result.confidence})
        self._debug(
            f"classify() 완료: scam_type={result.scam_type}, confidence={result.confidence:.3f}, "
            f"scores={result.all_scores}"
        )
        return result

    def extract(self, text: str, scam_type: str) -> list[extractor.Entity]:
        t0 = time.time()
        self._debug(f"extract() 시작: scam_type={scam_type}")
        entities = extractor.extract(text, scam_type)
        self._log_step("추출", t0, {"entity_count": len(entities)})
        self._debug(f"extract() 완료: entity_count={len(entities)}")
        return entities

    def verify(self, entities: list[extractor.Entity], scam_type: str) -> list[verifier.VerificationResult]:
        t0 = time.time()
        self._debug(f"verify() 시작: entities={len(entities)}, scam_type={scam_type}")
        results = verifier.verify(entities, scam_type)
        triggered = sum(1 for r in results if r.triggered)
        self._log_step("검증", t0, {"total_checks": len(results), "triggered": triggered})
        self._debug(f"verify() 완료: total_checks={len(results)}, triggered={triggered}")
        return results

    # ──────────────────────────────────
    # 전체 파이프라인
    # ──────────────────────────────────

    def analyze(self, source: str, skip_verification: bool = False) -> ScamReport:
        """
        전체 분석 파이프라인을 실행한다.

        Args:
            source: YouTube URL, 로컬 파일 경로, 또는 텍스트
            skip_verification: True이면 Serper API 검증 단계를 건너뜀 (테스트용)

        Returns:
            ScamReport 객체
        """
        self.steps = []
        pipeline_start = time.time()
        self._debug(f"analyze() 시작: skip_verification={skip_verification}")

        # 1단계: STT
        print("[1/5] STT 처리 중...")
        transcript = self.transcribe(source)
        text = transcript.text
        print(f"      → {transcript.source_type} | 텍스트 길이: {len(text)}자")

        # 2단계: 스캠 유형 분류
        print("[2/5] 스캠 유형 분류 중...")
        classification = self.classify(text)
        print(f"      → {classification.scam_type} (신뢰도: {classification.confidence:.1%})")

        # 3단계: 엔티티 추출
        print("[3/5] 엔티티 추출 중...")
        entities = self.extract(text, classification.scam_type)
        print(f"      → {len(entities)}개 엔티티 추출")
        for e in entities:
            print(f"         [{e.label}] {e.text} ({e.score:.2f})")

        # 4단계: 교차 검증
        if skip_verification:
            print("[4/5] 교차 검증 건너뜀 (skip_verification=True)")
            verification_results: list[verifier.VerificationResult] = []
        else:
            print("[4/5] 교차 검증 중 (Serper API)...")
            verification_results = self.verify(entities, classification.scam_type)
            triggered = sum(1 for r in verification_results if r.triggered)
            print(f"      → {len(verification_results)}건 검증, {triggered}건 플래그 발동")

        # 5단계: 스코어링
        print("[5/5] 스캠 스코어 산출 중...")
        report = scorer.score(
            verification_results=verification_results,
            classification=classification,
            entities=entities,
            source=source,
            transcript=text,
        )

        total_ms = (time.time() - pipeline_start) * 1000
        self._log_step("전체", pipeline_start)
        print(f"\n완료! (소요시간: {total_ms:.0f}ms)")

        return report

    def print_step_log(self):
        """각 단계별 소요 시간을 출력한다."""
        print("\n[단계별 소요 시간]")
        for step in self.steps:
            print(f"  {step.name}: {step.duration_ms:.0f}ms")
