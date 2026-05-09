"""
SQLite-backed history for benchmark runs.

The history layer is intentionally small and dependency-free. Writes are best
effort from the test runner so a database problem never breaks live tests.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from backend.core.logging import get_logger
from backend.models.schemas import ProtocolTestResult

logger = get_logger(__name__)

_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "test_history.sqlite3"


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db_sync() -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS test_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL,
                recorded_at REAL NOT NULL,
                duration_sec REAL,
                client_vm TEXT NOT NULL,
                protocol TEXT NOT NULL,
                condition TEXT NOT NULL,
                status TEXT NOT NULL,
                phase TEXT,
                avg_latency_ms REAL NOT NULL DEFAULT 0,
                max_latency_ms REAL NOT NULL DEFAULT 0,
                avg_throughput_mbps REAL NOT NULL DEFAULT 0,
                upload_mbps REAL NOT NULL DEFAULT 0,
                download_mbps REAL NOT NULL DEFAULT 0,
                avg_cpu_percent REAL NOT NULL DEFAULT 0,
                score REAL NOT NULL DEFAULT 0,
                dpi_resistance_score REAL NOT NULL DEFAULT 0,
                recommended INTEGER NOT NULL DEFAULT 0,
                error_message TEXT,
                latency_samples_json TEXT NOT NULL DEFAULT '[]',
                throughput_samples_json TEXT NOT NULL DEFAULT '[]',
                cpu_samples_json TEXT NOT NULL DEFAULT '[]'
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_test_history_recorded_at
            ON test_history(recorded_at DESC)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_test_history_run_id
            ON test_history(run_id)
            """
        )


async def init_history_db() -> None:
    await asyncio.to_thread(_init_db_sync)


def _sample_payload(samples: list[Any]) -> str:
    return json.dumps([sample.model_dump() for sample in samples], separators=(",", ":"))


def _insert_record_sync(record: dict[str, Any]) -> None:
    _init_db_sync()
    fields = list(record.keys())
    placeholders = ", ".join("?" for _ in fields)
    columns = ", ".join(fields)
    values = [record[field] for field in fields]
    with _connect() as conn:
        conn.execute(
            f"INSERT INTO test_history ({columns}) VALUES ({placeholders})",
            values,
        )


async def save_success(
    *,
    run_id: str,
    client_vm: str,
    result: ProtocolTestResult,
    started_at: float,
) -> None:
    throughput = result.throughput_samples[-1] if result.throughput_samples else None
    record = {
        "run_id": run_id,
        "recorded_at": time.time(),
        "duration_sec": max(0.0, time.time() - started_at),
        "client_vm": client_vm,
        "protocol": result.protocol,
        "condition": result.condition,
        "status": "success",
        "phase": "complete",
        "avg_latency_ms": result.avg_latency_ms,
        "max_latency_ms": result.max_latency_ms,
        "avg_throughput_mbps": result.avg_throughput_mbps,
        "upload_mbps": throughput.upload_mbps if throughput else 0.0,
        "download_mbps": throughput.download_mbps if throughput else 0.0,
        "avg_cpu_percent": result.avg_cpu_percent,
        "score": result.score,
        "dpi_resistance_score": result.dpi_resistance_score,
        "recommended": 1 if result.recommended else 0,
        "error_message": None,
        "latency_samples_json": _sample_payload(result.latency_samples),
        "throughput_samples_json": _sample_payload(result.throughput_samples),
        "cpu_samples_json": _sample_payload(result.cpu_samples),
    }
    await asyncio.to_thread(_insert_record_sync, record)


async def save_failure(
    *,
    run_id: str,
    client_vm: str,
    protocol: str,
    condition: str,
    status: str,
    phase: str,
    error_message: str,
    started_at: float,
) -> None:
    record = {
        "run_id": run_id,
        "recorded_at": time.time(),
        "duration_sec": max(0.0, time.time() - started_at),
        "client_vm": client_vm,
        "protocol": protocol,
        "condition": condition,
        "status": status,
        "phase": phase,
        "avg_latency_ms": 0.0,
        "max_latency_ms": 0.0,
        "avg_throughput_mbps": 0.0,
        "upload_mbps": 0.0,
        "download_mbps": 0.0,
        "avg_cpu_percent": 0.0,
        "score": 0.0,
        "dpi_resistance_score": 0.0,
        "recommended": 0,
        "error_message": error_message[:4000],
        "latency_samples_json": "[]",
        "throughput_samples_json": "[]",
        "cpu_samples_json": "[]",
    }
    await asyncio.to_thread(_insert_record_sync, record)


def _list_history_sync(limit: int) -> list[dict[str, Any]]:
    _init_db_sync()
    safe_limit = max(1, min(limit, 500))
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, run_id, recorded_at, duration_sec, client_vm, protocol,
                   condition, status, phase, avg_latency_ms, max_latency_ms,
                   avg_throughput_mbps, upload_mbps, download_mbps,
                   avg_cpu_percent, score, dpi_resistance_score, recommended,
                   error_message
            FROM test_history
            ORDER BY recorded_at DESC, id DESC
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()
    return [dict(row) for row in rows]


async def list_history(limit: int = 100) -> list[dict[str, Any]]:
    return await asyncio.to_thread(_list_history_sync, limit)


async def safe_save_success(**kwargs: Any) -> None:
    try:
        await save_success(**kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("history_save_success_failed", exc=str(exc))


async def safe_save_failure(**kwargs: Any) -> None:
    try:
        await save_failure(**kwargs)
    except Exception as exc:  # noqa: BLE001
        logger.warning("history_save_failure_failed", exc=str(exc))
