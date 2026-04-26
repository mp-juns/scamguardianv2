"""
ScamGuardian v2 — 파이프라인 오케스트레이터
전체 분석 흐름을 조율하며 각 단계를 순차 실행한다.
"""

from __future__ import annotations

import concurrent.futures
import time
from dataclasses import dataclass, field
from typing import Any

from pipeline import classifier, extractor, llm_assessor, rag, scorer, stt, verifier
from pipeline.config import CLASSIFICATION_THRESHOLD
from pipeline.config import RAG_TOP_K, SCORING_RULES
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
        self._debug(
            "analyze() 시작: "
            f"skip_verification={skip_verification}, use_llm={use_llm}, use_rag={effective_use_rag}"
        )

        # ════════════════════════════════
        # Phase 1: STT
        # ════════════════════════════════
        print("[Phase 1] STT 처리 중...")
        print(f"      → 입력: {source[:80]}{'…' if len(source) > 80 else ''}")
        transcript = self.transcribe(source)
        text = transcript.text
        preview = text[:100] + "…" if len(text) > 100 else text
        print(f"      ← 결과: {transcript.source_type} | {len(text)}자")
        if transcript.source_type != "text":
            print(f"      ← 전사: {preview}")

        # ════════════════════════════════
        # Phase 2: 스캠 유형 분류 (mDeBERTa)
        # ════════════════════════════════
        print("[Phase 2] 스캠 유형 분류 중...")
        print(f"      → mDeBERTa NLI 모델에 {len(text)}자 전송")
        classification = self.classify(text)
        classifier_original = classification
        scam_type_source = "classifier"
        scam_type_reason = ""
        top3 = sorted(classification.all_scores.items(), key=lambda x: x[1], reverse=True)[:3]
        top3_str = ", ".join(f"{k}({v:.1%})" for k, v in top3)
        print(f"      ← 판정: {classification.scam_type} (신뢰도: {classification.confidence:.1%})")
        print(f"      ← Top3: {top3_str}")

        # ════════════════════════════════
        # Phase 3: 병렬 실행 (LLM통합 + 엔티티추출 + RAG)
        # ════════════════════════════════
        print("[Phase 3] 병렬 실행 중 (LLM + 추출 + RAG)...")
        llm_result: llm_assessor.LLMAssessment | None = None
        unified_result: llm_assessor.UnifiedLLMResult | None = None
        entities: list[extractor.Entity] = []
        similar_cases: list[dict[str, Any]] = []

        def _task_extract():
            return self.extract(text, classification.scam_type)

        def _task_llm_unified():
            return llm_assessor.analyze_unified(text, classification.scam_type)

        def _task_rag():
            return self.retrieve_similar_cases(text, classification.scam_type)

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            # 항상 엔티티 추출
            future_extract = executor.submit(_task_extract)

            # LLM 통합 호출 (use_llm일 때만)
            future_llm = executor.submit(_task_llm_unified) if use_llm else None

            # RAG (use_rag일 때만)
            future_rag = executor.submit(_task_rag) if effective_use_rag else None

            # 결과 수집
            entities = future_extract.result()
            print(f"      ← 엔티티 추출: {len(entities)}개")
            for e in entities:
                print(f"         [{e.label}] {e.text} ({e.score:.2f})")

            if future_llm is not None:
                try:
                    unified_result = future_llm.result()
                    llm_result = unified_result.assessment
                    suggestion = unified_result.scam_type_suggestion
                    print(
                        f"      ← LLM 통합: 엔티티 {len(llm_result.suggested_entities)}개, "
                        f"플래그 {len(llm_result.suggested_flags)}개"
                    )
                    # LLM 스캠 유형 재판정 적용
                    if suggestion is not None and suggestion.scam_type != classification.scam_type:
                        classification = classifier.ClassificationResult(
                            scam_type=suggestion.scam_type,
                            confidence=suggestion.confidence,
                            all_scores=classifier_original.all_scores,
                            is_uncertain=suggestion.confidence < CLASSIFICATION_THRESHOLD,
                        )
                        scam_type_source = "llm"
                        scam_type_reason = suggestion.reason
                        print(
                            f"      → [LLM 재판정] {classification.scam_type} "
                            f"(신뢰도: {classification.confidence:.1%})"
                        )
                except Exception as exc:
                    llm_result = llm_assessor.LLMAssessment(
                        model=llm_assessor.default_model_name(), error=str(exc),
                    )
                    self._debug(f"analyze_unified() 실패: {exc}")
                    print(f"      ← LLM 통합 실패: {exc}")

            if future_rag is not None:
                try:
                    similar_cases = future_rag.result()
                    print(f"      ← RAG: 참고 사례 {len(similar_cases)}개")
                except Exception as exc:
                    self._debug(f"retrieve_similar_cases() 실패: {exc}")
                    print(f"      ← RAG 실패: {exc}")

        # LLM 엔티티 병합
        merged_entities = llm_assessor.merge_suggested_entities(entities, llm_result)
        if len(merged_entities) != len(entities):
            print(f"      ← 엔티티 병합 후 총 {len(merged_entities)}개")

        # ════════════════════════════════
        # Phase 4: 교차 검증 (내부 병렬) + 스코어링
        # ════════════════════════════════
        if skip_verification:
            print("[Phase 4] 교차 검증 건너뜀 (skip_verification=True)")
            verification_results: list[verifier.VerificationResult] = []
        else:
            # 검증 대상 엔티티를 스코어 상위 15개로 제한 (라벨당 최대 2개)
            MAX_VERIFY_ENTITIES = 15
            seen_labels: dict[str, int] = {}
            verify_entities: list[extractor.Entity] = []
            for e in sorted(merged_entities, key=lambda x: -x.score):
                count = seen_labels.get(e.label, 0)
                if count >= 2:
                    continue
                seen_labels[e.label] = count + 1
                verify_entities.append(e)
                if len(verify_entities) >= MAX_VERIFY_ENTITIES:
                    break

            print("[Phase 4] 교차 검증 중 (Serper API, 병렬)...")
            print(
                f"      → 엔티티 {len(verify_entities)}개 (전체 {len(merged_entities)}개 중), "
                f"scam_type={classification.scam_type}"
            )
            verification_results = self.verify(
                verify_entities,
                classification.scam_type,
                transcript=text,
            )
            triggered = sum(1 for r in verification_results if r.triggered)
            print(f"      ← {len(verification_results)}건 검증, {triggered}건 플래그 발동")
            for r in verification_results:
                if r.triggered:
                    delta = SCORING_RULES.get(r.flag, 0)
                    reason = r.evidence_snippets[0][:60] if r.evidence_snippets else ""
                    print(f"         🚩 {r.flag} (+{delta}점) {reason}")

        # ════════════════════════════════
        # Phase 5: 스코어링
        # ════════════════════════════════
        print("[Phase 5] 스캠 스코어 산출 중...")
        print(
            f"      → 입력: 검증플래그 {len(verification_results)}개, "
            f"엔티티 {len(merged_entities)}개, 분류={classification.scam_type}"
        )
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
            scam_type_source=scam_type_source,
            scam_type_reason=scam_type_reason,
            classifier_original=classifier_original,
        )

        total_ms = (time.time() - pipeline_start) * 1000
        self._log_step("전체", pipeline_start)
        print(f"      ← 위험도: {report.total_score}/100, 판정: {report.risk_level}")
        print(f"\n{'='*50}")
        print(f"✅ 분석 완료! (소요시간: {total_ms:.0f}ms)")
        print(f"   유형: {report.scam_type} | 위험도: {report.total_score}/100 ({report.risk_level})")
        print(f"{'='*50}")

        self.last_report = report
        return report

    def print_step_log(self):
        """각 단계별 소요 시간을 출력한다."""
        print("\n[단계별 소요 시간]")
        for step in self.steps:
            print(f"  {step.name}: {step.duration_ms:.0f}ms")
