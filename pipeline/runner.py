"""
ScamGuardian v2 — 파이프라인 오케스트레이터
전체 분석 흐름을 조율하며 각 단계를 순차 실행한다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from pipeline import classifier, extractor, llm_assessor, rag, scorer, stt, verifier
from pipeline.config import RAG_TOP_K
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
        self.last_transcript_result: stt.TranscriptResult | None = None
        self.last_classification: classifier.ClassificationResult | None = None
        self.last_entities: list[extractor.Entity] = []
        self.last_verification_results: list[verifier.VerificationResult] = []
        self.last_llm_assessment: llm_assessor.LLMAssessment | None = None
        self.last_similar_cases: list[dict[str, Any]] = []
        self.last_report: ScamReport | None = None

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
        self.last_transcript_result = result
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
        self.last_classification = result
        return result

    def extract(self, text: str, scam_type: str) -> list[extractor.Entity]:
        t0 = time.time()
        self._debug(f"extract() 시작: scam_type={scam_type}")
        entities = extractor.extract(text, scam_type)
        self._log_step("추출", t0, {"entity_count": len(entities)})
        self._debug(f"extract() 완료: entity_count={len(entities)}")
        self.last_entities = entities
        return entities

    def verify(
        self,
        entities: list[extractor.Entity],
        scam_type: str,
        transcript: str,
    ) -> list[verifier.VerificationResult]:
        t0 = time.time()
        self._debug(
            f"verify() 시작: entities={len(entities)}, scam_type={scam_type}, transcript_len={len(transcript)}"
        )
        results = verifier.verify(entities, scam_type, transcript=transcript)
        triggered = sum(1 for r in results if r.triggered)
        self._log_step("검증", t0, {"total_checks": len(results), "triggered": triggered})
        self._debug(f"verify() 완료: total_checks={len(results)}, triggered={triggered}")
        self.last_verification_results = results
        return results

    def retrieve_similar_cases(
        self,
        text: str,
        scam_type: str,
    ) -> list[dict[str, Any]]:
        t0 = time.time()
        self._debug(f"retrieve_similar_cases() 시작: scam_type={scam_type}, text_length={len(text)}")
        query_embedding = rag.compute_transcript_embedding(text)
        results = rag.retrieve_similar_runs(query_embedding, RAG_TOP_K, scam_type=scam_type)
        self._log_step("RAG", t0, {"similar_cases": len(results)})
        self._debug(f"retrieve_similar_cases() 완료: similar_cases={len(results)}")
        self.last_similar_cases = results
        return results

    def assess_with_llm(
        self,
        text: str,
        scam_type: str,
        entities: list[extractor.Entity],
        verification_results: list[verifier.VerificationResult],
        similar_cases: list[dict[str, Any]] | None = None,
    ) -> llm_assessor.LLMAssessment:
        t0 = time.time()
        self._debug(
            f"assess_with_llm() 시작: scam_type={scam_type}, entities={len(entities)}, "
            f"triggered={sum(1 for r in verification_results if r.triggered)}, "
            f"similar_cases={len(similar_cases or [])}"
        )
        result = llm_assessor.assess(
            text,
            scam_type,
            entities,
            verification_results,
            similar_cases=similar_cases,
        )
        self._log_step(
            "LLM",
            t0,
            {
                "model": result.model,
                "suggested_entities": len(result.suggested_entities),
                "suggested_flags": len(result.suggested_flags),
                "error": result.error,
            },
        )
        self._debug(
            f"assess_with_llm() 완료: entities={len(result.suggested_entities)}, "
            f"flags={len(result.suggested_flags)}, error={result.error!r}"
        )
        self.last_llm_assessment = result
        return result

    # ──────────────────────────────────
    # 전체 파이프라인
    # ──────────────────────────────────

    def analyze(
        self,
        source: str,
        skip_verification: bool = False,
        use_llm: bool = False,
        use_rag: bool = False,
    ) -> ScamReport:
        """
        전체 분석 파이프라인을 실행한다.

        Args:
            source: YouTube URL, 로컬 파일 경로, 또는 텍스트
            skip_verification: True이면 Serper API 검증 단계를 건너뜀 (테스트용)
            use_llm: True이면 Ollama 기반 보조 판정을 추가 수행

        Returns:
            ScamReport 객체
        """
        self.steps = []
        self.last_transcript_result = None
        self.last_classification = None
        self.last_entities = []
        self.last_verification_results = []
        self.last_llm_assessment = None
        self.last_similar_cases = []
        self.last_report = None
        pipeline_start = time.time()
        effective_use_rag = use_llm and use_rag
        total_steps = 7 if effective_use_rag else (6 if use_llm else 5)
        self._debug(
            "analyze() 시작: "
            f"skip_verification={skip_verification}, use_llm={use_llm}, use_rag={effective_use_rag}"
        )

        # 1단계: STT
        print(f"[1/{total_steps}] STT 처리 중...")
        transcript = self.transcribe(source)
        text = transcript.text
        print(f"      → {transcript.source_type} | 텍스트 길이: {len(text)}자")

        # 2단계: 스캠 유형 분류
        print(f"[2/{total_steps}] 스캠 유형 분류 중...")
        classification = self.classify(text)
        print(f"      → {classification.scam_type} (신뢰도: {classification.confidence:.1%})")

        # 3단계: 엔티티 추출
        print(f"[3/{total_steps}] 엔티티 추출 중...")
        entities = self.extract(text, classification.scam_type)
        print(f"      → {len(entities)}개 엔티티 추출")
        for e in entities:
            print(f"         [{e.label}] {e.text} ({e.score:.2f})")

        # 4단계: 교차 검증
        if skip_verification:
            print(f"[4/{total_steps}] 교차 검증 건너뜀 (skip_verification=True)")
            verification_results: list[verifier.VerificationResult] = []
        else:
            print(f"[4/{total_steps}] 교차 검증 중 (Serper API)...")
            verification_results = self.verify(
                entities,
                classification.scam_type,
                transcript=text,
            )
            triggered = sum(1 for r in verification_results if r.triggered)
            print(f"      → {len(verification_results)}건 검증, {triggered}건 플래그 발동")

        llm_result: llm_assessor.LLMAssessment | None = None
        merged_entities = entities
        similar_cases: list[dict[str, Any]] = []
        llm_step_index = 5
        if effective_use_rag:
            print(f"[5/{total_steps}] 유사 사례 검색 중 (RAG)...")
            try:
                similar_cases = self.retrieve_similar_cases(text, classification.scam_type)
                print(f"      → 참고 사례 {len(similar_cases)}개")
            except Exception as exc:
                self._log_step("RAG", time.time(), {"error": str(exc)})
                self._debug(f"retrieve_similar_cases() 실패: {exc}")
                print(f"      → 유사 사례 검색 실패: {exc}")
            llm_step_index = 6

        if use_llm:
            print(f"[{llm_step_index}/{total_steps}] LLM 보조 판정 중 (Ollama)...")
            try:
                llm_result = self.assess_with_llm(
                    text,
                    classification.scam_type,
                    entities,
                    verification_results,
                    similar_cases=similar_cases,
                )
                print(
                    "      → "
                    f"추가 엔티티 {len(llm_result.suggested_entities)}개, "
                    f"추가 플래그 {len(llm_result.suggested_flags)}개"
                )
                merged_entities = llm_assessor.merge_suggested_entities(entities, llm_result)
                if len(merged_entities) != len(entities):
                    print(f"      → 엔티티 병합 후 총 {len(merged_entities)}개")
            except Exception as exc:
                llm_result = llm_assessor.LLMAssessment(
                    model=llm_assessor.default_model_name(),
                    error=str(exc),
                )
                self._log_step("LLM", time.time(), {"error": str(exc)})
                print(f"      → LLM 보조 판정 실패: {exc}")

        # 마지막 단계: 스코어링
        print(f"[{total_steps}/{total_steps}] 스캠 스코어 산출 중...")
        report = scorer.score(
            verification_results=verification_results,
            classification=classification,
            entities=merged_entities,
            source=source,
            transcript=text,
            llm_assessment=llm_result,
            rag_context={
                "enabled": effective_use_rag,
                "similar_cases": similar_cases,
            }
            if effective_use_rag
            else None,
        )

        total_ms = (time.time() - pipeline_start) * 1000
        self._log_step("전체", pipeline_start)
        print(f"\n완료! (소요시간: {total_ms:.0f}ms)")

        self.last_report = report
        return report

    def print_step_log(self):
        """각 단계별 소요 시간을 출력한다."""
        print("\n[단계별 소요 시간]")
        for step in self.steps:
            print(f"  {step.name}: {step.duration_ms:.0f}ms")
