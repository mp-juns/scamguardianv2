"""
학습 데이터 로더 — `human_annotations` 테이블에서 정답 라벨을 받아
HuggingFace Dataset / GLiNER 입력 포맷으로 변환한다.

주 진입점:
    load_classifier_dataset() → 분류기(mDeBERTa) 학습용
    load_gliner_dataset()      → GLiNER 학습용 (entity span 자동 계산)
    train_val_split()          → seed 고정 split

DB 가 비어 있으면 AI Hub 등 외부 JSONL 도 함께 받을 수 있게 `extra_jsonl` 인자 지원.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from db import repository

DEFAULT_SEED = 17
NEGATIVE_LABEL = "정상 대화"


@dataclass
class ClassifierExample:
    text: str
    label: str
    run_id: str | None = None
    source: str = "annotation"


@dataclass
class GlinerExample:
    text: str
    ner: list[tuple[int, int, str]] = field(default_factory=list)  # (start, end, label)
    run_id: str | None = None


def _resolve_text(record: dict[str, Any]) -> str:
    return (
        record.get("transcript_corrected_text")
        or record.get("transcript_text")
        or ""
    ).strip()


def _spans_for_entity(text: str, target: str) -> list[tuple[int, int]]:
    """text 안에서 target 문자열의 모든 출현 위치(start, end) 반환."""
    if not target:
        return []
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        idx = text.find(target, start)
        if idx < 0:
            break
        spans.append((idx, idx + len(target)))
        start = idx + 1
    return spans


def _ner_from_annotation(text: str, entities: list[dict[str, Any]]) -> list[tuple[int, int, str]]:
    """엔티티 정답 리스트 → GLiNER (start, end, label) 형식.

    annotation 에 start/end 가 있으면 그대로, 없으면 text 검색으로 채운다.
    겹치는 span 은 첫 번째만 유지.
    """
    out: list[tuple[int, int, str]] = []
    used: list[tuple[int, int]] = []
    for ent in entities:
        ent_text = (ent.get("text") or "").strip()
        label = (ent.get("label") or "").strip()
        if not ent_text or not label:
            continue
        if isinstance(ent.get("start"), int) and isinstance(ent.get("end"), int):
            spans = [(ent["start"], ent["end"])]
        else:
            spans = _spans_for_entity(text, ent_text)
        for s, e in spans:
            if any(not (e <= us or s >= ue) for us, ue in used):
                continue
            out.append((s, e, label))
            used.append((s, e))
    out.sort(key=lambda x: (x[0], x[1]))
    return out


def _load_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def load_classifier_dataset(
    *,
    extra_jsonl: Path | None = None,
    include_negatives: bool = True,
) -> list[ClassifierExample]:
    """`scam_type_gt` 가 있는 라벨링 + (옵션) JSONL 추가 데이터.

    extra_jsonl 의 각 라인은 {"text": "...", "label": "...", "run_id"?: "..."} 형식.
    label 이 빈 문자열이거나 NEGATIVE_LABEL 이면 정상 대화로 간주한다.
    """
    rows = repository.fetch_annotated_pairs()
    examples: list[ClassifierExample] = []
    for row in rows:
        text = _resolve_text(row)
        if not text:
            continue
        label = (row.get("scam_type_gt") or "").strip()
        if not label:
            if not include_negatives:
                continue
            label = NEGATIVE_LABEL
        examples.append(
            ClassifierExample(text=text, label=label, run_id=row.get("run_id"))
        )

    if extra_jsonl:
        for record in _load_jsonl(Path(extra_jsonl)):
            text = (record.get("text") or "").strip()
            if not text:
                continue
            label = (record.get("label") or "").strip()
            if not label:
                if not include_negatives:
                    continue
                label = NEGATIVE_LABEL
            examples.append(
                ClassifierExample(
                    text=text,
                    label=label,
                    run_id=record.get("run_id"),
                    source=record.get("source", "extra_jsonl"),
                )
            )
    return examples


def load_gliner_dataset(*, extra_jsonl: Path | None = None) -> list[GlinerExample]:
    """엔티티 정답이 있는 라벨링 + (옵션) JSONL.

    extra_jsonl 의 각 라인은 {"text": "...", "ner": [[start, end, "label"], ...]} 또는
    {"text": "...", "entities": [{"text", "label", "start"?, "end"?}]} 둘 다 지원.
    """
    rows = repository.fetch_annotated_pairs()
    examples: list[GlinerExample] = []
    for row in rows:
        text = _resolve_text(row)
        ner = _ner_from_annotation(text, row.get("entities_gt") or [])
        if not text or not ner:
            continue
        examples.append(GlinerExample(text=text, ner=ner, run_id=row.get("run_id")))

    if extra_jsonl:
        for record in _load_jsonl(Path(extra_jsonl)):
            text = (record.get("text") or "").strip()
            if not text:
                continue
            ner = record.get("ner")
            if isinstance(ner, list) and all(len(t) == 3 for t in ner):
                spans = [(int(s), int(e), str(l)) for s, e, l in ner]
            else:
                spans = _ner_from_annotation(text, record.get("entities") or [])
            if not spans:
                continue
            examples.append(GlinerExample(text=text, ner=spans, run_id=record.get("run_id")))
    return examples


def train_val_split(
    examples: list,
    val_ratio: float = 0.1,
    seed: int = DEFAULT_SEED,
) -> tuple[list, list]:
    rng = random.Random(seed)
    indices = list(range(len(examples)))
    rng.shuffle(indices)
    n_val = max(1, int(len(examples) * val_ratio))
    val_idx = set(indices[:n_val])
    train: list = []
    val: list = []
    for i, ex in enumerate(examples):
        (val if i in val_idx else train).append(ex)
    return train, val


def stratified_split(
    examples: list[ClassifierExample],
    val_ratio: float = 0.1,
    seed: int = DEFAULT_SEED,
) -> tuple[list[ClassifierExample], list[ClassifierExample]]:
    """라벨별 균형 split — 적은 클래스가 val 에 누락되지 않게."""
    rng = random.Random(seed)
    by_label: dict[str, list[ClassifierExample]] = {}
    for ex in examples:
        by_label.setdefault(ex.label, []).append(ex)
    train: list[ClassifierExample] = []
    val: list[ClassifierExample] = []
    for label, items in by_label.items():
        rng.shuffle(items)
        n_val = max(1, int(len(items) * val_ratio)) if len(items) > 1 else 0
        val.extend(items[:n_val])
        train.extend(items[n_val:])
    rng.shuffle(train)
    rng.shuffle(val)
    return train, val


def label_distribution(examples: list[ClassifierExample]) -> dict[str, int]:
    out: dict[str, int] = {}
    for ex in examples:
        out[ex.label] = out.get(ex.label, 0) + 1
    return dict(sorted(out.items(), key=lambda x: -x[1]))


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="라벨링 데이터 통계 점검")
    parser.add_argument("--extra-jsonl", default=None)
    args = parser.parse_args()

    cls = load_classifier_dataset(extra_jsonl=args.extra_jsonl)
    gli = load_gliner_dataset(extra_jsonl=args.extra_jsonl)

    print(f"classifier examples: {len(cls)}")
    for label, n in label_distribution(cls).items():
        print(f"  {n:>4} | {label}")
    print()
    print(f"gliner examples: {len(gli)}")
    if gli:
        avg_ner = sum(len(e.ner) for e in gli) / len(gli)
        avg_len = sum(len(e.text) for e in gli) / len(gli)
        print(f"  평균 엔티티/문서: {avg_ner:.1f}")
        print(f"  평균 문서 길이(자): {avg_len:.0f}")
