from __future__ import annotations

import json
import math
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_VECTOR_DIMENSION = 384
_ROOT_DIR = Path(__file__).resolve().parents[1]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_sqlite_path(required: bool = False) -> str:
    raw = os.getenv("SCAMGUARDIAN_SQLITE_PATH", "").strip()
    if required and not raw:
        raise EnvironmentError("SCAMGUARDIAN_SQLITE_PATH가 설정되지 않았습니다.")
    return raw


def database_configured() -> bool:
    return bool(get_sqlite_path(required=False))


def _resolved_db_path() -> Path:
    raw = get_sqlite_path(required=True)
    path = Path(raw)
    if not path.is_absolute():
        path = _ROOT_DIR / path
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_resolved_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    if not database_configured():
        return

    statements = [
        """
        CREATE TABLE IF NOT EXISTS analysis_runs (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            input_source TEXT NOT NULL,
            whisper_model TEXT NOT NULL,
            skip_verification INTEGER NOT NULL,
            use_llm INTEGER NOT NULL,
            use_rag INTEGER NOT NULL DEFAULT 0,
            transcript_text TEXT NOT NULL,
            transcript_corrected_text TEXT,
            classification_scanner TEXT NOT NULL,
            entities_predicted TEXT NOT NULL,
            verification_results TEXT NOT NULL,
            triggered_flags_predicted TEXT NOT NULL,
            total_score_predicted INTEGER NOT NULL,
            risk_level_predicted TEXT NOT NULL,
            llm_assessment TEXT,
            metadata TEXT NOT NULL DEFAULT '{}'
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS human_annotations (
            run_id TEXT PRIMARY KEY REFERENCES analysis_runs(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            labeler TEXT,
            scam_type_gt TEXT NOT NULL,
            entities_gt TEXT NOT NULL,
            triggered_flags_gt TEXT NOT NULL,
            transcript_corrected_text TEXT,
            stt_quality INTEGER,
            notes TEXT NOT NULL DEFAULT ''
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS transcript_embeddings (
            run_id TEXT PRIMARY KEY REFERENCES analysis_runs(id) ON DELETE CASCADE,
            created_at TEXT NOT NULL,
            model_name TEXT NOT NULL,
            embedding TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS scam_type_catalog (
            name TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            labels TEXT NOT NULL DEFAULT '[]'
        )
        """,
        "CREATE INDEX IF NOT EXISTS idx_analysis_runs_created_at ON analysis_runs(created_at DESC)",
    ]

    with _connect() as conn:
        for statement in statements:
            conn.execute(statement)
        # 마이그레이션: claim 컬럼 추가 (이미 있으면 무시)
        for col, col_type in [("claimed_by", "TEXT"), ("claimed_at", "TEXT")]:
            try:
                conn.execute(f"ALTER TABLE analysis_runs ADD COLUMN {col} {col_type}")
            except sqlite3.OperationalError:
                pass
        conn.commit()


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _load_json(value: str | None, default: Any) -> Any:
    if value is None or value == "":
        return default
    return json.loads(value)


def list_custom_scam_types() -> list[dict[str, Any]]:
    init_db()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT name, created_at, updated_at, description, labels
            FROM scam_type_catalog
            ORDER BY created_at ASC, name ASC
            """
        ).fetchall()

    return [
        {
            "name": row["name"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "description": row["description"] or "",
            "labels": _load_json(row["labels"], []),
        }
        for row in rows
    ]


def upsert_custom_scam_type(
    *,
    name: str,
    description: str = "",
    labels: list[str] | None = None,
) -> dict[str, Any]:
    init_db()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT created_at FROM scam_type_catalog WHERE name = ?",
            (name,),
        ).fetchone()
        created_at = existing["created_at"] if existing is not None else _now_iso()
        updated_at = _now_iso()
        normalized_labels = [str(label).strip() for label in (labels or []) if str(label).strip()]
        conn.execute(
            """
            INSERT INTO scam_type_catalog (
                name,
                created_at,
                updated_at,
                description,
                labels
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
                updated_at = excluded.updated_at,
                description = excluded.description,
                labels = excluded.labels
            """,
            (
                name,
                created_at,
                updated_at,
                description.strip(),
                _dump_json(normalized_labels),
            ),
        )
        conn.commit()

    return {
        "name": name,
        "created_at": created_at,
        "updated_at": updated_at,
        "description": description.strip(),
        "labels": normalized_labels,
    }


def save_analysis_run(
    *,
    input_source: str,
    whisper_model: str,
    skip_verification: bool,
    use_llm: bool,
    use_rag: bool,
    transcript_text: str,
    classification_scanner: dict[str, Any],
    entities_predicted: list[dict[str, Any]],
    verification_results: list[dict[str, Any]],
    triggered_flags_predicted: list[dict[str, Any]],
    total_score_predicted: int,
    risk_level_predicted: str,
    llm_assessment: dict[str, Any] | None,
    metadata: dict[str, Any] | None = None,
) -> str:
    init_db()
    run_id = str(uuid.uuid4())
    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO analysis_runs (
                id,
                created_at,
                input_source,
                whisper_model,
                skip_verification,
                use_llm,
                use_rag,
                transcript_text,
                classification_scanner,
                entities_predicted,
                verification_results,
                triggered_flags_predicted,
                total_score_predicted,
                risk_level_predicted,
                llm_assessment,
                metadata
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                run_id,
                now,
                input_source,
                whisper_model,
                int(skip_verification),
                int(use_llm),
                int(use_rag),
                transcript_text,
                _dump_json(classification_scanner),
                _dump_json(entities_predicted),
                _dump_json(verification_results),
                _dump_json(triggered_flags_predicted),
                total_score_predicted,
                risk_level_predicted,
                _dump_json(llm_assessment) if llm_assessment is not None else None,
                _dump_json(metadata or {}),
            ),
        )
        conn.commit()
    return run_id


def save_transcript_embedding(run_id: str, embedding: list[float], model_name: str) -> None:
    if len(embedding) != _VECTOR_DIMENSION:
        raise ValueError(
            f"임베딩 차원이 {_VECTOR_DIMENSION}이 아닙니다. 실제 차원: {len(embedding)}"
        )
    init_db()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO transcript_embeddings (run_id, created_at, model_name, embedding)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                model_name = excluded.model_name,
                embedding = excluded.embedding
            """,
            (run_id, _now_iso(), model_name, _dump_json(embedding)),
        )
        conn.commit()


_CLAIM_TTL_SECONDS = 30 * 60  # 30분


def _run_status(row: sqlite3.Row, now_iso: str) -> str:
    """row에서 라벨링 상태를 계산한다."""
    if row["annotated"]:
        return "완료"
    claimed_at = row["claimed_at"]
    if claimed_at and claimed_at > _expire_iso(now_iso):
        return "진행중"
    return "미완료"


def _expire_iso(now_iso: str) -> str:
    from datetime import timedelta
    now = datetime.fromisoformat(now_iso)
    return (now - timedelta(seconds=_CLAIM_TTL_SECONDS)).isoformat()


def list_runs_for_labeling(
    limit: int = 50,
    offset: int = 0,
    status_filter: str | None = None,
) -> list[dict[str, Any]]:
    """
    라벨링 큐용 run 목록을 반환한다.

    status_filter: '미완료' | '진행중' | '완료' | None(전체)
    """
    init_db()
    now = _now_iso()
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT
                ar.id,
                ar.created_at,
                ar.classification_scanner,
                ar.total_score_predicted,
                ar.risk_level_predicted,
                ar.transcript_text,
                ar.claimed_by,
                ar.claimed_at,
                ha.labeler,
                (ha.run_id IS NOT NULL) AS annotated
            FROM analysis_runs ar
            LEFT JOIN human_annotations ha ON ha.run_id = ar.id
            ORDER BY ar.created_at ASC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()

    result = []
    for row in rows:
        status = _run_status(row, now)
        if status_filter and status != status_filter:
            continue
        transcript = row["transcript_text"] or ""
        classification = _load_json(row["classification_scanner"], {})
        result.append({
            "id": row["id"],
            "created_at": row["created_at"],
            "transcript_preview": transcript[:120] + ("..." if len(transcript) > 120 else ""),
            "predicted_scam_type": classification.get("scam_type", ""),
            "predicted_confidence": classification.get("confidence", 0.0),
            "total_score_predicted": row["total_score_predicted"],
            "risk_level_predicted": row["risk_level_predicted"],
            "status": status,
            "claimed_by": row["claimed_by"] if status == "진행중" else None,
            "labeler": row["labeler"],
        })
    return result


def claim_run(run_id: str, labeler: str) -> bool:
    """
    run을 특정 라벨러가 클레임한다.
    이미 다른 사람이 클레임 중이면 False 반환.
    """
    init_db()
    now = _now_iso()
    expire_threshold = _expire_iso(now)
    with _connect() as conn:
        # 이미 완료된 run은 클레임 불가
        annotated = conn.execute(
            "SELECT 1 FROM human_annotations WHERE run_id = ?", (run_id,)
        ).fetchone()
        if annotated:
            return False

        # 본인이거나 만료된 클레임이면 덮어쓰기 가능
        result = conn.execute(
            """
            UPDATE analysis_runs
            SET claimed_by = ?, claimed_at = ?
            WHERE id = ?
              AND (claimed_by IS NULL OR claimed_by = ? OR claimed_at <= ?)
            """,
            (labeler, now, run_id, labeler, expire_threshold),
        )
        conn.commit()
        return result.rowcount > 0


def get_next_unannotated_run() -> dict[str, Any] | None:
    init_db()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                ar.id,
                ar.created_at,
                ar.classification_scanner,
                ar.total_score_predicted,
                ar.risk_level_predicted,
                ar.transcript_text
            FROM analysis_runs ar
            LEFT JOIN human_annotations ha ON ha.run_id = ar.id
            WHERE ha.run_id IS NULL
            ORDER BY ar.created_at ASC
            LIMIT 1
            """
        ).fetchone()

    if row is None:
        return None

    transcript = row["transcript_text"] or ""
    classification = _load_json(row["classification_scanner"], {})
    return {
        "id": row["id"],
        "created_at": row["created_at"],
        "transcript_preview": transcript[:200] + ("..." if len(transcript) > 200 else ""),
        "predicted_scam_type": classification.get("scam_type", ""),
        "predicted_confidence": classification.get("confidence", 0.0),
        "total_score_predicted": row["total_score_predicted"],
        "risk_level_predicted": row["risk_level_predicted"],
    }


def get_run_detail(run_id: str) -> dict[str, Any] | None:
    init_db()
    with _connect() as conn:
        run_row = conn.execute(
            "SELECT * FROM analysis_runs WHERE id = ?",
            (run_id,),
        ).fetchone()
        if run_row is None:
            return None
        annotation_row = conn.execute(
            "SELECT * FROM human_annotations WHERE run_id = ?",
            (run_id,),
        ).fetchone()

    run = {
        "id": run_row["id"],
        "created_at": run_row["created_at"],
        "input_source": run_row["input_source"],
        "whisper_model": run_row["whisper_model"],
        "skip_verification": bool(run_row["skip_verification"]),
        "use_llm": bool(run_row["use_llm"]),
        "use_rag": bool(run_row["use_rag"]),
        "transcript_text": run_row["transcript_text"],
        "transcript_corrected_text": run_row["transcript_corrected_text"],
        "classification_scanner": _load_json(run_row["classification_scanner"], {}),
        "entities_predicted": _load_json(run_row["entities_predicted"], []),
        "verification_results": _load_json(run_row["verification_results"], []),
        "triggered_flags_predicted": _load_json(run_row["triggered_flags_predicted"], []),
        "total_score_predicted": run_row["total_score_predicted"],
        "risk_level_predicted": run_row["risk_level_predicted"],
        "llm_assessment": _load_json(run_row["llm_assessment"], None),
        "metadata": _load_json(run_row["metadata"], {}),
    }

    annotation = None
    if annotation_row is not None:
        annotation = {
            "run_id": annotation_row["run_id"],
            "created_at": annotation_row["created_at"],
            "updated_at": annotation_row["updated_at"],
            "labeler": annotation_row["labeler"],
            "scam_type_gt": annotation_row["scam_type_gt"],
            "entities_gt": _load_json(annotation_row["entities_gt"], []),
            "triggered_flags_gt": _load_json(annotation_row["triggered_flags_gt"], []),
            "transcript_corrected_text": annotation_row["transcript_corrected_text"],
            "stt_quality": annotation_row["stt_quality"],
            "notes": annotation_row["notes"] or "",
        }

    return {"run": run, "annotation": annotation}


def upsert_human_annotation(
    *,
    run_id: str,
    scam_type_gt: str,
    entities_gt: list[dict[str, Any]],
    triggered_flags_gt: list[dict[str, Any]],
    labeler: str | None = None,
    transcript_corrected_text: str | None = None,
    stt_quality: int | None = None,
    notes: str = "",
) -> dict[str, Any]:
    init_db()
    with _connect() as conn:
        existing = conn.execute(
            "SELECT created_at FROM human_annotations WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        created_at = existing["created_at"] if existing is not None else _now_iso()
        updated_at = _now_iso()
        conn.execute(
            """
            INSERT INTO human_annotations (
                run_id,
                created_at,
                updated_at,
                labeler,
                scam_type_gt,
                entities_gt,
                triggered_flags_gt,
                transcript_corrected_text,
                stt_quality,
                notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
                updated_at = excluded.updated_at,
                labeler = excluded.labeler,
                scam_type_gt = excluded.scam_type_gt,
                entities_gt = excluded.entities_gt,
                triggered_flags_gt = excluded.triggered_flags_gt,
                transcript_corrected_text = excluded.transcript_corrected_text,
                stt_quality = excluded.stt_quality,
                notes = excluded.notes
            """,
            (
                run_id,
                created_at,
                updated_at,
                labeler,
                scam_type_gt,
                _dump_json(entities_gt),
                _dump_json(triggered_flags_gt),
                transcript_corrected_text,
                stt_quality,
                notes,
            ),
        )
        conn.commit()

    return {
        "run_id": run_id,
        "created_at": created_at,
        "updated_at": updated_at,
        "labeler": labeler,
        "scam_type_gt": scam_type_gt,
        "entities_gt": entities_gt,
        "triggered_flags_gt": triggered_flags_gt,
        "transcript_corrected_text": transcript_corrected_text,
        "stt_quality": stt_quality,
        "notes": notes,
    }


def fetch_annotated_pairs(scam_type: str | None = None) -> list[dict[str, Any]]:
    init_db()
    query = """
        SELECT
            ar.id,
            ar.created_at,
            ar.transcript_text,
            ar.classification_scanner,
            ar.entities_predicted,
            ar.triggered_flags_predicted,
            ha.scam_type_gt,
            ha.entities_gt,
            ha.triggered_flags_gt,
            ha.labeler,
            ha.transcript_corrected_text,
            ha.stt_quality
        FROM analysis_runs ar
        INNER JOIN human_annotations ha ON ha.run_id = ar.id
        WHERE (? IS NULL OR ha.scam_type_gt = ?)
        ORDER BY ar.created_at DESC
    """
    with _connect() as conn:
        rows = conn.execute(query, (scam_type, scam_type)).fetchall()

    return [
        {
            "run_id": row["id"],
            "created_at": row["created_at"],
            "transcript_text": row["transcript_text"],
            "classification_scanner": _load_json(row["classification_scanner"], {}),
            "entities_predicted": _load_json(row["entities_predicted"], []),
            "triggered_flags_predicted": _load_json(row["triggered_flags_predicted"], []),
            "scam_type_gt": row["scam_type_gt"],
            "entities_gt": _load_json(row["entities_gt"], []),
            "triggered_flags_gt": _load_json(row["triggered_flags_gt"], []),
            "labeler": row["labeler"],
            "transcript_corrected_text": row["transcript_corrected_text"],
            "stt_quality": row["stt_quality"],
        }
        for row in rows
    ]


def _l2_distance(left: list[float], right: list[float]) -> float:
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(left, right)))


def search_similar_annotated_runs(
    query_embedding: list[float],
    *,
    limit: int = 3,
    scam_type: str | None = None,
) -> list[dict[str, Any]]:
    if not database_configured():
        return []

    init_db()
    query = """
        SELECT
            ar.id,
            ar.created_at,
            ar.transcript_text,
            ar.classification_scanner,
            ha.scam_type_gt,
            ha.entities_gt,
            ha.triggered_flags_gt,
            ha.transcript_corrected_text,
            te.model_name,
            te.embedding
        FROM transcript_embeddings te
        INNER JOIN analysis_runs ar ON ar.id = te.run_id
        INNER JOIN human_annotations ha ON ha.run_id = ar.id
        WHERE (? IS NULL OR ha.scam_type_gt = ?)
    """
    with _connect() as conn:
        rows = conn.execute(query, (scam_type, scam_type)).fetchall()

    results: list[dict[str, Any]] = []
    for row in rows:
        embedding = _load_json(row["embedding"], [])
        if len(embedding) != len(query_embedding):
            continue
        transcript = row["transcript_corrected_text"] or row["transcript_text"] or ""
        classification = _load_json(row["classification_scanner"], {})
        results.append(
            {
                "run_id": row["id"],
                "created_at": row["created_at"],
                "distance": _l2_distance(query_embedding, embedding),
                "model_name": row["model_name"],
                "predicted_scam_type": classification.get("scam_type", ""),
                "scam_type_gt": row["scam_type_gt"],
                "transcript_excerpt": transcript[:240] + ("..." if len(transcript) > 240 else ""),
                "entities_gt": _load_json(row["entities_gt"], []),
                "triggered_flags_gt": _load_json(row["triggered_flags_gt"], []),
            }
        )

    results.sort(key=lambda item: item["distance"])
    return results[:limit]

