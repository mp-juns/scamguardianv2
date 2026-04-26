"""
ScamGuardian v2 — 파이프라인 오케스트레이터
전체 분석 흐름을 조율하며 각 단계를 순차 실행한다.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from pipeline import classifier, extractor, llm_assessor, rag, scorer, stt, verifier
from pipeline.config import CLASSIFICATION_THRESHOLD
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
        print(f"      → 입력: {source[:80]}{'…' if len(source) > 80 else ''}")
        transcript = self.transcribe(source)
        text = transcript.text
        preview = text[:100] + "…" if len(text) > 100 else text
        print(f"      ← 결과: {transcript.source_type} | {len(text)}자")
        if transcript.source_type != "text":
            print(f"      ← 전사: {preview}")

        # 2단계: 스캠 유형 분류
        print(f"[2/{total_steps}] 스캠 유형 분류 중...")
        print(f"      → mDeBERTa NLI 모델에 {len(text)}자 전송")
        classification = self.classify(text)
        classifier_original = classification
        scam_type_source = "classifier"
        scam_type_reason = ""
        top3 = sorted(classification.all_scores.items(), key=lambda x: x[1], reverse=True)[:3]
        top3_str = ", ".join(f"{k}({v:.1%})" for k, v in top3)
        print(f"      ← 판정: {classification.scam_type} (신뢰도: {classification.confidence:.1%})")
        print(f"      ← Top3: {top3_str}")

        # (옵션) LLM이 문맥으로 스캠 유형을 재판정하여 이후 추출/검증을 그 유형으로 수행
        if use_llm:
            try:
                suggestion = llm_assessor.suggest_scam_type(text)
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
                        f"      → [LLM 재판정] {classification.scam_type} (신뢰도: {classification.confidence:.1%})"
                    )
            except Exception as exc:
                # 실패하면 기존 분류기로 계속 진행
                self._log_step("LLM-유형재판정", time.time(), {"error": str(exc)})
                self._debug(f"suggest_scam_type() 실패: {exc}")

        # 3단계: 엔티티 추출
        print(f"[3/{total_steps}] 엔티티 추출 중...")
        print(f"      → GLiNER에 전송: scam_type={classification.scam_type}")
        entities = self.extract(text, classification.scam_type)
        print(f"      ← {len(entities)}개 엔티티 추출")
        for e in entities:
            print(f"         [{e.label}] {e.text} ({e.score:.2f})")

        # 4단계: 교차 검증
        if skip_verification:
            print(f"[4/{total_steps}] 교차 검증 건너뜀 (skip_verification=True)")
            verification_results: list[verifier.VerificationResult] = []
        else:
            print(f"[4/{total_steps}] 교차 검증 중 (Serper API)...")
            print(f"      → Serper에 전송: 엔티티 {len(entities)}개, scam_type={classification.scam_type}")
            verification_results = self.verify(
                entities,
                classification.scam_type,
                transcript=text,
            )
            triggered = sum(1 for r in verification_results if r.triggered)
            print(f"      ← {len(verification_results)}건 검증, {triggered}건 플래그 발동")
            for r in verification_results:
                if r.triggered:
                    print(f"         🚩 {r.flag} (+{r.score_delta}점) {r.evidence.get('reason', '')[:60]}")

        llm_result: llm_assessor.LLMAssessment | None = None
        merged_entities = entities
        similar_cases: list[dict[str, Any]] = []
        llm_step_index = 5
        if effective_use_rag:
            print(f"[5/{total_steps}] 유사 사례 검색 중 (RAG)...")
            print(f"      → 벡터 DB 쿼리: top_k={RAG_TOP_K}, scam_type={classification.scam_type}")
            try:
                similar_cases = self.retrieve_similar_cases(text, classification.scam_type)
                print(f"      ← 참고 사례 {len(similar_cases)}개")
                for sc in similar_cases[:3]:
                    sim_src = sc.get("source", "?")[:40]
                    sim_score = sc.get("similarity", 0)
                    print(f"         ↳ {sim_src} (유사도: {sim_score:.2f})")
            except Exception as exc:
                self._log_step("RAG", time.time(), {"error": str(exc)})
                self._debug(f"retrieve_similar_cases() 실패: {exc}")
                print(f"      ← 유사 사례 검색 실패: {exc}")
            llm_step_index = 6

        if use_llm:
            model_name = llm_assessor.default_model_name()
            print(f"[{llm_step_index}/{total_steps}] LLM 보조 판정 중 ({model_name})...")
            print(
                f"      → LLM에 전송: text {len(text)}자, "
                f"entities {len(entities)}개, flags {len(verification_results)}개"
            )
            try:
                llm_result = self.assess_with_llm(
                    text,
                    classification.scam_type,
                    entities,
                    verification_results,
                    similar_cases=similar_cases,
                )
                print(
                    f"      ← 추가 엔티티 {len(llm_result.suggested_entities)}개, "
                    f"추가 플래그 {len(llm_result.suggested_flags)}개"
                )
                if llm_result.suggested_entities:
                    for se in llm_result.suggested_entities[:5]:
                        print(f"         ↳ 엔티티: [{se.label}] {se.text}")
                if llm_result.suggested_flags:
                    for sf in llm_result.suggested_flags[:5]:
                        print(f"         ↳ 플래그: {sf.flag}")
                merged_entities = llm_assessor.merge_suggested_entities(entities, llm_result)
                if len(merged_entities) != len(entities):
                    print(f"      ← 엔티티 병합 후 총 {len(merged_entities)}개")
            except Exception as exc:
                llm_result = llm_assessor.LLMAssessment(
                    model=llm_assessor.default_model_name(),
                    error=str(exc),
                )
                self._log_step("LLM", time.time(), {"error": str(exc)})
                print(f"      ← LLM 보조 판정 실패: {exc}")

        # 마지막 단계: 스코어링
        print(f"[{total_steps}/{total_steps}] 스캠 스코어 산출 중...")
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
